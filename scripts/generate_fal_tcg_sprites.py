#!/usr/bin/env python3
"""Generate Mogger Mon battle sprite sheets from TCG art via Fal Nano Banana 2."""

from __future__ import annotations

import argparse
import base64
import json
import math
import mimetypes
import os
import subprocess
import time
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

from PIL import Image


DEFAULT_MODEL = "fal-ai/nano-banana-2/edit"
GROK_EDIT_MODEL = "xai/grok-imagine-image/edit"
FAL_API_BASE_URL = "https://fal.run"
DEFAULT_RESOLUTION = "1K"
DEFAULT_OUTPUT_FORMAT = "png"
TEMPLATE_TARGET_LONG_EDGE = 1200
DEFAULT_HTTP_TIMEOUT = 300
DEFAULT_FAL_RETRIES = 2
FAL_GROK_HELPER = Path(__file__).with_name("fal_grok_edit.mjs")


def fail(message: str) -> None:
    raise SystemExit(message)


def read_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def normalize_model_name(raw_model: str | None) -> str:
    normalized = (raw_model or "").strip()
    if not normalized or normalized.lower() == "auto":
        return DEFAULT_MODEL
    if normalized.startswith("fal:"):
        normalized = normalized.removeprefix("fal:")
    return normalized


def resolve_model(meta: dict, override_model: str | None) -> str:
    if override_model and override_model.strip().lower() != "auto":
        return normalize_model_name(override_model)
    return normalize_model_name(meta.get("model"))


def _load_image_bytes(path: Path, nearest_upscale: bool = False) -> tuple[bytes, str]:
    image = Image.open(path).convert("RGBA")
    if nearest_upscale:
        max_dim = max(image.size)
        scale = max(1, min(8, math.ceil(TEMPLATE_TARGET_LONG_EDGE / max_dim)))
        if scale > 1:
            image = image.resize((image.width * scale, image.height * scale), Image.NEAREST)

    mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
    with Path(path).open("rb") as handle:
        raw_bytes = handle.read()

    if nearest_upscale:
        from io import BytesIO

        buffer = BytesIO()
        image.save(buffer, format="PNG")
        raw_bytes = buffer.getvalue()
        mime_type = "image/png"

    return raw_bytes, mime_type


def image_to_data_uri(path: Path, nearest_upscale: bool = False) -> str:
    raw_bytes, mime_type = _load_image_bytes(path, nearest_upscale=nearest_upscale)
    return f"data:{mime_type};base64,{base64.b64encode(raw_bytes).decode('ascii')}"


def build_reference_image_payload(path: Path, nearest_upscale: bool = False) -> dict:
    raw_bytes, mime_type = _load_image_bytes(path, nearest_upscale=nearest_upscale)
    file_name = path.with_suffix(".png").name if nearest_upscale else path.name
    return {
        "base64": base64.b64encode(raw_bytes).decode("ascii"),
        "mime_type": mime_type,
        "file_name": file_name,
    }


def remove_background(img_path: Path) -> None:
    image = Image.open(img_path).convert("RGBA")
    width, height = image.size
    pixels = image.load()
    tolerance = 30

    def color_match(color_a, color_b):
        return all(abs(a - b) <= tolerance for a, b in zip(color_a[:3], color_b[:3]))

    border_points = set()
    for x in range(width):
        border_points.add((x, 0))
        border_points.add((x, height - 1))
    for y in range(height):
        border_points.add((0, y))
        border_points.add((width - 1, y))

    border_colors = {}
    for x, y in border_points:
        color = pixels[x, y][:3]
        key = (color[0] // 8, color[1] // 8, color[2] // 8)
        border_colors[key] = border_colors.get(key, 0) + 1

    top_keys = sorted(border_colors, key=border_colors.get, reverse=True)[:6]
    reference_colors = [(key[0] * 8 + 4, key[1] * 8 + 4, key[2] * 8 + 4) for key in top_keys]

    def is_background(rgb):
        return any(color_match(rgb, reference) for reference in reference_colors)

    queue = list(border_points)
    visited = set()
    to_clear = []
    while queue:
        x, y = queue.pop()
        if (x, y) in visited or x < 0 or x >= width or y < 0 or y >= height:
            continue
        visited.add((x, y))
        r, g, b, _a = pixels[x, y]
        if not is_background((r, g, b)):
            continue

        to_clear.append((x, y))
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            queue.append((x + dx, y + dy))

    for x, y in to_clear:
        pixels[x, y] = (0, 0, 0, 0)

    image.save(img_path)


def choose_reference_art(tcg_dir: Path, preferred_file: str | None = None) -> Path:
    if preferred_file:
        preferred_path = tcg_dir / preferred_file
        if preferred_path.exists():
            return preferred_path
        fail(f"Requested reference art does not exist: {preferred_path}")

    preferred_stems = (
        "full-art-2",
        "full-art",
        "reference-style",
        "reference",
        "card",
    )
    preferred_extensions = (".png", ".jpg", ".jpeg", ".webp")

    for stem in preferred_stems:
        for extension in preferred_extensions:
            path = tcg_dir / f"{stem}{extension}"
            if path.exists():
                return path
    fail(f"No TCG reference art found in {tcg_dir}")


def choose_meta_file(tcg_dir: Path, preferred_file: str | None = None) -> Path:
    if preferred_file:
        preferred_path = tcg_dir / preferred_file
        if preferred_path.exists():
            return preferred_path
        fail(f"Requested metadata file does not exist: {preferred_path}")

    preferred_candidates = (
        tcg_dir / "meta-2.json",
        tcg_dir / "meta.json",
    )
    for candidate in preferred_candidates:
        if candidate.exists():
            return candidate

    fallback_candidates = sorted(tcg_dir.glob("meta*.json"))
    if fallback_candidates:
        return fallback_candidates[0]

    fail(f"Missing TCG metadata for {tcg_dir}")


def build_prompt(
    *,
    dex: int,
    view: str,
    meta: dict,
    include_front_reference: bool,
    omit_identity_text: bool,
) -> str:
    name = meta.get("name", f"Dex {dex}")
    formula = meta.get("formula", "")
    description = meta.get("description", "")
    stage_note = meta.get("stageNote", "")
    family_note = meta.get("familyContrastNote", "")
    stage_label = meta.get("stageLabel", "")

    image_count = 3 if include_front_reference else 2
    lines = [
        f"I gave you {image_count} images.",
        "",
        "IMAGE 1 is the exact Pokerogue battle sprite sheet template.",
        f"IMAGE 2 is the TCG full-art character reference for {name}.",
    ]

    if include_front_reference:
        lines.append(
            f"IMAGE 3 is the already-generated FRONT sprite sheet for {name}. Use it to keep the exact same creature design while drawing the BACK view."
        )

    lines.extend(
        [
            "",
            "Task:",
            "Redraw IMAGE 1 exactly as a paint-over replacement, but replace the original creature with the character from the supplied TCG reference.",
        ]
    )

    lines.extend([""])
    if not omit_identity_text:
        lines.extend(
            [
                f"Character name: {name}",
                f"Formula: {formula}",
            ]
        )
    lines.extend(
        [
            f"Stage label: {stage_label}",
            "Description:",
            description,
            "Evolution stage direction:",
            stage_note or "Keep the stage identity clean and readable.",
        ]
    )

    if family_note:
        lines.extend(["Family progression lock:", family_note])

    lines.extend(
        [
            f"Requested view: {view.upper()} battle sprite sheet.",
            "",
            "Strict requirements:",
            "- keep the exact same sprite sheet grid layout, frame count, frame size, spacing, transparent background, and empty cells as IMAGE 1",
            "- keep the same pixel-art rendering style, camera framing, body tilt, pose rhythm, and animation timing as IMAGE 1",
            "- every occupied frame in IMAGE 1 must stay occupied by the replacement creature, and every empty slot must remain empty",
            "- every occupied frame must contain one complete full-body creature rather than fragments",
            "- never crop the head, face, torso, weapon, legs, or feet out of a frame",
            "- never split a frame into detached limbs, floating props, broken body parts, isolated faces, or exploded pieces",
            "- keep the silhouette connected, readable, and battle-ready in every occupied frame",
            "- if a pose feels too big for its slot, zoom the whole creature out inside that slot instead of cropping or simplifying it",
            "- compact early-stage creatures must stay fully visible in every occupied frame; never reduce them to only hair, only leaves, only feet, or only a face",
            "- use IMAGE 2 as the design truth for the creature identity, face, silhouette language, colors, and stage-specific anatomy",
            "- reinterpret IMAGE 2 into crisp retro monster-battler pixel art rather than painterly card art",
            "- do not output TCG art, a poster, a single character illustration, a mockup, or a collage",
            "- do not add UI, labels, borders, scenery, props, effects, glow, motion streaks, watermark, or text",
            "- keep every frame fully inside its own slot",
        ]
    )

    if view == "back":
        lines.extend(
            [
                "- draw the exact same creature from behind; the back view must match the front-view design, colors, proportions, and anatomy",
                "- preserve recognizable stage-specific anatomy from IMAGE 3 while turning the pose set around to match the back-view template",
            ]
        )
    else:
        lines.append("- draw the creature facing the viewer in the same orientation as the front-view template")

    lines.extend(
        [
            "- the stage description outranks any extra anatomy implied by the art if they conflict",
            "- output only the finished sprite sheet image",
        ]
    )
    return "\n".join(lines)


def fal_edit(api_key: str, model: str, prompt: str, image_urls: list[str], resolution: str) -> dict:
    body = {
        "prompt": prompt,
        "image_urls": image_urls,
        "num_images": 1,
        "resolution": resolution,
        "output_format": DEFAULT_OUTPUT_FORMAT,
        "limit_generations": True,
    }

    request = urllib_request.Request(
        f"{FAL_API_BASE_URL}/{model}",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Key {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    for attempt in range(1, DEFAULT_FAL_RETRIES + 1):
        try:
            with urllib_request.urlopen(request, timeout=DEFAULT_HTTP_TIMEOUT) as response:
                return json.loads(response.read())
        except urllib_error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Fal API {exc.code}: {detail[:1200]}") from exc
        except (TimeoutError, urllib_error.URLError) as exc:
            if attempt >= DEFAULT_FAL_RETRIES:
                raise RuntimeError(
                    f"Fal request failed after {attempt} attempts: {exc}"
                ) from exc
            wait_seconds = attempt * 3
            print(
                f"Fal request attempt {attempt}/{DEFAULT_FAL_RETRIES} failed: {exc}. "
                f"Retrying in {wait_seconds}s..."
            )
            time.sleep(wait_seconds)


def fal_edit_via_helper(
    *,
    model: str,
    prompt: str,
    reference_images: list[dict],
    resolution: str,
    output_format: str,
) -> dict:
    if not FAL_GROK_HELPER.exists():
        raise RuntimeError(f"Fal helper not found: {FAL_GROK_HELPER}")

    payload = {
        "model": model,
        "prompt": prompt,
        "referenceImages": reference_images,
        "resolution": resolution.lower(),
        "outputFormat": output_format,
        "numImages": 1,
    }
    try:
        result = subprocess.run(
            ["node", str(FAL_GROK_HELPER)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=True,
            timeout=DEFAULT_HTTP_TIMEOUT + 120,
        )
    except subprocess.CalledProcessError as exc:
        error_text = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(error_text or f"Fal helper exited with code {exc.returncode}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Fal helper timed out after {exc.timeout} seconds") from exc

    stdout = result.stdout.strip()
    if not stdout:
        raise RuntimeError("Fal helper returned no output")

    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Fal helper returned invalid JSON: {stdout[:400]}") from exc


def run_fal_edit(
    *,
    api_key: str,
    model: str,
    prompt: str,
    image_urls: list[str],
    reference_images: list[dict],
    resolution: str,
) -> dict:
    if model.startswith("xai/") or model == GROK_EDIT_MODEL:
        return fal_edit_via_helper(
            model=model,
            prompt=prompt,
            reference_images=reference_images,
            resolution=resolution,
            output_format=DEFAULT_OUTPUT_FORMAT,
        )

    return fal_edit(
        api_key=api_key,
        model=model,
        prompt=prompt,
        image_urls=image_urls,
        resolution=resolution,
    )


def download_image(url: str, output_path: Path) -> None:
    for attempt in range(1, DEFAULT_FAL_RETRIES + 1):
        try:
            with urllib_request.urlopen(url, timeout=DEFAULT_HTTP_TIMEOUT) as response:
                output_path.write_bytes(response.read())
            return
        except (TimeoutError, urllib_error.URLError) as exc:
            if attempt >= DEFAULT_FAL_RETRIES:
                raise RuntimeError(
                    f"Download failed after {attempt} attempts for {url}: {exc}"
                ) from exc
            wait_seconds = attempt * 3
            print(
                f"Image download attempt {attempt}/{DEFAULT_FAL_RETRIES} failed: {exc}. "
                f"Retrying in {wait_seconds}s..."
            )
            time.sleep(wait_seconds)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def generate_one(
    *,
    api_key: str,
    dex: int,
    view: str,
    output_root: Path,
    assets_root: Path,
    tcg_root: Path,
    resolution: str,
    model_override: str | None,
    reference_file: str | None,
    meta_file: str | None,
    omit_identity_text: bool,
) -> dict:
    tcg_dir = tcg_root / f"{dex:03d}"
    meta_path = choose_meta_file(tcg_dir, preferred_file=meta_file)
    meta = read_json(meta_path)
    template_path = assets_root / ("back" if view == "back" else "") / f"{dex}.png"
    if not template_path.exists():
        fail(f"Missing template sprite sheet: {template_path}")

    reference_art_path = choose_reference_art(tcg_dir, preferred_file=reference_file)
    out_dir = output_root / view
    ensure_dir(out_dir)
    output_path = out_dir / f"{dex}.png"
    prompt_path = out_dir / f"{dex}.prompt.txt"
    meta_path = out_dir / f"{dex}.json"

    model = resolve_model(meta, model_override)
    include_front_reference = view == "back"
    image_urls = [
        image_to_data_uri(template_path, nearest_upscale=True),
        image_to_data_uri(reference_art_path, nearest_upscale=False),
    ]
    reference_images = [
        build_reference_image_payload(template_path, nearest_upscale=True),
        build_reference_image_payload(reference_art_path, nearest_upscale=False),
    ]

    if include_front_reference:
        front_output_path = output_root / "front" / f"{dex}.png"
        if not front_output_path.exists():
            fail(f"Back view requested before front output exists: {front_output_path}")
        image_urls.append(image_to_data_uri(front_output_path, nearest_upscale=True))
        reference_images.append(build_reference_image_payload(front_output_path, nearest_upscale=True))

    prompt = build_prompt(
        dex=dex,
        view=view,
        meta=meta,
        include_front_reference=include_front_reference,
        omit_identity_text=omit_identity_text,
    )
    prompt_path.write_text(prompt + "\n", encoding="utf-8")

    result = run_fal_edit(
        api_key=api_key,
        model=model,
        prompt=prompt,
        image_urls=image_urls,
        reference_images=reference_images,
        resolution=resolution,
    )
    images = result.get("images") or []
    if not images or not images[0].get("url"):
        raise RuntimeError(f"No image URL returned for dex {dex} {view}: {json.dumps(result)[:1200]}")

    download_image(images[0]["url"], output_path)
    remove_background(output_path)

    saved_meta = {
        "dex": dex,
        "view": view,
        "model": model,
        "resolution": resolution,
        "promptPath": str(prompt_path),
        "metaPath": str(meta_path),
        "templatePath": str(template_path),
        "referenceArtPath": str(reference_art_path),
        "frontReferencePath": str(output_root / "front" / f"{dex}.png") if include_front_reference else None,
        "falResponse": {
            "description": result.get("description", ""),
            "images": images,
        },
        "tcgMeta": meta,
    }
    meta_path.write_text(json.dumps(saved_meta, indent=2) + "\n", encoding="utf-8")

    return {
        "dex": dex,
        "view": view,
        "output": str(output_path),
        "prompt": str(prompt_path),
        "meta": str(meta_path),
    }


def parse_list_arg(raw: str) -> list[int]:
    values = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        values.append(int(part))
    return values


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Mogger Mon sprite sheets from TCG art via Fal edit models.")
    parser.add_argument("--dex", default="4,5,6", help="Comma-separated dex list. Default: 4,5,6")
    parser.add_argument("--views", default="front,back", help="Comma-separated views. Default: front,back")
    parser.add_argument(
        "--output-root",
        default="output/tung-family-nano-banana-2",
        help="Directory for generated raw sprite sheets.",
    )
    parser.add_argument(
        "--assets-root",
        default="assets/images/pokemon",
        help="Path to Pokerogue battle sprite atlases.",
    )
    parser.add_argument(
        "--tcg-root",
        default="output/private-generation-prompts/mogger-mon-tcg",
        help="Path to Mogger Mon TCG art folders.",
    )
    parser.add_argument("--resolution", default=DEFAULT_RESOLUTION, help="Fal output resolution. Default: 1K")
    parser.add_argument(
        "--model",
        default="auto",
        help="Fal model override. Default: auto (prefer TCG metadata model, otherwise nano-banana-2/edit).",
    )
    parser.add_argument(
        "--reference-file",
        default="",
        help="Optional exact reference filename inside each TCG dex folder, for example reference-style.jpg or card.png.",
    )
    parser.add_argument(
        "--meta-file",
        default="",
        help="Optional exact metadata filename inside each TCG dex folder, for example meta-2.json.",
    )
    parser.add_argument(
        "--omit-identity-text",
        action="store_true",
        help="Omit Character name and Formula lines from the Fal prompt. Useful when legacy TCG metadata is misleading.",
    )
    args = parser.parse_args()

    api_key = os.environ.get("FAL_KEY") or os.environ.get("FAL_API_KEY")
    if not api_key:
        fail("FAL_KEY or FAL_API_KEY is required.")

    root = Path(__file__).resolve().parent.parent
    output_root = (root / args.output_root).resolve()
    assets_root = (root / args.assets_root).resolve()
    tcg_root = (root / args.tcg_root).resolve()
    ensure_dir(output_root)

    dex_values = parse_list_arg(args.dex)
    views = [part.strip() for part in args.views.split(",") if part.strip()]

    manifest = []
    for dex in dex_values:
        for view in views:
            result = generate_one(
                api_key=api_key,
                dex=dex,
                view=view,
                output_root=output_root,
                assets_root=assets_root,
                tcg_root=tcg_root,
                resolution=args.resolution,
                model_override=args.model or None,
                reference_file=args.reference_file or None,
                meta_file=args.meta_file or None,
                omit_identity_text=args.omit_identity_text,
            )
            manifest.append(result)
            print(f"{view} {dex}: {result['output']}")

    manifest_path = output_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"manifest: {manifest_path}")


if __name__ == "__main__":
    main()
