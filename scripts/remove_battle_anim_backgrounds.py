#!/usr/bin/env python3
"""Remove baked generated backgrounds from battle animation sheets.

The GPT/Fal redraw pass sometimes returns sprite sheets on light or dark
backgrounds. This script keeps the generated artwork, but uses the original
transparent sheets as a seed map to remove only background pixels connected to
each 96px animation frame edge. Full-screen `BG` assets are skipped.
"""

from __future__ import annotations

import argparse
import shutil
from collections import Counter, deque
from pathlib import Path
from typing import Iterable

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "assets" / "images" / "battle_anims"
SOURCE_ALPHA_ROOT = ROOT / "output" / "original-art-redo-pack" / "images" / "battle_anims"
REFERENCE_ROOT = (
    ROOT
    / "output"
    / "original-art-redo-pack"
    / "generated-battle-anims-before-bg-removal"
    / "images"
    / "battle_anims"
)


def is_background_asset(path: Path) -> bool:
    return "BG" in path.stem.upper()


def iter_frame_bounds(width: int, height: int, frame_size: int) -> Iterable[tuple[int, int, int, int]]:
    for y in range(0, height, frame_size):
        for x in range(0, width, frame_size):
            yield x, y, min(frame_size, width - x), min(frame_size, height - y)


def border_points(width: int, height: int) -> set[tuple[int, int]]:
    points: set[tuple[int, int]] = set()
    for x in range(width):
        points.add((x, 0))
        points.add((x, height - 1))
    for y in range(height):
        points.add((0, y))
        points.add((width - 1, y))
    return points


def quantized_color(color: tuple[int, int, int, int], bucket_size: int) -> tuple[int, int, int]:
    return color[0] // bucket_size, color[1] // bucket_size, color[2] // bucket_size


def bucket_center(bucket: tuple[int, int, int], bucket_size: int) -> tuple[int, int, int]:
    return tuple(channel * bucket_size + bucket_size // 2 for channel in bucket)


def color_distance_sq(left: tuple[int, int, int, int], right: tuple[int, int, int]) -> int:
    return (left[0] - right[0]) ** 2 + (left[1] - right[1]) ** 2 + (left[2] - right[2]) ** 2


def alpha_stats(image: Image.Image) -> tuple[int, int]:
    alpha = image.getchannel("A")
    data = alpha.tobytes()
    transparent = data.count(0)
    opaque = sum(1 for value in data if value > 16)
    return transparent, opaque


def copy_reference_snapshot(asset_root: Path, reference_root: Path, refresh: bool) -> int:
    if refresh and reference_root.exists():
        shutil.rmtree(reference_root)

    copied = 0
    reference_root.mkdir(parents=True, exist_ok=True)
    for source in sorted(asset_root.glob("*.png")):
        target = reference_root / source.name
        if target.exists():
            continue
        shutil.copy2(source, target)
        copied += 1
    return copied


def remove_frame_background(
    frame: Image.Image,
    source_alpha: Image.Image,
    tolerance: int,
    bucket_size: int,
    source_seed_alpha: int,
    top_colors: int,
) -> int:
    rgba = frame.convert("RGBA")
    source_alpha = source_alpha.convert("L")
    width, height = rgba.size
    pixels = rgba.load()
    source_pixels = source_alpha.load()
    points = border_points(width, height)

    color_counts: Counter[tuple[int, int, int]] = Counter()
    seed_points: list[tuple[int, int]] = []
    for x, y in points:
        if source_pixels[x, y] > source_seed_alpha:
            continue
        color = pixels[x, y]
        if color[3] <= 0:
            continue
        color_counts[quantized_color(color, bucket_size)] += 1
        seed_points.append((x, y))

    if not color_counts or not seed_points:
        return 0

    reference_colors = [
        bucket_center(bucket, bucket_size)
        for bucket, _count in color_counts.most_common(top_colors)
    ]
    tolerance_sq = tolerance * tolerance * 3

    def is_background_pixel(x: int, y: int) -> bool:
        if source_pixels[x, y] > source_seed_alpha:
            return False
        color = pixels[x, y]
        if color[3] <= 0:
            return False
        return any(color_distance_sq(color, reference) <= tolerance_sq for reference in reference_colors)

    removed: set[tuple[int, int]] = set()
    queue = deque(seed_points)
    visited: set[tuple[int, int]] = set()
    while queue:
        x, y = queue.popleft()
        if (x, y) in visited or not (0 <= x < width and 0 <= y < height):
            continue
        visited.add((x, y))
        if not is_background_pixel(x, y):
            continue

        removed.add((x, y))
        queue.extend(((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)))

    # Clean disconnected speckles inside original transparent areas.
    for y in range(height):
        for x in range(width):
            if (x, y) in removed:
                continue
            if is_background_pixel(x, y):
                removed.add((x, y))

    for x, y in removed:
        pixels[x, y] = (0, 0, 0, 0)

    frame.paste(rgba, (0, 0))
    return len(removed)


def remove_sheet_background(
    asset_path: Path,
    source_alpha_path: Path,
    frame_size: int,
    tolerance: int,
    bucket_size: int,
    source_seed_alpha: int,
    top_colors: int,
) -> tuple[bool, int]:
    image = Image.open(asset_path).convert("RGBA")
    source = Image.open(source_alpha_path).convert("RGBA")
    if image.size != source.size:
        raise ValueError(f"Size mismatch for {asset_path.name}: generated {image.size}, source {source.size}")

    before_transparent, _before_opaque = alpha_stats(image)
    source_alpha = source.getchannel("A")
    removed_total = 0

    for x, y, width, height in iter_frame_bounds(image.width, image.height, frame_size):
        frame = image.crop((x, y, x + width, y + height))
        alpha_frame = source_alpha.crop((x, y, x + width, y + height))
        removed_total += remove_frame_background(
            frame,
            alpha_frame,
            tolerance=tolerance,
            bucket_size=bucket_size,
            source_seed_alpha=source_seed_alpha,
            top_colors=top_colors,
        )
        image.paste(frame, (x, y))

    after_transparent, _after_opaque = alpha_stats(image)
    changed = after_transparent != before_transparent
    if changed:
        image.save(asset_path)
    return changed, removed_total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets-root", type=Path, default=ASSET_ROOT)
    parser.add_argument("--source-alpha-root", type=Path, default=SOURCE_ALPHA_ROOT)
    parser.add_argument("--reference-root", type=Path, default=REFERENCE_ROOT)
    parser.add_argument("--frame-size", type=int, default=96)
    parser.add_argument("--tolerance", type=int, default=48)
    parser.add_argument("--bucket-size", type=int, default=8)
    parser.add_argument("--source-seed-alpha", type=int, default=8)
    parser.add_argument("--top-colors", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-reference", action="store_true")
    parser.add_argument("--refresh-reference", action="store_true")
    args = parser.parse_args()

    if not args.assets_root.exists():
        raise SystemExit(f"Missing assets root: {args.assets_root}")
    if not args.source_alpha_root.exists():
        raise SystemExit(f"Missing source alpha root: {args.source_alpha_root}")

    copied = 0
    if not args.skip_reference and not args.dry_run:
        copied = copy_reference_snapshot(args.assets_root, args.reference_root, args.refresh_reference)

    changed = 0
    skipped = 0
    missing_source = 0
    removed_pixels = 0
    for asset_path in sorted(args.assets_root.glob("*.png")):
        if is_background_asset(asset_path):
            skipped += 1
            continue

        source_alpha_path = args.source_alpha_root / asset_path.name
        if not source_alpha_path.exists():
            missing_source += 1
            continue

        if args.dry_run:
            image = Image.open(asset_path).convert("RGBA")
            transparent, opaque = alpha_stats(image)
            if transparent == 0 and opaque > 0:
                changed += 1
            continue

        did_change, removed = remove_sheet_background(
            asset_path,
            source_alpha_path,
            frame_size=args.frame_size,
            tolerance=args.tolerance,
            bucket_size=args.bucket_size,
            source_seed_alpha=args.source_seed_alpha,
            top_colors=args.top_colors,
        )
        if did_change:
            changed += 1
            removed_pixels += removed

    print(
        "battle anim background cleanup:",
        f"changed={changed}",
        f"skipped_bg={skipped}",
        f"missing_source={missing_source}",
        f"reference_copied={copied}",
        f"removed_pixels={removed_pixels}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
