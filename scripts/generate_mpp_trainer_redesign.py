#!/usr/bin/env python3
"""Generate MPP-paid Mogger Mon trainer atlases and normalize them into runtime frames."""

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

from mogmon_normalizer import pixelify_image


ROOT = Path(__file__).resolve().parent.parent
TRAINER_DIR = ROOT / "assets" / "images" / "trainer"
FAL_MPP_HELPER = Path(__file__).with_name("fal_mpp_generate.mjs")
FAL_DIRECT_HELPER = Path(__file__).with_name("fal_direct_generate.mjs")
DEFAULT_EDIT_MODEL = "xai/grok-imagine-image/edit"
DEFAULT_BG_REMOVE_MODEL = "fal-ai/bria/background/remove"
DEFAULT_MAX_SPEND = "0.03"

ROLE_OVERRIDES = {
    "player_m": "default Mogmaster, front-view lead runner with techwear jacket, amber trims, compact headset visor, and grounded street-hero energy",
    "player_f": "default Mogmaster, front-view lead runner with cropped techwear jacket, amber trims, compact headset visor, and grounded street-hero energy",
    "player_m_2": "alternate Mogmaster with sharper hustle-brawler silhouette, layered outerwear, and courier attitude",
    "player_f_2": "alternate Mogmaster with sharper hustle-brawler silhouette, layered outerwear, and courier attitude",
    "player_m_alternate": "festival-night Mogmaster with bright tape accents, utility straps, and scrappy signal-runner swagger",
    "player_f_alternate": "festival-night Mogmaster with bright tape accents, utility straps, and scrappy signal-runner swagger",
    "rival_m": "rival Mogmaster with chaos-entrepreneur energy, tailored streetwear, expensive sneakers, and smug challenger presence",
    "rival_f": "rival Mogmaster with media-mogul energy, tailored streetwear, jewelry accents, and smug challenger presence",
    "trainer_m_back": "rear battle pose of the default Mogmaster, modular Cryotank belt, no ball motifs",
    "trainer_f_back": "rear battle pose of the default Mogmaster, modular Cryotank belt, no ball motifs",
    "trainer_m_back_pb": "rear battle throw atlas using a compact glass Cryotank capsule with cold-blue core lights",
    "trainer_f_back_pb": "rear battle throw atlas using a compact glass Cryotank capsule with cold-blue core lights",
}

BRAINROT_CLASS_WORDS = {
    "ace trainer": "Looksmaxxer",
    "snow ace trainer": "Snowmaxxer",
    "youngster": "Mogster",
    "school kid": "Homeworkcel",
    "preschooler": "Tiny Mogster",
    "bug catcher": "Bugcel",
    "bug type superfan": "Bugcel Superfan",
    "aroma lady": "Scentmaxxer",
    "artist": "Paintcel",
    "backers": "Hype Backers",
    "backpacker": "Packmaxxer",
    "baker": "Doughmaxxer",
    "beauty": "Facecard",
    "biker": "Crashout Rider",
    "bird keeper": "Birdcel",
    "black belt": "Gymcel",
    "breeder": "Geneplug",
    "camper": "Tentcel",
    "clerk": "Retail Grinder",
    "collector": "Hoardmaxxer",
    "cyclist": "Wheelmaxxer",
    "dancer": "Emote Dancer",
    "depot agent": "Railplug",
    "doctor": "Medmaxxer",
    "dragon tamer": "Drip Tamer",
    "fairy tale girl": "Lore Girl",
    "firebreather": "Heatspitter",
    "fisherman": "Fishmaxxer",
    "guitarist": "Riffmaxxer",
    "harlequin": "Jestercel",
    "hex maniac": "Hexmaxxer",
    "hiker": "Hillcel",
    "hooligans": "Crashout Duo",
    "hoopster": "Hoopmaxxer",
    "infielder": "Ballpark Grinder",
    "interviewers": "Content Crew",
    "janitor": "Mopmaxxer",
    "linebacker": "Tacklemaxxer",
    "maid": "Chorecore",
    "musician": "Beatmaxxer",
    "mysterious sisters": "Aura Sisters",
    "nursery aide": "Pod Aide",
    "officer": "Badgecel",
    "parasol lady": "Shade Queen",
    "pilot": "Cloudmaxxer",
    "pokefan": "Signal Fan",
    "psychic": "Vibe Reader",
    "ranger": "Rizz Ranger",
    "rich": "Trustfund Mog",
    "rich kid": "Trustfund Kid",
    "roughneck": "Crashout",
    "ruin maniac": "Relic Goblin",
    "sailor": "Dockmaxxer",
    "scientist": "Labmaxxer",
    "scuba diver": "Depthcel",
    "smasher": "Smashmaxxer",
    "snow worker": "Snow Grinder",
    "striker": "Goalmaxxer",
    "swimmer": "Poolmaxxer",
    "twins": "Duo Mogsters",
    "veteran": "Oldhead",
    "waiter": "Traymaxxer",
    "worker": "Grindset Worker",
    "young couple": "Situationship Duo",
}


def fail(message: str) -> None:
    raise SystemExit(message)


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def discover_targets() -> list[str]:
    return [path.stem for path in sorted(TRAINER_DIR.glob("*.png")) if path.with_suffix(".json").exists()]


def humanize_stem(stem: str) -> str:
    tokens = [token for token in stem.replace("-", "_").split("_") if token]
    tokens = [token for token in tokens if token not in {"m", "f", "male", "female"}]
    if tokens and tokens[-1].isdigit():
        tokens = tokens[:-1]
    return " ".join(tokens)


def role_for_target(target: str) -> str:
    if target in ROLE_OVERRIDES:
        return ROLE_OVERRIDES[target]
    plain = humanize_stem(target)
    class_name = BRAINROT_CLASS_WORDS.get(plain, None)
    if class_name:
        return f"{class_name}, original brainrot trainer archetype based on the {plain} battle role"
    return f"original brainrot Mogmaster archetype for {plain or target}, redesigned enough to avoid existing franchise likeness"


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


def bytes_ref(image_bytes: bytes, file_name: str = "trainer.png") -> dict:
    mime_type, _encoding = mimetypes.guess_type(file_name)
    return {
        "base64": base64.b64encode(image_bytes).decode("ascii"),
        "mime_type": mime_type or "image/png",
        "file_name": file_name,
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
    req = urllib_request.Request(url, headers={"User-Agent": "mogmon-trainer-mpp/1.0"})
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


def run_edit(source_image: Path, prompt: str, model: str, max_spend: str, transport: str) -> dict:
    response = run_helper(
        {
            "model": model,
            "prompt": prompt,
            "referenceImages": [image_ref(source_image)],
            "outputFormat": "png",
            "resolution": "1k",
            "numImages": 1,
            "maxSpend": max_spend,
        },
        transport=transport,
    )
    images = response.get("images", [])
    if not images or not images[0].get("url"):
        raise RuntimeError("Fal MPP trainer edit returned no image URL")
    raw_bytes, mime_type = download_file(images[0]["url"])
    return {
        "model": response.get("model", f"mpp:{model}"),
        "mime_type": mime_type,
        "raw_bytes": raw_bytes,
        "remote_url": images[0]["url"],
    }


def run_background_remove(image_bytes: bytes, model: str, max_spend: str, transport: str) -> dict:
    image = bytes_ref(image_bytes, "trainer-raw.png")
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
    bg_bytes, mime_type = download_file(images[0]["url"])
    return {
        "model": response.get("model", f"mpp:{model}"),
        "mime_type": mime_type,
        "raw_bytes": bg_bytes,
        "remote_url": images[0]["url"],
    }


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


def trainer_pixel_base(output_width: int) -> int:
    if output_width <= 0:
        return 1
    return max(1, min(output_width, max(12, int(round(output_width * 0.9)))))


def load_trainer_frames(source_json: Path) -> list[dict]:
    atlas = json.loads(source_json.read_text(encoding="utf-8"))
    if "textures" in atlas:
        return atlas["textures"][0]["frames"]
    if "frames" in atlas and isinstance(atlas["frames"], list):
        return atlas["frames"]
    if "frames" in atlas and isinstance(atlas["frames"], dict):
        return list(atlas["frames"].values())
    raise KeyError("Unsupported trainer atlas JSON format: expected textures[] or frames")


def normalize_atlas(source_png: Path, source_json: Path, generated_bytes: bytes) -> tuple[Image.Image, Image.Image]:
    source = Image.open(source_png).convert("RGBA")
    frames = load_trainer_frames(source_json)
    generated = Image.open(BytesIO(generated_bytes)).convert("RGBA").resize(source.size, Image.NEAREST)

    normalized = Image.new("RGBA", source.size, (0, 0, 0, 0))
    single_frame_mode = len(frames) == 1
    whole_generated = strip_border_background(generated)
    for frame in frames:
        rect = frame["frame"]
        frame_box = (rect["x"], rect["y"], rect["x"] + rect["w"], rect["y"] + rect["h"])
        source_frame = source.crop(frame_box)
        target_bbox = alpha_bbox(source_frame) or (0, 0, rect["w"], rect["h"])

        cleaned = whole_generated if single_frame_mode else strip_border_background(generated.crop(frame_box))
        content_bbox = alpha_bbox(cleaned)
        if content_bbox is None:
            cleaned = source_frame
            content_bbox = alpha_bbox(cleaned)
        if content_bbox is None:
            continue

        content = cleaned.crop(content_bbox)
        max_width = max(1, target_bbox[2] - target_bbox[0])
        max_height = max(1, target_bbox[3] - target_bbox[1])
        scale = max(min(max_width / content.width, max_height / content.height), 0.05)
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


def build_prompt(role: str, source_size: tuple[int, int]) -> str:
    return "\n".join(
        [
            "Edit this exact trainer sprite atlas into an original Mogger Mon trainer design.",
            f"Role: {role}.",
            f"Reference atlas size: {source_size[0]}x{source_size[1]}.",
            "",
            "Hard constraints:",
            "- preserve the exact canvas size, frame count, frame boxes, transparent background, and pose coverage from the reference image",
            "- preserve the same handheld-era pixel art readability and same overall silhouette scale",
            "- keep each occupied frame filled by one complete human trainer, never fragments, cropped limbs, or duplicate collages",
            "- preserve the same gesture and animation rhythm as the reference image",
            "- use an original brainrot urban-future look: taped techwear, utility straps, headset pieces, weird sneakers, layered jackets, and Cryotank accessories",
            "- if the atlas includes a throw or summon action, replace any ball-like prop with a compact glass Cryotank capsule device",
            "- change faces, hair, outfits, props, and color accents enough that this is not a direct likeness of any existing franchise character or real person",
            "- output exactly one atlas; do not tile, repeat, collage, or show multiple alternate versions in one image",
            "- no logos, no text, no background scene, no extra particles, no franchise-coded costume motifs",
            "- output only the finished trainer sprite atlas on transparency",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate MPP-paid Mogger Mon trainer atlases.")
    parser.add_argument("--all", action="store_true", help="Process every trainer PNG with a JSON atlas sidecar.")
    parser.add_argument(
        "--targets",
        default="player_m,player_f,player_m_2,player_f_2,player_m_alternate,player_f_alternate,rival_m,rival_f,trainer_m_back,trainer_f_back,trainer_m_back_pb,trainer_f_back_pb",
        help="Comma-separated trainer atlas basenames to process when --all is not set.",
    )
    parser.add_argument("--output-root", default="output/trainer-mpp-redesign")
    parser.add_argument("--model", default=DEFAULT_EDIT_MODEL)
    parser.add_argument("--max-spend", default=DEFAULT_MAX_SPEND)
    parser.add_argument("--bg-remove-model", default=DEFAULT_BG_REMOVE_MODEL)
    parser.add_argument(
        "--transport",
        choices=("mpp", "direct"),
        default="mpp",
        help="Fal transport. Use mpp for Tempo MPP payment or direct for FAL_API_KEY. Default: mpp",
    )
    parser.add_argument("--no-bg-remove", action="store_true")
    parser.add_argument("--no-install", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    helper = helper_for_transport(args.transport)
    if not helper.exists():
        fail(f"Missing Fal helper: {helper}")

    targets = discover_targets() if args.all else parse_csv(args.targets)
    if args.start_index:
        targets = targets[args.start_index :]
    if args.limit > 0:
        targets = targets[: args.limit]

    output_root = (ROOT / args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path = output_root / "manifest.json"
    manifest = []
    if manifest_path.exists() and not args.no_resume:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = []
    by_target = {entry.get("target"): index for index, entry in enumerate(manifest) if entry.get("target")}

    completed = {entry.get("target") for entry in manifest if entry.get("status") == "ok" and entry.get("target")}
    print(
        f"[trainer-mpp] selected={len(targets)} completed={len([t for t in targets if t in completed])} remaining={len([t for t in targets if t not in completed])}",
        flush=True,
    )

    for index, target in enumerate(targets, start=1):
        source_png = TRAINER_DIR / f"{target}.png"
        source_json = TRAINER_DIR / f"{target}.json"
        target_output = output_root / target
        target_output.mkdir(parents=True, exist_ok=True)

        if target in completed and not args.no_resume:
            print(f"[trainer-mpp] {index}/{len(targets)} skip {target}", flush=True)
            continue
        print(f"[trainer-mpp] {index}/{len(targets)} start {target}", flush=True)

        try:
            if not source_png.exists() or not source_json.exists():
                raise RuntimeError(f"Missing trainer atlas source for {target}")
            source_image = Image.open(source_png).convert("RGBA")
            prompt = build_prompt(role_for_target(target), source_image.size)
            edit = run_edit(source_png, prompt, args.model, args.max_spend, args.transport)
            working_bytes = edit["raw_bytes"]
            bg_remove = None
            if not args.no_bg_remove:
                bg_remove = run_background_remove(working_bytes, args.bg_remove_model, args.max_spend, args.transport)
                working_bytes = bg_remove["raw_bytes"]

            generated, normalized = normalize_atlas(source_png, source_json, working_bytes)
            raw_path = target_output / "raw.png"
            raw_path.write_bytes(edit["raw_bytes"])
            bg_removed_path = None
            if bg_remove:
                bg_removed_path = target_output / "bg-removed.png"
                bg_removed_path.write_bytes(bg_remove["raw_bytes"])
            generated_path = target_output / "generated-resized.png"
            generated.save(generated_path)
            normalized_path = target_output / "normalized.png"
            normalized.save(normalized_path)
            prompt_path = target_output / "prompt.txt"
            prompt_path.write_text(prompt + "\n", encoding="utf-8")

            if not args.no_install:
                normalized.save(source_png)

            entry = {
                "status": "ok",
                "target": target,
                "edit_model": edit["model"],
                "bg_remove_model": bg_remove["model"] if bg_remove else None,
                "mime_type": edit["mime_type"],
                "source_png": str(source_png),
                "source_json": str(source_json),
                "raw_output": str(raw_path),
                "bg_removed_output": str(bg_removed_path) if bg_removed_path else None,
                "resized_output": str(generated_path),
                "normalized_output": str(normalized_path),
                "prompt_path": str(prompt_path),
                "remote_url": edit["remote_url"],
                "bg_remote_url": bg_remove["remote_url"] if bg_remove else None,
                "installed": not args.no_install,
            }
            print(f"[trainer-mpp] {index}/{len(targets)} ok {target}", flush=True)
        except Exception as error:
            entry = {
                "status": "error",
                "target": target,
                "error": str(error),
                "installed": False,
            }
            print(f"[trainer-mpp] {index}/{len(targets)} error {target}: {error}", flush=True)

        if target in by_target:
            manifest[by_target[target]] = entry
        else:
            by_target[target] = len(manifest)
            manifest.append(entry)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
