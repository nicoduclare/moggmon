#!/usr/bin/env python3

import argparse
import base64
import json
import mimetypes
import os
import shutil
import subprocess
import time
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request


MODEL = "gemini-3.1-flash-image-preview"
FAL_MODEL = "xai/grok-imagine-image/edit"
DEFAULT_TRANSPORT = "mpp"
TIMEOUT_SECONDS = 180
MAX_GENERATION_ATTEMPTS = 3
BASE_RETRY_DELAY_SECONDS = 6
DOWNLOAD_RETRY_ATTEMPTS = 3
MPP_HELPER = Path(__file__).with_name("gemini_mpp_generate.mjs")
FAL_HELPER = Path(__file__).with_name("fal_grok_edit.mjs")


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


def gemini_mpp_generate(prompt, reference_images=None):
    if not MPP_HELPER.exists():
        raise RuntimeError(f"Gemini MPP helper not found: {MPP_HELPER}")

    payload = {
        "model": MODEL,
        "prompt": prompt,
        "referenceImages": reference_images or [],
    }
    try:
        result = subprocess.run(
            ["node", str(MPP_HELPER)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=True,
            timeout=TIMEOUT_SECONDS + 60,
        )
    except subprocess.CalledProcessError as exc:
        error_text = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(error_text or f"Gemini MPP helper exited with code {exc.returncode}")
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Gemini MPP request timed out after {exc.timeout} seconds")

    stdout = result.stdout.strip()
    if not stdout:
        raise RuntimeError("Gemini MPP helper returned no output")

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Gemini MPP helper returned invalid JSON: {stdout[:400]}") from exc

    images = [
        {
            "bytes": base64.b64decode(image["base64"]),
            "mime_type": image.get("mime_type", "image/png"),
        }
        for image in data.get("images", [])
    ]
    return images, data.get("text", ""), data.get("model", f"mpp:{MODEL}")


def fal_edit_generate(prompt, reference_images=None):
    if not FAL_HELPER.exists():
        raise RuntimeError(f"FAL helper not found: {FAL_HELPER}")

    payload = {
        "model": FAL_MODEL,
        "prompt": prompt,
        "referenceImages": reference_images or [],
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
            timeout=TIMEOUT_SECONDS + 120,
        )
    except subprocess.CalledProcessError as exc:
        error_text = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(error_text or f"FAL helper exited with code {exc.returncode}")
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"FAL request timed out after {exc.timeout} seconds")

    stdout = result.stdout.strip()
    if not stdout:
        raise RuntimeError("FAL helper returned no output")

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"FAL helper returned invalid JSON: {stdout[:400]}") from exc

    return data.get("images", []), data.get("revised_prompt", ""), data.get("model", f"fal:{FAL_MODEL}")


def file_b64(path):
    return base64.b64encode(Path(path).read_bytes()).decode()


def inline_image_ref(path, label):
    mime_type, _encoding = mimetypes.guess_type(path)
    return {
        "label": label,
        "base64": file_b64(path),
        "mime_type": mime_type or "image/png",
        "file_name": Path(path).name,
    }


def extension_for_mime(mime_type):
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
    }.get(mime_type, ".png")


def art_variant_suffix(art_name):
    if art_name == "full-art":
        return ""
    if art_name.startswith("full-art"):
        return art_name[len("full-art"):]
    return f"-{art_name}"


def sidecar_path(out_dir, base_name, extension, art_name):
    suffix = art_variant_suffix(art_name)
    filename = f"{base_name}{suffix}{extension}" if suffix else f"{base_name}{extension}"
    return out_dir / filename


def download_file(url):
    req = urllib_request.Request(url, headers={"User-Agent": "mogmon-fal-client/1.0"})
    last_error = None
    for attempt in range(1, DOWNLOAD_RETRY_ATTEMPTS + 1):
        try:
            with urllib_request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
                mime_type = resp.headers.get_content_type() or "image/jpeg"
                return resp.read(), mime_type
        except TimeoutError as exc:
            last_error = exc
        except urllib_error.URLError as exc:
            last_error = exc
        if attempt < DOWNLOAD_RETRY_ATTEMPTS:
            time.sleep(BASE_RETRY_DELAY_SECONDS * attempt)
    raise RuntimeError(f"FAL download failed after {DOWNLOAD_RETRY_ATTEMPTS} attempts: {last_error}")


def stage_guardrails(stage_label):
    mapping = {
        "base": (
            "This is the family's first readable form. Keep it simple, compact, and intentionally limited. "
            "Withhold later-stage payoff traits, extra mass, ultimate weapons, extra appendages, and any final-form grandeur."
        ),
        "mid": (
            "This is the bridge form in the family, not the climax. It must stay visibly unfinished relative to the final form. "
            "Aim for a creature that feels around two-thirds evolved rather than almost complete. Add one meaningful upgrade over the base form, "
            "but hold back the family's full payoff silhouette, final ornament set, apex weapon scale, legendary aura, extra anatomy, and boss-level scene dominance. "
            "When in doubt, under-evolve the middle stage rather than letting it drift too close to the final."
        ),
        "final": (
            "This is the only stage allowed to feel fully complete, apex-level, and like the family's total payoff. "
            "Use the full silhouette complexity, ornament, final anatomy, and strongest scene presence here."
        ),
        "branch-final": (
            "This is a completed branch ending. It should feel fully realized and decisive for its route, with strong end-stage presence."
        ),
    }
    return mapping.get(stage_label, "Keep the form faithful to its intended evolution stage.")


def is_retryable_generation_error(exc):
    message = str(exc)
    lower_message = message.lower()
    if "gemini api 429" in lower_message or "gemini mpp 429" in lower_message or "fal 429" in lower_message:
        # Retry short-lived rate limits, but do not loop on explicit daily quota exhaustion.
        if "generate_requests_per_model_per_day" in lower_message:
            return False
        if "retry in " in lower_message:
            return False
        if "credits are depleted" in lower_message:
            return False
        if "manage your project and billing" in lower_message:
            return False
        return True
    return (
        "No TCG image returned" in message
        or "Gemini API 500" in message
        or "Gemini API 503" in message
        or "Gemini MPP 500" in message
        or "Gemini MPP 503" in message
        or "FAL 500" in message
        or "FAL 503" in message
    )


def main():
    parser = argparse.ArgumentParser(
        description="Generate one full-art Pokemon-style TCG illustration from the updated full-art brainrot reference image."
    )
    parser.add_argument("--out-dir", required=True, help="Directory to write the generated TCG art.")
    parser.add_argument("--name", required=True, help="Character name.")
    parser.add_argument("--formula", required=True, help="Short formula describing the trait fusion.")
    parser.add_argument("--description", required=True, help="Full character description.")
    parser.add_argument(
        "--flavor-text",
        default="",
        help="Optional flavor/mood line to influence the scene and atmosphere.",
    )
    parser.add_argument(
        "--stage-note",
        default="",
        help="Optional evolution-stage direction, e.g. base/cute or final/menacing.",
    )
    parser.add_argument(
        "--stage-label",
        default="",
        help="Optional normalized stage label, e.g. base, mid, final, branch-final.",
    )
    parser.add_argument(
        "--family-contrast-note",
        default="",
        help="Optional family-progression note contrasting this form with the rest of its line.",
    )
    parser.add_argument(
        "--reference-image",
        default="",
        help="Optional absolute path to the updated full-art brainrot reference image.",
    )
    parser.add_argument(
        "--style-reference-image",
        default="",
        help="Optional Pokemon-style reference image to use as the rendering/style target.",
    )
    parser.add_argument(
        "--camera-note",
        default="Zoom out and pull the camera back enough to show the whole creature with breathing room around it.",
        help="Optional composition/camera note.",
    )
    parser.add_argument(
        "--transport",
        choices=["mpp", "direct", "fal"],
        default=os.environ.get("MOGMON_GEMINI_TRANSPORT", DEFAULT_TRANSPORT),
        help="Image generation transport. Defaults to MPP.",
    )
    parser.add_argument(
        "--art-name",
        default="full-art",
        help="Output art stem, e.g. full-art or full-art-2.",
    )
    parser.add_argument(
        "--render-mode",
        default="",
        help="Optional batch render-mode marker to persist in metadata.",
    )
    args = parser.parse_args()
    model_used = MODEL
    api_key = None
    if args.transport == "direct":
        api_key = os.environ.get("GEMINI_KEY")
        if not api_key:
            raise SystemExit("GEMINI_KEY is required for --transport direct.")

    reference_image = Path(args.reference_image) if args.reference_image else None
    if reference_image and not reference_image.exists():
        raise SystemExit(f"Reference image not found: {reference_image}")
    style_reference_image = Path(args.style_reference_image) if args.style_reference_image else None
    if style_reference_image and not style_reference_image.exists():
        raise SystemExit(f"Style reference image not found: {style_reference_image}")
    if not reference_image and not style_reference_image:
        raise SystemExit("Provide at least one of --reference-image or --style-reference-image.")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    reference_copy_path = None
    if reference_image:
        reference_copy_path = out_dir / f"reference{reference_image.suffix.lower()}"
        shutil.copy2(reference_image, reference_copy_path)
    style_reference_copy_path = None
    if style_reference_image:
        style_reference_copy_path = out_dir / f"reference-style{style_reference_image.suffix.lower()}"
        shutil.copy2(style_reference_image, style_reference_copy_path)

    if reference_copy_path and style_reference_copy_path:
        reference_intro = "I gave you two reference images."
        task_text = "Edit IMAGE 1 into a brand-new creature illustration."
        source_requirements = """- use IMAGE 1 as the direct full-art source reference
- treat IMAGE 1 as the main visual truth for silhouette, face, costume, and signature details
- preserve the recognizable face, identity, and iconic traits from IMAGE 1
- create a NEW character based on the description above, not a literal copy of IMAGE 1
- if IMAGE 2 is present, use IMAGE 2 as the style target for rendering, anatomy polish, and Pokemon art direction
- IMAGE 2 is style guidance only; do not copy any specific anatomy from IMAGE 2 if it conflicts with the written stage description"""
        important_phrasing = "Edit the new full-art reference image, create a new character with this description, and make it zoomed out and panned back in the style of Pokemon full art. Use IMAGE 2 as the style example."
    elif reference_copy_path:
        reference_intro = "I gave you one updated full-art source character image."
        task_text = "Edit IMAGE 1 into a brand-new creature illustration."
        source_requirements = """- use IMAGE 1 as the direct full-art source reference
- treat IMAGE 1 as the main visual truth for silhouette, face, costume, and signature details
- preserve the recognizable face, identity, and iconic traits from IMAGE 1
- create a NEW character based on the description above, not a literal copy of IMAGE 1"""
        important_phrasing = "Edit the new full-art reference image, create a new character with this description, and make it zoomed out and panned back in the style of Pokemon full art."
    else:
        reference_intro = "I gave you one Pokemon-style reference image."
        task_text = "Create a brand-new creature illustration from the written design description."
        source_requirements = """- there is no source character image for anatomy; build the creature directly from the written description
- use IMAGE 1 only as Pokemon-style rendering guidance, finish level, and composition quality reference
- do not copy specific anatomy or identity from IMAGE 1
- create a NEW creature based on the description above"""
        important_phrasing = "Create a new character from this description and make it zoomed out and panned back in the style of Pokemon full art, using IMAGE 1 only as the style example."

    prompt = f"""{reference_intro}

Task:
{task_text}

Character name: {args.name}
Formula: {args.formula}

Description:
{args.description}

Flavor mood:
{args.flavor_text or "Let the scene feel like premium creature key art with strong personality."}

Evolution stage direction:
{args.stage_note or "Keep it balanced and card-art ready."}

Stage-specific lock:
{stage_guardrails(args.stage_label)}

Family progression lock:
{args.family_contrast_note or "Keep this form visually distinct from the other stages in its family."}

Composition note:
{args.camera_note}

Strict requirements:
{source_requirements}
- the written description outranks the reference images for evolution-stage anatomy
- if a source character image exists and the description removes or withholds later-stage traits from it, visibly remove them in the new creature instead of preserving the full reference body
- do not add missing limbs, heads, ornaments, armor, or full-form mass that belong to a later evolution stage
- if this is the middle member of a three-stage family, keep one major final-stage payoff trait visibly absent, reduced, or only half-formed
- if the description specifies a single-leg body plan, show only one true lower limb and one foot total; any off-side roots, robes, or foliage must hang free and must not touch the ground like a second support
- make it read like premium full-art Pokemon card illustration
- polished, painterly, colorful, dynamic monster art
- give the creature a distinctive action pose instead of a static neutral stance
- use a specific environmental background that suits the creature, and avoid generic repeated backdrops
- zoom out / pan back enough to show the whole character with some surrounding environment
- the subject should feel centered, readable, and ready for a TCG art crop
- one single finished illustration only
- not pixel art
- not a sprite sheet
- absolutely no visible text in the artwork itself
- no letters, words, numbers, symbols, runes, glyphs, signage, labels, captions, UI, logos, or watermark anywhere in the scene
- do not render speech, chants, sound effects, names, or magical energy as written text
- if the scene suggests sound, language, or magic, show it with light, mist, particles, or motion only, never typography
- if the flavor text or description mentions sounds or words like brr, sahur, tralala, chants, names, or speech, treat them as mood only and never show them literally in the image
- do not place readable signboards, storefront text, plaques, gravestone writing, carved symbols, pillar markings, or inscribed background props anywhere in the scene
- keep trees, rocks, ruins, mushrooms, monuments, props, and magical effects free of rune-like carvings, etched markings, faux script, decorative sigils, or symbol-shaped patterns
- background surfaces should stay plain, natural, and uninscribed rather than decorated with mysterious markings
- avoid inscription-prone props entirely, including standing stones, monoliths, grave markers, carved pillars, shrine tablets, temple ruins, and marked monuments
- prefer plain natural swamp/forest elements like roots, leaves, mud, water, moss, and unmarked stones instead of relics or ruins
- any sneakers, clothing, armor, or accessories must be original and unbranded
- no swooshes, trademark-like stripes, brand icons, signature shoe marks, or logo-shaped design elements on footwear or costume pieces
- no card frame, no border, no attack text
- no extra characters unless the description explicitly requires them

Important phrasing:
{important_phrasing}
"""

    prompt_path = sidecar_path(out_dir, "prompt", ".txt", args.art_name)
    prompt_path.write_text(prompt, encoding="utf-8")

    refs = []
    if reference_copy_path:
        refs.append(
            inline_image_ref(
                reference_copy_path,
                f'IMAGE 1 — UPDATED FULL-ART BRAINROT REFERENCE. This is the main source character reference for "{args.name}".',
            )
        )
    if style_reference_copy_path and reference_copy_path:
        refs.append(
            inline_image_ref(
                style_reference_copy_path,
                f'IMAGE 2 — POKEMON-STYLE REFERENCE. Match this rendering language and full-art finish for "{args.name}".',
            )
        )
    elif style_reference_copy_path:
        refs.append(
            inline_image_ref(
                style_reference_copy_path,
                f'IMAGE 1 — POKEMON-STYLE REFERENCE. Match this rendering language and full-art finish for "{args.name}".',
            )
        )

    last_error = None
    for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
        try:
            if args.transport == "fal":
                images, text, model_used = fal_edit_generate(prompt, refs)
            elif args.transport == "mpp":
                images, text, model_used = gemini_mpp_generate(prompt, refs)
            else:
                images, text = gemini_generate(api_key, prompt, refs)
            if not images:
                raise RuntimeError(f"No TCG image returned. Gemini text: {text[:400]}")
            break
        except RuntimeError as exc:
            last_error = exc
            if attempt == MAX_GENERATION_ATTEMPTS or not is_retryable_generation_error(exc):
                raise
            delay = BASE_RETRY_DELAY_SECONDS * attempt
            print(
                f"Retrying {args.name} after transient Gemini failure on attempt {attempt}: {exc}",
                flush=True,
            )
            time.sleep(delay)
    else:
        raise last_error

    first_image = images[0]
    if "url" in first_image:
        image_bytes, mime_type = download_file(first_image["url"])
    else:
        image_bytes = first_image["bytes"]
        mime_type = first_image["mime_type"]
    output_ext = extension_for_mime(mime_type)
    output_path = sidecar_path(out_dir, args.art_name, output_ext, "full-art")
    for existing in out_dir.glob(f"{args.art_name}.*"):
        existing.unlink()
    output_path.write_bytes(image_bytes)

    metadata = {
        "model": model_used,
        "transport": args.transport,
        "artName": args.art_name,
        "renderMode": args.render_mode,
        "name": args.name,
        "formula": args.formula,
        "description": args.description,
        "flavorText": args.flavor_text,
        "stageNote": args.stage_note,
        "stageLabel": args.stage_label,
        "familyContrastNote": args.family_contrast_note,
        "referenceImage": str(reference_image) if reference_image else "",
        "savedReferenceImage": str(reference_copy_path) if reference_copy_path else "",
        "styleReferenceImage": str(style_reference_image) if style_reference_image else "",
        "savedStyleReferenceImage": str(style_reference_copy_path) if style_reference_copy_path else "",
        "outputImage": str(output_path),
        "outputMimeType": mime_type,
    }
    sidecar_path(out_dir, "meta", ".json", args.art_name).write_text(f"{json.dumps(metadata, indent=2)}\n", encoding="utf-8")

    if text:
        sidecar_path(out_dir, "response", ".txt", args.art_name).write_text(text, encoding="utf-8")

    print(f"Saved {output_path}")


if __name__ == "__main__":
    main()
