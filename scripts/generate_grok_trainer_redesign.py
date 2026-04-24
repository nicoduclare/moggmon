#!/usr/bin/env python3
"""Generate Grok-edited Mogger Mon trainer atlases and normalize them back into exact runtime frames."""

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
TRAINER_DIR = ROOT / "assets" / "images" / "trainer"
FAL_HELPER = Path(__file__).with_name("fal_grok_edit.mjs")
MODEL = "xai/grok-imagine-image/edit"

TARGETS = {
    "player_m": "front-view lead trainer portrait, original skyline runner with techwear jacket, amber trims, compact headset visor, and grounded street-hero energy",
    "player_f": "front-view lead trainer portrait, original skyline runner with cropped techwear jacket, amber trims, compact headset visor, and grounded street-hero energy",
    "player_m_2": "alternate front-view hero outfit with a sharper hustle-brawler silhouette, layered outerwear, and fast courier attitude",
    "player_f_2": "alternate front-view hero outfit with a sharper hustle-brawler silhouette, layered outerwear, and fast courier attitude",
    "player_m_alternate": "festival-night front-view hero variant with brighter tape accents, utility straps, and scrappy signal-runner swagger",
    "player_f_alternate": "festival-night front-view hero variant with brighter tape accents, utility straps, and scrappy signal-runner swagger",
    "rival_m": "front-view rival trainer portrait, celebrity-coded chaos entrepreneur vibe, tailored streetwear, expensive sneakers, and smug challenger energy",
    "rival_f": "front-view rival trainer portrait, celebrity-coded media mogul vibe, tailored streetwear, expensive jewelry accents, and smug challenger energy",
    "trainer_m_back": "rear battle pose of the hero trainer, original Mogger Mon outfit, same pose framing, modular Cryotank belt, no pokeball motifs",
    "trainer_f_back": "rear battle pose of the hero trainer, original Mogger Mon outfit, same pose framing, modular Cryotank belt, no pokeball motifs",
    "trainer_m_back_pb": "three-frame rear battle atlas: idle, windup, and throw follow-through using a compact glass Cryotank capsule device with cold-blue core lights",
    "trainer_f_back_pb": "three-frame rear battle atlas: idle, windup, and throw follow-through using a compact glass Cryotank capsule device with cold-blue core lights",
}


def fail(message: str) -> None:
    raise SystemExit(message)


def image_ref(path: Path) -> dict:
    image = Image.open(path).convert("RGBA")
    max_dim = max(image.size)
    scale = max(1, min(16, round(1024 / max_dim)))
    if scale > 1:
        image = image.resize((image.width * scale, image.height * scale), Image.NEAREST)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return {
        "base64": base64.b64encode(buffer.getvalue()).decode("ascii"),
        "mime_type": "image/png",
        "file_name": path.with_suffix(".png").name,
    }


def download_file(url: str) -> tuple[bytes, str]:
    req = urllib_request.Request(url, headers={"User-Agent": "mogmon-grok-trainer/1.0"})
    with urllib_request.urlopen(req, timeout=300) as response:
        mime_type = response.headers.get_content_type() or "image/png"
        return response.read(), mime_type


def strip_border_background(image: Image.Image, tolerance: int = 28) -> Image.Image:
    image = image.convert("RGBA")
    if image.getchannel("A").getbbox() is None:
        return image
    if image.getchannel("A").getextrema()[0] < 255:
        return image

    width, height = image.size
    pixels = image.load()
    border_points = set()
    for x in range(width):
        border_points.add((x, 0))
        border_points.add((x, height - 1))
    for y in range(height):
        border_points.add((0, y))
        border_points.add((width - 1, y))

    buckets: dict[tuple[int, int, int], int] = {}
    for x, y in border_points:
        r, g, b, _a = pixels[x, y]
        key = (r // 8, g // 8, b // 8)
        buckets[key] = buckets.get(key, 0) + 1

    dominant = sorted(buckets, key=buckets.get, reverse=True)[:6]
    refs = [(r * 8 + 4, g * 8 + 4, b * 8 + 4) for r, g, b in dominant]

    def matches(rgb: tuple[int, int, int]) -> bool:
        return any(all(abs(a - b) <= tolerance for a, b in zip(rgb, ref)) for ref in refs)

    queue = list(border_points)
    seen = set()
    to_clear = []
    while queue:
        x, y = queue.pop()
        if (x, y) in seen or x < 0 or x >= width or y < 0 or y >= height:
            continue
        seen.add((x, y))
        r, g, b, a = pixels[x, y]
        if a == 0 or not matches((r, g, b)):
            continue
        to_clear.append((x, y))
        queue.extend(((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)))

    cleaned = image.copy()
    cleaned_pixels = cleaned.load()
    for x, y in to_clear:
        cleaned_pixels[x, y] = (0, 0, 0, 0)
    return cleaned


def alpha_bbox(image: Image.Image):
    return image.getchannel("A").getbbox()


def build_prompt(role: str, source_size: tuple[int, int]) -> str:
    return "\n".join(
        [
            "Edit this exact trainer sprite atlas into an original Mogger Mon trainer design.",
            f"Role: {role}.",
            f"Reference atlas size: {source_size[0]}x{source_size[1]}.",
            "",
            "Hard constraints:",
            "- preserve the exact canvas size, occupied frame count, frame boxes, transparent background, and pose coverage from the reference image",
            "- preserve the same handheld-era pixel art readability and same overall silhouette scale",
            "- keep each occupied frame filled by one complete human trainer, never fragments or cropped limbs",
            "- preserve the same gesture and animation rhythm as the reference image",
            "- use a grounded urban-future look: taped techwear, utility straps, headset pieces, sneakers, layered jackets, and Cryotank accessories",
            "- if the atlas includes a throw or summon action, replace any pokeball-like prop with a compact glass Cryotank capsule device",
            "- faces and outfits should feel original and distinct, inspired by internet-age hustler / mogul / runner archetypes without resembling any specific real person",
            "- output exactly one atlas; do not tile, repeat, collage, or show multiple alternate versions in one image",
            "- no logos, no text, no background scene, no extra particles, no franchise-coded costume motifs",
            "- output only the finished trainer sprite atlas on transparency",
        ]
    )


def run_edit(source_image: Path, prompt: str) -> dict:
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "referenceImages": [image_ref(source_image)],
        "outputFormat": "jpeg",
        "resolution": "1k",
        "numImages": 1,
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
    return json.loads(stdout)


def load_texture_frames(json_path: Path) -> list[dict]:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    return data["textures"][0]["frames"]


def trainer_pixel_base(output_width: int) -> int:
    # Trainer frames are already tiny; keep the downscale gentle so we preserve
    # silhouette pixels instead of re-crushing them before the final upscale.
    if output_width <= 0:
        return 1
    return max(1, min(output_width, max(12, int(round(output_width * 0.9)))))


def normalize_atlas(source_png: Path, source_json: Path, generated_bytes: bytes) -> tuple[Image.Image, Image.Image]:
    source = Image.open(source_png).convert("RGBA")
    frames = load_texture_frames(source_json)
    generated = Image.open(BytesIO(generated_bytes)).convert("RGBA").resize(source.size, Image.NEAREST)

    normalized = Image.new("RGBA", source.size, (0, 0, 0, 0))
    single_frame_mode = len(frames) == 1
    whole_generated = strip_border_background(generated)
    for frame in frames:
        rect = frame["frame"]
        frame_box = (
            rect["x"],
            rect["y"],
            rect["x"] + rect["w"],
            rect["y"] + rect["h"],
        )
        source_frame = source.crop(frame_box)
        target_bbox = alpha_bbox(source_frame) or (0, 0, rect["w"], rect["h"])

        if single_frame_mode:
            cleaned = whole_generated
        else:
            raw_frame = generated.crop(frame_box)
            cleaned = strip_border_background(raw_frame)
        content_bbox = alpha_bbox(cleaned)
        if content_bbox is None:
            cleaned = source_frame
            content_bbox = alpha_bbox(cleaned)
        if content_bbox is None:
            continue

        content = cleaned.crop(content_bbox)
        max_width = max(1, target_bbox[2] - target_bbox[0])
        max_height = max(1, target_bbox[3] - target_bbox[1])
        scale = min(max_width / content.width, max_height / content.height)
        scale = max(scale, 0.05)
        out_w = max(1, int(round(content.width * scale)))
        out_h = max(1, int(round(content.height * scale)))
        pixelified = pixelify_image(
            content,
            base_width=trainer_pixel_base(out_w),
            output_width=out_w,
            output_height=out_h,
        )

        frame_canvas = Image.new("RGBA", (rect["w"], rect["h"]), (0, 0, 0, 0))
        paste_x = target_bbox[0] + max(0, (max_width - out_w) // 2)
        paste_y = target_bbox[1] + max(0, (max_height - out_h) // 2)
        frame_canvas.alpha_composite(pixelified, (paste_x, paste_y))
        normalized.alpha_composite(frame_canvas, (rect["x"], rect["y"]))

    return generated, normalized


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Grok-edited Mogger Mon trainer atlases.")
    parser.add_argument(
        "--targets",
        default="player_m,player_f,player_m_2,player_f_2,player_m_alternate,player_f_alternate,rival_m,rival_f,trainer_m_back,trainer_f_back,trainer_m_back_pb,trainer_f_back_pb",
        help="Comma-separated trainer atlas basenames to regenerate.",
    )
    parser.add_argument(
        "--output-root",
        default="output/trainer-grok-redesign",
        help="Directory to store raw Grok outputs and manifests.",
    )
    args = parser.parse_args()

    output_root = (ROOT / args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    manifest = []

    for target in [name.strip() for name in args.targets.split(",") if name.strip()]:
        if target not in TARGETS:
            fail(f"Unsupported target: {target}")

        source_png = TRAINER_DIR / f"{target}.png"
        source_json = TRAINER_DIR / f"{target}.json"
        if not source_png.exists() or not source_json.exists():
            fail(f"Missing trainer atlas source for {target}")

        source_image = Image.open(source_png)
        prompt = build_prompt(TARGETS[target], source_image.size)
        response = run_edit(source_png, prompt)
        images = response.get("images", [])
        if not images or not images[0].get("url"):
            fail(f"No image returned for {target}")

        raw_bytes, mime_type = download_file(images[0]["url"])
        generated, normalized = normalize_atlas(source_png, source_json, raw_bytes)

        target_output = output_root / target
        target_output.mkdir(parents=True, exist_ok=True)
        raw_path = target_output / "raw.png"
        raw_path.write_bytes(raw_bytes)
        generated_path = target_output / "generated-resized.png"
        generated.save(generated_path)
        normalized_path = target_output / "normalized.png"
        normalized.save(normalized_path)

        normalized.save(source_png)

        prompt_path = target_output / "prompt.txt"
        prompt_path.write_text(prompt + "\n", encoding="utf-8")
        manifest.append(
            {
                "target": target,
                "model": response.get("model", f"fal:{MODEL}"),
                "mime_type": mime_type,
                "source_png": str(source_png),
                "source_json": str(source_json),
                "raw_output": str(raw_path),
                "resized_output": str(generated_path),
                "normalized_output": str(normalized_path),
                "prompt_path": str(prompt_path),
            }
        )
        print(source_png)

    (output_root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
