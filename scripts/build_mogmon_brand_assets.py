#!/usr/bin/env python3
"""Build MoggMon logo assets from a transparent source or generated wordmark."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = Path("/Users/alyssa/Downloads/SKiGDgGIZ3B6VEEZxZIor.png")
DEFAULT_WORDMARK = "MOGG\nMON"
FONT_CANDIDATES = [
  Path("/System/Library/Fonts/Supplemental/Impact.ttf"),
  Path("/System/Library/Fonts/Supplemental/Arial Black.ttf"),
  Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
]


def require_source(path: Path) -> Image.Image:
  if not path.exists():
    raise SystemExit(f"Missing source image: {path}")
  return Image.open(path).convert("RGBA")


def find_font_path() -> Path:
  for path in FONT_CANDIDATES:
    if path.exists():
      return path
  raise SystemExit("Missing a usable system font for MoggMon wordmark generation.")


def crop_transparent_bounds(image: Image.Image) -> Image.Image:
  alpha = image.getchannel("A")
  bbox = alpha.getbbox()
  if bbox is None:
    raise SystemExit("Source logo has no visible pixels.")
  return image.crop(bbox)


def fit_font(lines: list[str], canvas_size: tuple[int, int], padding: int = 80) -> ImageFont.FreeTypeFont:
  font_path = find_font_path()
  max_width = max(1, canvas_size[0] - padding * 2)
  max_height = max(1, canvas_size[1] - padding * 2)

  best_font = None
  for size in range(760, 120, -8):
    font = ImageFont.truetype(str(font_path), size=size)
    line_boxes = [font.getbbox(line, stroke_width=max(6, size // 16)) for line in lines]
    line_heights = [box[3] - box[1] for box in line_boxes]
    line_widths = [box[2] - box[0] for box in line_boxes]
    total_height = sum(line_heights) + max(0, len(lines) - 1) * max(14, size // 10)
    if max(line_widths) <= max_width and total_height <= max_height:
      best_font = font
      break

  if best_font is None:
    best_font = ImageFont.truetype(str(font_path), size=120)
  return best_font


def lerp_color(start: tuple[int, int, int], end: tuple[int, int, int], t: float) -> tuple[int, int, int]:
  return tuple(round(start[idx] + (end[idx] - start[idx]) * t) for idx in range(3))


def make_vertical_gradient(size: tuple[int, int], top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
  width, height = size
  gradient = Image.new("RGBA", size, (0, 0, 0, 0))
  draw = ImageDraw.Draw(gradient)
  for y in range(height):
    t = 0.0 if height <= 1 else y / (height - 1)
    color = lerp_color(top, bottom, t)
    draw.line((0, y, width, y), fill=(*color, 255))
  return gradient


def render_wordmark(wordmark: str, canvas_size: tuple[int, int] = (2200, 1600)) -> Image.Image:
  lines = [line.strip() for line in wordmark.splitlines() if line.strip()]
  if not lines:
    raise SystemExit("Wordmark must contain visible characters.")

  font = fit_font(lines, canvas_size)
  stroke_outer = max(10, font.size // 14)
  stroke_inner = max(4, font.size // 28)
  line_gap = max(16, font.size // 12)

  temp = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
  draw = ImageDraw.Draw(temp)
  line_boxes = [font.getbbox(line, stroke_width=stroke_outer) for line in lines]
  line_heights = [box[3] - box[1] for box in line_boxes]
  line_widths = [box[2] - box[0] for box in line_boxes]
  total_height = sum(line_heights) + max(0, len(lines) - 1) * line_gap
  y = (canvas_size[1] - total_height) // 2 - 12

  composed = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
  for index, line in enumerate(lines):
    line_width = line_widths[index]
    line_height = line_heights[index]
    x = (canvas_size[0] - line_width) // 2

    mask = Image.new("L", canvas_size, 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.text((x, y), line, font=font, fill=255, stroke_width=stroke_inner)

    outer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    outer_draw = ImageDraw.Draw(outer)
    outer_draw.text(
      (x, y),
      line,
      font=font,
      fill=(0, 0, 0, 0),
      stroke_width=stroke_outer,
      stroke_fill=ImageColor.getrgb("#5f0909"),
    )

    inner_stroke = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    inner_draw = ImageDraw.Draw(inner_stroke)
    inner_draw.text(
      (x, y),
      line,
      font=font,
      fill=(0, 0, 0, 0),
      stroke_width=max(1, stroke_outer - stroke_inner),
      stroke_fill=ImageColor.getrgb("#d92b13"),
    )

    extrusion = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    for depth in range(stroke_outer + 8, 6, -2):
      layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
      layer_draw = ImageDraw.Draw(layer)
      t = (stroke_outer + 8 - depth) / max(1, stroke_outer + 2)
      fill = lerp_color(ImageColor.getrgb("#5e0808"), ImageColor.getrgb("#c91711"), t)
      layer_draw.text(
        (x + depth, y + depth),
        line,
        font=font,
        fill=(*fill, 255),
        stroke_width=stroke_outer,
        stroke_fill=ImageColor.getrgb("#4d0505"),
      )
      extrusion.alpha_composite(layer)

    face = make_vertical_gradient(canvas_size, ImageColor.getrgb("#fff46c"), ImageColor.getrgb("#ffd100"))
    face.putalpha(mask)

    highlight_mask = Image.new("L", canvas_size, 0)
    highlight_draw = ImageDraw.Draw(highlight_mask)
    highlight_draw.text((x, y - max(2, stroke_inner // 2)), line, font=font, fill=160, stroke_width=0)
    highlight = make_vertical_gradient(canvas_size, ImageColor.getrgb("#fffbd1"), ImageColor.getrgb("#ffe34d"))
    highlight.putalpha(highlight_mask)

    line_image = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    line_image.alpha_composite(extrusion)
    line_image.alpha_composite(outer)
    line_image.alpha_composite(inner_stroke)
    line_image.alpha_composite(face)
    line_image.alpha_composite(highlight)

    angle = -4 if index == 0 else 3
    rotated = line_image.rotate(angle, resample=Image.Resampling.BICUBIC, expand=False)
    composed.alpha_composite(rotated)
    y += line_height + line_gap

  return crop_transparent_bounds(composed)


def fit_canvas(image: Image.Image, size: tuple[int, int], padding: int = 0) -> Image.Image:
  canvas = Image.new("RGBA", size, (0, 0, 0, 0))
  inner_width = max(1, size[0] - padding * 2)
  inner_height = max(1, size[1] - padding * 2)

  scale = min(inner_width / image.width, inner_height / image.height)
  fitted_size = (
    max(1, round(image.width * scale)),
    max(1, round(image.height * scale)),
  )
  fitted = image.resize(fitted_size, Image.Resampling.LANCZOS)

  paste_x = (size[0] - fitted.width) // 2
  paste_y = (size[1] - fitted.height) // 2
  canvas.alpha_composite(fitted, (paste_x, paste_y))
  return canvas


def save_logo_variants(source_path: Path | None, wordmark: str) -> None:
  if source_path is not None and source_path.exists():
    cropped = crop_transparent_bounds(require_source(source_path))
  else:
    cropped = render_wordmark(wordmark)

  title_logo = fit_canvas(cropped, (150, 84), padding=2)
  icon_128 = fit_canvas(cropped, (128, 128), padding=10)
  icon_512 = fit_canvas(cropped, (512, 512), padding=36)

  (ROOT / "assets" / "images" / "logo.png").parent.mkdir(parents=True, exist_ok=True)
  title_logo.save(ROOT / "assets" / "images" / "logo.png")
  title_logo.save(ROOT / "assets" / "images" / "logo_fake.png")
  icon_128.save(ROOT / "assets" / "logo128.png")
  icon_512.save(ROOT / "assets" / "logo512.png")


def main() -> None:
  parser = argparse.ArgumentParser(description="Build MoggMon logo assets from a transparent master logo or generated wordmark.")
  parser.add_argument("--source", default="", help="Optional transparent source logo PNG.")
  parser.add_argument("--wordmark", default=DEFAULT_WORDMARK, help="Wordmark text to generate when no source PNG is supplied.")
  args = parser.parse_args()
  source = Path(args.source).expanduser() if args.source else None
  if source == Path("."):
    source = None
  if source is not None and not source.exists() and source == DEFAULT_SOURCE:
    source = None
  save_logo_variants(source, args.wordmark)


if __name__ == "__main__":
  main()
