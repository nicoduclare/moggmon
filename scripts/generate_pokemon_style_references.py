#!/usr/bin/env python3

import argparse
import base64
import json
import mimetypes
import os
import shutil
import sys
import time
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request


MODEL = "gemini-3.1-flash-image-preview"
TIMEOUT_SECONDS = 180
VALID_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


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
                inline_data = part["inlineData"]
                images.append(
                    {
                        "bytes": base64.b64decode(inline_data["data"]),
                        "mime_type": inline_data.get("mimeType", "image/png"),
                    }
                )
            if "text" in part:
                texts.append(part["text"])

    return images, "\n".join(texts)


def file_b64(path):
    return base64.b64encode(Path(path).read_bytes()).decode()


def inline_image_ref(path, label):
    mime_type, _encoding = mimetypes.guess_type(path)
    return {
        "label": label,
        "base64": file_b64(path),
        "mime_type": mime_type or "image/png",
    }


def extension_for_mime(mime_type):
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
    }.get(mime_type, ".png")


def list_target_images(source_dir, slugs=None, limit=None):
    slug_filter = set(slugs or [])
    targets = []
    for path in sorted(source_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in VALID_IMAGE_SUFFIXES:
            continue
        if slug_filter and path.stem not in slug_filter:
            continue
        targets.append(path)
        if limit and len(targets) >= limit:
            break
    return targets


def build_prompt(target_slug, background_note, action_note, devoxelize):
    target_name = target_slug.replace("-", " ")
    devoxelize_lines = ""
    if devoxelize:
        devoxelize_lines = """- if IMAGE 3 looks voxel, blocky, cubic, or toy-like, do NOT keep the voxel rendering
- reinterpret any voxel or block-built forms as a hand-drawn illustrated creature while preserving the same character identity and proportions
"""
    return f"""I gave you three images.

IMAGE 1:
The original full-art brainrot reference for a solved example character.

IMAGE 2:
The Pokemon-style full-body restyle of IMAGE 1.

IMAGE 3:
The actual target character that must be preserved.

Task:
Create a single full-body reference illustration of IMAGE 3 in the style of Pokemon, using IMAGE 1 and IMAGE 2 as the before/after style lesson.

Target character:
{target_name}

Strict requirements:
- IMAGE 1 and IMAGE 2 are the style lesson only
- IMAGE 3 is the actual subject and must remain the same character
- keep the exact third character's identity, face, silhouette, costume pieces, props, colors, and signature weird details
- do not turn IMAGE 3 into IMAGE 1
- make IMAGE 3 look like a polished full-body Pokemon-style monster reference
- full body visible with breathing room around the entire silhouette
- show the character in action, with a dynamic readable pose that implies motion, power, or personality
- use a varied illustrated background environment that suits the character instead of a blank studio backdrop
- keep the background supportive and readable, not cluttered
- background direction: {background_note}
- action direction: {action_note}
- clean readable full-body composition, usually front, three-quarter, or side action angle
- this should read as a finished drawing or painted illustration, not a toy render
{devoxelize_lines}- one single character only unless IMAGE 3 contains inseparable attached parts
- no card frame, no border, no UI, no text, no logos, no watermark
- not pixel art
- not a sprite sheet
- not a collage

Important phrasing:
Keep the exact third character, but make it Pokemon style like IMAGE 1 and IMAGE 2. Use IMAGE 1 and IMAGE 2 as the style lesson, preserve IMAGE 3 as the subject, put the character in action, give it a varied background, and convert any voxel look into a drawn illustration.
"""


def generate_one(
    api_key,
    style_origin_image,
    style_reference_image,
    target_image,
    out_dir,
    overwrite,
    background_note,
    action_note,
    devoxelize,
):
    slug = target_image.stem
    target_out_dir = out_dir / slug
    target_out_dir.mkdir(parents=True, exist_ok=True)

    target_copy_path = target_out_dir / f"reference{target_image.suffix.lower()}"
    style_origin_copy_path = target_out_dir / f"style-origin{style_origin_image.suffix.lower()}"
    style_reference_copy_path = target_out_dir / f"reference-style{style_reference_image.suffix.lower()}"

    if overwrite or not target_copy_path.exists():
        shutil.copy2(target_image, target_copy_path)
    if overwrite or not style_origin_copy_path.exists():
        shutil.copy2(style_origin_image, style_origin_copy_path)
    if overwrite or not style_reference_copy_path.exists():
        shutil.copy2(style_reference_image, style_reference_copy_path)

    existing = next(target_out_dir.glob("pokemon-style.*"), None)
    if existing and not overwrite:
        print(f"Skipping {slug}: {existing.name} already exists")
        return

    prompt = build_prompt(slug, background_note, action_note, devoxelize)
    (target_out_dir / "prompt.txt").write_text(prompt, encoding="utf-8")

    refs = [
        inline_image_ref(
            style_origin_copy_path,
            "IMAGE 1 — ORIGINAL BRAINROT REFERENCE FOR THE SOLVED STYLE EXAMPLE.",
        ),
        inline_image_ref(
            style_reference_copy_path,
            "IMAGE 2 — POKEMON-STYLE RESTYLE OF IMAGE 1. Match this rendering style.",
        ),
        inline_image_ref(
            target_copy_path,
            f'IMAGE 3 — TARGET CHARACTER REFERENCE. Preserve this exact character identity for "{slug}".',
        ),
    ]

    images, text = gemini_generate(api_key, prompt, refs)
    if not images:
        raise RuntimeError(f"No image returned for {slug}. Gemini text: {text[:400]}")

    first_image = images[0]
    output_ext = extension_for_mime(first_image["mime_type"])
    output_path = target_out_dir / f"pokemon-style{output_ext}"
    output_path.write_bytes(first_image["bytes"])

    metadata = {
        "model": MODEL,
        "slug": slug,
        "styleOriginImage": str(style_origin_image),
        "savedStyleOriginImage": str(style_origin_copy_path),
        "styleReferenceImage": str(style_reference_image),
        "savedStyleReferenceImage": str(style_reference_copy_path),
        "targetReferenceImage": str(target_image),
        "savedTargetReferenceImage": str(target_copy_path),
        "outputImage": str(output_path),
        "outputMimeType": first_image["mime_type"],
        "backgroundNote": background_note,
        "actionNote": action_note,
        "devoxelize": devoxelize,
    }
    (target_out_dir / "meta.json").write_text(f"{json.dumps(metadata, indent=2)}\n", encoding="utf-8")

    if text:
        (target_out_dir / "response.txt").write_text(text, encoding="utf-8")

    print(f"Saved {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert full-art brainrot references into Pokemon-style full-body references using a solved before/after exemplar pair."
    )
    parser.add_argument(
        "--source-dir",
        default="output/private-generation-prompts/mogger-mon-tcg/references/original",
        help="Directory containing the source brainrot references.",
    )
    parser.add_argument(
        "--out-dir",
        default="output/private-generation-prompts/mogger-mon-tcg/references/pokemon-style",
        help="Directory to write Pokemon-style reference outputs into.",
    )
    parser.add_argument(
        "--style-origin-image",
        default="output/private-generation-prompts/mogger-mon-tcg/references/style-lesson/reference.webp",
        help="Original full-art brainrot image for the solved style example.",
    )
    parser.add_argument(
        "--style-reference-image",
        default="output/private-generation-prompts/mogger-mon-tcg/references/style-lesson/reference-style.jpg",
        help="Pokemon-style version of the solved style example.",
    )
    parser.add_argument(
        "--slug",
        action="append",
        dest="slugs",
        default=[],
        help="Specific image slug to generate. Repeat to generate multiple.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional maximum number of target references to generate.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing outputs.",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.0,
        help="Optional delay between generations for batch runs.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Keep going when one target generation fails.",
    )
    parser.add_argument(
        "--background-note",
        default="Use a different illustrated environment for each character, such as forest clearings, stormy skies, temple ruins, rooftops, lava fields, beaches, moonlit streets, underwater scenes, or surreal dream spaces that fit the creature.",
        help="Direction for background variety.",
    )
    parser.add_argument(
        "--action-note",
        default="Show the character doing something active: lunging, leaping, charging, splashing, casting, roaring, drifting, striking, spinning, or otherwise expressing motion and attitude.",
        help="Direction for action posing.",
    )
    parser.add_argument(
        "--no-voxel",
        action="store_true",
        help="Convert voxel or blocky source characters into a drawn illustration style instead of preserving voxel rendering.",
    )
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_KEY")
    if not api_key:
        raise SystemExit("GEMINI_KEY is required.")

    source_dir = Path(args.source_dir)
    out_dir = Path(args.out_dir)
    style_origin_image = Path(args.style_origin_image)
    style_reference_image = Path(args.style_reference_image)

    if not source_dir.exists():
        raise SystemExit(f"Source directory not found: {source_dir}")
    if not style_origin_image.exists():
        raise SystemExit(f"Style origin image not found: {style_origin_image}")
    if not style_reference_image.exists():
        raise SystemExit(f"Style reference image not found: {style_reference_image}")

    out_dir.mkdir(parents=True, exist_ok=True)

    targets = list_target_images(source_dir, slugs=args.slugs, limit=args.limit or None)
    if not targets:
        raise SystemExit("No target reference images found.")

    failures = []
    for index, target_image in enumerate(targets):
        print(f"[{index + 1}/{len(targets)}] {target_image.stem}")
        try:
            generate_one(
                api_key=api_key,
                style_origin_image=style_origin_image,
                style_reference_image=style_reference_image,
                target_image=target_image,
                out_dir=out_dir,
                overwrite=args.overwrite,
                background_note=args.background_note,
                action_note=args.action_note,
                devoxelize=args.no_voxel,
            )
        except Exception as exc:
            failures.append({"slug": target_image.stem, "error": str(exc)})
            print(f"Failed {target_image.stem}: {exc}", file=sys.stderr)
            if not args.continue_on_error:
                raise
        if args.sleep_seconds and index < len(targets) - 1:
            time.sleep(args.sleep_seconds)

    if failures:
        failure_path = out_dir / "failures.json"
        failure_path.write_text(f"{json.dumps(failures, indent=2)}\n", encoding="utf-8")
        print(f"Wrote failures to {failure_path}")


if __name__ == "__main__":
    main()
