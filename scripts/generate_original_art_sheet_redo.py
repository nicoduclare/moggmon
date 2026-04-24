#!/usr/bin/env python3
"""Generate sheet-based redraws for small non-character original-art assets."""

from __future__ import annotations

import argparse
import base64
import fnmatch
import json
import mimetypes
import shutil
import subprocess
from collections import deque
from io import BytesIO
from pathlib import Path
from urllib import request as urllib_request

from PIL import Image, ImageFilter


ROOT = Path(__file__).resolve().parent.parent
PACK_ROOT = ROOT / "output" / "original-art-redo-pack"
IMAGE_ROOT = PACK_ROOT / "images"
ASSET_ROOT = ROOT / "assets" / "images"
FAL_HELPER = Path(__file__).with_name("fal_grok_edit.mjs")

DEFAULT_OUTPUT_ROOT = ROOT / "output" / "original-art-sheet-redo"
DEFAULT_MODEL = "openai/gpt-image-2/edit"
DEFAULT_IMAGE_SIZE = "1536x1024"
DEFAULT_CHUNKS = 6
DEFAULT_PADDING = 8
DEFAULT_CELL_SIZE = 128
MIN_ALPHA_PIXELS = 8
DEFAULT_MASK_DILATION = 4
DEFAULT_BG_TOLERANCE = 18

INCLUDED_DIRS = {"items", "pokeball", "egg", "effects", "mystery-encounters"}
EXCLUDED_DIRS = {"pokemon", "character", "trainer", "arenas", "cg", "events", "inputs", "ui"}
ACTOR_DIRS = {"pokemon", "character", "trainer"}
SKIP_ROOT_PREFIXES = ("types", "statuses", "categories", "logo")
SKIP_SUBSTRINGS = ("oauth", "github_icon", "discord_icon", ".ds_store")


def fail(message: str) -> None:
    raise SystemExit(message)


def parse_image_size(value: str) -> tuple[int, int]:
    width, height = value.lower().split("x", 1)
    return int(width), int(height)


def is_gpt_image_2_model(model: str) -> bool:
    return model.strip().lower() == "openai/gpt-image-2/edit"


def fal_image_size_value(model: str, image_size: str) -> str | dict:
    if is_gpt_image_2_model(model) and "x" in image_size.lower():
        width, height = parse_image_size(image_size)
        return {"width": width, "height": height}
    return image_size


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
    req = urllib_request.Request(url, headers={"User-Agent": "mogmon-sheet-redo/1.0"})
    with urllib_request.urlopen(req, timeout=300) as response:
        mime_type = response.headers.get_content_type() or "image/png"
        return response.read(), mime_type


def extension_for_mime(mime_type: str) -> str:
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
    }.get(mime_type, ".png")


def should_include(
    rel: Path,
    image: Image.Image,
    max_asset_size: int,
    all_folders: bool,
    include_actors: bool,
    include_skipped: bool,
) -> bool:
    rel_text = rel.as_posix().lower()
    top = rel.parts[0]
    excluded_dirs = set() if include_actors else (ACTOR_DIRS if all_folders else EXCLUDED_DIRS)
    if top in excluded_dirs:
        return False
    if not all_folders and top not in INCLUDED_DIRS:
        return False
    if not include_skipped and any(part.startswith(".") for part in rel.parts):
        return False
    if not include_skipped and any(token in rel_text for token in SKIP_SUBSTRINGS):
        return False
    if not include_skipped and len(rel.parts) == 1 and rel.name.lower().startswith(SKIP_ROOT_PREFIXES):
        return False
    return max(image.size) <= max_asset_size


def discover_targets(
    max_asset_size: int,
    include_globs: list[str],
    exclude_globs: list[str],
    all_folders: bool,
    include_actors: bool,
    include_skipped: bool,
) -> list[dict]:
    targets = []
    for path in sorted(IMAGE_ROOT.rglob("*.png")):
        rel = path.relative_to(IMAGE_ROOT)
        rel_text = rel.as_posix()
        if include_globs and not any(fnmatch.fnmatch(rel_text, pattern) for pattern in include_globs):
            continue
        if exclude_globs and any(fnmatch.fnmatch(rel_text, pattern) for pattern in exclude_globs):
            continue
        image = Image.open(path).convert("RGBA")
        if not should_include(rel, image, max_asset_size, all_folders, include_actors, include_skipped):
            continue
        targets.append(
            {
                "target": rel_text,
                "path": str(path),
                "width": image.width,
                "height": image.height,
                "max_side": max(image.size),
            }
        )
    return targets


def split_evenly(targets: list[dict], chunk_count: int) -> list[list[dict]]:
    chunks = [[] for _ in range(max(1, chunk_count))]
    for index, target in enumerate(targets):
        chunks[index % len(chunks)].append(target)
    return [chunk for chunk in chunks if chunk]


def split_contiguous(targets: list[dict], chunk_count: int) -> list[list[dict]]:
    chunk_count = max(1, chunk_count)
    chunk_size = max(1, (len(targets) + chunk_count - 1) // chunk_count)
    return [targets[index : index + chunk_size] for index in range(0, len(targets), chunk_size)]


def fit_size(source_size: tuple[int, int], max_size: tuple[int, int]) -> tuple[int, int]:
    source_w, source_h = source_size
    max_w, max_h = max_size
    scale = min(max_w / source_w, max_h / source_h)
    return max(1, int(source_w * scale)), max(1, int(source_h * scale))


def resize_nearest(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    return image.resize(size, Image.Resampling.NEAREST)


def alpha_bbox(image: Image.Image) -> tuple[int, int, int, int] | None:
    return image.getchannel("A").getbbox()


def alpha_pixel_count(image: Image.Image) -> int:
    alpha = image.getchannel("A")
    histogram = alpha.histogram()
    return sum(histogram[1:])


def color_distance_ok(color: tuple[int, int, int, int], bg: tuple[int, int, int], tolerance: int) -> bool:
    return max(abs(color[channel] - bg[channel]) for channel in range(3)) <= tolerance


def infer_edge_bg_color(image: Image.Image) -> tuple[int, int, int]:
    pixels = image.convert("RGBA").load()
    width, height = image.size
    samples = [
        pixels[0, 0],
        pixels[width - 1, 0],
        pixels[0, height - 1],
        pixels[width - 1, height - 1],
    ]
    # Use the darkest corner. GPT Image 2 sheet previews usually come back on black.
    return min((sample[:3] for sample in samples), key=sum)


def remove_edge_background(image: Image.Image, tolerance: int) -> Image.Image:
    """Preview-only background key: remove bg pixels connected to crop edges."""
    src = image.convert("RGBA")
    width, height = src.size
    if width == 0 or height == 0:
        return src

    bg = infer_edge_bg_color(src)
    pixels = src.load()
    visited = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()

    def enqueue_if_bg(x: int, y: int) -> None:
        index = y * width + x
        if visited[index]:
            return
        visited[index] = 1
        if color_distance_ok(pixels[x, y], bg, tolerance):
            queue.append((x, y))

    for x in range(width):
        enqueue_if_bg(x, 0)
        enqueue_if_bg(x, height - 1)
    for y in range(1, height - 1):
        enqueue_if_bg(0, y)
        enqueue_if_bg(width - 1, y)

    while queue:
        x, y = queue.popleft()
        r, g, b, _a = pixels[x, y]
        pixels[x, y] = (r, g, b, 0)
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if nx < 0 or ny < 0 or nx >= width or ny >= height:
                continue
            index = ny * width + nx
            if visited[index]:
                continue
            visited[index] = 1
            if color_distance_ok(pixels[nx, ny], bg, tolerance):
                queue.append((nx, ny))
    return src


def validate_nonblank(image: Image.Image, label: str) -> None:
    count = alpha_pixel_count(image)
    if count < MIN_ALPHA_PIXELS:
        raise RuntimeError(f"{label} is blank or nearly blank after cut ({count} alpha pixels)")


def build_sheet(
    chunk: list[dict],
    sheet_size: tuple[int, int],
    padding: int,
    cell_size_arg: int,
    fixed_cell_size: bool,
    output_dir: Path,
    index: int,
) -> dict:
    sheet_width, sheet_height = sheet_size
    max_side = max(target["max_side"] for target in chunk)
    cell_size = cell_size_arg if fixed_cell_size else max(cell_size_arg, max_side + padding * 2)
    cols = sheet_width // cell_size
    rows = sheet_height // cell_size
    capacity = cols * rows
    if capacity < len(chunk):
        raise RuntimeError(
            f"chunk {index} has {len(chunk)} assets but only {capacity} fit in {sheet_width}x{sheet_height} with cell {cell_size}"
        )

    sheet = Image.new("RGBA", sheet_size, (0, 0, 0, 0))
    entries = []
    for item_index, target in enumerate(chunk):
        source = Image.open(target["path"]).convert("RGBA")
        col = item_index % cols
        row = item_index // cols
        cell_x = col * cell_size
        cell_y = row * cell_size
        reference_size = fit_size(source.size, (cell_size - padding * 2, cell_size - padding * 2))
        reference = resize_nearest(source, reference_size)
        paste_x = cell_x + (cell_size - reference.width) // 2
        paste_y = cell_y + (cell_size - reference.height) // 2
        sheet.alpha_composite(reference, (paste_x, paste_y))
        entries.append(
            {
                **target,
                "source_size": {"w": source.width, "h": source.height},
                "cell": {"x": cell_x, "y": cell_y, "w": cell_size, "h": cell_size},
                "reference_box": {"x": paste_x, "y": paste_y, "w": reference.width, "h": reference.height},
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    sheet_path = output_dir / f"sheet-{index:02d}.png"
    manifest_path = output_dir / f"sheet-{index:02d}.json"
    sheet.save(sheet_path)
    manifest = {
        "index": index,
        "sheet": str(sheet_path),
        "sheet_size": list(sheet_size),
        "cell_size": cell_size,
        "fixed_cell_size": fixed_cell_size,
        "cols": cols,
        "rows": rows,
        "padding": padding,
        "entries": entries,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def build_prompt(manifest: dict) -> str:
    return "\n".join(
        [
            "Edit this exact transparent game item sprite sheet into original Mogger Mon inventory art.",
            f"Canvas: {manifest['sheet_size'][0]}x{manifest['sheet_size'][1]} pixels.",
            f"Tiles: {len(manifest['entries'])}.",
            f"Grid: {manifest['cols']} columns x {manifest['rows']} rows; each occupied cell is {manifest['cell_size']}x{manifest['cell_size']} pixels.",
            "",
            "Hard constraints:",
            "- this is a technical sprite-sheet edit, not concept art and not a scene",
            "- return one PNG image with the exact same pixel dimensions as the input sheet",
            "- preserve true transparent alpha; no checkerboard preview, no matte, no background grid",
            "- all pixels outside the item silhouettes must remain fully transparent alpha=0",
            "- do not paint sheet-wide light, fog, atmosphere, shadows, gradients, or glow behind the sprites",
            "- keep one centered sprite in each occupied cell; do not merge cells or move sprites between cells",
            "- keep each sprite fully inside its cell with transparent space around it",
            "- do not add labels, numbers, captions, UI callouts, or extra objects",
            "- output finished crisp pixel art icons, not high-resolution rendered objects to be pixelified later",
            "- replace Pokeball/ball motifs with Mogger Mon Cryotanks: compact cryo canisters, glass chambers, seals, metal locks",
            "- replace berries/fruit/snacks with Mogger Mon Zaza/shroom consumables: fungal caps, stash packs, foil dose packets, powder jars",
            "- replace TM/memory/module motifs with BrainDance media: chrome wafers, data chips, compact memory discs",
            "- keep non-franchise utility identity readable: potion-like items still read as consumables, charms still read as charms, shards still read as shards",
            "",
            "Output only the edited sheet.",
        ]
    )


def build_alpha_mask(sheet_path: Path, output_dir: Path, index: int, dilation: int) -> Path:
    source = Image.open(sheet_path).convert("RGBA")
    mask = source.getchannel("A").point(lambda value: 255 if value else 0)
    if dilation > 0:
        mask = mask.filter(ImageFilter.MaxFilter(dilation * 2 + 1))
    mask_path = output_dir / f"sheet-{index:02d}.mask.png"
    mask.save(mask_path)
    return mask_path


def run_fal_sheet(
    manifest: dict,
    output_dir: Path,
    model: str,
    image_size: str,
    resolution: str | None,
    quality: str,
    background: str,
    mask_dilation: int,
    use_mask: bool,
) -> dict:
    sheet_path = Path(manifest["sheet"])
    prompt = build_prompt(manifest)
    prompt_path = output_dir / f"sheet-{manifest['index']:02d}.prompt.txt"
    prompt_path.write_text(prompt + "\n", encoding="utf-8")
    payload = {
        "model": model,
        "prompt": prompt,
        "referenceImages": [image_ref(sheet_path, sheet_path.stem)],
        "imageSize": fal_image_size_value(model, image_size),
        "quality": quality,
        "outputFormat": "png",
        "numImages": 1,
    }
    if not is_gpt_image_2_model(model):
        payload["background"] = background
        payload["inputFidelity"] = "high"
    if resolution and not is_gpt_image_2_model(model):
        payload["resolution"] = resolution
    mask_path = None
    if use_mask and is_gpt_image_2_model(model):
        mask_path = build_alpha_mask(sheet_path, output_dir, manifest["index"], mask_dilation)
        payload["maskImage"] = image_ref(mask_path, f"{sheet_path.stem}-mask")
    response = run_json_helper(payload)
    images = response.get("images") or []
    if not images or not images[0].get("url"):
        raise RuntimeError(f"FAL returned no image URL: {json.dumps(response)[:600]}")
    raw_bytes, mime_type = download_file(images[0]["url"])
    raw_path = output_dir / f"sheet-{manifest['index']:02d}.raw{extension_for_mime(mime_type)}"
    raw_path.write_bytes(raw_bytes)
    return {
        "model": response.get("model", f"fal:{model}"),
        "request_id": response.get("requestId"),
        "remote_url": images[0]["url"],
        "mime_type": mime_type,
        "raw_path": str(raw_path),
        "prompt_path": str(prompt_path),
        "mask_path": str(mask_path) if mask_path else None,
    }


def fit_cell_to_source(cell_image: Image.Image, source_size: tuple[int, int], target: str) -> Image.Image:
    bbox = alpha_bbox(cell_image)
    if bbox is None:
        raise RuntimeError(f"{target} has no alpha content in generated cell")
    subject = cell_image.crop(bbox)
    validate_nonblank(subject, target)
    out_w, out_h = source_size
    fitted_size = fit_size(subject.size, source_size)
    fitted = resize_nearest(subject, fitted_size)
    out = Image.new("RGBA", source_size, (0, 0, 0, 0))
    out.alpha_composite(fitted, ((out_w - fitted.width) // 2, (out_h - fitted.height) // 2))
    validate_nonblank(out, target)
    return out


def cut_sheet(
    manifest: dict,
    raw_path: Path,
    output_dir: Path,
    cut_mode: str,
    preview_cut_opaque: bool,
    bg_tolerance: int,
) -> list[dict]:
    sheet = Image.open(raw_path).convert("RGBA")
    expected_size = tuple(manifest["sheet_size"])
    if sheet.size != expected_size:
        raise RuntimeError(f"generated sheet is {sheet.width}x{sheet.height}, expected {expected_size[0]}x{expected_size[1]}")
    is_opaque_preview = sheet.getchannel("A").getextrema()[0] == 255
    if is_opaque_preview and not preview_cut_opaque:
        raise RuntimeError("generated sheet has no transparent alpha")

    cut_root = output_dir / ("preview-cut" if is_opaque_preview else "cut")
    outputs = []
    failures = []
    for entry in manifest["entries"]:
        try:
            if cut_mode == "reference-box":
                box = entry["reference_box"]
                crop = sheet.crop((box["x"], box["y"], box["x"] + box["w"], box["y"] + box["h"]))
                if is_opaque_preview:
                    crop = remove_edge_background(crop, bg_tolerance)
                source_size = (entry["source_size"]["w"], entry["source_size"]["h"])
                crop = resize_nearest(crop, source_size) if crop.size != source_size else crop
            elif cut_mode == "cell-raw":
                box = entry["cell"]
                crop = sheet.crop((box["x"], box["y"], box["x"] + box["w"], box["y"] + box["h"]))
                if is_opaque_preview:
                    crop = remove_edge_background(crop, bg_tolerance)
            elif cut_mode == "cell-fit":
                box = entry["cell"]
                cell = sheet.crop((box["x"], box["y"], box["x"] + box["w"], box["y"] + box["h"]))
                if is_opaque_preview:
                    cell = remove_edge_background(cell, bg_tolerance)
                crop = fit_cell_to_source(cell, (entry["source_size"]["w"], entry["source_size"]["h"]), entry["target"])
            else:
                raise RuntimeError(f"unsupported cut mode: {cut_mode}")
            validate_nonblank(crop, entry["target"])
        except Exception as error:
            failures.append({"target": entry["target"], "error": str(error)})
            continue

        out_path = cut_root / entry["target"]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        crop.save(out_path)
        outputs.append(
            {
                "target": entry["target"],
                "output": str(out_path),
                "size": list(crop.size),
                "alpha_pixels": alpha_pixel_count(crop),
                "preview": is_opaque_preview,
            }
        )
    if failures:
        (output_dir / "cut-failures.json").write_text(json.dumps(failures, indent=2) + "\n", encoding="utf-8")
    return outputs


def backup_file(path: Path, backup_root: Path) -> None:
    backup = backup_root / path.relative_to(ASSET_ROOT)
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        shutil.copy2(path, backup)


def rebuild_atlas(atlas_name: str, asset_subdir: str, backup_root: Path) -> None:
    atlas_json = ASSET_ROOT / f"{atlas_name}.json"
    atlas_png = ASSET_ROOT / f"{atlas_name}.png"
    if not atlas_json.exists() or not atlas_png.exists():
        return

    metadata = json.loads(atlas_json.read_text(encoding="utf-8"))
    texture = metadata["textures"][0]
    size = texture["size"]
    atlas = Image.new("RGBA", (size["w"], size["h"]), (0, 0, 0, 0))
    for frame in texture["frames"]:
        source_path = ASSET_ROOT / asset_subdir / f"{frame['filename']}.png"
        if not source_path.exists():
            continue
        source = Image.open(source_path).convert("RGBA")
        source_size = frame["sourceSize"]
        sprite_source = frame["spriteSourceSize"]
        rect = frame["frame"]
        if source.size != (source_size["w"], source_size["h"]):
            source = resize_nearest(source, (source_size["w"], source_size["h"]))
        crop = source.crop(
            (
                sprite_source["x"],
                sprite_source["y"],
                sprite_source["x"] + sprite_source["w"],
                sprite_source["y"] + sprite_source["h"],
            )
        )
        if crop.size != (rect["w"], rect["h"]):
            crop = resize_nearest(crop, (rect["w"], rect["h"]))
        atlas.alpha_composite(crop, (rect["x"], rect["y"]))

    backup_file(atlas_png, backup_root)
    atlas.save(atlas_png)


def install_outputs(cut_outputs: list[dict], rebuild_atlases: bool) -> list[str]:
    backup_root = ASSET_ROOT / "_original-art-sheet-redo-backup"
    installed_roots: set[str] = set()
    for item in cut_outputs:
        rel = Path(item["target"])
        source = Path(item["output"])
        dest = ASSET_ROOT / rel
        if not dest.exists():
            continue
        backup_file(dest, backup_root)
        shutil.copy2(source, dest)
        installed_roots.add(rel.parts[0])

    rebuilt = []
    if rebuild_atlases and "items" in installed_roots:
        rebuild_atlas("items", "items", backup_root)
        rebuilt.append("items.png")
    if rebuild_atlases and "pokeball" in installed_roots:
        rebuild_atlas("pb", "pokeball", backup_root)
        rebuilt.append("pb.png")
    return rebuilt


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and optionally generate chunked FAL redraw sheets for small non-actor assets.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--image-size", default=DEFAULT_IMAGE_SIZE, help="FAL image_size, e.g. 1536x1024 or 1024x1024.")
    parser.add_argument("--fal-image-size", default="", help="Optional FAL image_size override. Use auto for GPT Image 2 input-size inference.")
    parser.add_argument("--resolution", default="", help="Optional FAL resolution value for models that use resolution instead of image_size.")
    parser.add_argument("--chunks", type=int, default=DEFAULT_CHUNKS)
    parser.add_argument("--split-mode", default="round-robin", choices=["round-robin", "contiguous"])
    parser.add_argument("--padding", type=int, default=DEFAULT_PADDING)
    parser.add_argument("--cell-size", type=int, default=DEFAULT_CELL_SIZE, help="Per-asset sheet cell size. 128 fits about 96 sprites per 1536x1024 sheet.")
    parser.add_argument("--fixed-cell-size", action="store_true", help="Always scale sources into --cell-size instead of growing cells for large source images.")
    parser.add_argument("--mask-dilation", type=int, default=DEFAULT_MASK_DILATION, help="GPT Image 2 edit mask dilation in pixels.")
    parser.add_argument("--no-mask", action="store_true", help="Disable GPT Image 2 edit mask generation.")
    parser.add_argument("--all-folders", action="store_true", help="Include all small non-actor folders instead of only item-style folders.")
    parser.add_argument("--include-actors", action="store_true", help="With --all-folders, also include small pokemon, trainer, and character files.")
    parser.add_argument("--include-skipped", action="store_true", help="Include files normally skipped by logo/oauth/status/type filters.")
    parser.add_argument("--max-asset-size", type=int, default=64)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--include-glob", action="append", default=[])
    parser.add_argument("--exclude-glob", action="append", default=[])
    parser.add_argument("--run-fal", action="store_true")
    parser.add_argument("--cut", action="store_true")
    parser.add_argument("--cut-mode", default="cell-fit", choices=["cell-fit", "cell-raw", "reference-box"])
    parser.add_argument("--preview-cut-opaque", action="store_true", help="Cut opaque GPT Image 2 sheets by keying edge-connected background; not safe for install.")
    parser.add_argument("--bg-tolerance", type=int, default=DEFAULT_BG_TOLERANCE)
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--allow-partial-install", action="store_true")
    parser.add_argument("--no-rebuild-atlases", action="store_true")
    parser.add_argument("--quality", default="high", choices=["low", "medium", "high"])
    parser.add_argument("--background", default="transparent", choices=["auto", "transparent", "opaque"])
    args = parser.parse_args()

    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    sheet_size = parse_image_size(args.image_size)
    if args.chunks < 1:
        fail("--chunks must be at least 1")
    if args.cell_size <= args.padding * 2:
        fail("--cell-size must be larger than twice --padding")
    if args.mask_dilation < 0:
        fail("--mask-dilation must be non-negative")
    if args.bg_tolerance < 0:
        fail("--bg-tolerance must be non-negative")
    if args.install and args.preview_cut_opaque:
        fail("--preview-cut-opaque is preview-only and cannot be combined with --install")
    if args.install and args.cut_mode == "cell-raw":
        fail("--install requires source-size cuts; use --cut-mode cell-fit or reference-box")
    targets = discover_targets(
        args.max_asset_size,
        args.include_glob,
        args.exclude_glob,
        args.all_folders,
        args.include_actors,
        args.include_skipped,
    )
    targets = sorted(targets, key=lambda item: (item["target"].split("/", 1)[0], item["target"]))
    if args.limit > 0:
        targets = targets[: args.limit]
    if not targets:
        fail("No targets matched")

    chunks = split_contiguous(targets, args.chunks) if args.split_mode == "contiguous" else split_evenly(targets, args.chunks)
    run_manifest = {
        "model": args.model,
        "image_size": args.image_size,
        "fal_image_size": args.fal_image_size or args.image_size,
        "background": args.background,
        "quality": args.quality,
        "resolution": args.resolution or None,
        "cell_size": args.cell_size,
        "fixed_cell_size": args.fixed_cell_size,
        "split_mode": args.split_mode,
        "mask_dilation": args.mask_dilation,
        "use_mask": not args.no_mask,
        "all_folders": args.all_folders,
        "include_actors": args.include_actors,
        "include_skipped": args.include_skipped,
        "preview_cut_opaque": args.preview_cut_opaque,
        "bg_tolerance": args.bg_tolerance,
        "cut_mode": args.cut_mode,
        "target_count": len(targets),
        "chunks": [],
    }

    for index, chunk in enumerate(chunks, start=1):
        chunk_dir = output_root / f"chunk-{index:02d}"
        manifest = build_sheet(chunk, sheet_size, args.padding, args.cell_size, args.fixed_cell_size, chunk_dir, index)
        record = {"manifest": str(chunk_dir / f"sheet-{index:02d}.json"), "target_count": len(chunk)}
        print(f"[sheet] {index}/{len(chunks)} built {len(chunk)} targets -> {manifest['sheet']}", flush=True)
        if args.run_fal:
            try:
                fal_result = run_fal_sheet(
                    manifest,
                    chunk_dir,
                    args.model,
                    args.fal_image_size or args.image_size,
                    args.resolution or None,
                    args.quality,
                    args.background,
                    args.mask_dilation,
                    not args.no_mask,
                )
                record["fal"] = fal_result
                print(f"[sheet] {index}/{len(chunks)} fal ok -> {fal_result['raw_path']}", flush=True)
                if args.cut:
                    cut_outputs = cut_sheet(
                        manifest,
                        Path(fal_result["raw_path"]),
                        chunk_dir,
                        args.cut_mode,
                        args.preview_cut_opaque,
                        args.bg_tolerance,
                    )
                    record["cut_outputs"] = cut_outputs
                    failures_path = chunk_dir / "cut-failures.json"
                    if failures_path.exists():
                        record["cut_failures"] = str(failures_path)
                    print(f"[sheet] {index}/{len(chunks)} cut {len(cut_outputs)} assets", flush=True)
                    if args.install:
                        if failures_path.exists() and not args.allow_partial_install:
                            raise RuntimeError(f"refusing partial install; inspect {failures_path}")
                        rebuilt = install_outputs(cut_outputs, not args.no_rebuild_atlases)
                        record["installed"] = True
                        record["rebuilt_atlases"] = rebuilt
                        print(f"[sheet] {index}/{len(chunks)} installed; rebuilt atlases: {', '.join(rebuilt) or 'none'}", flush=True)
            except Exception as error:
                record["error"] = str(error)
                print(f"[sheet] {index}/{len(chunks)} error {error}", flush=True)
        run_manifest["chunks"].append(record)
        (output_root / "manifest.json").write_text(json.dumps(run_manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
