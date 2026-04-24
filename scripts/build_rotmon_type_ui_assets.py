#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TYPE_ORDER = [
    "unknown",
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
    "stellar",
]

TYPE_COLORS = {
    "unknown": "#8f969d",
    "bug": "#6aa73a",
    "dark": "#4e405a",
    "dragon": "#526fd8",
    "electric": "#e2bd33",
    "fairy": "#d46cc3",
    "fighting": "#bf543f",
    "fire": "#d95a33",
    "flying": "#79a7bd",
    "ghost": "#7653a7",
    "grass": "#42a957",
    "ground": "#b88746",
    "ice": "#86d9e4",
    "normal": "#b6b2a0",
    "poison": "#9748b8",
    "psychic": "#cf4f89",
    "rock": "#8f7a58",
    "steel": "#8fa2a6",
    "water": "#347ec6",
    "stellar": "#78d6ff",
}

TYPE_LABELS = {
    "unknown": ("?", "???"),
    "bug": ("虫", "BUG"),
    "dark": ("悪", "DRK"),
    "dragon": ("竜", "DRG"),
    "electric": ("電", "ELC"),
    "fairy": ("妖", "FAE"),
    "fighting": ("闘", "FGT"),
    "fire": ("火", "FIR"),
    "flying": ("飛", "FLY"),
    "ghost": ("霊", "GST"),
    "grass": ("草", "GRS"),
    "ground": ("地", "GRD"),
    "ice": ("氷", "ICE"),
    "normal": ("普", "NRM"),
    "poison": ("毒", "PSN"),
    "psychic": ("念", "PSY"),
    "rock": ("岩", "RCK"),
    "steel": ("鋼", "STL"),
    "water": ("水", "WTR"),
    "stellar": ("星", "STR"),
}

CATEGORY_ORDER = ["physical", "special", "status"]
CATEGORY_LABELS = {
    "physical": "PHY",
    "special": "SPC",
    "status": "FX",
}
CATEGORY_COLORS = {
    "physical": "#cf5134",
    "special": "#4e6fd3",
    "status": "#5f9f4d",
}

try:
    RESAMPLE = Image.Resampling.LANCZOS
except AttributeError:
    RESAMPLE = Image.LANCZOS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Rotmon type UI atlases from extracted TCG type assets.")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("output/rotmon-tcg-type-icons"),
        help="Folder containing icons/*.png and labels/*.png from extract_tcg_type_icons.py.",
    )
    parser.add_argument("--asset-root", type=Path, default=Path("assets/images"))
    parser.add_argument("--preview", type=Path, default=Path("output/qc/rotmon-type-ui-preview.png"))
    return parser.parse_args()


def atlas_json(image_name: str, frame_w: int, frame_h: int, names: list[str]) -> dict:
    frames = []
    for index, name in enumerate(names):
        frames.append(
            {
                "filename": name,
                "rotated": False,
                "trimmed": False,
                "sourceSize": {"w": frame_w, "h": frame_h},
                "spriteSourceSize": {"x": 0, "y": 0, "w": frame_w, "h": frame_h},
                "frame": {"x": 0, "y": index * frame_h, "w": frame_w, "h": frame_h},
            }
        )
    return {
        "textures": [
            {
                "image": image_name,
                "format": "RGBA8888",
                "size": {"w": frame_w, "h": frame_h * len(names)},
                "scale": 1,
                "frames": frames,
            }
        ],
        "meta": {"app": "rotmon-type-ui-builder", "version": "1.0"},
    }


def save_atlas(path: Path, image: Image.Image, frame_w: int, frame_h: int, names: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    json_path = path.with_suffix(".json")
    if json_path.exists():
        layout = json.loads(json_path.read_text())
        texture = layout["textures"][0]
        if texture.get("image") == path.name and texture.get("size") == {"w": image.width, "h": image.height}:
            return
        texture["image"] = path.name
        texture["size"] = {"w": image.width, "h": image.height}
    else:
        layout = atlas_json(path.name, frame_w, frame_h, names)
    json_path.write_text(json.dumps(layout, indent="\t") + "\n")


def alpha_trim(image: Image.Image) -> Image.Image:
    bbox = image.getchannel("A").getbbox()
    return image.crop(bbox) if bbox else image


def fit_image(image: Image.Image, size: tuple[int, int], padding: int = 0) -> Image.Image:
    target_w, target_h = size
    max_w = target_w - padding * 2
    max_h = target_h - padding * 2
    image = alpha_trim(image.convert("RGBA"))
    scale = min(max_w / image.width, max_h / image.height)
    resized = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), RESAMPLE)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    canvas.alpha_composite(resized, ((target_w - resized.width) // 2, (target_h - resized.height) // 2))
    return canvas


def posterize_icon(image: Image.Image, palette_colors: int = 28) -> Image.Image:
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    rgb = rgba.convert("RGB").quantize(colors=palette_colors).convert("RGB")
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    return out


def load_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Black.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def load_glyph_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def load_pixel_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "assets/fonts/pkmnems.ttf",
        "assets/fonts/pokemon-bw.ttf",
        "assets/fonts/pokemon-emerald-pro.ttf",
        "/System/Library/Fonts/Supplemental/Arial Black.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, stroke_width: int = 0) -> tuple[int, int, int, int]:
    return draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)


def fit_text_font(draw: ImageDraw.ImageDraw, text: str, max_width: int, max_height: int, start_size: int, min_size: int = 4) -> ImageFont.ImageFont:
    for font_size in range(start_size, min_size - 1, -1):
        font = load_pixel_font(font_size)
        bbox = text_size(draw, text, font, stroke_width=1)
        if bbox[2] - bbox[0] <= max_width and bbox[3] - bbox[1] <= max_height:
            return font
    return load_pixel_font(min_size)


def draw_pixel_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int, int] = (255, 250, 238, 255),
    shadow: tuple[int, int, int, int] = (31, 28, 26, 190),
) -> None:
    x, y = xy
    draw.text((x + 1, y + 1), text, font=font, fill=shadow)
    draw.text((x, y), text, font=font, fill=fill)


def build_type_label(name: str, size: tuple[int, int]) -> Image.Image:
    width, height = size
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    fill = TYPE_COLORS[name]
    radius = max(3, round(height * 0.42))
    draw.rounded_rectangle(
        (0, 1, width - 1, height - 2),
        radius=radius,
        fill=fill,
        outline=darken(fill, 0.5),
    )
    draw.line((3, 2, width - 4, 2), fill=(255, 255, 245, 90))

    glyph, label = TYPE_LABELS[name]
    glyph_font = load_glyph_font(max(6, round(height * 0.5)))
    glyph_bbox = text_size(draw, glyph, glyph_font)
    glyph_x = round(width * 0.14 - (glyph_bbox[2] - glyph_bbox[0]) / 2 - glyph_bbox[0])
    glyph_y = round(height * 0.5 - (glyph_bbox[3] - glyph_bbox[1]) / 2 - glyph_bbox[1] - 0.2)
    draw.text((glyph_x, glyph_y), glyph, font=glyph_font, fill=(255, 248, 232, 255))

    label_left = round(width * 0.28)
    label_max_w = width - label_left - 2
    label_font = fit_text_font(draw, label, label_max_w, height - 3, max(8, round(height * 0.62)), 6)
    label_bbox = text_size(draw, label, label_font)
    label_x = label_left
    label_y = round(height * 0.5 - (label_bbox[3] - label_bbox[1]) / 2 - label_bbox[1] - 0.2)
    draw_pixel_text(draw, (label_x, label_y), label, label_font)

    return canvas


def fallback_label(name: str, size: tuple[int, int]) -> Image.Image:
    color = TYPE_COLORS[name]
    width, height = size
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((0, 1, width - 1, height - 2), radius=3, fill=color, outline=(48, 42, 37, 255))
    text = "???" if name == "unknown" else ("STAR" if name == "stellar" else name.upper())
    for font_size in range(9, 4, -1):
        font = load_font(font_size)
        bbox = draw.textbbox((0, 0), text, font=font, stroke_width=1)
        if bbox[2] - bbox[0] <= width - 3:
            break
    x = (width - (bbox[2] - bbox[0])) // 2 - bbox[0]
    y = (height - (bbox[3] - bbox[1])) // 2 - bbox[1] - 1
    draw.text((x, y), text, font=font, fill=(255, 255, 245, 255), stroke_width=1, stroke_fill=(35, 32, 29, 255))
    return canvas


def fallback_icon(name: str, size: tuple[int, int]) -> Image.Image:
    width, height = size
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    fill = TYPE_COLORS[name]
    cx = width / 2
    cy = height / 2
    r = min(width, height) / 2 - 1
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill, outline=(38, 35, 32, 255))
    text = "?" if name == "unknown" else "*"
    font = load_font(max(8, int(r * 1.3)))
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=1)
    draw.text(
        (cx - (bbox[2] - bbox[0]) / 2 - bbox[0], cy - (bbox[3] - bbox[1]) / 2 - bbox[1] - 1),
        text,
        font=font,
        fill=(255, 255, 255, 255),
        stroke_width=1,
        stroke_fill=(35, 32, 29, 255),
    )
    return canvas


def load_label(source: Path, name: str, size: tuple[int, int]) -> Image.Image:
    path = source / "labels" / f"{name}.png"
    if not path.exists():
        return fallback_label(name, size)
    return fit_image(Image.open(path), size, padding=1)


def load_icon(source: Path, name: str, size: tuple[int, int], padding: int = 0) -> Image.Image:
    path = source / "icons" / f"{name}.png"
    if not path.exists():
        return fallback_icon(name, size)
    return posterize_icon(fit_image(Image.open(path), size, padding=padding))


def build_vertical_strip(frames: list[Image.Image]) -> Image.Image:
    width = frames[0].width
    height = frames[0].height
    strip = Image.new("RGBA", (width, height * len(frames)), (0, 0, 0, 0))
    for index, frame in enumerate(frames):
        strip.alpha_composite(frame, (0, index * height))
    return strip


def build_horizontal_strip(frames: list[Image.Image]) -> Image.Image:
    width = frames[0].width
    height = frames[0].height
    strip = Image.new("RGBA", (width * len(frames), height), (0, 0, 0, 0))
    for index, frame in enumerate(frames):
        strip.alpha_composite(frame, (index * width, 0))
    return strip


def darken(hex_color: str, factor: float) -> tuple[int, int, int, int]:
    value = hex_color.lstrip("#")
    rgb = tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))
    return tuple(max(0, min(255, round(channel * factor))) for channel in rgb) + (255,)


def build_type_bg(name: str) -> Image.Image:
    canvas = Image.new("RGBA", (14, 14), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    fill = TYPE_COLORS[name]
    draw.rounded_rectangle((0, 0, 13, 13), radius=2, fill=darken(fill, 0.88), outline=darken(fill, 0.45))
    draw.line((2, 2, 11, 2), fill=darken("#ffffff", 0.9))
    draw.rectangle((2, 4, 11, 10), fill=darken(fill, 1.1))
    draw.point((2, 11), fill=darken(fill, 0.6))
    draw.point((11, 11), fill=darken(fill, 0.6))
    return canvas


def alpha_composite_centered(base: Image.Image, overlay: Image.Image) -> None:
    x = (base.width - overlay.width) // 2
    y = (base.height - overlay.height) // 2
    crop_left = max(0, -x)
    crop_top = max(0, -y)
    crop_right = overlay.width - max(0, x + overlay.width - base.width)
    crop_bottom = overlay.height - max(0, y + overlay.height - base.height)
    if crop_right <= crop_left or crop_bottom <= crop_top:
        return
    base.alpha_composite(overlay.crop((crop_left, crop_top, crop_right, crop_bottom)), (max(0, x), max(0, y)))


def polygon_points(size: tuple[int, int]) -> list[tuple[int, int]]:
    width, height = size
    if height <= 12:
        return [(2, 0), (width - 4, 0), (width - 1, height // 2), (width - 4, height - 1), (2, height - 1), (0, height // 2)]
    return [
        (4, 0),
        (width - 5, 0),
        (width - 1, 4),
        (width - 1, height - 5),
        (width - 5, height - 1),
        (4, height - 1),
        (0, height - 5),
        (0, 4),
    ]


def build_category_icon(name: str, size: tuple[int, int]) -> Image.Image:
    width, height = size
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    fill = CATEGORY_COLORS[name]
    points = polygon_points(size)
    draw.polygon(points, fill=darken(fill, 0.78), outline=darken(fill, 0.38))
    draw.polygon(
        [(min(width - 2, max(1, x)), min(height - 2, max(1, y))) for x, y in points],
        fill=darken(fill, 1.04),
    )
    draw.line(points[:2], fill=(255, 255, 242, 115))

    icon_color = (255, 250, 232, 255)
    icon_shadow = (28, 24, 22, 180)
    if name == "physical":
        for offset in (0, 2):
            draw.line((3 + offset, 7, 7 + offset, 3), fill=icon_shadow, width=1)
            draw.line((3 + offset, 6, 7 + offset, 2), fill=icon_color, width=1)
    elif name == "special":
        draw.polygon([(6, 2), (8, 5), (6, 8), (4, 5)], fill=icon_shadow)
        draw.polygon([(6, 1), (8, 5), (6, 9), (4, 5)], fill=icon_color)
        draw.point((3, 3), fill=icon_color)
        draw.point((9, 7), fill=icon_color)
    else:
        draw.rectangle((4, 3, 8, 7), outline=icon_shadow)
        draw.rectangle((4, 2, 8, 6), outline=icon_color)
        draw.point((6, 4), fill=icon_color)
        draw.point((3, 8), fill=icon_color)
        draw.point((9, 2), fill=icon_color)

    label = CATEGORY_LABELS[name]
    font = fit_text_font(draw, label, width - 12, height - 2, 8, 6)
    bbox = text_size(draw, label, font)
    label_x = 12
    label_y = round(height * 0.5 - (bbox[3] - bbox[1]) / 2 - bbox[1] - 0.1)
    draw_pixel_text(draw, (label_x, label_y), label, font, fill=icon_color, shadow=icon_shadow)
    draw.line(points + [points[0]], fill=darken(fill, 0.3))
    return canvas


def build_battle_type_icon(source: Path, name: str, size: tuple[int, int]) -> Image.Image:
    width, height = size
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    points = polygon_points(size)
    fill = TYPE_COLORS[name]
    draw.polygon(points, fill=darken(fill, 0.72), outline=darken(fill, 0.38))
    inner = [(max(1, x - 1) if x > width // 2 else min(width - 2, x + 1), max(1, y - 1) if y > height // 2 else min(height - 2, y + 1)) for x, y in points]
    draw.polygon(inner, fill=darken(fill, 1.08))
    draw.line(points[:2], fill=(245, 246, 232, 130))

    icon_size = 18 if height <= 12 else 22
    icon = load_icon(source, name, (icon_size, icon_size), padding=0)
    alpha_composite_centered(canvas, icon)
    draw.line(points + [points[0]], fill=darken(fill, 0.3), width=1)
    draw.line(points[:2], fill=(255, 255, 240, 150), width=1)
    return canvas


def make_preview(source: Path, output: Path) -> None:
    cell_w, cell_h = 112, 80
    cols = 5
    rows = math.ceil(len(TYPE_ORDER) / cols)
    preview = Image.new("RGBA", (cols * cell_w, rows * cell_h), (34, 34, 34, 255))
    draw = ImageDraw.Draw(preview)
    font = load_font(10)
    for index, name in enumerate(TYPE_ORDER):
        x = (index % cols) * cell_w
        y = (index // cols) * cell_h
        draw.rectangle((x, y, x + cell_w - 1, y + cell_h - 1), outline=(68, 68, 68, 255))
        icon = build_battle_type_icon(source, name, (34, 34))
        label = build_type_label(name, (64, 28))
        small_label = build_type_label(name, (32, 14))
        preview.alpha_composite(icon, (x + 6, y + 7))
        preview.alpha_composite(label, (x + 42, y + 10))
        preview.alpha_composite(small_label, (x + 42, y + 45))
        draw.text((x + 6, y + 48), name, font=font, fill=(220, 220, 220, 255))
    output.parent.mkdir(parents=True, exist_ok=True)
    preview.save(output)


def make_category_preview(output: Path) -> None:
    scale = 8
    frames = [build_category_icon(name, (28, 11)) for name in CATEGORY_ORDER]
    strip = build_horizontal_strip(frames)
    preview = Image.new("RGBA", (strip.width * scale, strip.height * scale), (34, 34, 34, 255))
    preview.alpha_composite(strip.resize(preview.size, Image.Resampling.NEAREST))
    output.parent.mkdir(parents=True, exist_ok=True)
    preview.save(output)


def main() -> None:
    args = parse_args()
    source = args.source
    asset_root = args.asset_root

    labels = [build_type_label(name, (32, 14)) for name in TYPE_ORDER]
    save_atlas(asset_root / "types.png", build_vertical_strip(labels), 32, 14, TYPE_ORDER)

    categories = [build_category_icon(name, (28, 11)) for name in CATEGORY_ORDER]
    save_atlas(asset_root / "categories.png", build_horizontal_strip(categories), 28, 11, CATEGORY_ORDER)

    bg_names = [name for name in TYPE_ORDER if name != "stellar"]
    bgs = [build_type_bg(name) for name in bg_names]
    save_atlas(asset_root / "ui" / "type_bgs.png", build_vertical_strip(bgs), 14, 14, bg_names)

    dual_enemy_top = [build_battle_type_icon(source, name, (20, 12)) for name in TYPE_ORDER]
    dual_enemy_bottom = [build_battle_type_icon(source, name, (20, 12)) for name in TYPE_ORDER]
    dual_player_top = [build_battle_type_icon(source, name, (20, 12)) for name in TYPE_ORDER]
    dual_player_bottom = [build_battle_type_icon(source, name, (20, 12)) for name in TYPE_ORDER]
    single_enemy = [build_battle_type_icon(source, name, (20, 23)) for name in TYPE_ORDER]
    single_player = [build_battle_type_icon(source, name, (20, 23)) for name in TYPE_ORDER]

    for image_name, frames, frame_h in [
        ("pbinfo_enemy_type.png", single_enemy, 23),
        ("pbinfo_player_type.png", single_player, 23),
        ("pbinfo_enemy_type1.png", dual_enemy_top, 12),
        ("pbinfo_enemy_type2.png", dual_enemy_bottom, 12),
        ("pbinfo_player_type1.png", dual_player_top, 12),
        ("pbinfo_player_type2.png", dual_player_bottom, 12),
    ]:
        save_atlas(asset_root / "ui" / image_name, build_vertical_strip(frames), 20, frame_h, TYPE_ORDER)

    make_preview(source, args.preview)
    make_category_preview(args.preview.with_name("rotmon-category-ui-preview.png"))
    print(f"Wrote type UI assets from {source}")
    print(f"Preview: {args.preview}")


if __name__ == "__main__":
    main()
