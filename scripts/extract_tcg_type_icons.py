#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from collections import deque
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

TYPE_NAMES = [
    "bug",
    "dark",
    "dragon",
    "electric",
    "fairy",
    "fighting",
    "fire",
    "flying",
    "ghost",
    "grass",
    "ground",
    "ice",
    "normal",
    "poison",
    "psychic",
    "rock",
    "steel",
    "water",
]

GRID_COLS = 6
GRID_ROWS = 3
ICON_TARGET_SIZE = 198
ICON_SOURCE_SIZE = 206
LUMINANCE_THRESHOLD = 100
ROW_ACTIVITY_THRESHOLD = 5
MIN_SEGMENT_HEIGHT = 20
BACKGROUND_TOLERANCE = 28
LABEL_PADDING = 4

try:
    RESAMPLE = Image.Resampling.LANCZOS
except AttributeError:
    RESAMPLE = Image.LANCZOS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract TCG type icons and labels from the combined sheet."
    )
    parser.add_argument(
        "--sheet",
        type=Path,
        default=Path("output/private-generation-prompts/mogger-mon-tcg/icons/icons-full.png"),
        help="Path to the source sheet image.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/mogmon-tcg-type-icons"),
        help="Destination folder for extracted assets.",
    )
    return parser.parse_args()


def luminance(pixel: tuple[int, int, int, int]) -> float:
    r, g, b, _ = pixel
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def cell_bounds(size: int, index: int, total: int) -> tuple[int, int]:
    start = round(index * size / total)
    end = round((index + 1) * size / total)
    return start, end


def long_segments(counts: list[int], threshold: int, min_length: int) -> list[tuple[int, int]]:
    segments: list[tuple[int, int]] = []
    start: int | None = None
    for idx, value in enumerate(counts + [0]):
        if value > threshold and start is None:
            start = idx
        elif value <= threshold and start is not None:
            end = idx - 1
            if end - start + 1 >= min_length:
                segments.append((start, end))
            start = None
    return segments


def segment_bbox(
    sheet: Image.Image,
    cell_box: tuple[int, int, int, int],
    segment: tuple[int, int],
    threshold: int,
) -> tuple[int, int, int, int]:
    x0, y0, x1, _ = cell_box
    seg_y0 = y0 + segment[0]
    seg_y1 = y0 + segment[1]
    pixels = sheet.load()

    min_x = min_y = 10**9
    max_x = max_y = -1
    for y in range(seg_y0, seg_y1 + 1):
        for x in range(x0, x1):
            if luminance(pixels[x, y]) > threshold:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)

    if max_x < 0:
        raise ValueError(f"Unable to locate pixels for segment {segment} in cell {cell_box}")
    return min_x, min_y, max_x + 1, max_y + 1


def detect_segments(
    sheet: Image.Image,
    cell_box: tuple[int, int, int, int],
    threshold: int,
) -> tuple[tuple[int, int], tuple[int, int]]:
    x0, y0, x1, y1 = cell_box
    pixels = sheet.load()
    row_counts: list[int] = []
    for y in range(y0, y1):
        count = 0
        for x in range(x0, x1):
            if luminance(pixels[x, y]) > threshold:
                count += 1
        row_counts.append(count)

    segments = long_segments(row_counts, ROW_ACTIVITY_THRESHOLD, MIN_SEGMENT_HEIGHT)
    if len(segments) < 2:
        raise ValueError(f"Expected icon and label segments in cell {cell_box}, found {segments}")
    return segments[0], segments[1]


def clamp_box(
    box: tuple[int, int, int, int],
    bounds: tuple[int, int],
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    max_w, max_h = bounds
    return (
        max(0, x0),
        max(0, y0),
        min(max_w, x1),
        min(max_h, y1),
    )


def square_box(center_x: float, center_y: float, side: int, bounds: tuple[int, int]) -> tuple[int, int, int, int]:
    half = side / 2
    x0 = round(center_x - half)
    y0 = round(center_y - half)
    x1 = x0 + side
    y1 = y0 + side
    max_w, max_h = bounds

    if x0 < 0:
        x1 -= x0
        x0 = 0
    if y0 < 0:
        y1 -= y0
        y0 = 0
    if x1 > max_w:
        shift = x1 - max_w
        x0 -= shift
        x1 = max_w
    if y1 > max_h:
        shift = y1 - max_h
        y0 -= shift
        y1 = max_h
    return x0, y0, x1, y1


def expand_box(
    box: tuple[int, int, int, int],
    padding: int,
    bounds: tuple[int, int],
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    return clamp_box((x0 - padding, y0 - padding, x1 + padding, y1 + padding), bounds)


def remove_edge_background(image: Image.Image, tolerance: int = BACKGROUND_TOLERANCE) -> Image.Image:
    rgba = image.convert("RGBA")
    width, height = rgba.size
    pixels = rgba.load()

    border_points = set()
    for x in range(width):
        border_points.add((x, 0))
        border_points.add((x, height - 1))
    for y in range(height):
        border_points.add((0, y))
        border_points.add((width - 1, y))

    color_counts: dict[tuple[int, int, int], int] = {}
    for x, y in border_points:
        r, g, b, a = pixels[x, y]
        if a == 0:
            continue
        key = (r // 8, g // 8, b // 8)
        color_counts[key] = color_counts.get(key, 0) + 1

    if not color_counts:
        return rgba

    reference_colors = [
        (r * 8 + 4, g * 8 + 4, b * 8 + 4)
        for r, g, b in sorted(color_counts, key=color_counts.get, reverse=True)[:6]
    ]

    def is_background(color: tuple[int, int, int, int]) -> bool:
        r, g, b, a = color
        if a == 0:
            return False
        return any(
            abs(r - rr) <= tolerance and abs(g - gg) <= tolerance and abs(b - bb) <= tolerance
            for rr, gg, bb in reference_colors
        )

    queue = deque(border_points)
    visited = set()
    while queue:
        x, y = queue.popleft()
        if (x, y) in visited or not (0 <= x < width and 0 <= y < height):
            continue
        visited.add((x, y))
        if not is_background(pixels[x, y]):
            continue
        pixels[x, y] = (0, 0, 0, 0)
        queue.extend(((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)))

    return rgba


def alpha_trimmed(image: Image.Image) -> Image.Image:
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    if not bbox:
        return image
    return image.crop(bbox)


def circle_mask(size: int, inset: int = 1) -> Image.Image:
    scale = 4
    large = Image.new("L", (size * scale, size * scale), 0)
    draw = ImageDraw.Draw(large)
    offset = inset * scale
    draw.ellipse((offset, offset, size * scale - offset - 1, size * scale - offset - 1), fill=255)
    return large.resize((size, size), RESAMPLE)


def rounded_rect_mask(size: tuple[int, int], inset: int) -> Image.Image:
    width, height = size
    scale = 4
    large = Image.new("L", (width * scale, height * scale), 0)
    draw = ImageDraw.Draw(large)
    x0 = inset * scale
    y0 = inset * scale
    x1 = width * scale - x0 - 1
    y1 = height * scale - y0 - 1
    radius = max(1, (height - inset * 2) // 2) * scale
    draw.rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=255)
    return large.resize((width, height), RESAMPLE)


def checkerboard(size: tuple[int, int], tile: int = 18) -> Image.Image:
    canvas = Image.new("RGBA", size, (235, 235, 235, 255))
    draw = ImageDraw.Draw(canvas)
    for y in range(0, size[1], tile):
        for x in range(0, size[0], tile):
            if ((x // tile) + (y // tile)) % 2:
                draw.rectangle((x, y, x + tile - 1, y + tile - 1), fill=(204, 204, 204, 255))
    return canvas


def build_preview(icons_dir: Path, labels_dir: Path, out_path: Path) -> None:
    cell_w = 240
    cell_h = 270
    preview = checkerboard((GRID_COLS * cell_w, GRID_ROWS * cell_h))
    for index, name in enumerate(TYPE_NAMES):
        row = index // GRID_COLS
        col = index % GRID_COLS
        icon = Image.open(icons_dir / f"{name}.png").convert("RGBA")
        label = Image.open(labels_dir / f"{name}.png").convert("RGBA")
        base_x = col * cell_w
        base_y = row * cell_h
        preview.alpha_composite(icon, (base_x + (cell_w - icon.width) // 2, base_y + 12))
        preview.alpha_composite(label, (base_x + (cell_w - label.width) // 2, base_y + 214))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    preview.save(out_path)


def main() -> None:
    args = parse_args()
    sheet = Image.open(args.sheet).convert("RGBA")
    sheet_w, sheet_h = sheet.size
    icons_dir = args.output / "icons"
    labels_dir = args.output / "labels"
    icons_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    for index, name in enumerate(TYPE_NAMES):
        row = index // GRID_COLS
        col = index % GRID_COLS
        cell_x0, cell_x1 = cell_bounds(sheet_w, col, GRID_COLS)
        cell_y0, cell_y1 = cell_bounds(sheet_h, row, GRID_ROWS)
        cell_box = (cell_x0, cell_y0, cell_x1, cell_y1)

        icon_segment, label_segment = detect_segments(sheet, cell_box, LUMINANCE_THRESHOLD)
        icon_bbox = segment_bbox(sheet, cell_box, icon_segment, LUMINANCE_THRESHOLD)
        label_bbox = segment_bbox(sheet, cell_box, label_segment, LUMINANCE_THRESHOLD)

        center_x = (icon_bbox[0] + icon_bbox[2]) / 2
        center_y = (icon_bbox[1] + icon_bbox[3]) / 2
        icon_crop_box = square_box(center_x, center_y, ICON_SOURCE_SIZE, (sheet_w, sheet_h))
        icon = sheet.crop(icon_crop_box).resize((ICON_TARGET_SIZE, ICON_TARGET_SIZE), RESAMPLE)
        icon = remove_edge_background(icon)
        icon.putalpha(ImageChops.multiply(icon.getchannel("A"), circle_mask(ICON_TARGET_SIZE)))
        icon_path = icons_dir / f"{name}.png"
        icon.save(icon_path)

        label_crop_box = expand_box(label_bbox, LABEL_PADDING, (sheet_w, sheet_h))
        label = sheet.crop(label_crop_box)
        label.putalpha(rounded_rect_mask(label.size, LABEL_PADDING))
        label = alpha_trimmed(label)
        label_path = labels_dir / f"{name}.png"
        label.save(label_path)

        manifest.append(
            {
                "name": name,
                "icon_path": icon_path.as_posix(),
                "label_path": label_path.as_posix(),
                "cell_box": cell_box,
                "icon_crop_box": icon_crop_box,
                "label_crop_box": label_crop_box,
            }
        )

    build_preview(icons_dir, labels_dir, args.output / "preview.png")
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
