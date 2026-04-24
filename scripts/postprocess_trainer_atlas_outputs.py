#!/usr/bin/env python3
"""Salvage generated Mogmaster trainer sheets from saved Fal outputs.

The first trainer generation pass often returned a 1024px sprite sheet that did
not exactly preserve the original atlas frame boxes. This post-process pass
extracts complete high-resolution sprite components first, then fits them back
into the existing TexturePacker frame rectangles.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from generate_mpp_trainer_redesign import load_trainer_frames, strip_border_background
from mogmon_normalizer import pixelify_image


ROOT = Path(__file__).resolve().parent.parent
TRAINER_DIR = ROOT / "assets" / "images" / "trainer"
DEFAULT_OUTPUT_ROOT = ROOT / "output" / "trainer-mpp-redesign"
ALPHA_THRESHOLD = 24
MIN_COMPONENT_AREA = 96

GROUP_TARGETS = {
    "backers_f",
    "backers_m",
    "hooligans",
    "interviewers",
    "mysterious_sisters",
    "twins",
    "young_couple",
}


@dataclass(frozen=True)
class Slot:
    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class Candidate:
    box: tuple[int, int, int, int]
    crop: Image.Image
    area: int


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def discover_targets() -> list[str]:
    return [path.stem for path in sorted(TRAINER_DIR.glob("*.png")) if path.with_suffix(".json").exists()]


def manifest_priority(path: Path) -> tuple[int, float, str]:
    parts = set(path.parts)
    if "last7" in parts:
        bucket = 5
    elif any(part.startswith("final-retry-") for part in parts):
        bucket = 4
    elif any(part.startswith("retry-") for part in parts):
        bucket = 3
    elif any(part.startswith("chunk-") for part in parts):
        bucket = 2
    else:
        bucket = 1
    return (bucket, path.stat().st_mtime, str(path))


def find_outputs(output_root: Path) -> dict[str, Path]:
    outputs: dict[str, Path] = {}
    manifest_paths = sorted(output_root.rglob("manifest.json"), key=manifest_priority)
    for manifest_path in manifest_paths:
        try:
            entries = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for entry in entries:
            if entry.get("status") != "ok" or not entry.get("target"):
                continue
            bg_path = entry.get("bg_removed_output") or entry.get("raw_output")
            if not bg_path:
                continue
            path = Path(bg_path)
            if not path.is_absolute():
                path = ROOT / path
            if path.exists():
                outputs[entry["target"]] = path

    for path in output_root.rglob("bg-removed.png"):
        target = path.parent.name
        current = outputs.get(target)
        if current is None or path.stat().st_mtime > current.stat().st_mtime:
            outputs[target] = path
    return outputs


def unique_slots(source_json: Path, order: str) -> list[Slot]:
    slots: list[Slot] = []
    seen: set[tuple[int, int, int, int]] = set()
    for frame in load_trainer_frames(source_json):
        rect = frame["frame"]
        key = (int(rect["x"]), int(rect["y"]), int(rect["w"]), int(rect["h"]))
        if key in seen:
            continue
        seen.add(key)
        slots.append(Slot(*key))
    if order == "layout":
        slots.sort(key=lambda slot: (slot.y, slot.x))
    return slots


def alpha_area(image: Image.Image) -> int:
    alpha = image.getchannel("A")
    return sum(1 for value in alpha.tobytes() if value >= ALPHA_THRESHOLD)


def alpha_bbox(image: Image.Image) -> tuple[int, int, int, int] | None:
    mask = image.getchannel("A").point(lambda value: 255 if value >= ALPHA_THRESHOLD else 0)
    return mask.getbbox()


def extract_component_boxes(image: Image.Image, min_area: int) -> list[tuple[int, int, int, int]]:
    alpha = image.getchannel("A")
    pixels = alpha.load()
    width, height = image.size
    visited = bytearray(width * height)
    boxes: list[tuple[int, int, int, int]] = []

    for y in range(height):
        for x in range(width):
            index = y * width + x
            if visited[index] or pixels[x, y] < ALPHA_THRESHOLD:
                continue

            queue = deque([(x, y)])
            visited[index] = 1
            xs: list[int] = []
            ys: list[int] = []

            while queue:
                cx, cy = queue.popleft()
                xs.append(cx)
                ys.append(cy)
                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                    if nx < 0 or nx >= width or ny < 0 or ny >= height:
                        continue
                    n_index = ny * width + nx
                    if visited[n_index] or pixels[nx, ny] < ALPHA_THRESHOLD:
                        continue
                    visited[n_index] = 1
                    queue.append((nx, ny))

            if len(xs) >= min_area:
                boxes.append((min(xs), min(ys), max(xs) + 1, max(ys) + 1))

    return boxes


def low_alpha_runs(counts: list[int], threshold: int, min_width: int) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, count in enumerate(counts):
        if count <= threshold:
            if start is None:
                start = index
        elif start is not None:
            if index - start >= min_width:
                runs.append((start, index))
            start = None
    if start is not None and len(counts) - start >= min_width:
        runs.append((start, len(counts)))
    return runs


def split_box_by_projection(image: Image.Image, box: tuple[int, int, int, int], target_aspect: float) -> list[tuple[int, int, int, int]]:
    x0, y0, x1, y1 = box
    width = x1 - x0
    height = y1 - y0
    if width < 80 or height < 80:
        return [box]

    # Wide merged blobs usually mean two adjacent trainer variants. Split on
    # vertical whitespace before fitting into a narrow human frame.
    if width / max(1, height) > max(1.25, target_aspect * 1.35):
        alpha = image.getchannel("A")
        counts = [
            sum(1 for y in range(y0, y1) if alpha.getpixel((x, y)) >= ALPHA_THRESHOLD)
            for x in range(x0, x1)
        ]
        gap_threshold = max(2, int(height * 0.025))
        min_gap = max(6, int(width * 0.018))
        gaps = [(a + x0, b + x0) for a, b in low_alpha_runs(counts, gap_threshold, min_gap)]
        if gaps:
            segments: list[tuple[int, int, int, int]] = []
            cursor = x0
            for gap_start, gap_end in gaps:
                if gap_start - cursor >= 24:
                    segments.append((cursor, y0, gap_start, y1))
                cursor = gap_end
            if x1 - cursor >= 24:
                segments.append((cursor, y0, x1, y1))
            trimmed = trim_boxes(image, segments)
            if len(trimmed) > 1:
                return trimmed

    return [box]


def trim_boxes(image: Image.Image, boxes: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    trimmed: list[tuple[int, int, int, int]] = []
    for x0, y0, x1, y1 in boxes:
        crop = image.crop((x0, y0, x1, y1))
        bbox = alpha_bbox(crop)
        if bbox is None:
            continue
        tx0, ty0, tx1, ty1 = bbox
        box = (x0 + tx0, y0 + ty0, x0 + tx1, y0 + ty1)
        if (box[2] - box[0]) * (box[3] - box[1]) >= MIN_COMPONENT_AREA:
            trimmed.append(box)
    return trimmed


def candidate_from_box(image: Image.Image, box: tuple[int, int, int, int]) -> Candidate | None:
    crop = image.crop(box)
    bbox = alpha_bbox(crop)
    if bbox is None:
        return None
    crop = crop.crop(bbox)
    area = alpha_area(crop)
    if area < MIN_COMPONENT_AREA:
        return None
    return Candidate(box, crop, area)


def extract_candidates(image: Image.Image, target_aspect: float) -> list[Candidate]:
    cleaned = strip_border_background(image, tolerance=38).convert("RGBA")
    boxes = extract_component_boxes(cleaned, MIN_COMPONENT_AREA)
    if not boxes:
        bbox = alpha_bbox(cleaned)
        boxes = [bbox] if bbox else []

    split: list[tuple[int, int, int, int]] = []
    for box in boxes:
        split.extend(split_box_by_projection(cleaned, box, target_aspect))

    candidates = [candidate for box in split if (candidate := candidate_from_box(cleaned, box)) is not None]
    candidates.sort(key=lambda candidate: (candidate.box[1], candidate.box[0]))
    return candidates


def candidate_score(candidate: Candidate, target_aspect: float, target_area: float) -> float:
    width = max(1, candidate.crop.width)
    height = max(1, candidate.crop.height)
    aspect = width / height
    aspect_penalty = abs(math.log(max(0.05, aspect) / max(0.05, target_aspect)))
    area_ratio = min(candidate.area / max(1.0, target_area), 4.0)
    return area_ratio - aspect_penalty * 0.65


def select_candidates(target: str, slots: list[Slot], candidates: list[Candidate]) -> list[Candidate]:
    if not candidates:
        raise RuntimeError("No usable trainer candidates were detected")

    slot_count = len(slots)
    average_aspect = sum(slot.w / max(1, slot.h) for slot in slots) / max(1, slot_count)
    average_area = sum(slot.w * slot.h for slot in slots) / max(1, slot_count)

    if slot_count == 1:
        if target in GROUP_TARGETS or average_aspect > 1.15:
            return [max(candidates, key=lambda candidate: candidate.area)]
        return [max(candidates, key=lambda candidate: candidate_score(candidate, average_aspect, average_area))]

    if len(candidates) > slot_count:
        candidates = sorted(candidates, key=lambda candidate: candidate.area, reverse=True)[:slot_count]
        candidates.sort(key=lambda candidate: (candidate.box[1], candidate.box[0]))

    if len(candidates) < slot_count:
        expanded: list[Candidate] = []
        for index in range(slot_count):
            expanded.append(candidates[index % len(candidates)])
        return expanded

    return candidates


def fixed_grid_dimensions(slot_count: int) -> list[tuple[int, int]]:
    dims: set[tuple[int, int]] = set()
    max_extra = max(4, math.ceil(slot_count * 0.35))
    for rows in range(1, min(9, slot_count + 1)):
        cols = math.ceil(slot_count / rows)
        for d_rows, d_cols in ((rows, cols), (cols, rows)):
            cells = d_rows * d_cols
            if cells >= slot_count and cells <= slot_count + max_extra:
                dims.add((d_cols, d_rows))
    return sorted(dims, key=lambda item: (item[0] * item[1], abs(item[0] - item[1]), item[1], item[0]))


def extract_fixed_grid_candidates(image: Image.Image, cols: int, rows: int) -> list[Candidate]:
    cleaned = strip_border_background(image, tolerance=38).convert("RGBA")
    bbox = alpha_bbox(cleaned)
    if bbox is None:
        return []
    clean = cleaned.crop(bbox)
    candidates: list[Candidate] = []
    for row in range(rows):
        y0 = round(row * clean.height / rows)
        y1 = round((row + 1) * clean.height / rows)
        for col in range(cols):
            x0 = round(col * clean.width / cols)
            x1 = round((col + 1) * clean.width / cols)
            cell = clean.crop((x0, y0, x1, y1))
            cell_bbox = alpha_bbox(cell)
            if cell_bbox is None:
                continue
            tx0, ty0, tx1, ty1 = cell_bbox
            crop = cell.crop(cell_bbox)
            area = alpha_area(crop)
            if area < MIN_COMPONENT_AREA:
                continue
            candidates.append(Candidate((bbox[0] + x0 + tx0, bbox[1] + y0 + ty0, bbox[0] + x0 + tx1, bbox[1] + y0 + ty1), crop, area))
    return candidates


def fit_candidate(candidate: Candidate, slot: Slot, pixel_ratio: float) -> Image.Image:
    max_width = max(1, slot.w - 1)
    max_height = max(1, slot.h - 1)
    scale = min(max_width / max(1, candidate.crop.width), max_height / max(1, candidate.crop.height))
    out_w = max(1, int(round(candidate.crop.width * scale)))
    out_h = max(1, int(round(candidate.crop.height * scale)))
    base_width = max(8, min(out_w, int(round(out_w * pixel_ratio))))
    resized = pixelify_image(candidate.crop, base_width=base_width, output_width=out_w, output_height=out_h)

    frame = Image.new("RGBA", (slot.w, slot.h), (0, 0, 0, 0))
    paste_x = max(0, (slot.w - out_w) // 2)
    paste_y = max(0, slot.h - out_h)
    frame.alpha_composite(resized, (paste_x, paste_y))
    return frame


def normalize_from_candidates(slots: list[Slot], candidates: list[Candidate], pixel_ratio: float) -> Image.Image:
    source_w = max(slot.x + slot.w for slot in slots)
    source_h = max(slot.y + slot.h for slot in slots)
    normalized = Image.new("RGBA", (source_w, source_h), (0, 0, 0, 0))
    for slot, candidate in zip(slots, candidates):
        normalized.alpha_composite(fit_candidate(candidate, slot, pixel_ratio), (slot.x, slot.y))
    return normalized


def normalized_score(image: Image.Image, slots: list[Slot]) -> float:
    ratios: list[float] = []
    area_ratios: list[float] = []
    empty = 0
    for slot in slots:
        crop = image.crop((slot.x, slot.y, slot.x + slot.w, slot.y + slot.h))
        bbox = alpha_bbox(crop)
        if bbox is None:
            empty += 1
            ratios.append(0.0)
            area_ratios.append(0.0)
            continue
        bw = bbox[2] - bbox[0]
        bh = bbox[3] - bbox[1]
        ratios.append(min(bw / max(1, slot.w), bh / max(1, slot.h)))
        area_ratios.append(alpha_area(crop) / max(1, slot.w * slot.h))

    ratios.sort()
    area_ratios.sort()
    median_ratio = ratios[len(ratios) // 2] if ratios else 0.0
    median_area = area_ratios[len(area_ratios) // 2] if area_ratios else 0.0
    min_area = area_ratios[0] if area_ratios else 0.0
    return median_ratio * 2.0 + median_area + min_area * 0.5 - empty * 0.75


def pad_to_source_size(image: Image.Image, source_size: tuple[int, int]) -> Image.Image:
    if image.size == source_size:
        return image
    padded = Image.new("RGBA", source_size, (0, 0, 0, 0))
    padded.alpha_composite(image, (0, 0))
    return padded


def normalize_from_output(target: str, source_json: Path, generated_path: Path, order: str, pixel_ratio: float) -> tuple[Image.Image, str]:
    slots = unique_slots(source_json, order)
    if not slots:
        raise RuntimeError(f"No frame slots found in {source_json}")
    source_size = Image.open(source_json.with_suffix(".png")).size
    average_aspect = sum(slot.w / max(1, slot.h) for slot in slots) / len(slots)
    generated = Image.open(generated_path).convert("RGBA")

    attempts: list[tuple[float, str, Image.Image]] = []
    component_candidates = select_candidates(target, slots, extract_candidates(generated, average_aspect))
    component_image = pad_to_source_size(normalize_from_candidates(slots, component_candidates, pixel_ratio), source_size)
    attempts.append((normalized_score(component_image, slots), "components", component_image))

    if len(slots) > 1:
        for cols, rows in fixed_grid_dimensions(len(slots)):
            grid_candidates = extract_fixed_grid_candidates(generated, cols, rows)
            if len(grid_candidates) < max(1, math.ceil(len(slots) * 0.55)):
                continue
            selected = select_candidates(target, slots, grid_candidates)
            grid_image = pad_to_source_size(normalize_from_candidates(slots, selected, pixel_ratio), source_size)
            attempts.append((normalized_score(grid_image, slots), f"fixed-grid-{cols}x{rows}", grid_image))

    score, method, normalized = max(attempts, key=lambda item: item[0])
    return normalized, method


def make_contact_sheet(paths: list[tuple[str, Path]], output_path: Path) -> None:
    if not paths:
        return
    tile_w, tile_h = 112, 116
    cols = 8
    rows = math.ceil(len(paths) / cols)
    sheet = Image.new("RGBA", (cols * tile_w, rows * tile_h), (14, 17, 23, 255))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 10)
    except Exception:
        font = None
    for index, (label, path) in enumerate(paths):
        image = Image.open(path).convert("RGBA")
        image.thumbnail((tile_w - 12, tile_h - 24), Image.Resampling.NEAREST)
        x = (index % cols) * tile_w
        y = (index // cols) * tile_h
        sheet.alpha_composite(image, (x + (tile_w - image.width) // 2, y + 4))
        draw.text((x + 4, y + tile_h - 16), label[:18], fill=(235, 238, 226, 255), font=font)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Post-process generated trainer atlases into exact runtime frame boxes.")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--targets", default="")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--no-install", action="store_true")
    parser.add_argument("--slot-order", choices=("layout", "json"), default="layout")
    parser.add_argument("--pixel-ratio", type=float, default=0.82)
    parser.add_argument("--preview-limit", type=int, default=48)
    args = parser.parse_args()

    output_root = Path(args.output_root)
    targets = discover_targets() if args.all else parse_csv(args.targets)
    if not targets:
        raise SystemExit("No targets selected. Pass --all or --targets name,name2.")

    outputs = find_outputs(output_root)
    manifest: list[dict] = []
    preview_paths: list[tuple[str, Path]] = []

    for index, target in enumerate(targets, start=1):
        source_png = TRAINER_DIR / f"{target}.png"
        source_json = TRAINER_DIR / f"{target}.json"
        generated_path = outputs.get(target)
        target_output = output_root / target
        if generated_path and generated_path.parent.name == target:
            target_output = generated_path.parent
        target_output.mkdir(parents=True, exist_ok=True)
        postprocessed_path = target_output / "postprocessed.png"

        try:
            if generated_path is None:
                raise RuntimeError("No saved bg-removed/raw output found")
            normalized, method = normalize_from_output(target, source_json, generated_path, args.slot_order, args.pixel_ratio)
            normalized.save(postprocessed_path)
            if not args.no_install:
                normalized.save(source_png)
            status = "ok"
            error = None
            if len(preview_paths) < args.preview_limit:
                preview_paths.append((target, postprocessed_path))
            print(f"[trainer-post] {index}/{len(targets)} ok {target}", flush=True)
        except Exception as exc:
            status = "error"
            error = str(exc)
            print(f"[trainer-post] {index}/{len(targets)} error {target}: {exc}", flush=True)

        manifest.append(
            {
                "status": status,
                "target": target,
                "source_png": str(source_png),
                "source_json": str(source_json),
                "generated_input": str(generated_path) if generated_path else None,
                "postprocessed_output": str(postprocessed_path) if status == "ok" else None,
                "method": method if status == "ok" else None,
                "installed": status == "ok" and not args.no_install,
                "error": error,
            }
        )

    manifest_path = output_root / "postprocess-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    make_contact_sheet(preview_paths, output_root / "postprocess-preview.png")
    errors = [entry for entry in manifest if entry["status"] != "ok"]
    print(f"[trainer-post] complete ok={len(manifest) - len(errors)} error={len(errors)} manifest={manifest_path}", flush=True)


if __name__ == "__main__":
    main()
