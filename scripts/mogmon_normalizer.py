#!/usr/bin/env python3
"""Helpers for normalizing generated Mogger Mon sprite sheets into game atlases."""

from __future__ import annotations

import json
import math
from collections import deque
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageChops, ImageFilter

ALPHA_THRESHOLD = 8
MIN_COMPONENT_AREA = 96
ICON_PADDING = 1
FRAME_PADDING = 1
FRAME_PIXELIFY_BASE = 96
ICON_PIXELIFY_BASE = 64
EDGE_BACKGROUND_MIN_OPAQUE_BORDER_PIXELS = 24
EDGE_BACKGROUND_MIN_OPAQUE_BORDER_RATIO = 0.18
EDGE_BACKGROUND_MIN_DOMINANT_RATIO = 0.16
EDGE_BACKGROUND_MAX_QUANTIZED_COLORS = 20
MASK_CLIP_FILTER = 9
SCALE_FIT_QUANTILE = 0.4
EXACT_GRID_SCALE_QUANTILES = (0.0, 0.18, 0.3, 0.4)
SCALE_FIT_ITERATIONS = 5
SCALE_FIT_TOLERANCE = 0.03


def load_template_atlas(template_json_path):
    with open(template_json_path) as f:
        data = json.load(f)

    if "textures" in data:
        tex = data["textures"][0]
    elif "frames" in data and "meta" in data:
        tex = {
            "image": data["meta"]["image"],
            "format": data["meta"].get("format", "RGBA8888"),
            "size": data["meta"]["size"],
            "scale": data["meta"].get("scale", 1),
            "frames": data["frames"],
        }
    else:
        raise KeyError("Unsupported atlas JSON format: expected textures[] or frames+meta")

    frames = tex["frames"]
    atlas_dir = Path(template_json_path).parent
    atlas_image = Image.open(atlas_dir / tex["image"]).convert("RGBA")
    sheet_size = tex["size"]

    unique_frames = []
    unique_lookup = {}
    frame_to_unique = []
    unique_masks = []
    source_w = max(frame["sourceSize"]["w"] for frame in frames)
    source_h = max(frame["sourceSize"]["h"] for frame in frames)
    for frame in frames:
        fr = frame["frame"]
        key = (fr["x"], fr["y"], fr["w"], fr["h"])
        if key not in unique_lookup:
            unique_lookup[key] = len(unique_frames)
            frame_crop = atlas_image.crop((fr["x"], fr["y"], fr["x"] + fr["w"], fr["y"] + fr["h"]))
            full_mask = Image.new("L", (source_w, source_h), 0)
            sprite_source = frame["spriteSourceSize"]
            alpha_crop = frame_crop.getchannel("A")
            full_mask.paste(alpha_crop, (sprite_source["x"], sprite_source["y"]))
            unique_frames.append(
                {
                    "frame": {"x": fr["x"], "y": fr["y"], "w": fr["w"], "h": fr["h"]},
                    "sourceSize": frame["sourceSize"],
                    "spriteSourceSize": frame["spriteSourceSize"],
                }
            )
            unique_masks.append(full_mask)
        frame_to_unique.append(unique_lookup[key])

    return {
        "image": tex["image"],
        "format": tex.get("format", "RGBA8888"),
        "scale": tex.get("scale", 1),
        "frames": frames,
        "frame_to_unique": frame_to_unique,
        "unique_frames": unique_frames,
        "unique_masks": unique_masks,
        "unique_count": len(unique_frames),
        "sheet_w": sheet_size["w"],
        "sheet_h": sheet_size["h"],
        "source_w": source_w,
        "source_h": source_h,
    }


def _find_runs(values: Iterable[int], threshold: int, max_gap: int):
    runs = []
    start = None
    last_active = None
    gap = 0

    for index, value in enumerate(values):
        if value >= threshold:
            if start is None:
                start = index
            last_active = index
            gap = 0
            continue

        if start is None:
            continue

        gap += 1
        if gap > max_gap:
            runs.append((start, last_active))
            start = None
            last_active = None
            gap = 0

    if start is not None:
        runs.append((start, last_active))

    return runs


def _alpha_bbox(alpha, x0, y0, x1, y1, threshold):
    pixels = alpha.load()
    xs = []
    ys = []
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            if pixels[x, y] >= threshold:
                xs.append(x)
                ys.append(y)

    if not xs:
        return None

    return (min(xs), min(ys), max(xs) + 1, max(ys) + 1)


def _extract_row_column_boxes(image, alpha_threshold, row_threshold, col_threshold, max_gap):
    alpha = image.getchannel("A")
    width, height = image.size
    pixels = alpha.load()

    row_counts = [
        sum(1 for x in range(width) if pixels[x, y] >= alpha_threshold)
        for y in range(height)
    ]
    row_runs = _find_runs(row_counts, row_threshold, max_gap)

    boxes = []
    for y0, y1 in row_runs:
        col_counts = [
            sum(1 for y in range(y0, y1 + 1) if pixels[x, y] >= alpha_threshold)
            for x in range(width)
        ]
        col_runs = _find_runs(col_counts, col_threshold, max_gap)
        for x0, x1 in col_runs:
            bbox = _alpha_bbox(alpha, x0, y0, x1, y1, alpha_threshold)
            if bbox is None:
                continue
            area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
            if area >= MIN_COMPONENT_AREA:
                boxes.append(bbox)

    return boxes


def _extract_component_boxes(image, alpha_threshold, min_area):
    alpha = image.getchannel("A")
    pixels = alpha.load()
    width, height = image.size
    visited = [[False for _ in range(width)] for _ in range(height)]
    boxes = []

    for y in range(height):
        for x in range(width):
            if visited[y][x] or pixels[x, y] < alpha_threshold:
                continue

            queue = deque([(x, y)])
            visited[y][x] = True
            xs = []
            ys = []

            while queue:
                cx, cy = queue.popleft()
                xs.append(cx)
                ys.append(cy)
                for nx, ny in (
                    (cx - 1, cy),
                    (cx + 1, cy),
                    (cx, cy - 1),
                    (cx, cy + 1),
                ):
                    if not (0 <= nx < width and 0 <= ny < height):
                        continue
                    if visited[ny][nx] or pixels[nx, ny] < alpha_threshold:
                        continue
                    visited[ny][nx] = True
                    queue.append((nx, ny))

            if len(xs) < min_area:
                continue

            boxes.append((min(xs), min(ys), max(xs) + 1, max(ys) + 1))

    boxes.sort(key=lambda box: (box[1], box[0]))
    return boxes


def _extract_regular_grid_boxes(image, cols, rows, alpha_threshold, min_area):
    alpha = image.getchannel("A")
    pixels = alpha.load()
    width, height = image.size
    boxes = []

    for row in range(rows):
        y0 = round(row * height / rows)
        y1 = round((row + 1) * height / rows) - 1
        for col in range(cols):
            x0 = round(col * width / cols)
            x1 = round((col + 1) * width / cols) - 1
            bbox = _alpha_bbox(alpha, x0, y0, x1, y1, alpha_threshold)
            if bbox is None:
                continue
            area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
            if area >= min_area:
                boxes.append(bbox)

    return boxes


def _boxes_signature(boxes):
    return tuple(boxes)


def _target_trim_average(template):
    widths = [frame["spriteSourceSize"]["w"] for frame in template["unique_frames"]]
    heights = [frame["spriteSourceSize"]["h"] for frame in template["unique_frames"]]
    return (
        sum(widths) / len(widths),
        sum(heights) / len(heights),
    )


def _average_alpha_bbox(frames):
    widths = []
    heights = []
    for frame in frames:
        bbox = frame.getchannel("A").getbbox()
        if bbox is None:
            continue
        widths.append(bbox[2] - bbox[0])
        heights.append(bbox[3] - bbox[1])
    if not widths:
        return (0.0, 0.0)
    return (
        sum(widths) / len(widths),
        sum(heights) / len(heights),
    )


def _bbox_for_image(image_or_mask):
    if image_or_mask.mode == "L":
        return image_or_mask.getbbox()
    return image_or_mask.getchannel("A").getbbox()


def _edge_touch_flags(frames, source_w, source_h, margin=0):
    flags = []
    for frame in frames:
        bbox = _bbox_for_image(frame)
        if bbox is None:
            flags.append(False)
            continue
        flags.append(
            bbox[0] <= margin
            or bbox[1] <= margin
            or bbox[2] >= (source_w - margin)
            or bbox[3] >= (source_h - margin)
        )
    return flags


def _edge_touch_count(frames, source_w, source_h, margin=0):
    return sum(1 for touched in _edge_touch_flags(frames, source_w, source_h, margin=margin) if touched)


def _alpha_area(frame):
    alpha = frame.getchannel("A")
    return sum(1 for value in alpha.getdata() if value >= ALPHA_THRESHOLD)


def _repair_tiny_frames(normalized_frames):
    areas = [_alpha_area(frame) for frame in normalized_frames]
    nonzero = [area for area in areas if area > 0]
    if not nonzero:
        return normalized_frames

    median_area = sorted(nonzero)[len(nonzero) // 2]
    threshold = median_area * 0.35
    repaired = list(normalized_frames)

    for index, area in enumerate(areas):
        if area <= 0 or area >= threshold:
            continue

        replacement_index = None
        for distance in range(1, len(normalized_frames)):
            for candidate in (index - distance, index + distance):
                if 0 <= candidate < len(normalized_frames) and areas[candidate] >= threshold:
                    replacement_index = candidate
                    break
            if replacement_index is not None:
                break

        if replacement_index is not None:
            repaired[index] = normalized_frames[replacement_index].copy()

    return repaired


def _quantile(values, q):
    if not values:
        return 1.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = max(0.0, min(1.0, q)) * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    blend = position - lower
    return ordered[lower] * (1.0 - blend) + ordered[upper] * blend


def _choose_regular_grid_dims(expected_count, image_width, image_height):
    aspect = image_width / max(1, image_height)
    best = None
    max_rows = max(2, int(math.ceil(math.sqrt(expected_count))) + 4)

    for rows in range(1, max_rows + 1):
        min_cols = math.ceil(expected_count / rows)
        for cols in range(min_cols, min_cols + 5):
            cell_count = cols * rows
            candidate_aspect = cols / max(1, rows)
            score = (
                abs(math.log((candidate_aspect + 1e-6) / (aspect + 1e-6))),
                cell_count - expected_count,
                abs(cols - rows),
            )
            if best is None or score < best[0]:
                best = (score, cols, rows)

    return best[1], best[2]


def _binary_alpha(image_or_mask):
    alpha = image_or_mask if image_or_mask.mode == "L" else image_or_mask.getchannel("A")
    return alpha.point(lambda value: 255 if value >= ALPHA_THRESHOLD else 0, mode="L")


def analyze_frame_similarity(normalized_frames, template):
    frame_stats = []
    for frame, reference_mask in zip(normalized_frames, template["unique_masks"], strict=True):
        current_mask = _binary_alpha(frame)
        reference_mask = _binary_alpha(reference_mask)
        current_pixels = current_mask.load()
        reference_pixels = reference_mask.load()

        intersection = union = current_area = reference_area = 0
        for y in range(template["source_h"]):
            for x in range(template["source_w"]):
                current = 1 if current_pixels[x, y] else 0
                reference = 1 if reference_pixels[x, y] else 0
                current_area += current
                reference_area += reference
                intersection += current and reference
                union += current or reference

        iou = intersection / union if union else 1.0
        area_ratio = current_area / reference_area if reference_area else 1.0
        frame_stats.append(
            {
                "iou": iou,
                "area_ratio": area_ratio,
            }
        )

    avg_iou = sum(frame["iou"] for frame in frame_stats) / len(frame_stats)
    min_iou = min(frame["iou"] for frame in frame_stats)
    avg_area_ratio = sum(frame["area_ratio"] for frame in frame_stats) / len(frame_stats)
    min_area_ratio = min(frame["area_ratio"] for frame in frame_stats)
    max_area_ratio = max(frame["area_ratio"] for frame in frame_stats)

    return {
        "avg_iou": avg_iou,
        "min_iou": min_iou,
        "avg_area_ratio": avg_area_ratio,
        "min_area_ratio": min_area_ratio,
        "max_area_ratio": max_area_ratio,
        "frame_stats": frame_stats,
    }


def _median(values):
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2


def summarize_frame_quality(normalized_frames, template, detected_count):
    areas = [_alpha_area(frame) for frame in normalized_frames]
    nonzero_areas = [area for area in areas if area > 0]
    median_area = _median(nonzero_areas)
    tiny_threshold = median_area * 0.45 if median_area > 0 else 0
    tiny_frame_count = sum(1 for area in nonzero_areas if area < tiny_threshold)
    blank_frame_count = len(areas) - len(nonzero_areas)

    similarity = analyze_frame_similarity(normalized_frames, template)
    template_edge_touches = _edge_touch_count(
        template["unique_masks"],
        template["source_w"],
        template["source_h"],
        margin=0,
    )
    edge_touch_count = _edge_touch_count(normalized_frames, template["source_w"], template["source_h"], margin=0)
    excess_edge_touches = max(0, edge_touch_count - template_edge_touches)
    expected_count = max(1, template["unique_count"])
    detected_penalty = max(0, detected_count - expected_count) / expected_count
    area_ratio_penalty = abs(math.log(max(similarity["avg_area_ratio"], 1e-6)))
    min_area_ratio_penalty = abs(math.log(max(similarity["min_area_ratio"], 1e-6)))

    score = similarity["avg_iou"] * 4.0
    score += similarity["min_iou"] * 1.5
    score -= area_ratio_penalty * 1.25
    score -= min_area_ratio_penalty * 1.75
    score -= (tiny_frame_count / max(1, len(areas))) * 4.5
    score -= (blank_frame_count / max(1, len(areas))) * 8.0
    score -= (excess_edge_touches / max(1, len(areas))) * 5.0
    score -= detected_penalty * 0.75

    return {
        "score": score,
        "avg_iou": similarity["avg_iou"],
        "min_iou": similarity["min_iou"],
        "avg_area_ratio": similarity["avg_area_ratio"],
        "min_area_ratio": similarity["min_area_ratio"],
        "max_area_ratio": similarity["max_area_ratio"],
        "min_area_ratio_penalty": min_area_ratio_penalty,
        "tiny_frame_count": tiny_frame_count,
        "blank_frame_count": blank_frame_count,
        "edge_touch_count": edge_touch_count,
        "excess_edge_touches": excess_edge_touches,
        "median_area": median_area,
    }


def _candidate_score(candidate, template):
    expected_count = template["unique_count"]
    sampled_boxes = resample_boxes(candidate["boxes"], expected_count)
    max_width = max(1, template["source_w"] - FRAME_PADDING * 2)
    max_height = max(1, template["source_h"] - FRAME_PADDING * 2)

    scales = []
    output_sizes = []
    for x0, y0, x1, y1 in sampled_boxes:
        box_w = max(1, x1 - x0)
        box_h = max(1, y1 - y0)
        scales.append(min(max_width / box_w, max_height / box_h))

    shared_scale = max(min(scales), 0.01)
    for x0, y0, x1, y1 in sampled_boxes:
        box_w = x1 - x0
        box_h = y1 - y0
        output_sizes.append((box_w * shared_scale, box_h * shared_scale))

    avg_out_w = sum(width for width, _ in output_sizes) / len(output_sizes)
    avg_out_h = sum(height for _, height in output_sizes) / len(output_sizes)
    target_avg_w, target_avg_h = _target_trim_average(template)

    size_penalty = abs(math.log((avg_out_w + 1e-6) / (target_avg_w + 1e-6))) + abs(
        math.log((avg_out_h + 1e-6) / (target_avg_h + 1e-6))
    )
    count_diff = abs(candidate["count"] - expected_count)
    overshoot_window = max(3, expected_count // 4)
    fit_class = 2
    if candidate["count"] == expected_count:
        fit_class = 0
    elif candidate["count"] > expected_count and count_diff <= overshoot_window:
        fit_class = 1
    coverage = avg_out_w * avg_out_h
    return (size_penalty, fit_class, count_diff, -coverage)


def choose_frame_boxes(image, template, mode="auto"):
    expected_count = template["unique_count"]
    min_candidate_count = max(4, expected_count // 2)
    candidates = []
    seen = set()

    row_presets = [
        (1, 1, 1, 2),
        (1, 1, 1, 4),
        (1, 2, 2, 4),
        (4, 2, 2, 4),
        (8, 3, 3, 6),
        (16, 4, 4, 8),
    ]
    component_presets = [
        (1, 96),
        (8, 96),
        (16, 96),
        (8, 160),
    ]

    if mode in ("auto", "row-column"):
        for alpha_threshold, row_threshold, col_threshold, max_gap in row_presets:
            boxes = _extract_row_column_boxes(
                image,
                alpha_threshold=alpha_threshold,
                row_threshold=row_threshold,
                col_threshold=col_threshold,
                max_gap=max_gap,
            )
            if not boxes:
                continue
            signature = ("grid", _boxes_signature(boxes))
            if signature in seen:
                continue
            seen.add(signature)
            candidate = {
                "method": "row-column",
                "boxes": boxes,
                "count": len(boxes),
            }
            if candidate["count"] < min_candidate_count:
                continue
            candidates.append(candidate)

    if mode in ("auto", "components"):
        for alpha_threshold, min_area in component_presets:
            boxes = _extract_component_boxes(
                image,
                alpha_threshold=alpha_threshold,
                min_area=min_area,
            )
            if not boxes:
                continue
            signature = ("components", _boxes_signature(boxes))
            if signature in seen:
                continue
            seen.add(signature)
            candidate = {
                "method": "components",
                "boxes": boxes,
                "count": len(boxes),
            }
            if candidate["count"] < min_candidate_count:
                continue
            candidates.append(candidate)

    if mode in ("auto", "regular-grid"):
        for rows in range(2, 7):
            for cols in range(3, 10):
                if cols * rows < expected_count or cols * rows > expected_count + 8:
                    continue
                boxes = _extract_regular_grid_boxes(
                    image,
                    cols=cols,
                    rows=rows,
                    alpha_threshold=8,
                    min_area=MIN_COMPONENT_AREA,
                )
                if not boxes:
                    continue
                signature = ("grid", _boxes_signature(boxes))
                if signature in seen:
                    continue
                seen.add(signature)
                candidate = {
                    "method": f"grid-{cols}x{rows}",
                    "boxes": boxes,
                    "count": len(boxes),
                }
                if candidate["count"] < min_candidate_count:
                    continue
                candidates.append(candidate)

    if not candidates:
        raise RuntimeError(f"Could not detect any sprite frames in generated sheet using mode={mode}.")
    return min(candidates, key=lambda candidate: _candidate_score(candidate, template))


def _prune_small_outlier_boxes(boxes, expected_count):
    if len(boxes) <= expected_count:
        return list(boxes)

    widths = sorted(box[2] - box[0] for box in boxes)
    heights = sorted(box[3] - box[1] for box in boxes)
    areas = sorted((box[2] - box[0]) * (box[3] - box[1]) for box in boxes)
    median_width = widths[len(widths) // 2]
    median_height = heights[len(heights) // 2]
    median_area = areas[len(areas) // 2]

    filtered = [
        box
        for box in boxes
        if (box[2] - box[0]) >= median_width * 0.55
        and (box[3] - box[1]) >= median_height * 0.55
        and ((box[2] - box[0]) * (box[3] - box[1])) >= median_area * 0.4
    ]
    if len(filtered) >= expected_count:
        return filtered

    stricter = [
        box
        for box in boxes
        if (box[2] - box[0]) >= median_width * 0.7
        and (box[3] - box[1]) >= median_height * 0.55
        and ((box[2] - box[0]) * (box[3] - box[1])) >= median_area * 0.45
    ]
    if len(stricter) >= expected_count:
        return stricter

    ranked = sorted(
        boxes,
        key=lambda box: (
            -((box[2] - box[0]) * (box[3] - box[1])),
            -(box[2] - box[0]),
            -(box[3] - box[1]),
        ),
    )
    keep = set(ranked[:expected_count])
    return [box for box in boxes if box in keep]


def _prune_edge_touching_boxes(boxes, image_size, expected_count, margin=4):
    if not boxes:
        return []

    width, height = image_size
    filtered = [
        box
        for box in boxes
        if box[0] > margin
        and box[1] > margin
        and box[2] < (width - margin)
        and box[3] < (height - margin)
    ]
    minimum_keep = max(4, int(math.ceil(expected_count * 0.85)))
    if len(filtered) >= minimum_keep:
        return filtered
    return list(boxes)


def resample_boxes(boxes, expected_count):
    if not boxes:
        raise RuntimeError("No frame boxes available to normalize.")
    boxes = _prune_small_outlier_boxes(boxes, expected_count)
    if len(boxes) == expected_count:
        return list(boxes)
    if expected_count == 1:
        return [boxes[len(boxes) // 2]]

    last = len(boxes) - 1
    result = []
    for index in range(expected_count):
        src_index = round(index * last / (expected_count - 1))
        result.append(boxes[src_index])
    return result


def _resample_indices(count, expected_count):
    if count <= 0:
        raise RuntimeError("No regular-grid cells available to normalize.")
    if count == expected_count:
        return list(range(count))
    if expected_count == 1:
        return [count // 2]

    last = count - 1
    return [round(index * last / (expected_count - 1)) for index in range(expected_count)]


def _has_meaningful_transparency(image, threshold=ALPHA_THRESHOLD, min_ratio=0.02):
    alpha = image.getchannel("A")
    min_alpha, _max_alpha = alpha.getextrema()
    if min_alpha >= threshold:
        return False

    transparent_pixels = sum(1 for value in alpha.getdata() if value < threshold)
    return transparent_pixels >= max(8, int(round(image.width * image.height * min_ratio)))


def pixelify_image(image, base_width=32, output_width=None, output_height=None):
    """Mirror TempaiTown's pixelify pass: nearest downscale, then nearest upscale."""
    width, height = image.size
    if width <= 0 or height <= 0:
        return image

    output_width = output_width or width
    output_height = output_height or max(1, int(round(height * output_width / width)))
    base_width = max(1, min(base_width, width, output_width))
    base_height = max(1, int(round(height * base_width / width)))

    reduced = image.resize((base_width, base_height), Image.NEAREST)
    return reduced.resize((output_width, output_height), Image.NEAREST)


def pixelify_file_in_place(image_path, base_width):
    image = Image.open(image_path).convert("RGBA")
    pixelified = pixelify_image(image, base_width=base_width, output_width=image.width, output_height=image.height)
    pixelified.save(image_path)


def _resize_crop(crop, max_width, max_height, pixel_base):
    width, height = crop.size
    if width <= 0 or height <= 0:
        return crop

    scale = min(max_width / width, max_height / height)
    scale = max(scale, 0.01)
    new_width = max(1, int(round(width * scale)))
    new_height = max(1, int(round(height * scale)))
    return pixelify_image(
        crop,
        base_width=min(pixel_base, new_width),
        output_width=new_width,
        output_height=new_height,
    )


def _focus_bbox_for_scale(crop):
    """Use the full silhouette so tall species stay inside the battle frame."""
    alpha = crop.getchannel("A")
    width, height = crop.size
    bbox = alpha.getbbox()
    if bbox is None:
        return (0, 0, width, height)
    return bbox


def _render_scaled_frames(crops, template, shared_scale, clip_to_template_mask=True):
    source_w = template["source_w"]
    source_h = template["source_h"]
    normalized = []

    for index, (crop, focus_bbox) in enumerate(crops):
        resized = _resize_crop(
            crop,
            max_width=max(1, int(round(crop.size[0] * shared_scale))),
            max_height=max(1, int(round(crop.size[1] * shared_scale))),
            pixel_base=FRAME_PIXELIFY_BASE,
        )

        frame = Image.new("RGBA", (source_w, source_h), (0, 0, 0, 0))
        trim = template["unique_frames"][index]["spriteSourceSize"]
        resize_scale_x = resized.size[0] / max(1, crop.size[0])
        resize_scale_y = resized.size[1] / max(1, crop.size[1])
        focus_center_x = ((focus_bbox[0] + focus_bbox[2]) / 2) * resize_scale_x
        focus_bottom_y = focus_bbox[3] * resize_scale_y
        dest_x = round(trim["x"] + trim["w"] / 2 - focus_center_x)
        dest_y = round(trim["y"] + trim["h"] - focus_bottom_y)
        frame.paste(resized, (dest_x, dest_y), resized)
        if clip_to_template_mask:
            mask = template["unique_masks"][index].filter(ImageFilter.MaxFilter(MASK_CLIP_FILTER))
            frame.putalpha(ImageChops.multiply(frame.getchannel("A"), mask))
        normalized.append(frame)

    return normalized


def _render_regular_grid_frames(cells, template):
    source_w = template["source_w"]
    source_h = template["source_h"]
    normalized = []

    for cell in cells:
        cleaned = _remove_edge_background(cell)
        trimmed = _alpha_trimmed(cleaned)
        resized = _resize_crop(
            trimmed,
            max_width=max(1, source_w - FRAME_PADDING * 2),
            max_height=max(1, source_h - FRAME_PADDING * 2),
            pixel_base=FRAME_PIXELIFY_BASE,
        )

        frame = Image.new("RGBA", (source_w, source_h), (0, 0, 0, 0))
        alpha_bbox = resized.getchannel("A").getbbox() or (0, 0, resized.size[0], resized.size[1])
        alpha_center_x = (alpha_bbox[0] + alpha_bbox[2]) / 2
        alpha_bottom_y = alpha_bbox[3]
        dest_x = round(source_w / 2 - alpha_center_x)
        dest_y = round(source_h - FRAME_PADDING - alpha_bottom_y)
        frame.paste(resized, (dest_x, dest_y), resized)
        normalized.append(frame)

    return normalized


def _render_centered_frames(crops, source_w, source_h, shared_scale):
    normalized = []

    for crop in crops:
        resized = _resize_crop(
            crop,
            max_width=max(1, int(round(crop.size[0] * shared_scale))),
            max_height=max(1, int(round(crop.size[1] * shared_scale))),
            pixel_base=FRAME_PIXELIFY_BASE,
        )

        frame = Image.new("RGBA", (source_w, source_h), (0, 0, 0, 0))
        alpha_bbox = resized.getchannel("A").getbbox() or (0, 0, resized.size[0], resized.size[1])
        alpha_center_x = (alpha_bbox[0] + alpha_bbox[2]) / 2
        alpha_bottom_y = alpha_bbox[3]
        dest_x = round(source_w / 2 - alpha_center_x)
        dest_y = round(source_h - FRAME_PADDING - alpha_bottom_y)
        frame.paste(resized, (dest_x, dest_y), resized)
        normalized.append(frame)

    return normalized


def _mapped_template_boxes(image, template):
    mapped = []
    for frame in template["unique_frames"]:
        rect = frame["frame"]
        x0 = max(0, min(image.width - 1, round(rect["x"] * image.width / template["sheet_w"])))
        y0 = max(0, min(image.height - 1, round(rect["y"] * image.height / template["sheet_h"])))
        x1 = max(x0 + 1, min(image.width, round((rect["x"] + rect["w"]) * image.width / template["sheet_w"])))
        y1 = max(y0 + 1, min(image.height, round((rect["y"] + rect["h"]) * image.height / template["sheet_h"])))
        mapped.append((x0, y0, x1, y1))
    return mapped


def _normalize_crops(crops, template, clip_to_template_mask=True, centered=False):
    scales = []
    prepared_crops = []
    for index, crop in enumerate(crops):
        focus_bbox = _focus_bbox_for_scale(crop)
        focus_w = max(1, focus_bbox[2] - focus_bbox[0])
        focus_h = max(1, focus_bbox[3] - focus_bbox[1])
        if centered:
            target_width = max(1, template["source_w"] - FRAME_PADDING * 2)
            target_height = max(1, template["source_h"] - FRAME_PADDING * 2)
        else:
            trim = template["unique_frames"][index]["spriteSourceSize"]
            target_width = max(1, trim["w"] - FRAME_PADDING * 2)
            target_height = max(1, trim["h"] - FRAME_PADDING * 2)
        scales.append(min(target_width / focus_w, target_height / focus_h))
        prepared_crops.append((crop, focus_bbox))

    if centered:
        shared_scale = max(min(scales) * 0.98, 0.01)
        normalized = _render_centered_frames(
            [crop for crop, _ in prepared_crops],
            template["source_w"],
            template["source_h"],
            shared_scale,
        )
    else:
        shared_scale = max(_quantile(scales, SCALE_FIT_QUANTILE), 0.01)
        target_avg_w, target_avg_h = _target_trim_average(template)
        template_edge_touches = _edge_touch_count(template["unique_masks"], template["source_w"], template["source_h"], margin=0)
        normalized = []
        for _ in range(SCALE_FIT_ITERATIONS):
            normalized = _render_scaled_frames(
                prepared_crops,
                template,
                shared_scale,
                clip_to_template_mask=clip_to_template_mask,
            )
            avg_out_w, avg_out_h = _average_alpha_bbox(normalized)
            if avg_out_w <= 0 or avg_out_h <= 0:
                break
            correction = min(target_avg_w / avg_out_w, target_avg_h / avg_out_h)
            edge_touches = _edge_touch_count(normalized, template["source_w"], template["source_h"], margin=0)
            excess_edge_touches = max(0, edge_touches - template_edge_touches)
            if excess_edge_touches:
                touch_ratio = excess_edge_touches / max(1, len(normalized))
                correction = min(correction, 0.85 if touch_ratio > 0.15 else 0.92)
            if abs(1.0 - correction) <= SCALE_FIT_TOLERANCE:
                break
            shared_scale *= max(0.75, min(1.5, correction))

    return {
        "frames": _repair_tiny_frames(normalized),
        "shared_scale": shared_scale,
    }


def _result_quality(result, template):
    stats = analyze_frame_similarity(result["frames"], template)
    avg_area_penalty = abs(math.log(max(stats["avg_area_ratio"], 1e-6)))
    overfill_penalty = max(0.0, stats["max_area_ratio"] - 1.2)
    score = (
        stats["avg_iou"] * 4.0
        + stats["min_iou"] * 2.5
        + min(1.0, stats["min_area_ratio"]) * 1.5
        - avg_area_penalty
        - overfill_penalty
    )
    return score, stats


def normalize_template_layout_frames(image, template, clip_to_template_mask=True, centered=False):
    mapped_boxes = _mapped_template_boxes(image, template)
    crops = []
    for x0, y0, x1, y1 in mapped_boxes:
        cell = _strip_edge_background_if_needed(image.crop((x0, y0, x1, y1)))
        alpha_bbox = cell.getchannel("A").getbbox()
        crops.append(cell.crop(alpha_bbox) if alpha_bbox else cell)

    normalized = _normalize_crops(
        crops,
        template,
        clip_to_template_mask=clip_to_template_mask,
        centered=centered,
    )
    return {
        "frames": normalized["frames"],
        "sampled_boxes": mapped_boxes,
        "detected_count": len(mapped_boxes),
        "method": "template-layout-centered" if centered else "template-layout",
        "shared_scale": normalized["shared_scale"],
    }


def _prune_small_outlier_images(cells, expected_count):
    if len(cells) <= expected_count:
        return list(cells)

    metrics = []
    for index, cell in enumerate(cells):
        bbox = cell.getchannel("A").getbbox()
        if bbox is None:
            continue
        bbox_w = bbox[2] - bbox[0]
        bbox_h = bbox[3] - bbox[1]
        metrics.append(
            {
                "index": index,
                "cell": cell,
                "bbox_w": bbox_w,
                "bbox_h": bbox_h,
                "bbox_area": bbox_w * bbox_h,
                "alpha_area": _alpha_area(cell),
            }
        )

    if len(metrics) <= expected_count:
        return [entry["cell"] for entry in metrics]

    bbox_widths = sorted(entry["bbox_w"] for entry in metrics)
    bbox_heights = sorted(entry["bbox_h"] for entry in metrics)
    alpha_areas = sorted(entry["alpha_area"] for entry in metrics)
    median_width = bbox_widths[len(bbox_widths) // 2]
    median_height = bbox_heights[len(bbox_heights) // 2]
    median_alpha_area = alpha_areas[len(alpha_areas) // 2]
    minimum_keep = max(4, int(math.ceil(expected_count * 0.85)))

    filtered = [
        entry
        for entry in metrics
        if entry["alpha_area"] >= median_alpha_area * 0.32
        and (
            entry["bbox_w"] >= median_width * 0.4
            or entry["bbox_h"] >= median_height * 0.4
        )
    ]
    if len(filtered) >= minimum_keep:
        return [entry["cell"] for entry in filtered]

    if len(filtered) < expected_count:
        filtered = [
            entry
            for entry in metrics
            if entry["alpha_area"] >= median_alpha_area * 0.24
            and (
                entry["bbox_w"] >= median_width * 0.35
                or entry["bbox_h"] >= median_height * 0.35
            )
        ]
    if len(filtered) >= minimum_keep:
        return [entry["cell"] for entry in filtered]
    return list(cells)


def normalize_frames(image, template, clip_to_template_mask=True, mode="auto", centered=False):
    choice = choose_frame_boxes(image, template, mode=mode)
    boxes = choice["boxes"]
    if choice["method"] == "components":
        boxes = _prune_edge_touching_boxes(boxes, image.size, template["unique_count"])
    sampled_boxes = resample_boxes(boxes, template["unique_count"])

    crops = []
    for index, (x0, y0, x1, y1) in enumerate(sampled_boxes):
        crop = image.crop((x0, y0, x1, y1))
        crops.append(crop)

    normalized = _normalize_crops(
        crops,
        template,
        clip_to_template_mask=clip_to_template_mask,
        centered=centered,
    )

    return {
        "frames": normalized["frames"],
        "sampled_boxes": sampled_boxes,
        "detected_count": len(boxes),
        "method": f"{choice['method']}-centered" if centered else choice["method"],
        "shared_scale": normalized["shared_scale"],
    }


def normalize_regular_grid_frames(image, template):
    expected_count = template["unique_count"]
    cols, rows = _choose_regular_grid_dims(expected_count, image.width, image.height)
    cells = []

    for row in range(rows):
        y0 = round(row * image.height / rows)
        y1 = round((row + 1) * image.height / rows)
        for col in range(cols):
            x0 = round(col * image.width / cols)
            x1 = round((col + 1) * image.width / cols)
            cell = image.crop((x0, y0, x1, y1))
            alpha_bbox = cell.getchannel("A").getbbox()
            if alpha_bbox is None:
                continue
            area = sum(1 for value in cell.getchannel("A").getdata() if value >= ALPHA_THRESHOLD)
            if area < MIN_COMPONENT_AREA:
                continue
            cells.append(cell)

    sampled_indices = _resample_indices(len(cells), expected_count)
    sampled_images = [cells[index] for index in sampled_indices]
    normalized = _render_regular_grid_frames(sampled_images, template)
    normalized = _repair_tiny_frames(normalized)

    return {
        "frames": normalized,
        "sampled_boxes": sampled_indices,
        "detected_count": len(cells),
        "method": f"regular-grid-{cols}x{rows}",
        "shared_scale": 1.0,
    }


def _normalize_grid_cell_crops(cells, template, method, detected_count):
    expected_count = template["unique_count"]
    cells = _prune_small_outlier_images(cells, expected_count)
    sampled_indices = _resample_indices(len(cells), expected_count)
    sampled_crops = [cells[index] for index in sampled_indices]

    source_w = template["source_w"]
    source_h = template["source_h"]
    scales = []
    for crop in sampled_crops:
        focus_bbox = _focus_bbox_for_scale(crop)
        focus_w = max(1, focus_bbox[2] - focus_bbox[0])
        focus_h = max(1, focus_bbox[3] - focus_bbox[1])
        scale = min(
            max(1, source_w - FRAME_PADDING * 2) / focus_w,
            max(1, source_h - FRAME_PADDING * 2) / focus_h,
        )
        scales.append(scale)

    # Fal sheets already define a coherent slot layout, so use one shared fit against
    # the full battle canvas instead of inheriting per-frame offsets from the template.
    candidate_scales = []
    for quantile in EXACT_GRID_SCALE_QUANTILES:
        if quantile <= 0:
            candidate_scales.append(max(min(scales) * 0.98, 0.01))
        else:
            candidate_scales.append(max(_quantile(scales, quantile) * 0.98, 0.01))

    target_avg_w, target_avg_h = _target_trim_average(template)
    template_edge_touches = _edge_touch_count(template["unique_masks"], source_w, source_h, margin=0)

    best_normalized = None
    best_score = None
    best_scale = None
    seen_scales = set()
    for initial_scale in candidate_scales:
        scale_key = round(initial_scale, 4)
        if scale_key in seen_scales:
            continue
        seen_scales.add(scale_key)

        shared_scale = initial_scale
        normalized = []
        for _ in range(SCALE_FIT_ITERATIONS):
            normalized = _render_centered_frames(sampled_crops, source_w, source_h, shared_scale)
            avg_out_w, avg_out_h = _average_alpha_bbox(normalized)
            if avg_out_w <= 0 or avg_out_h <= 0:
                break
            correction = min(target_avg_w / avg_out_w, target_avg_h / avg_out_h)
            edge_touches = _edge_touch_count(normalized, source_w, source_h, margin=0)
            excess_edge_touches = max(0, edge_touches - template_edge_touches)
            if excess_edge_touches:
                touch_ratio = excess_edge_touches / max(1, len(normalized))
                correction = min(correction, 0.85 if touch_ratio > 0.15 else 0.92)
            if abs(1.0 - correction) <= SCALE_FIT_TOLERANCE:
                break
            shared_scale *= max(0.75, min(1.4, correction))

        normalized = _repair_tiny_frames(normalized)
        score, _stats = _result_quality({"frames": normalized}, template)
        if best_score is None or score > best_score:
            best_score = score
            best_normalized = normalized
            best_scale = shared_scale

    return {
        "frames": best_normalized,
        "sampled_boxes": sampled_indices,
        "detected_count": detected_count,
        "method": method,
        "shared_scale": best_scale,
    }


def normalize_fixed_grid_frames(image, template, cols, rows):
    cells = []
    for row in range(rows):
        y0 = round(row * image.height / rows)
        y1 = round((row + 1) * image.height / rows)
        for col in range(cols):
            x0 = round(col * image.width / cols)
            x1 = round((col + 1) * image.width / cols)
            cell = _strip_edge_background_if_needed(image.crop((x0, y0, x1, y1)))
            alpha_bbox = cell.getchannel("A").getbbox()
            if alpha_bbox is None:
                continue
            trimmed = cell.crop(alpha_bbox)
            if _alpha_area(trimmed) < MIN_COMPONENT_AREA:
                continue
            cells.append(trimmed)

    return _normalize_grid_cell_crops(cells, template, f"exact-grid-{cols}x{rows}", len(cells))


def normalize_slot_grid_frames(image, template, cols, rows):
    """Group disconnected sprite fragments back into fixed source-sheet slots."""
    clean = _strip_edge_background_if_needed(image)
    cell_w = clean.width / max(1, cols)
    cell_h = clean.height / max(1, rows)
    slot_boxes = [[] for _ in range(cols * rows)]
    components = _extract_component_boxes(clean, ALPHA_THRESHOLD, 24)

    for x0, y0, x1, y1 in components:
        area = (x1 - x0) * (y1 - y0)
        if area < 24:
            continue
        center_x = (x0 + x1) / 2
        center_y = (y0 + y1) / 2
        col = min(cols - 1, max(0, int(center_x / cell_w)))
        row = min(rows - 1, max(0, int(center_y / cell_h)))
        slot_boxes[row * cols + col].append((x0, y0, x1, y1))

    pad = max(4, int(round(min(cell_w, cell_h) * 0.025)))
    cells = []
    for boxes in slot_boxes:
        if not boxes:
            continue
        x0 = max(0, min(box[0] for box in boxes) - pad)
        y0 = max(0, min(box[1] for box in boxes) - pad)
        x1 = min(clean.width, max(box[2] for box in boxes) + pad)
        y1 = min(clean.height, max(box[3] for box in boxes) + pad)
        crop = clean.crop((x0, y0, x1, y1))
        alpha_bbox = crop.getchannel("A").getbbox()
        if alpha_bbox is None:
            continue
        trimmed = crop.crop(alpha_bbox)
        if _alpha_area(trimmed) < MIN_COMPONENT_AREA:
            continue
        cells.append(trimmed)

    if not cells:
        raise RuntimeError(f"Could not extract slot-grid cells from generated sheet {cols}x{rows}.")

    return _normalize_grid_cell_crops(cells, template, f"slot-grid-{cols}x{rows}", len(cells))


def write_normalized_atlas(normalized_frames, template, output_png_path, output_json_path):
    unique_count = len(normalized_frames)
    source_w = template["source_w"]
    source_h = template["source_h"]
    cols = max(1, math.ceil(math.sqrt(unique_count)))
    rows = max(1, math.ceil(unique_count / cols))
    sheet_w = cols * source_w
    sheet_h = rows * source_h

    atlas_image = Image.new("RGBA", (sheet_w, sheet_h), (0, 0, 0, 0))
    frame_meta = []
    for index, frame in enumerate(normalized_frames):
        slot_x = (index % cols) * source_w
        slot_y = (index // cols) * source_h
        bbox = frame.getchannel("A").getbbox()
        if bbox is None:
          bbox = (0, 0, 1, 1)
        crop = frame.crop(bbox)
        atlas_image.paste(crop, (slot_x, slot_y), crop)
        frame_meta.append(
            {
                "slot_x": slot_x,
                "slot_y": slot_y,
                "bbox": bbox,
                "trimmed": bbox != (0, 0, source_w, source_h),
            }
        )

    atlas_image.save(output_png_path)

    atlas_frames = []
    for original_frame, unique_index in zip(
        template["frames"], template["frame_to_unique"], strict=True
    ):
        meta = frame_meta[unique_index]
        bbox = meta["bbox"]
        bbox_w = bbox[2] - bbox[0]
        bbox_h = bbox[3] - bbox[1]
        atlas_frames.append(
            {
                "filename": original_frame["filename"],
                "rotated": False,
                "trimmed": meta["trimmed"],
                "sourceSize": original_frame["sourceSize"],
                "spriteSourceSize": {"x": bbox[0], "y": bbox[1], "w": bbox_w, "h": bbox_h},
                "frame": {"x": meta["slot_x"], "y": meta["slot_y"], "w": bbox_w, "h": bbox_h},
            }
        )

    atlas = {
        "textures": [
            {
                "image": template["image"],
                "format": template["format"],
                "size": {"w": sheet_w, "h": sheet_h},
                "scale": template["scale"],
                "frames": atlas_frames,
            }
        ]
    }

    with open(output_json_path, "w") as f:
        json.dump(atlas, f, indent="\t")

    return {"sheet_w": sheet_w, "sheet_h": sheet_h, "cols": cols, "rows": rows}


def normalize_battle_sprite(
    raw_png_path,
    template_json_path,
    output_png_path,
    output_json_path,
    clip_to_template_mask=True,
    mode="auto",
    grid_dims=None,
    centered=False,
):
    template = load_template_atlas(template_json_path)
    image = Image.open(raw_png_path).convert("RGBA")
    if grid_dims:
        if mode == "slot-grid":
            result = normalize_slot_grid_frames(image, template, grid_dims[0], grid_dims[1])
        else:
            result = normalize_fixed_grid_frames(image, template, grid_dims[0], grid_dims[1])
    elif mode == "regular-grid":
        result = normalize_regular_grid_frames(image, template)
    else:
        candidates = [
            normalize_fixed_grid_frames(
                image,
                template,
                *_choose_regular_grid_dims(template["unique_count"], image.width, image.height),
            ),
            normalize_template_layout_frames(
                image,
                template,
                clip_to_template_mask=clip_to_template_mask,
                centered=centered,
            ),
            normalize_frames(
                image,
                template,
                clip_to_template_mask=clip_to_template_mask,
                mode=mode,
                centered=centered,
            ),
        ]
        result = max(candidates, key=lambda candidate: _result_quality(candidate, template)[0])
    sheet_meta = write_normalized_atlas(
        result["frames"],
        template,
        output_png_path,
        output_json_path,
    )
    return {
        "expected_count": template["unique_count"],
        "detected_count": result["detected_count"],
        "method": result["method"],
        "shared_scale": result["shared_scale"],
        **sheet_meta,
    }


def _run_normalization_plan(
    image,
    template,
    *,
    clip_to_template_mask=True,
    mode="auto",
    grid_dims=None,
    centered=False,
):
    if grid_dims:
        if mode == "slot-grid":
            result = normalize_slot_grid_frames(image, template, grid_dims[0], grid_dims[1])
        else:
            result = normalize_fixed_grid_frames(image, template, grid_dims[0], grid_dims[1])
    elif mode == "template-layout":
        result = normalize_template_layout_frames(
            image,
            template,
            clip_to_template_mask=clip_to_template_mask,
            centered=centered,
        )
    elif mode == "regular-grid":
        result = normalize_regular_grid_frames(image, template)
    else:
        result = normalize_frames(
            image,
            template,
            clip_to_template_mask=clip_to_template_mask,
            mode=mode,
            centered=centered,
        )

    quality = summarize_frame_quality(result["frames"], template, result["detected_count"])
    return {
        **result,
        "quality": quality,
    }


def _plan_key(mode, grid_dims, centered):
    return (
        mode,
        tuple(grid_dims) if grid_dims else None,
        centered,
    )


def _candidate_plans(mode, grid_dims, centered, inferred_grid_dims=None):
    if mode == "slot-grid" and grid_dims:
        return [
            {"mode": "slot-grid", "grid_dims": grid_dims, "centered": centered},
        ]

    candidates = [
        {"mode": mode, "grid_dims": grid_dims, "centered": centered},
    ]

    if grid_dims:
        candidates.extend(
            [
                {"mode": "template-layout", "grid_dims": None, "centered": centered},
                {"mode": "auto", "grid_dims": None, "centered": True},
                {"mode": "components", "grid_dims": None, "centered": True},
                {"mode": "regular-grid", "grid_dims": None, "centered": False},
            ]
        )
    else:
        if inferred_grid_dims and inferred_grid_dims[0] * inferred_grid_dims[1] >= 4:
            candidates.append({"mode": "auto", "grid_dims": inferred_grid_dims, "centered": False})
        candidates.extend(
            [
                {"mode": "template-layout", "grid_dims": None, "centered": False},
                {"mode": "template-layout", "grid_dims": None, "centered": True},
                {"mode": "auto", "grid_dims": None, "centered": True},
                {"mode": "components", "grid_dims": None, "centered": True},
                {"mode": "row-column", "grid_dims": None, "centered": True},
                {"mode": "regular-grid", "grid_dims": None, "centered": False},
            ]
        )
        if centered:
            candidates.append({"mode": "auto", "grid_dims": None, "centered": False})
        else:
            candidates.append({"mode": "components", "grid_dims": None, "centered": False})

    unique = []
    seen = set()
    for candidate in candidates:
        key = _plan_key(candidate["mode"], candidate["grid_dims"], candidate["centered"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def normalize_battle_sprite_best_effort(
    raw_png_path,
    template_json_path,
    output_png_path,
    output_json_path,
    clip_to_template_mask=True,
    mode="auto",
    grid_dims=None,
    centered=False,
):
    template = load_template_atlas(template_json_path)
    image = Image.open(raw_png_path).convert("RGBA")
    candidates = []
    inferred_grid_dims = None if grid_dims else _choose_regular_grid_dims(template["unique_count"], image.width, image.height)

    for plan in _candidate_plans(mode, grid_dims, centered, inferred_grid_dims=inferred_grid_dims):
        try:
            result = _run_normalization_plan(
                image,
                template,
                clip_to_template_mask=clip_to_template_mask,
                mode=plan["mode"],
                grid_dims=plan["grid_dims"],
                centered=plan["centered"],
            )
            candidates.append(
                {
                    **plan,
                    **result,
                }
            )
        except RuntimeError:
            continue

    if not candidates:
        raise RuntimeError("Could not normalize sprite sheet with any extraction plan.")

    best = max(
        candidates,
        key=lambda candidate: (
            candidate["quality"]["score"],
            candidate["quality"]["avg_iou"],
            candidate["quality"]["min_iou"],
        ),
    )
    sheet_meta = write_normalized_atlas(
        best["frames"],
        template,
        output_png_path,
        output_json_path,
    )
    requested_key = _plan_key(mode, grid_dims, centered)
    applied_key = _plan_key(best["mode"], best["grid_dims"], best["centered"])
    tried_methods = [
        f"{candidate['method']} [score={candidate['quality']['score']:.3f}]"
        for candidate in sorted(candidates, key=lambda candidate: candidate["quality"]["score"], reverse=True)
    ]
    return {
        "expected_count": template["unique_count"],
        "detected_count": best["detected_count"],
        "method": best["method"],
        "shared_scale": best["shared_scale"],
        "quality_score": best["quality"]["score"],
        "avg_iou": best["quality"]["avg_iou"],
        "min_iou": best["quality"]["min_iou"],
        "tiny_frame_count": best["quality"]["tiny_frame_count"],
        "blank_frame_count": best["quality"]["blank_frame_count"],
        "excess_edge_touches": best["quality"]["excess_edge_touches"],
        "fallback_used": applied_key != requested_key,
        "tried_methods": tried_methods,
        **sheet_meta,
    }


def _alpha_trimmed(image):
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    if not bbox:
        return image
    return image.crop(bbox)


def _remove_edge_background(image, tolerance=24):
    """Flood-fill border colors to transparent for crops that still have baked backgrounds."""
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

    color_counts = {}
    opaque_border_points = 0
    for x, y in border_points:
        r, g, b, a = pixels[x, y]
        if a == 0:
            continue
        opaque_border_points += 1
        key = (r // 8, g // 8, b // 8)
        color_counts[key] = color_counts.get(key, 0) + 1

    if not color_counts:
        return rgba

    border_point_count = len(border_points)
    if opaque_border_points < max(EDGE_BACKGROUND_MIN_OPAQUE_BORDER_PIXELS, int(border_point_count * 0.08)):
        return rgba

    opaque_ratio = opaque_border_points / max(1, border_point_count)
    dominant_ratio = max(color_counts.values()) / max(1, opaque_border_points)
    if (
        opaque_ratio < EDGE_BACKGROUND_MIN_OPAQUE_BORDER_RATIO
        or dominant_ratio < EDGE_BACKGROUND_MIN_DOMINANT_RATIO
        or len(color_counts) > EDGE_BACKGROUND_MAX_QUANTIZED_COLORS
    ):
        return rgba

    reference_colors = [
        (r * 8 + 4, g * 8 + 4, b * 8 + 4)
        for r, g, b in sorted(color_counts, key=color_counts.get, reverse=True)[:6]
    ]

    def is_background(color):
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


def _strip_edge_background_if_needed(image, tolerance=24):
    if _has_meaningful_transparency(image):
        return image
    return _remove_edge_background(image, tolerance=tolerance)


def render_icon_from_battle_atlas(game_png_path, game_json_path, target_w, target_h, pixel_base=ICON_PIXELIFY_BASE):
    template = load_template_atlas(game_json_path)
    img = Image.open(game_png_path).convert("RGBA")
    first_frame = template["frames"][0]["frame"]
    frame = img.crop(
        (
            first_frame["x"],
            first_frame["y"],
            first_frame["x"] + first_frame["w"],
            first_frame["y"] + first_frame["h"],
        )
    )

    alpha = frame.getchannel("A")
    has_transparency = alpha.getextrema()[0] == 0
    if has_transparency:
        cropped = _alpha_trimmed(frame)
    else:
        cropped = _alpha_trimmed(_remove_edge_background(frame))
    master_size = 32
    master = Image.new("RGBA", (master_size, master_size), (0, 0, 0, 0))
    resized = _resize_crop(
        cropped,
        max(1, master_size - ICON_PADDING * 2),
        max(1, master_size - ICON_PADDING * 2),
        pixel_base=pixel_base,
    )
    dest_x = (master_size - resized.size[0]) // 2
    dest_y = master_size - ICON_PADDING - resized.size[1]
    master.paste(resized, (dest_x, dest_y), resized)

    if target_w == master_size and target_h == master_size:
        return master
    return master.resize((target_w, target_h), Image.NEAREST)
