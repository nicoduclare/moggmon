#!/usr/bin/env python3
"""Generate sheet-based redraws for battle animation visual assets.

This packs the original battle animation PNGs into transparent edit sheets,
optionally sends those sheets to Fal, cuts the edited result back into the
original filenames and dimensions, and installs the cuts into assets/images.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from urllib import request as urllib_request

from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
PACK_BATTLE_ANIM_ROOT = ROOT / "output" / "original-art-redo-pack" / "images" / "battle_anims"
ASSET_BATTLE_ANIM_ROOT = ROOT / "assets" / "images" / "battle_anims"
FAL_HELPER = Path(__file__).with_name("fal_grok_edit.mjs")

DEFAULT_OUTPUT_ROOT = ROOT / "output" / "battle-anim-sheet-redo"
DEFAULT_MODEL = "openai/gpt-image-2/edit"
DEFAULT_IMAGE_SIZE = "1536x1536"
DEFAULT_PADDING = 12
MIN_ALPHA_PIXELS = 8


@dataclass
class Target:
    name: str
    path: Path
    width: int
    height: int
    alpha_pixels: int

    @property
    def area(self) -> int:
        return self.width * self.height


@dataclass
class Shelf:
    y: int
    height: int
    x: int = 0


@dataclass
class Page:
    index: int
    width: int
    height: int
    padding: int
    shelves: list[Shelf] = field(default_factory=list)
    next_y: int = 0
    entries: list[dict] = field(default_factory=list)

    def try_place(self, target: Target) -> bool:
        padded_w = target.width + self.padding * 2
        padded_h = target.height + self.padding * 2
        if padded_w > self.width or padded_h > self.height:
            return False

        for shelf in self.shelves:
            if padded_h <= shelf.height and shelf.x + padded_w <= self.width:
                x = shelf.x + self.padding
                y = shelf.y + self.padding
                shelf.x += padded_w
                self.entries.append(entry_for_target(target, x, y))
                return True

        if self.next_y + padded_h <= self.height:
            shelf = Shelf(y=self.next_y, height=padded_h, x=padded_w)
            self.shelves.append(shelf)
            x = self.padding
            y = self.next_y + self.padding
            self.next_y += padded_h
            self.entries.append(entry_for_target(target, x, y))
            return True

        return False


def fail(message: str) -> None:
    raise SystemExit(message)


def parse_image_size(value: str) -> tuple[int, int]:
    if "x" not in value.lower():
        fail(f"--image-size must look like WIDTHxHEIGHT, got {value!r}")
    width, height = value.lower().split("x", 1)
    return int(width), int(height)


def image_size_payload(model: str, size: tuple[int, int]) -> object:
    if "gpt-image-2" in model:
        return {"width": size[0], "height": size[1]}
    return f"{size[0]}x{size[1]}"


def alpha_pixel_count(image: Image.Image) -> int:
    alpha = image.getchannel("A")
    histogram = alpha.histogram()
    return sum(histogram[1:])


def validate_nonblank(image: Image.Image, label: str) -> None:
    count = alpha_pixel_count(image)
    if count < MIN_ALPHA_PIXELS:
        raise RuntimeError(f"{label} is blank or nearly blank after cut ({count} alpha pixels)")


def entry_for_target(target: Target, x: int, y: int) -> dict:
    return {
        "target": target.name,
        "source_path": str(target.path),
        "source_size": {"w": target.width, "h": target.height},
        "source_alpha_pixels": target.alpha_pixels,
        "rect": {"x": x, "y": y, "w": target.width, "h": target.height},
    }


def discover_targets(input_root: Path, limit: int) -> list[Target]:
    if not input_root.exists():
        fail(f"Input root does not exist: {input_root}")

    targets: list[Target] = []
    for path in sorted(input_root.glob("*.png")):
        if path.name.startswith("."):
            continue
        image = Image.open(path).convert("RGBA")
        alpha_pixels = alpha_pixel_count(image)
        if alpha_pixels < MIN_ALPHA_PIXELS:
            print(f"[skip] {path.name} has only {alpha_pixels} alpha pixels", flush=True)
            continue
        targets.append(
            Target(
                name=path.name,
                path=path,
                width=image.width,
                height=image.height,
                alpha_pixels=alpha_pixels,
            )
        )

    targets.sort(key=lambda item: (-item.height, -item.width, item.name.lower()))
    if limit > 0:
        targets = targets[:limit]
    if not targets:
        fail("No battle animation PNGs matched")
    return targets


def pack_targets(targets: list[Target], sheet_size: tuple[int, int], padding: int) -> list[Page]:
    pages: list[Page] = []
    for target in targets:
        if target.width + padding * 2 > sheet_size[0] or target.height + padding * 2 > sheet_size[1]:
            fail(
                f"{target.name} is {target.width}x{target.height}, which does not fit in "
                f"{sheet_size[0]}x{sheet_size[1]} with {padding}px padding"
            )
        placed = False
        for page in pages:
            if page.try_place(target):
                placed = True
                break
        if not placed:
            page = Page(index=len(pages) + 1, width=sheet_size[0], height=sheet_size[1], padding=padding)
            if not page.try_place(target):
                fail(f"Could not place {target.name}")
            pages.append(page)
    return pages


def file_b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def image_ref(path: Path, label: str) -> dict:
    mime_type, _encoding = mimetypes.guess_type(path.name)
    return {
        "label": label,
        "base64": file_b64(path),
        "mime_type": mime_type or "image/png",
        "file_name": path.name,
    }


def run_json_helper(payload: dict) -> dict:
    result = subprocess.run(
        ["node", str(FAL_HELPER)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(detail or f"{FAL_HELPER.name} exited with code {result.returncode}")
    return json.loads(result.stdout)


def download_file(url: str) -> tuple[bytes, str]:
    req = urllib_request.Request(url, headers={"User-Agent": "mogger-mon-battle-anim-redo/1.0"})
    with urllib_request.urlopen(req, timeout=300) as response:
        mime_type = response.headers.get_content_type() or "image/png"
        return response.read(), mime_type


def write_page_sheet(page: Page, output_root: Path) -> dict:
    page_dir = output_root / f"page-{page.index:03d}"
    page_dir.mkdir(parents=True, exist_ok=True)
    sheet = Image.new("RGBA", (page.width, page.height), (0, 0, 0, 0))
    for entry in page.entries:
        source = Image.open(entry["source_path"]).convert("RGBA")
        rect = entry["rect"]
        sheet.alpha_composite(source, (rect["x"], rect["y"]))

    sheet_path = page_dir / f"battle-anim-page-{page.index:03d}.png"
    manifest_path = page_dir / f"battle-anim-page-{page.index:03d}.json"
    sheet.save(sheet_path)
    manifest = {
        "index": page.index,
        "sheet": str(sheet_path),
        "sheet_size": {"w": page.width, "h": page.height},
        "padding": page.padding,
        "entries": page.entries,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def build_prompt(manifest: dict) -> str:
    size = manifest["sheet_size"]
    return "\n".join(
        [
            "Edit this exact transparent 2D game battle VFX sprite-sheet page into original Mogger Mon battle animation art.",
            f"Canvas: {size['w']}x{size['h']} pixels.",
            f"Animation strips on this page: {len(manifest['entries'])}.",
            "",
            "Hard constraints:",
            "- return one PNG with the exact same pixel dimensions as the input image",
            "- preserve transparent alpha outside the existing effects; no background, checkerboard, grid, matte, fog, or scene",
            "- keep every effect inside its original transparent rectangle and keep the frame order/timing readable",
            "- do not add monsters, trainers, hands, UI, labels, captions, icons, logos, watermarks, or text",
            "- do not merge effects together or move one effect into another effect's rectangle",
            "- keep the art as crisp low-resolution game VFX, but avoid chunky over-pixelation and muddy blur",
            "- make the artwork original: abstract energy, sound waves, impact bursts, smoke, speed lines, beams, sparks, charms, and elemental particles",
            "- avoid recognizable franchise motifs, original move names, brand marks, or copied commercial designs",
            "- preserve the apparent animation purpose of each strip: sounds still read as sound, slash as slash, fire as fire, impact as impact",
            "",
            "Output only the edited transparent sprite-sheet page.",
        ]
    )


def run_fal_page(manifest: dict, model: str, quality: str, resume: bool) -> dict:
    sheet_path = Path(manifest["sheet"])
    page_dir = sheet_path.parent
    raw_path = page_dir / f"battle-anim-page-{manifest['index']:03d}.raw.png"
    prompt_path = page_dir / f"battle-anim-page-{manifest['index']:03d}.prompt.txt"
    response_path = page_dir / f"battle-anim-page-{manifest['index']:03d}.fal.json"

    if resume and raw_path.exists():
        return {
            "model": f"fal:{model}",
            "request_id": None,
            "remote_url": None,
            "mime_type": "image/png",
            "raw_path": str(raw_path),
            "prompt_path": str(prompt_path),
            "resumed": True,
        }

    prompt = build_prompt(manifest)
    prompt_path.write_text(prompt + "\n", encoding="utf-8")
    size = manifest["sheet_size"]
    payload = {
        "model": model,
        "prompt": prompt,
        "referenceImages": [image_ref(sheet_path, sheet_path.name)],
        "imageSize": image_size_payload(model, (size["w"], size["h"])),
        "quality": quality,
        "outputFormat": "png",
        "numImages": 1,
    }
    response = run_json_helper(payload)
    images = response.get("images") or []
    if not images or not images[0].get("url"):
        raise RuntimeError(f"FAL returned no image URL: {json.dumps(response)[:600]}")

    raw_bytes, mime_type = download_file(images[0]["url"])
    raw_path.write_bytes(raw_bytes)
    response_path.write_text(json.dumps(response, indent=2) + "\n", encoding="utf-8")
    return {
        "model": response.get("model", f"fal:{model}"),
        "request_id": response.get("requestId"),
        "remote_url": images[0]["url"],
        "mime_type": mime_type,
        "raw_path": str(raw_path),
        "prompt_path": str(prompt_path),
        "response_path": str(response_path),
    }


def clean_rgb_where_transparent(image: Image.Image) -> Image.Image:
    image = image.convert("RGBA")
    transparent = Image.new("RGBA", image.size, (0, 0, 0, 0))
    transparent.alpha_composite(image)
    return transparent


def key_dark_background_alpha(crop: Image.Image, threshold: int, softness: int) -> Image.Image:
    crop = crop.convert("RGBA")
    if softness <= 0:
        softness = 1
    output = Image.new("RGBA", crop.size, (0, 0, 0, 0))
    in_px = crop.load()
    out_px = output.load()
    for y in range(crop.height):
        for x in range(crop.width):
            r, g, b, _a = in_px[x, y]
            value = max(r, g, b)
            if value <= threshold:
                continue
            alpha = min(255, int(((value - threshold) / softness) * 255))
            out_px[x, y] = (r, g, b, alpha)
    return clean_rgb_where_transparent(output)


def apply_alpha_mode(
    crop: Image.Image,
    source: Image.Image,
    alpha_mode: str,
    key_threshold: int,
    key_softness: int,
) -> Image.Image:
    crop = crop.convert("RGBA")
    source = source.convert("RGBA")
    if crop.size != source.size:
        crop = crop.resize(source.size, Image.Resampling.BICUBIC)

    if alpha_mode == "generated":
        return clean_rgb_where_transparent(crop)
    if alpha_mode == "generated-key":
        return key_dark_background_alpha(crop, key_threshold, key_softness)

    generated_alpha = crop.getchannel("A")
    generated_has_transparency = generated_alpha.getextrema()[0] < 255
    if alpha_mode == "auto" and generated_has_transparency:
        return clean_rgb_where_transparent(crop)
    if alpha_mode == "auto-key":
        if generated_has_transparency:
            return clean_rgb_where_transparent(crop)
        return key_dark_background_alpha(crop, key_threshold, key_softness)

    r, g, b, _a = crop.split()
    output = Image.merge("RGBA", (r, g, b, source.getchannel("A")))
    return clean_rgb_where_transparent(output)


def cut_page(
    manifest: dict,
    raw_path: Path,
    output_root: Path,
    alpha_mode: str,
    allow_resize_raw: bool,
    key_threshold: int,
    key_softness: int,
) -> list[dict]:
    sheet = Image.open(raw_path).convert("RGBA")
    expected = (manifest["sheet_size"]["w"], manifest["sheet_size"]["h"])
    if sheet.size != expected:
        if not allow_resize_raw:
            raise RuntimeError(f"{raw_path.name} is {sheet.width}x{sheet.height}, expected {expected[0]}x{expected[1]}")
        sheet = sheet.resize(expected, Image.Resampling.BICUBIC)

    cut_root = output_root / "cut"
    outputs = []
    failures = []
    for entry in manifest["entries"]:
        try:
            rect = entry["rect"]
            crop = sheet.crop((rect["x"], rect["y"], rect["x"] + rect["w"], rect["y"] + rect["h"]))
            source = Image.open(entry["source_path"]).convert("RGBA")
            crop = apply_alpha_mode(crop, source, alpha_mode, key_threshold, key_softness)
            validate_nonblank(crop, entry["target"])
            out_path = cut_root / entry["target"]
            out_path.parent.mkdir(parents=True, exist_ok=True)
            crop.save(out_path)
            outputs.append(
                {
                    "target": entry["target"],
                    "output": str(out_path),
                    "size": [crop.width, crop.height],
                    "alpha_pixels": alpha_pixel_count(crop),
                }
            )
        except Exception as error:
            failures.append({"target": entry["target"], "error": str(error)})

    failures_path = output_root / "cut-failures.json"
    if failures:
        failures_path.write_text(json.dumps(failures, indent=2) + "\n", encoding="utf-8")
    elif failures_path.exists():
        failures_path.unlink()
    return outputs


def install_outputs(cut_outputs: list[dict], install_root: Path, backup_root: Path) -> list[dict]:
    installed = []
    backup_root.mkdir(parents=True, exist_ok=True)
    for item in cut_outputs:
        source = Path(item["output"])
        dest = install_root / item["target"]
        if not dest.exists():
            continue
        backup = backup_root / item["target"]
        if not backup.exists():
            shutil.copy2(dest, backup)
        shutil.copy2(source, dest)
        installed.append({"target": item["target"], "dest": str(dest), "backup": str(backup)})
    return installed


def selected_page(index: int, start_page: int, end_page: int, max_pages: int, selected_count: int) -> bool:
    if start_page and index < start_page:
        return False
    if end_page and index > end_page:
        return False
    if max_pages and selected_count >= max_pages:
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Build, edit, cut, and install battle animation visual redraw sheets.")
    parser.add_argument("--input-root", default=str(PACK_BATTLE_ANIM_ROOT))
    parser.add_argument("--install-root", default=str(ASSET_BATTLE_ANIM_ROOT))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--image-size", default=DEFAULT_IMAGE_SIZE)
    parser.add_argument("--quality", default="medium", choices=["low", "medium", "high"])
    parser.add_argument("--padding", type=int, default=DEFAULT_PADDING)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--start-page", type=int, default=0)
    parser.add_argument("--end-page", type=int, default=0)
    parser.add_argument("--max-pages", type=int, default=0)
    parser.add_argument("--run-fal", action="store_true")
    parser.add_argument("--cut", action="store_true")
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--allow-partial-install", action="store_true")
    parser.add_argument("--no-resize-raw", action="store_true")
    parser.add_argument(
        "--alpha-mode",
        default="auto-key",
        choices=["source-mask", "generated", "generated-key", "auto", "auto-key"],
        help="How to recover transparency from generated sheets. auto-key keys black backgrounds when the model returns opaque PNGs.",
    )
    parser.add_argument("--key-threshold", type=int, default=14, help="RGB max-channel value treated as transparent black.")
    parser.add_argument("--key-softness", type=int, default=70, help="Brightness ramp width for generated-key alpha extraction.")
    args = parser.parse_args()

    sheet_size = parse_image_size(args.image_size)
    if sheet_size[0] % 16 or sheet_size[1] % 16:
        fail("--image-size edges must be multiples of 16 for GPT Image 2 custom dimensions")
    if args.padding < 0:
        fail("--padding must be >= 0")
    if args.install and not args.cut:
        fail("--install requires --cut")

    input_root = Path(args.input_root).resolve()
    install_root = Path(args.install_root).resolve()
    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    targets = discover_targets(input_root, args.limit)
    pages = pack_targets(targets, sheet_size, args.padding)
    run_manifest = {
        "model": args.model,
        "image_size": {"w": sheet_size[0], "h": sheet_size[1]},
        "quality": args.quality,
        "padding": args.padding,
        "alpha_mode": args.alpha_mode,
        "input_root": str(input_root),
        "install_root": str(install_root),
        "target_count": len(targets),
        "page_count": len(pages),
        "pages": [],
    }

    selected_count = 0
    for page in pages:
        manifest = write_page_sheet(page, output_root)
        page_dir = Path(manifest["sheet"]).parent
        record = {
            "index": page.index,
            "manifest": str(page_dir / f"battle-anim-page-{page.index:03d}.json"),
            "sheet": manifest["sheet"],
            "target_count": len(page.entries),
        }
        should_process = selected_page(page.index, args.start_page, args.end_page, args.max_pages, selected_count)
        if should_process:
            selected_count += 1
        print(
            f"[sheet] {page.index:03d}/{len(pages):03d} built {len(page.entries)} targets"
            f"{' (selected)' if should_process else ''}",
            flush=True,
        )

        if should_process and args.run_fal:
            try:
                fal_result = run_fal_page(manifest, args.model, args.quality, args.resume)
                record["fal"] = fal_result
                print(f"[fal] page {page.index:03d} -> {fal_result['raw_path']}", flush=True)
            except Exception as error:
                record["error"] = str(error)
                print(f"[fal] page {page.index:03d} error: {error}", flush=True)

        if should_process and args.cut:
            try:
                raw_path = Path(record.get("fal", {}).get("raw_path") or page_dir / f"battle-anim-page-{page.index:03d}.raw.png")
                if not raw_path.exists():
                    raise RuntimeError(f"raw image missing: {raw_path}")
                cut_outputs = cut_page(
                    manifest,
                    raw_path,
                    page_dir,
                    args.alpha_mode,
                    allow_resize_raw=not args.no_resize_raw,
                    key_threshold=args.key_threshold,
                    key_softness=args.key_softness,
                )
                failures_path = page_dir / "cut-failures.json"
                if failures_path.exists():
                    record["cut_failures"] = str(failures_path)
                    if args.install and not args.allow_partial_install:
                        raise RuntimeError(f"refusing partial install; inspect {failures_path}")
                record["cut_outputs"] = cut_outputs
                print(f"[cut] page {page.index:03d} cut {len(cut_outputs)} targets", flush=True)

                if args.install:
                    backup_root = output_root / "backup" / "assets" / "images" / "battle_anims"
                    installed = install_outputs(cut_outputs, install_root, backup_root)
                    record["installed"] = installed
                    print(f"[install] page {page.index:03d} installed {len(installed)} targets", flush=True)
            except Exception as error:
                record["error"] = str(error)
                print(f"[cut] page {page.index:03d} error: {error}", flush=True)

        run_manifest["pages"].append(record)
        (output_root / "manifest.json").write_text(json.dumps(run_manifest, indent=2) + "\n", encoding="utf-8")

    print(
        f"[done] {len(targets)} targets packed across {len(pages)} pages; "
        f"manifest: {output_root / 'manifest.json'}",
        flush=True,
    )


if __name__ == "__main__":
    main()
