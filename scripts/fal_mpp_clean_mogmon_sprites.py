#!/usr/bin/env python3
"""Remove baked backgrounds from installed Mogger Mon battle atlases via Fal MPP."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import subprocess
import time
from io import BytesIO
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

from PIL import Image

from mogmon_normalizer import normalize_battle_sprite_best_effort


ROOT = Path(__file__).resolve().parent.parent
POKEMON_DIR = ROOT / "assets" / "images" / "pokemon"
BACKUP_DIR = POKEMON_DIR / "_backup"
FAL_MPP_HELPER = Path(__file__).with_name("fal_mpp_generate.mjs")
FAL_DIRECT_HELPER = Path(__file__).with_name("fal_direct_generate.mjs")
DEFAULT_BG_REMOVE_MODEL = "fal-ai/bria/background/remove"
DEFAULT_MAX_SPEND = "0.03"


def fail(message: str) -> None:
    raise SystemExit(message)


def parse_csv_ints(raw_value: str) -> list[int]:
    return [int(item.strip()) for item in raw_value.split(",") if item.strip()]


def parse_csv_strings(raw_value: str) -> list[str]:
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def view_subdir(view: str) -> Path:
    return Path() if view == "front" else Path("back")


def discover_installed_dexes() -> list[int]:
    front = {int(path.stem) for path in BACKUP_DIR.glob("*.png") if path.stem.isdigit()}
    back = {int(path.stem) for path in (BACKUP_DIR / "back").glob("*.png") if path.stem.isdigit()}
    return sorted(front | back)


def image_ref(path: Path) -> dict:
    image = Image.open(path).convert("RGBA")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    mime_type, _encoding = mimetypes.guess_type(path.name)
    return {
        "base64": base64.b64encode(buffer.getvalue()).decode("ascii"),
        "mime_type": mime_type or "image/png",
        "file_name": path.with_suffix(".png").name,
    }


def as_data_url(image: dict) -> str:
    return f"data:{image.get('mime_type', 'image/png')};base64,{image['base64']}"


def helper_for_transport(transport: str) -> Path:
    return FAL_DIRECT_HELPER if transport == "direct" else FAL_MPP_HELPER


def run_helper(payload: dict, timeout: int = 720, transport: str = "mpp") -> dict:
    helper = helper_for_transport(transport)
    result = subprocess.run(
        ["node", str(helper)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(detail or f"{helper.name} exited with code {result.returncode}")
    return json.loads(result.stdout)


def download_file(url: str) -> tuple[bytes, str]:
    req = urllib_request.Request(url, headers={"User-Agent": "mogmon-sprite-bg-mpp/1.0"})
    last_error = None
    for attempt in range(1, 4):
        try:
            with urllib_request.urlopen(req, timeout=300) as response:
                mime_type = response.headers.get_content_type() or "image/png"
                return response.read(), mime_type
        except (TimeoutError, urllib_error.URLError) as error:
            last_error = error
            if attempt >= 3:
                break
            time.sleep(attempt * 3)
    raise RuntimeError(f"Download failed after 3 attempts for {url}: {last_error}")


def run_background_remove(source_png: Path, model: str, max_spend: str, transport: str) -> dict:
    image = image_ref(source_png)
    body = {
        "image_url": as_data_url(image),
        "output_format": "png",
    }
    if model == "fal-ai/birefnet/v2":
        body["model"] = "General Use (Light)"
        body["operating_resolution"] = "1024x1024"

    response = run_helper({"model": model, "body": body, "maxSpend": max_spend}, transport=transport)
    images = response.get("images", [])
    if not images or not images[0].get("url"):
        raise RuntimeError(f"Fal MPP background remover returned no image URL for {model}")
    raw_bytes, mime_type = download_file(images[0]["url"])
    return {
        "model": response.get("model", f"mpp:{model}"),
        "mime_type": mime_type,
        "raw_bytes": raw_bytes,
        "remote_url": images[0]["url"],
    }


def installed_paths(dex: int, view: str) -> tuple[Path, Path, Path, Path]:
    subdir = view_subdir(view)
    live_png = POKEMON_DIR / subdir / f"{dex}.png"
    live_json = POKEMON_DIR / subdir / f"{dex}.json"
    template_png = BACKUP_DIR / subdir / f"{dex}.png"
    template_json = BACKUP_DIR / subdir / f"{dex}.json"
    return live_png, live_json, template_png, template_json


def normalize_removed_sprite(
    *,
    dex: int,
    view: str,
    bg_removed_path: Path,
    normalized_png: Path,
    normalized_json: Path,
    mode: str,
    centered: bool,
) -> dict:
    live_png, live_json, template_png, template_json = installed_paths(dex, view)
    if not live_png.exists() or not live_json.exists():
        raise RuntimeError(f"Missing installed {view} atlas for dex {dex}")
    if not template_png.exists() or not template_json.exists():
        raise RuntimeError(f"Missing backup template {view} atlas for dex {dex}")

    return normalize_battle_sprite_best_effort(
        bg_removed_path,
        template_json,
        normalized_png,
        normalized_json,
        clip_to_template_mask=False,
        mode=mode,
        centered=centered,
    )


def preserve_atlas_layout(
    *,
    source_png: Path,
    source_json: Path,
    bg_removed_path: Path,
    normalized_png: Path,
    normalized_json: Path,
) -> dict:
    source = Image.open(source_png).convert("RGBA")
    cleaned = Image.open(bg_removed_path).convert("RGBA")
    if cleaned.size != source.size:
        cleaned = cleaned.resize(source.size, Image.NEAREST)
    cleaned.save(normalized_png)
    normalized_json.write_text(source_json.read_text(encoding="utf-8"), encoding="utf-8")
    return {
        "expected_count": None,
        "detected_count": None,
        "method": "preserve-atlas-layout",
        "shared_scale": 1.0,
        "quality_score": None,
        "avg_iou": None,
        "min_iou": None,
        "tiny_frame_count": 0,
        "blank_frame_count": 0,
        "excess_edge_touches": 0,
        "fallback_used": False,
        "tried_methods": ["preserve-atlas-layout"],
        "sheet_w": source.size[0],
        "sheet_h": source.size[1],
    }


def update_manifest(manifest_path: Path, manifest: list[dict], by_key: dict[str, int], entry: dict) -> None:
    key = entry["key"]
    if key in by_key:
        manifest[by_key[key]] = entry
    else:
        by_key[key] = len(manifest)
        manifest.append(entry)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def rebuild_icons(dexes: list[int], pixelify_base: int) -> None:
    if not dexes:
        return
    command = [
        "python3",
        str(ROOT / "scripts" / "install_mogmon_icons.py"),
        "--dex",
        ",".join(str(dex) for dex in sorted(set(dexes))),
        "--pixelify-base",
        str(pixelify_base),
    ]
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean installed Mogger Mon sprite atlases with Fal MPP background removal.")
    parser.add_argument(
        "--dex-list",
        default="",
        help="Optional comma-separated dex list. Default processes every dex with a backup install.",
    )
    parser.add_argument(
        "--views",
        default="front,back",
        help="Comma-separated views to process. Default: front,back",
    )
    parser.add_argument("--output-root", default="output/mogmon-sprite-bg-remove-mpp")
    parser.add_argument("--model", default=DEFAULT_BG_REMOVE_MODEL)
    parser.add_argument("--max-spend", default=DEFAULT_MAX_SPEND)
    parser.add_argument(
        "--transport",
        choices=("mpp", "direct"),
        default="mpp",
        help="Fal transport. Use mpp for Tempo MPP payment or direct for FAL_API_KEY. Default: mpp",
    )
    parser.add_argument(
        "--mode",
        default="template-layout",
        help="Normalizer extraction mode. Default: template-layout, safest for already-installed atlases.",
    )
    parser.add_argument(
        "--centered",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use bottom-center anchoring during normalization. Default: enabled.",
    )
    parser.add_argument(
        "--renormalize",
        action="store_true",
        help="Run frame extraction after background removal. Default preserves existing atlas layout/JSON.",
    )
    parser.add_argument("--no-install", action="store_true")
    parser.add_argument("--no-icons", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--icon-pixelify-base", type=int, default=64)
    args = parser.parse_args()

    helper = helper_for_transport(args.transport)
    if not helper.exists():
        fail(f"Missing Fal helper: {helper}")

    dexes = parse_csv_ints(args.dex_list) if args.dex_list else discover_installed_dexes()
    views = parse_csv_strings(args.views)
    tasks = [(dex, view) for dex in dexes for view in views]
    if args.start_index:
        tasks = tasks[args.start_index :]
    if args.limit > 0:
        tasks = tasks[: args.limit]

    output_root = (ROOT / args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path = output_root / "manifest.json"
    manifest = []
    if manifest_path.exists() and not args.no_resume:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = []
    by_key = {entry.get("key"): index for index, entry in enumerate(manifest) if entry.get("key")}
    completed = {entry.get("key") for entry in manifest if entry.get("status") == "ok" and entry.get("key")}
    installed_dexes: set[int] = set()

    print(
        f"[mogmon-bg] selected={len(tasks)} completed={len([task for task in tasks if f'{task[0]:03d}-{task[1]}' in completed])} "
        f"remaining={len([task for task in tasks if f'{task[0]:03d}-{task[1]}' not in completed])}",
        flush=True,
    )

    for index, (dex, view) in enumerate(tasks, start=1):
        key = f"{dex:03d}-{view}"
        target_dir = output_root / f"{dex:03d}" / view
        target_dir.mkdir(parents=True, exist_ok=True)
        live_png, live_json, _template_png, template_json = installed_paths(dex, view)

        if key in completed and not args.no_resume:
            print(f"[mogmon-bg] {index}/{len(tasks)} skip {key}", flush=True)
            continue
        print(f"[mogmon-bg] {index}/{len(tasks)} start {key}", flush=True)

        try:
            if not live_png.exists() or not live_json.exists():
                raise RuntimeError(f"Missing live {view} atlas for dex {dex}")
            if not template_json.exists():
                raise RuntimeError(f"Missing backup template JSON for dex {dex} {view}")

            input_path = target_dir / "input.png"
            Image.open(live_png).convert("RGBA").save(input_path)
            input_json_path = target_dir / "input.json"
            input_json_path.write_text(live_json.read_text(encoding="utf-8"), encoding="utf-8")

            bg_remove = run_background_remove(live_png, args.model, args.max_spend, args.transport)
            bg_removed_path = target_dir / "bg-removed.png"
            bg_removed_path.write_bytes(bg_remove["raw_bytes"])

            normalized_png = target_dir / "normalized.png"
            normalized_json = target_dir / "normalized.json"
            if args.renormalize:
                normalize_result = normalize_removed_sprite(
                    dex=dex,
                    view=view,
                    bg_removed_path=bg_removed_path,
                    normalized_png=normalized_png,
                    normalized_json=normalized_json,
                    mode=args.mode,
                    centered=args.centered,
                )
            else:
                normalize_result = preserve_atlas_layout(
                    source_png=live_png,
                    source_json=live_json,
                    bg_removed_path=bg_removed_path,
                    normalized_png=normalized_png,
                    normalized_json=normalized_json,
                )

            if not args.no_install:
                Image.open(normalized_png).convert("RGBA").save(live_png)
                live_json.write_text(normalized_json.read_text(encoding="utf-8"), encoding="utf-8")
                installed_dexes.add(dex)

            entry = {
                "status": "ok",
                "key": key,
                "dex": dex,
                "view": view,
                "bg_remove_model": bg_remove["model"],
                "mime_type": bg_remove["mime_type"],
                "source_png": str(live_png),
                "source_json": str(live_json),
                "template_json": str(template_json),
                "input_output": str(input_path),
                "input_json_output": str(input_json_path),
                "bg_removed_output": str(bg_removed_path),
                "normalized_png": str(normalized_png),
                "normalized_json": str(normalized_json),
                "bg_remote_url": bg_remove["remote_url"],
                "installed": not args.no_install,
                "normalize": normalize_result,
            }
            print(
                f"[mogmon-bg] {index}/{len(tasks)} ok {key}"
                f" {normalize_result['method']}"
                + (
                    f" score={normalize_result['quality_score']:.3f}"
                    if normalize_result.get("quality_score") is not None
                    else ""
                ),
                flush=True,
            )
        except Exception as error:
            entry = {
                "status": "error",
                "key": key,
                "dex": dex,
                "view": view,
                "error": str(error),
                "installed": False,
            }
            print(f"[mogmon-bg] {index}/{len(tasks)} error {key}: {error}", flush=True)

        update_manifest(manifest_path, manifest, by_key, entry)

    if not args.no_install and not args.no_icons:
        rebuild_icons(sorted(installed_dexes), args.icon_pixelify_base)


if __name__ == "__main__":
    main()
