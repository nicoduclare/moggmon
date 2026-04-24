#!/usr/bin/env python3
"""Generate battle HUD concept edits with Fal Grok using a live Mogger Mon screenshot."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import subprocess
from io import BytesIO
from pathlib import Path
from urllib import request as urllib_request

from PIL import Image

from mogmon_normalizer import pixelify_image


ROOT = Path(__file__).resolve().parent.parent
FAL_HELPER = Path(__file__).with_name("fal_grok_edit.mjs")
MODEL = "xai/grok-imagine-image/edit"


def fail(message: str) -> None:
    raise SystemExit(message)


def file_b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def inline_image_ref(path: Path, label: str) -> dict:
    mime_type, _encoding = mimetypes.guess_type(path.name)
    return {
        "label": label,
        "base64": file_b64(path),
        "mime_type": mime_type or "image/png",
        "file_name": path.name,
    }


def download_file(url: str) -> tuple[bytes, str]:
    req = urllib_request.Request(url, headers={"User-Agent": "mogmon-grok-hud/1.0"})
    with urllib_request.urlopen(req, timeout=300) as response:
        mime_type = response.headers.get_content_type() or "image/jpeg"
        return response.read(), mime_type


def extension_for_mime(mime_type: str) -> str:
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
    }.get(mime_type, ".png")


def maybe_write_pixelified(raw_bytes: bytes, output_path: Path, pixelify_base: int) -> str | None:
    if pixelify_base <= 0:
        return None

    image = Image.open(BytesIO(raw_bytes)).convert("RGBA")
    pixelified = pixelify_image(
        image,
        base_width=max(1, min(pixelify_base, image.width)),
        output_width=image.width,
        output_height=image.height,
    )
    pixel_output_path = output_path.with_suffix(".pixel.png")
    pixelified.save(pixel_output_path)
    return str(pixel_output_path)


def build_prompt(theme: str) -> str:
    return "\n".join(
        [
            "Redesign only the battle HUD and menu chrome in this creature-battler screenshot.",
            f"Visual direction: {theme}.",
            "",
            "Keep these things intact:",
            "- preserve the exact battle scene composition, camera framing, monsters, trainers, background, and text layout",
            "- preserve the same information hierarchy and panel placement: enemy status panel at the top, player status panel at the bottom, command box/menu area, HP bars, EXP bar, and party indicators",
            "- preserve retro handheld JRPG readability and pixel-art compatibility",
            "",
            "Required changes:",
            "- make the HUD clearly inspired by the current one but not the same design",
            "- change border silhouettes, corner cuts, bevel language, panel rhythm, divider shapes, meter caps, texture treatment, and ornament motifs",
            "- remove any franchise-coded motifs such as pokeball-style circles, exact border geometry, or one-to-one matching chrome details",
            "- keep it feeling like a polished production battle HUD, not a mockup pasted on top",
            "",
            "Constraints:",
            "- edit only the HUD, bars, command panels, and battle UI chrome",
            "- do not redraw the creatures, trainers, battlefield, or camera angle",
            "- do not add logos, watermarks, captions, extra menus, or concept callouts",
            "- output one finished screenshot concept",
        ]
    )


def generate_edits(source_image: Path, output_root: Path, prompt: str, variations: int, pixelify_base: int) -> list[dict]:
    if not FAL_HELPER.exists():
        fail(f"Fal helper not found: {FAL_HELPER}")

    payload = {
        "model": MODEL,
        "prompt": prompt,
        "referenceImages": [inline_image_ref(source_image, "battle-hud-reference")],
        "outputFormat": "jpeg",
        "resolution": "1k",
        "numImages": variations,
    }
    try:
        result = subprocess.run(
            ["node", str(FAL_HELPER)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=True,
            timeout=480,
        )
    except subprocess.CalledProcessError as exc:
        error_text = (exc.stderr or exc.stdout or "").strip()
        fail(error_text or f"Fal helper exited with code {exc.returncode}")
    except subprocess.TimeoutExpired as exc:
        fail(f"Fal helper timed out after {exc.timeout} seconds")

    stdout = result.stdout.strip()
    if not stdout:
        fail("Fal helper returned no output")

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        fail(f"Fal helper returned invalid JSON: {stdout[:400]}")

    output_root.mkdir(parents=True, exist_ok=True)
    prompt_path = output_root / "hud-redesign.prompt.txt"
    prompt_path.write_text(prompt + "\n", encoding="utf-8")

    manifest = {
        "model": data.get("model", f"fal:{MODEL}"),
        "revised_prompt": data.get("revised_prompt", ""),
        "source_image": str(source_image),
        "prompt_path": str(prompt_path),
        "images": [],
    }

    for index, image in enumerate(data.get("images", []), start=1):
        if not image.get("url"):
            continue
        raw_bytes, mime_type = download_file(image["url"])
        extension = extension_for_mime(mime_type)
        output_path = output_root / f"hud-redesign-{index}{extension}"
        output_path.write_bytes(raw_bytes)
        pixelified_output = maybe_write_pixelified(raw_bytes, output_path, pixelify_base)
        manifest["images"].append(
            {
                "index": index,
                "url": image["url"],
                "mime_type": mime_type,
                "output": str(output_path),
                "pixelified_output": pixelified_output,
            }
        )

    manifest_path = output_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest["images"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Grok-edited Mogger Mon HUD concepts from a battle screenshot.")
    parser.add_argument(
        "--source-image",
        required=True,
        help="Battle screenshot to edit.",
    )
    parser.add_argument(
        "--output-root",
        default="output/hud-grok-redesign",
        help="Directory for generated HUD concept screenshots.",
    )
    parser.add_argument(
        "--theme",
        default="clean retro monster-battler UI with slate panels, warm ivory insets, teal meter accents, and angular industrial corners",
        help="Short art-direction string for the HUD redesign.",
    )
    parser.add_argument(
        "--variations",
        type=int,
        default=4,
        help="Number of HUD concept variations to request. Default: 4",
    )
    parser.add_argument(
        "--pixelify-base",
        type=int,
        default=0,
        help="Optional nearest-neighbor base width for a pixelified sidecar output. Disabled by default.",
    )
    args = parser.parse_args()

    source_image = (ROOT / args.source_image).resolve() if not Path(args.source_image).is_absolute() else Path(args.source_image)
    if not source_image.exists():
        fail(f"Missing source image: {source_image}")

    output_root = (ROOT / args.output_root).resolve()
    prompt = build_prompt(args.theme)
    images = generate_edits(source_image, output_root, prompt, max(1, args.variations), args.pixelify_base)
    if not images:
        fail("No HUD edits were returned.")
    for image in images:
        print(image["output"])


if __name__ == "__main__":
    main()
