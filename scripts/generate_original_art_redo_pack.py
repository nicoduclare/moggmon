#!/usr/bin/env python3
"""Run a small original-art redo sweep against the exported non-mon asset pack."""

from __future__ import annotations

import argparse
import base64
import fnmatch
import json
import mimetypes
import os
import re
import subprocess
import time
from collections import deque
from io import BytesIO
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
PACK_ROOT = ROOT / "output" / "original-art-redo-pack"
IMAGE_ROOT = PACK_ROOT / "images"
ASSET_MANIFEST_PATH = ROOT / "docs" / "brainrot-asset-manifest.json"
FAL_HELPER = Path(__file__).with_name("fal_grok_edit.mjs")
FAL_MPP_HELPER = Path(__file__).with_name("fal_mpp_generate.mjs")
GEMINI_HELPER = Path(__file__).with_name("gemini_mpp_generate.mjs")

DEFAULT_GROK_MODEL = "xai/grok-imagine-image/edit"
DEFAULT_FAL_MPP_MODEL = "xai/grok-imagine-image/edit"
DEFAULT_GPT_IMAGE_2_MODEL = "openai/gpt-image-2/edit"
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-image-preview"
DEFAULT_GEMINI_TRANSPORT = "auto"
FAL_PROVIDERS = {"fal-mpp", "grok", "gpt-image-2"}
DEFAULT_TARGET_MODE = "pilot"
DEFAULT_TARGETS = [
    "arenas/beach_a.png",
    "trainer/lance.png",
    "items/potion.png",
    "ui/pbinfo_player.png",
]
HELPER_TIMEOUT_SECONDS = 600
NETWORK_RETRY_ATTEMPTS = 4
NETWORK_RETRY_BASE_SECONDS = 4
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
SKIP_PREFIXES = (
    "events/",
    "inputs/",
    "ui/text_images/",
    "ui/legacy/text_images/",
)
SKIP_ROOT_PREFIXES = ("types", "statuses", "categories", "logo")
SKIP_SUBSTRINGS = (
    "oauth",
    "github_icon",
    "discord_icon",
    "steam_oauth",
    "google_oauth",
    "kakao_oauth",
    "line_oauth",
    "numbers_",
)
TOKEN_OVERRIDES = {
    "pbinfo": "battle info panel",
    "pb": "capsule",
    "bg": "background",
    "bgm": "music",
    "hp": "health",
    "exp": "experience",
    "lv": "level",
    "ui": "interface",
    "sel": "selector",
    "mg": "special accent",
    "vfx": "visual effect",
    "cg": "cutscene",
    "gacha": "gacha",
    "underlay": "underlay",
    "lightrays": "light rays",
    "namebox": "name box",
    "mmenu": "main menu",
    "pokeball": "capsule",
}
TOP_LEVEL_DESCRIPTION_FALLBACKS = {
    "(root)": "Shared top-level atlases and global art assets used across multiple screens.",
    "arenas": "Battle backgrounds and arena tiles.",
    "cg": "Cutscene and splash artwork.",
    "character": "Character portrait and overworld identity art.",
    "effects": "Battle animation frame sheets and special effects.",
    "egg": "Egg art and incubation visuals.",
    "events": "Event banners and promo art.",
    "inputs": "Input device diagrams and button prompt art.",
    "items": "Inventory icons, held item atlases, and utility object art.",
    "mystery-encounters": "Special encounter illustrations and scene cards.",
    "pokeball": "Ball, capsule, and summon device art.",
    "trainer": "Trainer battler art and trainer-adjacent identity sprites.",
    "ui": "Core UI chrome, prompts, selectors, and menu framing.",
}

GEMINI_MODEL_ALIASES = {
    "nanobanana": "gemini-2.5-flash-image",
    "nano-banana": "gemini-2.5-flash-image",
    "nanobanana-2": "gemini-3.1-flash-image-preview",
    "nano-banana-2": "gemini-3.1-flash-image-preview",
}


def fail(message: str) -> None:
    raise SystemExit(message)


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def resolve_gemini_model(model: str) -> str:
    normalized = model.strip()
    return GEMINI_MODEL_ALIASES.get(normalized, normalized)


def load_category_descriptions() -> dict[str, str]:
    descriptions = dict(TOP_LEVEL_DESCRIPTION_FALLBACKS)
    if not ASSET_MANIFEST_PATH.exists():
        return descriptions

    try:
        data = json.loads(ASSET_MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return descriptions

    bucket_map = {
        "branding": "(root)",
        "ui_skin": "ui",
        "character_portraits": "character",
        "trainer_sprites": "trainer",
        "arenas": "arenas",
        "egg_assets": "egg",
        "cutscene_cg": "cg",
        "battle_vfx": "effects",
    }
    for bucket in data.get("assetBuckets", []):
        mapped = bucket_map.get(bucket.get("key", ""))
        description = str(bucket.get("description", "")).strip()
        if mapped and description:
            descriptions[mapped] = description
    return descriptions


CATEGORY_DESCRIPTIONS = load_category_descriptions()


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


def read_source_image(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")


def has_json_sidecar(source_path: Path) -> bool:
    return source_path.with_suffix(".json").exists()


def source_has_alpha(image: Image.Image) -> bool:
    return image.getchannel("A").getextrema()[0] < 255


def key_dark_background(image: Image.Image, threshold: int = 24, softness: int = 48) -> Image.Image:
    keyed = image.convert("RGBA")
    pixels = keyed.load()
    width, height = keyed.size
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            brightness = max(r, g, b)
            if brightness <= threshold:
                pixels[x, y] = (r, g, b, 0)
            elif brightness < threshold + softness:
                alpha = int(a * (brightness - threshold) / softness)
                pixels[x, y] = (r, g, b, alpha)
    return keyed


def remove_edge_matte(image: Image.Image) -> Image.Image:
    """Remove white/gray/checkerboard mattes connected to the image edge."""
    cleaned = image.convert("RGBA")
    width, height = cleaned.size
    if width == 0 or height == 0:
        return cleaned

    pixels = cleaned.load()
    corners = [
        pixels[0, 0],
        pixels[width - 1, 0],
        pixels[0, height - 1],
        pixels[width - 1, height - 1],
    ]
    opaque_corners = [color for color in corners if color[3] > 0]
    if len(opaque_corners) < 2:
        return cleaned

    def is_light_or_gray(color: tuple[int, int, int, int]) -> bool:
        r, g, b, a = color
        if a == 0:
            return False
        brightness = max(r, g, b)
        saturation = brightness - min(r, g, b)
        return min(r, g, b) >= 200 or (brightness >= 90 and saturation <= 36)

    matte_refs = [color[:3] for color in opaque_corners if is_light_or_gray(color)]
    if not matte_refs:
        return cleaned

    def close_to_ref(color: tuple[int, int, int]) -> bool:
        return any(max(abs(channel - ref_channel) for channel, ref_channel in zip(color, ref)) <= 64 for ref in matte_refs)

    def is_background(color: tuple[int, int, int, int]) -> bool:
        r, g, b, a = color
        if a == 0:
            return True
        brightness = max(r, g, b)
        saturation = brightness - min(r, g, b)
        return close_to_ref((r, g, b)) or min(r, g, b) >= 210 or (brightness >= 96 and saturation <= 40)

    queue: deque[tuple[int, int]] = deque()
    visited = bytearray(width * height)

    def enqueue(x: int, y: int) -> None:
        index = y * width + x
        if visited[index]:
            return
        visited[index] = 1
        if is_background(pixels[x, y]):
            queue.append((x, y))

    for x in range(width):
        enqueue(x, 0)
        enqueue(x, height - 1)
    for y in range(1, height - 1):
        enqueue(0, y)
        enqueue(width - 1, y)

    while queue:
        x, y = queue.popleft()
        r, g, b, _a = pixels[x, y]
        pixels[x, y] = (r, g, b, 0)
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if nx < 0 or ny < 0 or nx >= width or ny >= height:
                continue
            enqueue(nx, ny)

    return cleaned


def verify_generated_image(source: Image.Image, generated_bytes: bytes) -> Image.Image:
    """Return the generated image only when it is already a drop-in asset."""
    generated = Image.open(BytesIO(generated_bytes)).convert("RGBA")
    generated = remove_edge_matte(generated)
    if source_has_alpha(source) and not source_has_alpha(generated):
        generated = key_dark_background(generated)
    if generated.size != source.size:
        generated = generated.resize(source.size, Image.Resampling.LANCZOS)
        generated = remove_edge_matte(generated)
    if source_has_alpha(source) and not source_has_alpha(generated):
        generated.putalpha(source.getchannel("A"))
    return generated


def extension_for_mime(mime_type: str) -> str:
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
    }.get(mime_type, ".png")


def iter_image_targets() -> list[str]:
    targets = []
    for path in sorted(IMAGE_ROOT.rglob("*")):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            targets.append(path.relative_to(IMAGE_ROOT).as_posix())
    return targets


def is_redrawable_target(target: str) -> bool:
    lower = target.lower()
    if any(lower.startswith(prefix) for prefix in SKIP_PREFIXES):
        return False
    rel = Path(lower)
    if rel.parent == Path(".") and any(rel.name.startswith(prefix) for prefix in SKIP_ROOT_PREFIXES):
        return False
    if any(fragment in lower for fragment in SKIP_SUBSTRINGS):
        return False
    return True


def discover_targets(target_mode: str) -> list[str]:
    if target_mode == "pilot":
        return list(DEFAULT_TARGETS)
    targets = iter_image_targets()
    if target_mode == "all-redrawable":
        return [target for target in targets if is_redrawable_target(target)]
    if target_mode == "all-images":
        return targets
    fail(f"Unsupported target mode: {target_mode}")


def apply_match_filters(targets: list[str], include_globs: list[str], exclude_globs: list[str]) -> list[str]:
    if include_globs:
        targets = [
            target
            for target in targets
            if any(fnmatch.fnmatch(target, pattern) for pattern in include_globs)
        ]
    if exclude_globs:
        targets = [
            target
            for target in targets
            if not any(fnmatch.fnmatch(target, pattern) for pattern in exclude_globs)
        ]
    return targets


def humanize_asset_name(stem: str) -> str:
    raw_tokens = [token for token in re.split(r"[_.\-]+", stem) if token]
    cooked = []
    for token in raw_tokens:
        replacement = TOKEN_OVERRIDES.get(token.lower(), token.lower())
        if len(replacement) == 1 and replacement.isalpha():
            cooked.append(f"variant {replacement.upper()}")
        else:
            cooked.append(replacement)
    return " ".join(cooked) if cooked else stem


def asset_description(target: str) -> str:
    rel = Path(target)
    top_level = rel.parts[0] if len(rel.parts) > 1 else "(root)"
    base = CATEGORY_DESCRIPTIONS.get(top_level, TOP_LEVEL_DESCRIPTION_FALLBACKS.get(top_level, "Game art asset."))
    stem = rel.stem
    humanized = humanize_asset_name(stem)

    if top_level == "trainer":
        identity = f"Trainer artwork for {humanized}."
    elif top_level == "arenas":
        identity = f"Battle arena or terrain plate for {humanized}."
    elif top_level == "items":
        identity = f"Inventory item art for {humanized}."
    elif top_level == "ui":
        identity = f"UI component for {humanized}."
    elif top_level == "pokeball":
        identity = f"Capsule or summon-device art for {humanized}."
    elif top_level == "(root)":
        identity = f"Shared atlas or global art sheet for {humanized}."
    else:
        identity = f"Asset identity: {humanized}."
    return f"{base} {identity}"


def infer_mapping_notes(target: str) -> list[str]:
    lower = target.lower()
    notes = []

    if (
        lower.startswith("pokeball/")
        or "/pb" in lower
        or re.search(r"/(?:gb|mb|rb|ub)\.png$", lower)
        or lower.startswith("pb.")
        or any(
            token in lower
            for token in (
                "pokeball",
                "great_ball",
                "ultra_ball",
                "master_ball",
                "rogue_ball",
                "luxury_ball",
                "strange_ball",
                "lock_capsule",
                "lure",
                "golden_net",
                "catching_charm",
            )
        )
        or ("ball" in lower and Path(lower).parts[0] in {"items", "ui", "pokeball"})
    ):
        notes.append(
            "capture-device mapping: Pokeball and ball motifs must become Cryotank gear. Use compact cryo canisters, glass fluid chambers, sealed capsule tanks, metal locks, and cryo indicators. Never leave a classic split red-white sphere or a stock Pokeball seam."
        )

    if any(token in lower for token in ("berry", "juice", "honey", "herb", "seed", "sweet", "apple")):
        notes.append(
            "consumable mapping: berry and fruit-snack motifs must become Mogger Mon Zaza shroom consumables. For any asset with berry in the filename, keep the original color/readability role but convert the main fruit/berry body into a mushroom cap, fungal vial, zaza stash pouch, or compact shroom packet. The final icon must read as shroom/zaza first, not fruit first. Do not leave literal fruit, berry, citrus, cherry, apple, pineapple, leaf-snack, or flower-fruit silhouettes as the final read."
        )

    if any(token in lower for token in ("tm", "memory", "drive", "disc", "disk", "module", "braince")):
        notes.append(
            "tech-media mapping: TM, module, and memory-media motifs must become BrainDance gear. Use compact discs, chrome wafers, data chips, and black-market memory media instead of stock franchise discs."
        )

    if any(
        token in lower
        for token in (
            "hp_up",
            "protein",
            "iron",
            "calcium",
            "zinc",
            "carbos",
            "pp_up",
            "pp_max",
            "dire_hit",
            "guard_spec",
            "x_accuracy",
            "x_attack",
            "x_defense",
            "x_sp_atk",
            "x_sp_def",
            "x_speed",
            "booster_energy",
            "mint_",
            "candy",
            "exp_charm",
        )
    ):
        notes.append(
            "booster mapping: vitamin, candy, mint, and battle-boost motifs must become original Mogger Mon booster items. Prefer biotech injector cartridges, neon supplement vials, foil stimulant packets, capsule jars, and compact stat-chip boosters; avoid medical brand copies or stock Pokemon vitamin bottles."
        )

    if any(
        token in lower
        for token in (
            "relic_",
            "nugget",
            "amulet_coin",
            "coin_case",
            "mystic_ticket",
            "pair_of_tickets",
            "teacup",
            "cracked_pot",
            "chipped_pot",
            "sacred_ash",
            "prison_bottle",
            "reveal_glass",
        )
    ):
        notes.append(
            "relic mapping: treasure, ticket, and artifact motifs must become original Mogger Mon relics. Use offbeat black-market charms, engraved scrap-metal trophies, holo tickets, glitch coins, antique cyber-ceramics, and ritual tech artifacts; avoid direct franchise treasure silhouettes."
        )

    return notes


def download_file(url: str) -> tuple[bytes, str]:
    req = urllib_request.Request(url, headers={"User-Agent": "mogmon-original-art-redo/1.0"})
    last_error = None
    for attempt in range(1, NETWORK_RETRY_ATTEMPTS + 1):
        try:
            with urllib_request.urlopen(req, timeout=300) as response:
                mime_type = response.headers.get_content_type() or "image/png"
                return response.read(), mime_type
        except (urllib_error.URLError, TimeoutError) as error:
            last_error = error
            if attempt >= NETWORK_RETRY_ATTEMPTS:
                break
            time.sleep(NETWORK_RETRY_BASE_SECONDS * attempt)
    raise RuntimeError(f"download failed after {NETWORK_RETRY_ATTEMPTS} attempts: {last_error}")


def build_prompt(target: str, size: tuple[int, int], transparent: bool, atlas: bool) -> str:
    category = Path(target).parts[0]
    transparency_line = "preserve transparent background" if transparent else "preserve opaque full-frame composition"
    transparency_fallback_notes = []
    if transparent:
        transparency_fallback_notes = [
            "- output true PNG alpha transparency if the model supports it; do not render a transparency preview checkerboard, white matte, gray matte, drop shadow, or background grid",
            "- if the renderer cannot output alpha, use one flat pure black background only: no texture, no shadows, no gradients, no glow, no rim haze",
            "- keep a crisp clean subject edge against the background so automated transparency cleanup can remove it",
        ]
    asset_role = asset_description(target)

    if category == "arenas":
        direction = (
            "Edit this exact battle arena background into original Mogger Mon world art."
        )
    elif category == "trainer":
        direction = (
            "Edit this exact trainer artwork into original Mogger Mon character art."
        )
    elif category == "items":
        direction = (
            "Edit this exact item icon or item sheet into original Mogger Mon inventory art."
        )
    elif category == "ui":
        direction = (
            "Edit this exact UI asset into original Mogger Mon interface chrome."
        )
    else:
        direction = "Edit this exact game art asset into original Mogger Mon art."

    atlas_line = (
        "- if this file is a sprite atlas, icon sheet, or multi-frame sheet, preserve the exact frame count, frame ordering, grid layout, and occupancy"
        if atlas
        else "- preserve the exact object count and composition from the reference"
    )
    mapping_notes = infer_mapping_notes(target)
    identity_line = "- preserve the exact subject identity, crop, silhouette, spacing, and composition footprint of the reference"
    if category in {"trainer", "character"}:
        identity_line = (
            "- preserve the exact crop, frame occupancy, pose order, gesture language, and silhouette footprint of the reference, "
            "but redesign the person into a clearly different original Mogger Mon character"
        )
    category_specific = {
        "arenas": "- preserve the exact camera angle, horizon placement, ground-plane read, and scene silhouette",
        "trainer": "- keep the atlas structure and motion beats, but change the face, hair silhouette, outfit construction, accessory set, and palette enough that it no longer reads as the original trainer in cosplay",
        "character": "- keep the same portrait or overworld pose structure, but change the face, hair, clothing cut, color story, and accessories so it reads as an original Mogger Mon person rather than a touched-up franchise character",
        "items": "- keep the same item identity and centered icon or atlas layout; do not turn it into a different creature or prop",
        "ui": "- preserve the exact panel role, geometry, negative space, meter housing, and readability footprint",
    }.get(category, "- preserve the exact runtime role and readability of the reference asset")
    originality_notes = []
    if category in {"trainer", "character"}:
        originality_notes = [
            "- do not preserve the original trainer's exact facial features, hairstyle, eye design, costume cut lines, or one-to-one accessory placement",
            "- invent a new Mogger Mon person with a distinctly Gen Z, internet-native streetwear look: layered thrift-tech outfits, asymmetry, chunky sneakers, cropped or oversized silhouettes, dyed or high-contrast hair accents, wearable tech, and Cryotank-era props where relevant",
            "- the pose sheet and silhouette rhythm must stay, but the person inside those poses should feel materially different at first glance",
        ]

    return "\n".join(
        [
            direction,
            f"Asset description: {asset_role}",
            f"Reference asset path: {target}.",
            f"Exact canvas target: {size[0]}x{size[1]}.",
            f"The returned image file itself must be exactly {size[0]} pixels wide and {size[1]} pixels tall; do not output a 1k render, enlarged preview, padded sheet, or alternate aspect ratio.",
            "",
            "This is an exact edit pass, not a redesign from scratch.",
            "Treat the reference image as the final template for subject, layout, silhouette, and composition.",
            "",
            "Hard constraints:",
            f"- {transparency_line}",
            *transparency_fallback_notes,
            "- preserve the exact canvas size",
            identity_line,
            atlas_line,
            category_specific,
            *originality_notes,
            "- output should already look like finished game pixel art: crisp hard-edged pixel clusters, limited antialiasing, no painterly concept-art blur, no 3D render lighting",
            "- do not make a high-resolution illustration that merely could be pixelified later; make the returned image read as the final pixel sprite/icon/atlas",
            "- change only the art treatment: materials, ornament language, costume details, texture treatment, and inherited franchise-coded motifs",
            "- replace inherited Pokemon-coded motifs with original Mogger Mon equivalents without inventing a different asset",
            "- do not add extra characters, logos, watermarks, UI labels, or mockup callouts",
            "- do not add alternate versions, concept-sheet framing, or extra empty padding around the subject",
            "- keep the asset readable as a direct drop-in replacement candidate, not a concept board",
            "",
            "Canon replacement vocabulary to respect:" if mapping_notes else "",
            *[f"- {note}" for note in mapping_notes],
            "" if mapping_notes else "",
            "Output one finished asset only.",
        ]
    )


def run_json_helper(command: list[str], payload: dict, timeout: int = HELPER_TIMEOUT_SECONDS) -> dict:
    try:
        result = subprocess.run(
            command,
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=True,
            timeout=timeout,
        )
    except subprocess.CalledProcessError as exc:
        error_text = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(error_text or f"{command[0]} exited with code {exc.returncode}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{command[0]} timed out after {exc.timeout} seconds") from exc

    stdout = result.stdout.strip()
    if not stdout:
        raise RuntimeError(f"{command[0]} returned no output")
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{command[0]} returned invalid JSON: {stdout[:400]}") from exc


def run_gemini_api(source_path: Path, prompt: str, model: str) -> dict:
    api_key = os.environ.get("GEMINI_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_KEY is required for direct Gemini API transport")
    reference = image_ref(source_path, source_path.stem)

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": f"[Reference: {source_path.stem}]"},
                    {
                        "inlineData": {
                            "mimeType": reference["mime_type"],
                            "data": reference["base64"],
                        }
                    },
                    {"text": prompt},
                ],
            }
        ],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
            "temperature": 1.0,
        },
    }
    api_url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    )
    req = urllib_request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=300) as response:
            data = json.loads(response.read())
    except urllib_error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")[:1200]
        raise RuntimeError(f"Gemini API {exc.code}: {details}") from exc

    images = []
    texts = []
    for candidate in data.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            inline_data = part.get("inlineData")
            if inline_data and inline_data.get("data"):
                images.append(
                    {
                        "mime_type": inline_data.get("mimeType", "image/png"),
                        "base64": inline_data["data"],
                    }
                )
            if part.get("text"):
                texts.append(part["text"])
    if not images:
        raise RuntimeError(f"Gemini API returned no inline image. Text: {' '.join(texts)[:300]}")

    return {
        "images": images,
        "text": "\n".join(texts),
        "model": model,
    }


def run_fal_edit(source_path: Path, prompt: str, model: str, provider: str, output_format: str) -> dict:
    if not FAL_HELPER.exists():
        fail(f"Fal helper not found: {FAL_HELPER}")

    payload = {
        "model": model,
        "prompt": prompt,
        "referenceImages": [image_ref(source_path, source_path.stem)],
        "outputFormat": output_format,
        "resolution": "1k",
        "numImages": 1,
    }
    last_error = None
    for attempt in range(1, NETWORK_RETRY_ATTEMPTS + 1):
        try:
            response = run_json_helper(["node", str(FAL_HELPER)], payload)
            images = response.get("images", [])
            if not images or not images[0].get("url"):
                raise RuntimeError(f"{provider} returned no image URL")
            raw_bytes, mime_type = download_file(images[0]["url"])
            return {
                "provider": provider,
                "model": response.get("model", f"fal:{model}"),
                "revised_prompt": response.get("revised_prompt", ""),
                "mime_type": mime_type,
                "raw_bytes": raw_bytes,
                "remote_url": images[0]["url"],
            }
        except RuntimeError as error:
            last_error = error
            if attempt >= NETWORK_RETRY_ATTEMPTS or not is_retryable_fal_error(error):
                break
            time.sleep(NETWORK_RETRY_BASE_SECONDS * attempt)
    raise last_error if last_error else RuntimeError(f"{provider} request failed")


def run_fal_mpp(source_path: Path, prompt: str, model: str, max_spend: str | None) -> dict:
    if not FAL_MPP_HELPER.exists():
        fail(f"Fal MPP helper not found: {FAL_MPP_HELPER}")

    payload = {
        "model": model,
        "prompt": prompt,
        "referenceImages": [image_ref(source_path, source_path.stem)],
        "outputFormat": "png",
        "resolution": "1k",
        "numImages": 1,
    }
    if max_spend:
        payload["maxSpend"] = max_spend

    last_error = None
    for attempt in range(1, NETWORK_RETRY_ATTEMPTS + 1):
        try:
            response = run_json_helper(["node", str(FAL_MPP_HELPER)], payload)
            images = response.get("images", [])
            if not images or not images[0].get("url"):
                raise RuntimeError("fal-mpp returned no image URL")
            raw_bytes, mime_type = download_file(images[0]["url"])
            return {
                "provider": "fal-mpp",
                "model": response.get("model", f"mpp:{model}"),
                "revised_prompt": response.get("raw", {}).get("revised_prompt", ""),
                "mime_type": mime_type,
                "raw_bytes": raw_bytes,
                "remote_url": images[0]["url"],
                "transport": "mpp",
                "transport_errors": [],
            }
        except RuntimeError as error:
            last_error = error
            if attempt >= NETWORK_RETRY_ATTEMPTS or not is_retryable_fal_error(error):
                break
            time.sleep(NETWORK_RETRY_BASE_SECONDS * attempt)
    raise last_error if last_error else RuntimeError("fal-mpp request failed")


def run_grok(source_path: Path, prompt: str, model: str) -> dict:
    return run_fal_edit(source_path, prompt, model, "grok", "jpeg")


def run_gpt_image_2(source_path: Path, prompt: str, model: str) -> dict:
    return run_fal_edit(source_path, prompt, model, "gpt-image-2", "png")


def run_gemini(
    source_path: Path,
    prompt: str,
    model: str,
    max_spend: str | None,
    transport: str,
) -> dict:
    if not GEMINI_HELPER.exists():
        fail(f"Gemini helper not found: {GEMINI_HELPER}")

    response = None
    transport_used = transport
    errors = []

    if transport in {"auto", "mpp"}:
        payload = {
            "model": model,
            "prompt": prompt,
            "referenceImages": [image_ref(source_path, source_path.stem)],
        }
        if max_spend:
            payload["maxSpend"] = max_spend
        try:
            response = run_json_helper(["node", str(GEMINI_HELPER)], payload)
            transport_used = "mpp"
        except RuntimeError as error:
            errors.append(str(error))
            if transport == "mpp":
                raise

    if response is None and transport in {"auto", "api"}:
        response = run_gemini_api(source_path, prompt, model)
        transport_used = "api"

    images = response.get("images", [])
    if not images or not images[0].get("base64"):
        raise RuntimeError(f"Gemini returned no inline image. Text: {response.get('text', '')[:300]}")
    return {
        "provider": "gemini",
        "model": response.get("model", model),
        "revised_prompt": response.get("text", ""),
        "mime_type": images[0].get("mime_type", "image/png"),
        "raw_bytes": base64.b64decode(images[0]["base64"]),
        "remote_url": None,
        "transport": transport_used,
        "transport_errors": errors,
    }


def write_result(
    provider_root: Path,
    target: str,
    prompt: str,
    source_path: Path,
    source_image: Image.Image,
    response: dict,
) -> dict:
    rel = Path(target)
    output_dir = provider_root / rel.parent / rel.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    prompt_path = output_dir / "prompt.txt"
    prompt_path.write_text(prompt + "\n", encoding="utf-8")

    source_copy = output_dir / f"source{source_path.suffix.lower()}"
    if not source_copy.exists():
        source_copy.write_bytes(source_path.read_bytes())

    raw_extension = extension_for_mime(response["mime_type"])
    raw_path = output_dir / f"raw{raw_extension}"
    raw_path.write_bytes(response["raw_bytes"])

    normalized_path = output_dir / "normalized.png"
    if normalized_path.exists():
        normalized_path.unlink()
    try:
        normalized = verify_generated_image(source_image, response["raw_bytes"])
    except RuntimeError as error:
        raise RuntimeError(f"{error}; raw output saved at {raw_path}") from error
    normalized.save(normalized_path)

    meta = {
        "status": "ok",
        "target": target,
        "provider": response["provider"],
        "model": response["model"],
        "source_path": str(source_path),
        "source_size": list(source_image.size),
        "source_has_alpha": source_has_alpha(source_image),
        "prompt_path": str(prompt_path),
        "raw_output": str(raw_path),
        "normalized_output": str(normalized_path),
        "mime_type": response["mime_type"],
        "remote_url": response["remote_url"],
        "provider_text": response["revised_prompt"],
        "transport": response.get("transport"),
        "transport_errors": response.get("transport_errors", []),
    }
    meta_path = output_dir / "meta.json"
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta


def output_dir_for_target(provider_root: Path, target: str) -> Path:
    rel = Path(target)
    return provider_root / rel.parent / rel.stem


def recover_existing_raw_result(provider_root: Path, target: str, source_path: Path, prompt: str) -> dict | None:
    output_dir = output_dir_for_target(provider_root, target)
    raw_candidates = sorted(output_dir.glob("raw.*"))
    if not raw_candidates:
        return None
    raw_path = raw_candidates[0]
    mime_type, _encoding = mimetypes.guess_type(raw_path.name)
    return write_result(
        provider_root,
        target,
        prompt,
        source_path,
        read_source_image(source_path),
        {
            "provider": provider_root.name,
            "model": "recovered-existing-raw",
            "revised_prompt": "",
            "mime_type": mime_type or "image/png",
            "raw_bytes": raw_path.read_bytes(),
            "remote_url": None,
        },
    )


def load_manifest_entries(manifest_path: Path) -> list[dict]:
    if not manifest_path.exists():
        return []
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def load_existing_meta_entries(provider_root: Path) -> list[dict]:
    entries = []
    for meta_path in sorted(provider_root.rglob("meta.json")):
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("status") == "ok" and data.get("target"):
            entries.append(data)
    return entries


def upsert_manifest_entry(manifest: list[dict], index_by_target: dict[str, int], entry: dict, manifest_path: Path) -> None:
    target = entry.get("target")
    if target in index_by_target:
        manifest[index_by_target[target]] = entry
    else:
        index_by_target[target] = len(manifest)
        manifest.append(entry)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def is_provider_fatal_error(provider: str, error: Exception) -> bool:
    message = str(error).lower()
    if provider != "gemini":
        return False
    return (
        "payment verification failed" in message
        or "credits are depleted" in message
        or "resource_exhausted" in message
    )


def is_retryable_fal_error(error: Exception) -> bool:
    message = str(error).lower()
    return any(
        fragment in message
        for fragment in (
            "fetch failed",
            "timed out",
            "timeout",
            "temporary failure",
            "nodename nor servname provided",
            "connection reset",
            "429",
            "500",
            "502",
            "503",
            "504",
            "download failed",
        )
    )


def model_for_provider(provider: str, fal_mpp_model: str, grok_model: str, gpt_image_2_model: str, gemini_model: str) -> str:
    if provider == "fal-mpp":
        return fal_mpp_model
    if provider == "grok":
        return grok_model
    if provider == "gpt-image-2":
        return gpt_image_2_model
    return gemini_model


def run_provider(
    provider: str,
    targets: list[str],
    output_root: Path,
    fal_mpp_model: str,
    fal_mpp_max_spend: str | None,
    grok_model: str,
    gpt_image_2_model: str,
    gemini_model: str,
    gemini_max_spend: str | None,
    gemini_transport: str,
    resume: bool,
) -> list[dict]:
    provider_root = output_root / provider
    provider_root.mkdir(parents=True, exist_ok=True)
    manifest_path = provider_root / "manifest.json"
    manifest = load_manifest_entries(manifest_path) if resume else []
    index_by_target = {entry.get("target"): index for index, entry in enumerate(manifest) if entry.get("target")}
    if resume:
        for entry in load_existing_meta_entries(provider_root):
            target = entry.get("target")
            if target and target not in index_by_target:
                index_by_target[target] = len(manifest)
                manifest.append(entry)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    completed = {
        entry.get("target")
        for entry in manifest
        if entry.get("status") == "ok" and entry.get("target")
    }
    print(
        f"[{provider}] selected={len(targets)} completed={len([target for target in targets if target in completed])} remaining={len([target for target in targets if target not in completed])}",
        flush=True,
    )

    for index, target in enumerate(targets, start=1):
        if resume and target in completed:
            print(f"[{provider}] {index}/{len(targets)} skip {target}", flush=True)
            continue
        source_path = (IMAGE_ROOT / target).resolve()
        print(f"[{provider}] {index}/{len(targets)} start {target}", flush=True)
        if not source_path.exists():
            upsert_manifest_entry(
                manifest,
                index_by_target,
                {
                    "status": "error",
                    "target": target,
                    "provider": provider,
                    "error": f"Missing target image: {target}",
                },
                manifest_path,
            )
            continue

        try:
            source_image = read_source_image(source_path)
            prompt = build_prompt(target, source_image.size, source_has_alpha(source_image), has_json_sidecar(source_path))
            if resume:
                recovered_entry = recover_existing_raw_result(provider_root, target, source_path, prompt)
                if recovered_entry:
                    upsert_manifest_entry(manifest, index_by_target, recovered_entry, manifest_path)
                    print(f"[{provider}] {index}/{len(targets)} recovered {target}", flush=True)
                    continue

            if provider == "fal-mpp":
                response = run_fal_mpp(source_path, prompt, fal_mpp_model, fal_mpp_max_spend)
            elif provider == "grok":
                response = run_grok(source_path, prompt, grok_model)
            elif provider == "gpt-image-2":
                response = run_gpt_image_2(source_path, prompt, gpt_image_2_model)
            elif provider == "gemini":
                response = run_gemini(source_path, prompt, gemini_model, gemini_max_spend, gemini_transport)
            else:
                raise RuntimeError(f"Unsupported provider: {provider}")

            entry = write_result(provider_root, target, prompt, source_path, source_image, response)
            upsert_manifest_entry(manifest, index_by_target, entry, manifest_path)
            print(f"[{provider}] {index}/{len(targets)} ok {target}", flush=True)
        except Exception as error:
            entry = {
                "status": "error",
                "target": target,
                "provider": provider,
                "model": model_for_provider(provider, fal_mpp_model, grok_model, gpt_image_2_model, gemini_model),
                "error": str(error),
            }
            upsert_manifest_entry(manifest, index_by_target, entry, manifest_path)
            print(f"[{provider}] {index}/{len(targets)} error {target}: {error}", flush=True)
            if provider in FAL_PROVIDERS:
                continue
            if is_provider_fatal_error(provider, error):
                break

    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Grok and Gemini redo sweeps over the original-art-redo-pack.")
    parser.add_argument(
        "--targets",
        default="",
        help="Optional comma-separated asset paths relative to output/original-art-redo-pack/images.",
    )
    parser.add_argument(
        "--target-mode",
        default=DEFAULT_TARGET_MODE,
        help="Target discovery mode: pilot, all-redrawable, or all-images. Default: pilot",
    )
    parser.add_argument(
        "--include-glob",
        action="append",
        default=[],
        help="Optional glob filter to include only matching targets. Repeatable.",
    )
    parser.add_argument(
        "--exclude-glob",
        action="append",
        default=[],
        help="Optional glob filter to exclude matching targets. Repeatable.",
    )
    parser.add_argument(
        "--start-index",
        type=int,
        default=0,
        help="Start index into the discovered target list after filtering. Default: 0",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional maximum number of targets to process after start-index. Default: 0 (no limit)",
    )
    parser.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Resume from existing manifest.json entries and skip successful targets. Default: true",
    )
    parser.add_argument(
        "--providers",
        default="grok,gemini",
        help="Comma-separated providers to run. Supported: fal-mpp, grok, gpt-image-2, gemini.",
    )
    parser.add_argument(
        "--output-root",
        default=str(PACK_ROOT),
        help="Root directory where provider folders will be written.",
    )
    parser.add_argument(
        "--fal-mpp-model",
        default=DEFAULT_FAL_MPP_MODEL,
        help="Fal model through Tempo MPP. Default: xai/grok-imagine-image/edit",
    )
    parser.add_argument(
        "--fal-mpp-max-spend",
        default="0.03",
        help="Optional MPP max spend per Fal request.",
    )
    parser.add_argument(
        "--grok-model",
        default=DEFAULT_GROK_MODEL,
        help="Fal Grok edit model. Default: xai/grok-imagine-image/edit",
    )
    parser.add_argument(
        "--gpt-image-2-model",
        default=DEFAULT_GPT_IMAGE_2_MODEL,
        help="Fal OpenAI GPT Image 2 edit model. Default: openai/gpt-image-2/edit",
    )
    parser.add_argument(
        "--gemini-model",
        default=DEFAULT_GEMINI_MODEL,
        help="Gemini model or alias. Aliases: nanobanana, nanobanana-2.",
    )
    parser.add_argument(
        "--gemini-max-spend",
        default="0.02",
        help="Optional MPP max spend per Gemini request.",
    )
    parser.add_argument(
        "--gemini-transport",
        default=DEFAULT_GEMINI_TRANSPORT,
        help="Gemini transport: auto, mpp, or api. Default: auto",
    )
    args = parser.parse_args()

    providers = parse_csv(args.providers)
    unsupported = [provider for provider in providers if provider not in {*FAL_PROVIDERS, "gemini"}]
    if unsupported:
        fail(f"Unsupported providers: {', '.join(unsupported)}")
    if args.gemini_transport not in {"auto", "mpp", "api"}:
        fail(f"Unsupported Gemini transport: {args.gemini_transport}")
    if args.target_mode not in {"pilot", "all-redrawable", "all-images"}:
        fail(f"Unsupported target mode: {args.target_mode}")

    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    targets = parse_csv(args.targets) if args.targets else discover_targets(args.target_mode)
    targets = apply_match_filters(targets, args.include_glob, args.exclude_glob)
    targets = sorted(dict.fromkeys(targets))
    if args.start_index > 0:
        targets = targets[args.start_index :]
    if args.limit > 0:
        targets = targets[: args.limit]
    if not targets:
        fail("No targets matched the current filters")

    run_summary = {
        "targets": targets,
        "target_mode": args.target_mode,
        "include_glob": args.include_glob,
        "exclude_glob": args.exclude_glob,
        "start_index": args.start_index,
        "limit": args.limit,
        "providers": providers,
        "fal_mpp_model": args.fal_mpp_model,
        "fal_mpp_max_spend": args.fal_mpp_max_spend,
        "grok_model": args.grok_model,
        "gpt_image_2_model": args.gpt_image_2_model,
        "gemini_model": resolve_gemini_model(args.gemini_model),
        "gemini_max_spend": args.gemini_max_spend,
        "gemini_transport": args.gemini_transport,
        "resume": args.resume,
        "results": {},
    }

    for provider in providers:
        run_summary["results"][provider] = run_provider(
            provider=provider,
            targets=targets,
            output_root=output_root,
            fal_mpp_model=args.fal_mpp_model,
            fal_mpp_max_spend=args.fal_mpp_max_spend,
            grok_model=args.grok_model,
            gpt_image_2_model=args.gpt_image_2_model,
            gemini_model=resolve_gemini_model(args.gemini_model),
            gemini_max_spend=args.gemini_max_spend,
            gemini_transport=args.gemini_transport,
            resume=args.resume,
        )

    summary_path = output_root / "redo-manifest.json"
    summary_path.write_text(json.dumps(run_summary, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
