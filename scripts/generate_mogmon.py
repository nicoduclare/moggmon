#!/usr/bin/env python3
"""
generate_mogmon.py — One-shot Mogger Mon pipeline.

  1. Generate front + back sprite sheets via Gemini (direct replacement from the original sprite sheet)
  2. Resize & install into the game's pokemon asset tree (with backup)
  3. Extract icon frames and splice into the pokemon_icons sheets

Usage:
  python3 scripts/generate_mogmon.py --dex 1,4,7
  python3 scripts/generate_mogmon.py                  # all 49 curated species
  python3 scripts/generate_mogmon.py --dex 25 --skip-generate  # install only
  python3 scripts/generate_mogmon.py --dex 1 --use-concept     # optional concept-art assist
"""

import argparse
import base64
import json
import math
import os
import shutil
import subprocess
import time
from urllib import error as urllib_error
from urllib import request as urllib_request

from PIL import Image
from mogmon_normalizer import (
    _prune_small_outlier_boxes,
    analyze_frame_similarity,
    choose_frame_boxes,
    load_template_atlas,
    normalize_frames,
    normalize_battle_sprite,
    pixelify_file_in_place,
    render_icon_from_battle_atlas,
)

# ---------------------------------------------------------------------------
# Background removal — Gemini bakes in a fake checkerboard instead of alpha
# ---------------------------------------------------------------------------


def remove_background(img_path):
    """Remove the checkerboard/gray background via flood-fill from edges.

    Gemini bakes in a visible checkerboard pattern instead of real alpha.
    We flood-fill from all border pixels, only removing contiguous regions
    that color-match the border — so interior sprite pixels are untouched.
    """
    img = Image.open(img_path).convert("RGBA")
    w, h = img.size
    pixels = img.load()

    tolerance = 30

    def color_match(c1, c2):
        return all(abs(a - b) <= tolerance for a, b in zip(c1[:3], c2[:3]))

    # Collect all border pixel colors as seed bg colors
    bg_seeds = set()
    for x in range(w):
        bg_seeds.add((x, 0))
        bg_seeds.add((x, h - 1))
    for y in range(h):
        bg_seeds.add((0, y))
        bg_seeds.add((w - 1, y))

    # BFS flood fill from all border pixels
    visited = set()
    queue = list(bg_seeds)
    to_clear = []

    # Get the two most common border colors (checkerboard has 2 shades)
    border_colors = {}
    for x, y in bg_seeds:
        c = pixels[x, y][:3]
        # Quantize to reduce noise
        key = (c[0] // 8, c[1] // 8, c[2] // 8)
        border_colors[key] = border_colors.get(key, 0) + 1
    # Top N border color clusters
    top_keys = sorted(border_colors, key=border_colors.get, reverse=True)[:6]
    ref_colors = [(k[0] * 8 + 4, k[1] * 8 + 4, k[2] * 8 + 4) for k in top_keys]

    def is_bg_color(r, g, b):
        return any(color_match((r, g, b), rc) for rc in ref_colors)

    while queue:
        x, y = queue.pop()
        if (x, y) in visited:
            continue
        if x < 0 or x >= w or y < 0 or y >= h:
            continue
        visited.add((x, y))

        r, g, b, a = pixels[x, y]
        if not is_bg_color(r, g, b):
            continue

        to_clear.append((x, y))
        # Expand to neighbors
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in visited:
                queue.append((nx, ny))

    for x, y in to_clear:
        pixels[x, y] = (0, 0, 0, 0)

    img.save(img_path)
    pct = 100 * len(to_clear) / (w * h)
    return len(to_clear), pct

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POKEMON_DIR = os.path.join(ROOT, "assets", "images", "pokemon")
MOGMON_DIR = os.path.join(ROOT, "assets", "images", "mogmon")
BACKUP_DIR = os.path.join(POKEMON_DIR, "_backup")
PROMPTS_FILE = os.environ.get(
    "MOGGER_MON_PROMPTS_FILE",
    os.path.join(ROOT, "output", "private-generation-prompts", "mogger-mon-prompts.json"),
)
TEMPAITOWN_PIXELIFY = os.path.abspath(
    os.path.join(ROOT, "..", "..", "aura", "tempaitown", "scripts", "pixelify.mjs")
)

API_KEY = os.environ.get("GEMINI_KEY")
if not API_KEY:
    raise SystemExit("GEMINI_KEY is required to generate Mogger Mon sprites.")
MODEL = "gemini-3.1-flash-image-preview"
API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}"
    f":generateContent?key={API_KEY}"
)

VIEWS = ["front", "back"]
CONCEPT_PIXELIFY_BASE = 64
MAX_GENERATION_ATTEMPTS = 3
MIN_SIMILARITY_AVG_IOU = 0.58
MIN_SIMILARITY_MIN_IOU = 0.42
MIN_AVG_AREA_RATIO = 0.78
MAX_AVG_AREA_RATIO = 1.08
GEMINI_TIMEOUT_SECONDS = 180

# ---------------------------------------------------------------------------
# Gemini helpers
# ---------------------------------------------------------------------------


def gemini_generate(prompt, reference_images=None):
    """Call Gemini with text (+ optional images) and return generated images."""
    parts = []
    for ref in reference_images or []:
        parts.append({"text": f"[Reference: {ref['label']}]"})
        parts.append(
            {"inlineData": {"mimeType": "image/png", "data": ref["base64"]}}
        )
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
        API_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib_request.urlopen(req, timeout=GEMINI_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read())
    except urllib_error.HTTPError as e:
        raise RuntimeError(f"Gemini API {e.code}: {e.read().decode()[:300]}")

    images, texts = [], []
    for cand in data.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            if "inlineData" in part:
                images.append(base64.b64decode(part["inlineData"]["data"]))
            if "text" in part:
                texts.append(part["text"])
    return images, "\n".join(texts)


# ---------------------------------------------------------------------------
# Atlas / grid helpers
# ---------------------------------------------------------------------------


def read_original_atlas(dex, view):
    """Read the BACKUP (original) atlas JSON and return grid metadata."""
    subdir = "" if view == "front" else "back/"
    # Prefer backup if it exists (means we've already installed once)
    json_path = os.path.join(BACKUP_DIR, subdir, f"{dex}.json")
    if not os.path.exists(json_path):
        json_path = os.path.join(POKEMON_DIR, subdir, f"{dex}.json")
    if not os.path.exists(json_path):
        return None

    with open(json_path) as f:
        data = json.load(f)
    tex = data["textures"][0]

    # Count unique visual positions
    positions = set()
    for fr in tex["frames"]:
        f = fr["frame"]
        positions.add((f["x"], f["y"]))

    unique = len(positions)
    cols = math.ceil(math.sqrt(unique))
    rows = math.ceil(unique / cols)

    return {
        "json_path": json_path,
        "sheet_w": tex["size"]["w"],
        "sheet_h": tex["size"]["h"],
        "frame_w": tex["frames"][0]["sourceSize"]["w"],
        "frame_h": tex["frames"][0]["sourceSize"]["h"],
        "frame_count": len(tex["frames"]),
        "unique_cells": unique,
        "cols": cols,
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Step 1a — Generate a concept/reference image of the new creature
# ---------------------------------------------------------------------------


def generate_concept(species):
    """Generate a single concept art image of the creature (NOT a sprite sheet)."""
    concept_dir = os.path.join(MOGMON_DIR, "concepts")
    os.makedirs(concept_dir, exist_ok=True)
    concept_path = os.path.join(concept_dir, f"{species['dex']}.png")

    if os.path.exists(concept_path):
        print(f"    ⏩ Concept art already exists")
        return concept_path

    prompt = f"""Draw a single character design for a creature called "{species['mogmon']}".

It is: {species['formula']}.

{species['prompt']}

Draw ONE full-body front-facing view of this creature. NOT a sprite sheet — just one clean character illustration. Pixel art style, transparent background, small and cute like a monster-battling game creature. Show the full body clearly so it can be used as a reference for making sprite sheets later."""

    print(f"    🖌️  Generating concept art...")
    try:
        images, text = gemini_generate(prompt)
    except Exception as e:
        print(f"    ❌ Concept generation failed: {e}")
        return None

    if not images:
        print(f"    ⚠️  No concept image returned. Gemini: {text[:200]}")
        return None

    with open(concept_path, "wb") as f:
        f.write(images[0])
    changed, pct = remove_background(concept_path)
    pixelify_generated_image(concept_path, base_width=CONCEPT_PIXELIFY_BASE)
    kb = os.path.getsize(concept_path) / 1024
    print(
        f"    ✅ Concept art saved ({kb:.1f}KB, removed {pct:.0f}% bg,"
        f" pixelified at {CONCEPT_PIXELIFY_BASE}px base)"
    )
    return concept_path


# ---------------------------------------------------------------------------
# Step 1b — Generate sprite sheet using concept art + original template
# ---------------------------------------------------------------------------


def generate_sprite(species, view, meta, concept_path=None):
    """Generate a sprite sheet by directly replacing the original species in the template."""
    out_subdir = "" if view == "front" else "back/"
    out_dir = os.path.join(MOGMON_DIR, out_subdir)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{species['dex']}.png")

    if os.path.exists(out_path):
        print(f"    ⏩ {view} already exists, skipping")
        return out_path

    refs = []

    # Image 1: the original sprite sheet (format template)
    subdir = "" if view == "front" else "back/"
    orig_png = os.path.join(BACKUP_DIR, subdir, f"{species['dex']}.png")
    if not os.path.exists(orig_png):
        orig_png = os.path.join(POKEMON_DIR, subdir, f"{species['dex']}.png")
    if os.path.exists(orig_png):
        with open(orig_png, "rb") as f:
            refs.append(
                {
                    "label": "IMAGE 1 — SPRITE SHEET TEMPLATE. This is the exact sprite sheet format to follow.",
                    "base64": base64.b64encode(f.read()).decode(),
                }
            )

    # Optional Image 2: concept art of the new creature
    if concept_path and os.path.exists(concept_path):
        with open(concept_path, "rb") as f:
            refs.append(
                {
                    "label": f"IMAGE 2 — THE NEW CHARACTER. This is {species['mogmon']}. Draw THIS character in the sprite sheet.",
                    "base64": base64.b64encode(f.read()).decode(),
                }
            )

    # Image 3 (back view only): the already-generated front sprite for consistency
    if view == "back":
        front_path = os.path.join(MOGMON_DIR, f"{species['dex']}.png")
        if os.path.exists(front_path):
            with open(front_path, "rb") as f:
                refs.append(
                    {
                        "label": f"IMAGE 3 — FRONT SPRITE SHEET already generated for {species['mogmon']}. Now make the back view of this same character.",
                        "base64": base64.b64encode(f.read()).decode(),
                    }
                )

    view_desc = (
        "front-facing (creature faces TOWARD the viewer)"
        if view == "front"
        else "back-facing (creature faces AWAY, we see its back/rear)"
    )
    layout_desc = f"{meta['cols']} columns by {meta['rows']} rows with {meta['unique_cells']} occupied animation slots"
    view_specific_prompt = species.get(f"{view}Prompt", "")
    silhouette_guard = (
        f'- This must still read as a redesigned "{species["original"]}" with the same basic anatomy and proportions.\n'
        "- Keep the head size, eye placement, torso width, leg count, and tail/root placement very close to the original.\n"
        "- Treat the original sprite like a paint-over base from the same pixel artist, not a brand new redesign.\n"
        "- Preserve the original frame-by-frame limb angles, torso tilt, head tilt, and overall alpha silhouette as closely as possible.\n"
        "- Reinterpret meme/object elements as costume details, textures, or attachments on the original creature body.\n"
        "- Do not turn the character into an abstract object, logo, symbol, or floating prop.\n"
    )
    back_view_guard = ""
    if view == "back":
        back_view_guard = (
            "BACK VIEW REQUIREMENTS:\n"
            "- Keep the rear-facing body silhouette readable at a glance.\n"
            "- The torso, hips, hind legs, tail base, and head outline must stay visible from behind.\n"
            "- The themed attachment must sit on top of the body, not replace or fully cover the body mass.\n"
            "- Keep the attachment no taller or wider than the original back-mounted object footprint.\n"
            "- Avoid flat blobs of foliage, clothing, smoke, or props that hide the original pose.\n\n"
        )

    prompt = f"""I have given you one or more images.

IMAGE 1 is a sprite sheet from a pixel art monster-battling game. It contains multiple animation frames of a creature arranged in a grid. This is your FORMAT TEMPLATE.

If IMAGE 2 is present, it is a character design reference for the replacement creature.

YOUR TASK: Redraw the sprite sheet from Image 1, replacing the original creature in every frame with a new creature called "{species['mogmon']}".

Treat IMAGE 1 as the canonical animation sheet. This is a paint-over replacement, not a new composition.

NEW CREATURE DESIGN BRIEF:
- Name: {species['mogmon']}
- Original species base: {species['original']}
- Formula: {species['formula']}
- Description: {species['prompt']}

WHAT TO KEEP IDENTICAL FROM IMAGE 1:
- Exact same grid layout and number of frames
- Exact same frame dimensions and spacing
- Exact same animation poses and body positions per frame
- Same per-frame placement, silhouette footprint, and camera framing as closely as possible
- Same pixel art style and level of detail
- Transparent background
- Same body mass distribution and readable pose silhouette in every slot

WHAT TO CHANGE:
- The creature in every frame. Replace it with "{species['mogmon']}" using the design brief above.
- ALL frames must consistently show the same new character — no frames should still have the old creature.

CHARACTER INTERPRETATION RULES:
{silhouette_guard}
{f"- Extra species-specific fit rules: {view_specific_prompt}\n" if view_specific_prompt else ""}

VIEW: {view_desc}

{back_view_guard}

STRICT SLOT RULES:
- Treat this as a rigid sprite strip with {layout_desc}.
- Keep exactly one pose per slot and keep every pose fully inside its own slot.
- Do not let outlines, leaves, flames, tails, smoke, or accessories spill across slot boundaries.
- Leave transparent gutter between neighboring slots.
- Keep the creature large and readable inside each slot, roughly 80-90% of slot height.
- Match the original creature's footprint in each slot as closely as possible.
- Preserve the same idle posture and camera framing as the original species.
- Keep the head, torso, limbs, and tail mass aligned to the original pose for that slot.
- If you squint, the new frame should have nearly the same pose silhouette as the original frame.
- Do not add new effects, props, splash shapes, or extra background pixels.
- Favor chunky low-resolution handheld sprite readability over thin detail.
- Render like a 32px-era sprite that has been upscaled with nearest-neighbor, not soft painted art.

This is a drop-in sprite sheet replacement. Same format, every frame redrawn with the new character. Generate now."""

    template_json = os.path.join(BACKUP_DIR, subdir, f"{species['dex']}.json")
    if not os.path.exists(template_json):
        template_json = os.path.join(POKEMON_DIR, subdir, f"{species['dex']}.json")

    repair_prompt = ""
    for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
        print(
            f"    🎨 Generating {view} sprite sheet..."
            f"{'' if attempt == 1 else f' (retry {attempt}/{MAX_GENERATION_ATTEMPTS})'}"
        )
        try:
            images, text = gemini_generate(prompt + repair_prompt, refs)
        except Exception as e:
            print(f"    ❌ {e}")
            return None

        if not images:
            print(f"    ⚠️  No image returned. Gemini: {text[:200]}")
            return None

        with open(out_path, "wb") as f:
            f.write(images[0])
        changed, pct = remove_background(out_path)
        kb = os.path.getsize(out_path) / 1024

        quality = inspect_generated_sheet(out_path, template_json)
        if quality["valid"]:
            print(f"    ✅ Saved {view} sprite sheet ({kb:.1f}KB, removed {pct:.0f}% bg)")
            return out_path

        print(
            "    ⚠️  Generated sheet failed review"
            f" (detected {quality['detected_count']} frames,"
            f" usable {quality['usable_count']},"
            f" outliers {quality['outlier_count']}: {quality['outlier_summary']};"
            f" similarity avg IoU {quality['avg_iou']:.3f}, min IoU {quality['min_iou']:.3f},"
            f" avg area ratio {quality['avg_area_ratio']:.3f})."
        )
        if attempt == MAX_GENERATION_ATTEMPTS:
            print(f"    ✅ Saved {view} sprite sheet ({kb:.1f}KB, removed {pct:.0f}% bg)")
            return out_path

        repair_prompt = (
            "\n\nRETRY FIXES FROM THE PREVIOUS ATTEMPT:\n"
            "- Some slots collapsed into tiny fragments or partial vertical strips.\n"
            "- Every occupied slot must contain the full creature body for that pose.\n"
            "- Do not leave any slot with only a line, a sliver, or a detached accessory.\n"
            "- Keep the creature footprint consistent from frame to frame.\n"
            "- If a pose is duplicated in the source, redraw the same complete pose again instead of inventing a blank or tiny variant.\n"
            "- The new sheet drifted too far from the original pose silhouette.\n"
            "- Keep the exact same body orientation, limb placement, head tilt, and bulk distribution as the source frame.\n"
            "- Think of this as repainting the original monster into a meme reskin, not changing the animation.\n"
        )

    return out_path


def inspect_generated_sheet(image_path, template_json_path):
    image = Image.open(image_path).convert("RGBA")
    template = load_template_atlas(template_json_path)
    choice = choose_frame_boxes(image, template)
    boxes = choice["boxes"]
    usable_boxes = _prune_small_outlier_boxes(boxes, template["unique_count"])
    widths = sorted(box[2] - box[0] for box in boxes)
    heights = sorted(box[3] - box[1] for box in boxes)
    areas = sorted((box[2] - box[0]) * (box[3] - box[1]) for box in boxes)
    median_width = widths[len(widths) // 2]
    median_height = heights[len(heights) // 2]
    median_area = areas[len(areas) // 2]

    outliers = []
    for index, box in enumerate(boxes):
        width = box[2] - box[0]
        height = box[3] - box[1]
        area = width * height
        if width < median_width * 0.55 or height < median_height * 0.55 or area < median_area * 0.4:
            outliers.append((index, width, height))

    normalized = normalize_frames(image, template)
    similarity = analyze_frame_similarity(normalized["frames"], template)
    similarity_valid = (
        similarity["avg_iou"] >= MIN_SIMILARITY_AVG_IOU
        and similarity["min_iou"] >= MIN_SIMILARITY_MIN_IOU
        and MIN_AVG_AREA_RATIO <= similarity["avg_area_ratio"] <= MAX_AVG_AREA_RATIO
    )

    return {
        "valid": len(usable_boxes) >= template["unique_count"] and similarity_valid,
        "detected_count": choice["count"],
        "usable_count": len(usable_boxes),
        "outlier_count": len(outliers),
        "outlier_summary": ", ".join(
            f"#{index} {width}x{height}" for index, width, height in outliers[:4]
        ) or "none",
        "avg_iou": similarity["avg_iou"],
        "min_iou": similarity["min_iou"],
        "avg_area_ratio": similarity["avg_area_ratio"],
    }


def pixelify_generated_image(img_path, base_width):
    """Use TempaiTown's exact pixelify script when available, with a Python fallback."""
    if os.path.exists(TEMPAITOWN_PIXELIFY):
        cmd = [
            "node",
            TEMPAITOWN_PIXELIFY,
            "--pixel",
            str(base_width),
            img_path,
            img_path,
        ]
        try:
            subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.strip() or exc.stdout.strip()
            print(f"    ⚠️  TempaiTown pixelify failed, falling back to Python: {stderr[:200]}")
            pixelify_file_in_place(img_path, base_width=base_width)
        else:
            webp_path = os.path.splitext(img_path)[0] + ".webp"
            if os.path.exists(webp_path):
                os.remove(webp_path)
        return

    pixelify_file_in_place(img_path, base_width=base_width)


def clear_generated_species_outputs(dex, clear_concept):
    """Delete generated artifacts so --regenerate always forces a fresh Gemini run."""
    paths = [
        os.path.join(MOGMON_DIR, f"{dex}.png"),
        os.path.join(MOGMON_DIR, f"{dex}.webp"),
        os.path.join(MOGMON_DIR, "back", f"{dex}.png"),
        os.path.join(MOGMON_DIR, "back", f"{dex}.webp"),
    ]
    if clear_concept:
        paths.extend(
            [
                os.path.join(MOGMON_DIR, "concepts", f"{dex}.png"),
                os.path.join(MOGMON_DIR, "concepts", f"{dex}.webp"),
            ]
        )
    for path in paths:
        if os.path.exists(path):
            os.remove(path)


# ---------------------------------------------------------------------------
# Step 2 — Install battle sprites into game asset tree
# ---------------------------------------------------------------------------


def install_battle_sprite(dex, view, meta):
    """Normalize a generated Mogger Mon sheet into the game atlas format."""
    subdir = "" if view == "front" else "back/"
    mogmon_png = os.path.join(MOGMON_DIR, subdir, f"{dex}.png")
    game_png = os.path.join(POKEMON_DIR, subdir, f"{dex}.png")
    game_json = os.path.join(POKEMON_DIR, subdir, f"{dex}.json")

    if not os.path.exists(mogmon_png):
        print(f"    ⏭  No mogmon {view} for dex {dex}")
        return False

    backup_sub = os.path.join(BACKUP_DIR, subdir)
    os.makedirs(backup_sub, exist_ok=True)
    bk_png = os.path.join(backup_sub, f"{dex}.png")
    bk_json = os.path.join(backup_sub, f"{dex}.json")
    if not os.path.exists(bk_png) and os.path.exists(game_png):
        shutil.copy2(game_png, bk_png)
        shutil.copy2(game_json, bk_json)
        print(f"    📦 Backed up originals")

    orig_json = bk_json if os.path.exists(bk_json) else game_json
    result = normalize_battle_sprite(
        mogmon_png,
        orig_json,
        game_png,
        game_json,
    )

    print(
        "    ✅ Installed"
        f" {view} battle sprite using {result['method']} detection"
        f" ({result['detected_count']} raw frames -> {result['expected_count']} atlas frames,"
        f" sheet {result['sheet_w']}x{result['sheet_h']})"
    )
    return True


# ---------------------------------------------------------------------------
# Step 3 — Install icons
# ---------------------------------------------------------------------------


def find_icon_sheet_for_dex(dex):
    """Find which pokemon_icons_N sheet contains this dex's icon."""
    for i in range(10):
        json_path = os.path.join(ROOT, "assets", "images", f"pokemon_icons_{i}.json")
        if not os.path.exists(json_path):
            continue
        with open(json_path) as f:
            data = json.load(f)
        for fr in data["textures"][0]["frames"]:
            if fr["filename"] == str(dex) or fr["filename"] == f"{dex}":
                return i, json_path
    return None, None


def install_icons(dex_list):
    """Extract a frame from each installed mogmon sprite and splice into icon sheets."""
    # Group by icon sheet
    sheet_groups = {}  # sheet_index -> [(dex, frame_name, pos)]
    for dex in dex_list:
        sheet_idx, json_path = find_icon_sheet_for_dex(dex)
        if sheet_idx is None:
            print(f"  ⏭  No icon found for dex {dex}")
            continue

        with open(json_path) as f:
            data = json.load(f)

        for fr in data["textures"][0]["frames"]:
            name = fr["filename"]
            # Match "N" and "Ns" (shiny)
            if name == str(dex) or name == f"{dex}s":
                sheet_groups.setdefault(sheet_idx, []).append(
                    (dex, name, fr["frame"])
                )

    for sheet_idx, entries in sheet_groups.items():
        png_path = os.path.join(ROOT, "assets", "images", f"pokemon_icons_{sheet_idx}.png")
        backup_path = png_path.replace(f"_icons_{sheet_idx}.png", f"_icons_{sheet_idx}.backup.png")

        # Backup once
        if not os.path.exists(backup_path):
            shutil.copy2(png_path, backup_path)
            print(f"  📦 Backed up {os.path.basename(png_path)}")

        icon_sheet = Image.open(png_path).convert("RGBA")

        for dex, frame_name, pos in entries:
            # Read installed game sprite and extract first frame
            game_png = os.path.join(POKEMON_DIR, f"{dex}.png")
            game_json = os.path.join(POKEMON_DIR, f"{dex}.json")

            if not os.path.exists(game_png):
                continue

            tw, th = pos["w"], pos["h"]
            tx, ty = pos["x"], pos["y"]
            icon = render_icon_from_battle_atlas(game_png, game_json, tw, th)
            blank = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
            icon_sheet.paste(blank, (tx, ty))
            icon_sheet.paste(icon, (tx, ty), icon)
            print(f"  ✅ Icon dex {dex} '{frame_name}' ({tw}x{th}) at ({tx},{ty})")

        icon_sheet.save(png_path)
        print(f"  💾 Saved {os.path.basename(png_path)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Mogger Mon sprite pipeline")
    parser.add_argument("--dex", type=str, help="Comma-separated dex numbers (default: all curated)")
    parser.add_argument("--skip-generate", action="store_true", help="Skip Gemini generation, install only")
    parser.add_argument("--skip-install", action="store_true", help="Generate only, don't install")
    parser.add_argument("--regenerate", action="store_true", help="Re-generate even if sprites exist")
    parser.add_argument("--use-concept", action="store_true", help="Generate concept art first and include it as an extra reference")
    args = parser.parse_args()

    # Load prompts
    with open(PROMPTS_FILE) as f:
        prompts = json.load(f)
    all_species = prompts["species"]

    # Filter by dex
    if args.dex:
        dex_filter = set(int(d) for d in args.dex.split(","))
        all_species = [s for s in all_species if s["dex"] in dex_filter]

    print(f"\n🧠 Mogger Mon Pipeline")
    print(f"   Species: {len(all_species)}")
    print(f"   Generate: {'no' if args.skip_generate else 'yes'}")
    print(f"   Install:  {'no' if args.skip_install else 'yes'}")

    generated, installed, icons_done = 0, 0, 0
    dex_with_sprites = []

    for sp in all_species:
        dex = sp["dex"]
        print(f"\n{'='*60}")
        print(f"[{dex}] {sp['original']} → {sp['mogmon']} ({sp['formula']})")
        print(f"{'='*60}")

        has_all_views = True
        concept_path = None

        if args.regenerate and not args.skip_generate:
            clear_generated_species_outputs(dex, clear_concept=args.use_concept)

        # --- Optional Step 1a: Generate concept art (once per species) ---
        if not args.skip_generate and args.use_concept:
            concept_path = generate_concept(sp)
            if not concept_path:
                print(f"  ❌ Concept art failed, skipping species")
                continue
            time.sleep(2)

        for view in VIEWS:
            meta = read_original_atlas(dex, view)
            if not meta:
                print(f"  ⏭  No original {view} atlas for dex {dex}, skipping")
                has_all_views = False
                continue

            # --- Step 1b: Generate sprite sheet from template + design brief ---
            if not args.skip_generate:
                result = generate_sprite(sp, view, meta, concept_path)
                if result:
                    generated += 1
                else:
                    has_all_views = False
                    continue
                time.sleep(2)

            # --- Step 2: Install battle sprite ---
            if not args.skip_install:
                if install_battle_sprite(dex, view, meta):
                    installed += 1

        if has_all_views:
            dex_with_sprites.append(dex)

    # --- Step 3: Install icons ---
    if not args.skip_install and dex_with_sprites:
        print(f"\n{'='*60}")
        print(f"Installing icons for {len(dex_with_sprites)} species...")
        print(f"{'='*60}")
        install_icons(dex_with_sprites)
        icons_done = len(dex_with_sprites)

    print(f"\n🏁 Done!")
    print(f"   Generated: {generated} sprite sheets")
    print(f"   Installed: {installed} battle sprites")
    print(f"   Icons:     {icons_done} species")
    print(f"   Output:    {MOGMON_DIR}")
    print(f"   Backups:   {BACKUP_DIR}")


if __name__ == "__main__":
    main()
