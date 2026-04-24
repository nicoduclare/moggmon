#!/usr/bin/env python3

import argparse
import base64
import json
import mimetypes
import os
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

from PIL import Image


MODEL = "gemini-3.1-flash-image-preview"
TIMEOUT_SECONDS = 180


def remove_background(img_path):
    img = Image.open(img_path).convert("RGBA")
    w, h = img.size
    pixels = img.load()
    tolerance = 30

    def color_match(c1, c2):
        return all(abs(a - b) <= tolerance for a, b in zip(c1[:3], c2[:3]))

    border_points = set()
    for x in range(w):
        border_points.add((x, 0))
        border_points.add((x, h - 1))
    for y in range(h):
        border_points.add((0, y))
        border_points.add((w - 1, y))

    border_colors = {}
    for x, y in border_points:
        c = pixels[x, y][:3]
        key = (c[0] // 8, c[1] // 8, c[2] // 8)
        border_colors[key] = border_colors.get(key, 0) + 1
    top_keys = sorted(border_colors, key=border_colors.get, reverse=True)[:6]
    ref_colors = [(k[0] * 8 + 4, k[1] * 8 + 4, k[2] * 8 + 4) for k in top_keys]

    def is_bg_color(rgb):
        return any(color_match(rgb, ref) for ref in ref_colors)

    queue = list(border_points)
    visited = set()
    to_clear = []
    while queue:
        x, y = queue.pop()
        if (x, y) in visited or x < 0 or x >= w or y < 0 or y >= h:
            continue
        visited.add((x, y))

        r, g, b, _a = pixels[x, y]
        if not is_bg_color((r, g, b)):
            continue

        to_clear.append((x, y))
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            queue.append((x + dx, y + dy))

    for x, y in to_clear:
        pixels[x, y] = (0, 0, 0, 0)

    img.save(img_path)


def gemini_generate(api_key, prompt, reference_images=None):
    api_url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}"
        f":generateContent?key={api_key}"
    )
    parts = []
    for ref in reference_images or []:
        parts.append({"text": f"[Reference: {ref['label']}]"})
        parts.append({"inlineData": {"mimeType": ref["mime_type"], "data": ref["base64"]}})
    parts.append({"text": prompt})

    body = json.dumps(
        {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "responseModalities": ["TEXT", "IMAGE"],
                "temperature": 1.0,
            },
        }
    ).encode()

    req = urllib_request.Request(
        api_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib_request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read())
    except urllib_error.HTTPError as exc:
        raise RuntimeError(f"Gemini API {exc.code}: {exc.read().decode()[:600]}")

    images = []
    texts = []
    for cand in data.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            if "inlineData" in part:
                images.append(base64.b64decode(part["inlineData"]["data"]))
            if "text" in part:
                texts.append(part["text"])
    return images, "\n".join(texts)


def png_b64(path):
    return base64.b64encode(Path(path).read_bytes()).decode()


def inline_image_ref(path, label):
    mime_type, _encoding = mimetypes.guess_type(path)
    return {
        "label": label,
        "base64": png_b64(path),
        "mime_type": mime_type or "image/png",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Generate one Gemini sprite test with a three-step flow: real reference -> pixel concept -> sprite sheet."
    )
    parser.add_argument("--template", required=True, help="Absolute path to the reference sprite sheet template.")
    parser.add_argument("--out-dir", required=True, help="Directory to write concept/sprite outputs.")
    parser.add_argument("--name", required=True, help="Character name.")
    parser.add_argument("--formula", required=True, help="Short formula describing the trait fusion.")
    parser.add_argument("--description", required=True, help="Full character description.")
    parser.add_argument(
        "--stage-note",
        default="",
        help="Optional evolution-stage direction, e.g. base/cute or final/more menacing.",
    )
    parser.add_argument(
        "--real-reference-image",
        help="Optional absolute path to a non-sprite character reference image. If set, first convert it into a 2D pixel concept.",
    )
    parser.add_argument(
        "--pixel-concept-image",
        help="Optional absolute path to an existing 2D pixel concept image. If set, skip the pixel concept generation step.",
    )
    parser.add_argument(
        "--concept-image",
        help="Deprecated alias for --real-reference-image.",
    )
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_KEY")
    if not api_key:
        raise SystemExit("GEMINI_KEY is required.")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    reference_path = out_dir / "reference.png"
    pixel_concept_path = out_dir / "pixel-concept.png"
    sprite_path = out_dir / "front-4.png"
    real_reference_input = args.real_reference_image or args.concept_image

    if args.pixel_concept_image:
        source_pixel_concept_path = Path(args.pixel_concept_image)
        if not source_pixel_concept_path.exists():
            raise SystemExit(f"Pixel concept image not found: {source_pixel_concept_path}")
        Image.open(source_pixel_concept_path).convert("RGBA").save(pixel_concept_path)
    elif real_reference_input:
        source_reference_path = Path(real_reference_input)
        if not source_reference_path.exists():
            raise SystemExit(f"Reference image not found: {source_reference_path}")
        Image.open(source_reference_path).convert("RGBA").save(reference_path)

        concept_refs = [
            inline_image_ref(
                reference_path,
                f'IMAGE 1 — REAL CHARACTER REFERENCE. This is the real/source brainrot reference for "{args.name}".',
            ),
        ]

        concept_prompt = f"""I gave you one source character image.

Task:
Create one single full-body 2D pixel-art monster concept inspired by IMAGE 1.

Character name: {args.name}
Formula: {args.formula}
Description:
{args.description}
Evolution stage direction:
{args.stage_note or "Keep it balanced and game-ready."}

Strict requirements:
- output one single character only, not a sprite sheet
- transparent background
- pixel-art style suitable for a monster battler
- front-facing three-quarter pose
- full body visible
- compact silhouette that can later be adapted into battle sprites
- preserve the recognizable identity, face, and major traits from IMAGE 1
- do not copy the exact render style of IMAGE 1 if it is not already pixel art
- no scenery, text, props, UI, or extra characters
"""

        concept_images, concept_text = gemini_generate(api_key, concept_prompt, concept_refs)
        if not concept_images:
            raise RuntimeError(f"No pixel concept image returned. Gemini text: {concept_text[:400]}")
        pixel_concept_path.write_bytes(concept_images[0])
        remove_background(pixel_concept_path)
    else:
        concept_prompt = f"""Draw one full-body character design for a creature called "{args.name}".

Formula: {args.formula}

Description:
{args.description}

Requirements:
- one single character only, not a sprite sheet
- pixel-art creature concept for a monster battler
- transparent background
- full body visible
- cute but mischievous
- readable silhouette
- front-facing three-quarter pose
- keep it compact and game-ready
- evolution direction: {args.stage_note or "none"}
"""

        concept_images, concept_text = gemini_generate(api_key, concept_prompt)
        if not concept_images:
            raise RuntimeError(f"No pixel concept image returned. Gemini text: {concept_text[:400]}")
        pixel_concept_path.write_bytes(concept_images[0])
        remove_background(pixel_concept_path)

    refs = [
        inline_image_ref(
            args.template,
            "IMAGE 1 — SPRITE SHEET TEMPLATE. Match this exact sheet format, pose layout, spacing, and pixel-art style.",
        ),
        inline_image_ref(
            pixel_concept_path,
            f"IMAGE 2 — PIXEL CONCEPT REFERENCE. This is the 2D pixel concept for {args.name}. Redraw IMAGE 1 using this exact character design.",
        ),
    ]

    sprite_prompt = f"""I gave you two images.

IMAGE 1 is the exact sprite sheet template.
IMAGE 2 is the exact character to put into that sprite sheet.

Task:
Redraw IMAGE 1 exactly as a paint-over replacement, but replace the original creature with IMAGE 2.

Character name: {args.name}
Formula: {args.formula}
Description:
{args.description}
Evolution stage direction:
{args.stage_note or "Keep the exact same core character shape and attitude as the reference."}

Strict requirements:
- keep the exact same sprite sheet grid layout, frame count, frame size, and spacing as IMAGE 1
- keep the same transparent background
- keep the same pixel art style and same camera framing
- keep the same per-frame poses, body tilt, silhouette footprint, and animation rhythm
- do not invent new poses
- do not add effects, props, text, or background
- keep every frame fully inside its own slot
- IMAGE 2 is the pixel concept design to use in every frame
- apply the evolution stage direction while keeping IMAGE 2 clearly recognizable as the same brainrot character
- output only the finished sprite sheet
"""

    sprite_images, sprite_text = gemini_generate(api_key, sprite_prompt, refs)
    if not sprite_images:
        raise RuntimeError(f"No sprite sheet image returned. Gemini text: {sprite_text[:400]}")
    sprite_path.write_bytes(sprite_images[0])
    remove_background(sprite_path)

    if real_reference_input:
        print(f"reference={reference_path}")
    print(f"pixel_concept={pixel_concept_path}")
    print(f"sprite={sprite_path}")


if __name__ == "__main__":
    main()
