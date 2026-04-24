#!/usr/bin/env python3
"""Build a custom Mogger Mon battle HUD skin from the existing UI asset masks."""

from __future__ import annotations

import json
import zlib
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent.parent
UI_ROOT = ROOT / "assets" / "images" / "ui"
WINDOW_ROOT = UI_ROOT / "windows"
ARENA_ROOT = ROOT / "assets" / "images" / "arenas"


INK = (24, 28, 35)
STEEL_DARK = (72, 84, 97)
STEEL_MID = (102, 114, 125)
STEEL_LIGHT = (148, 159, 171)
STEEL_GLINT = (192, 200, 208)
SLATE_DARK = (34, 42, 56)
SLATE_MID = (59, 72, 90)
SLATE_LIGHT = (91, 112, 138)
WINDOW_FILL_DARK = (24, 30, 39)
WINDOW_FILL = (36, 45, 58)
WINDOW_FILL_LIGHT = (66, 84, 106)
PARCHMENT_DARK = (181, 166, 136)
PARCHMENT = (222, 210, 182)
PARCHMENT_LIGHT = (239, 230, 205)
PANEL_SHADOW = (46, 54, 63)
DEEP_SHADOW = (34, 40, 48)
HP_HIGH = (60, 205, 188)
HP_HIGH_DARK = (36, 114, 114)
HP_MED = (225, 178, 88)
HP_MED_DARK = (136, 96, 44)
HP_LOW = (222, 104, 79)
HP_LOW_DARK = (138, 70, 55)
EXP_FILL = (59, 203, 248)
EXP_FILL_DARK = (23, 82, 112)
RELIC_METAL = (160, 173, 189)
RELIC_SHADOW = (18, 22, 30)
RELIC_INNER = (232, 238, 244)


@dataclass(frozen=True)
class AccentPalette:
  dark: tuple[int, int, int]
  mid: tuple[int, int, int]
  light: tuple[int, int, int]


VARIANTS = [
  AccentPalette((108, 86, 70), (214, 133, 92), (244, 191, 134)),
  AccentPalette((49, 110, 109), (53, 203, 196), (170, 241, 228)),
  AccentPalette((104, 113, 124), (204, 208, 214), (239, 243, 246)),
  AccentPalette((130, 101, 53), (223, 178, 87), (245, 218, 154)),
  AccentPalette((76, 111, 127), (132, 215, 235), (199, 243, 250)),
]


BASE_REMAP = {
  (24, 24, 24): INK,
  (33, 33, 33): INK,
  (48, 48, 48): PANEL_SHADOW,
  (54, 45, 62): STEEL_DARK,
  (65, 65, 65): DEEP_SHADOW,
  (68, 60, 76): STEEL_DARK,
  (71, 45, 60): STEEL_DARK,
  (99, 99, 99): STEEL_MID,
  (109, 103, 115): STEEL_LIGHT,
  (113, 113, 113): STEEL_MID,
  (129, 125, 134): STEEL_LIGHT,
  (154, 146, 154): STEEL_LIGHT,
  (178, 178, 178): STEEL_GLINT,
  (214, 214, 214): PARCHMENT_DARK,
  (215, 215, 215): PARCHMENT_DARK,
  (243, 243, 243): PARCHMENT,
  (248, 248, 248): PARCHMENT_LIGHT,
  (255, 255, 255): PARCHMENT_LIGHT,
}


def rgba(rgb: tuple[int, int, int], alpha: int = 255) -> tuple[int, int, int, int]:
  return (rgb[0], rgb[1], rgb[2], alpha)


def luminance(rgb: tuple[int, int, int]) -> float:
  return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722


def map_color(color: tuple[int, int, int, int], accent: AccentPalette | None = None) -> tuple[int, int, int, int]:
  if color[3] == 0:
    return color

  rgb = color[:3]
  if rgb in BASE_REMAP:
    return rgba(BASE_REMAP[rgb], color[3])

  if accent is None:
    return rgba(STEEL_MID, color[3])

  tone = luminance(rgb)
  if tone < 96:
    mapped = accent.dark
  elif tone < 170:
    mapped = accent.mid
  else:
    mapped = accent.light
  return rgba(mapped, color[3])


def recolor_image(image: Image.Image, accent: AccentPalette | None = None) -> Image.Image:
  src = image.convert("RGBA")
  dst = Image.new("RGBA", src.size, (0, 0, 0, 0))
  src_pixels = src.load()
  dst_pixels = dst.load()
  for y in range(src.height):
    for x in range(src.width):
      dst_pixels[x, y] = map_color(src_pixels[x, y], accent)
  return dst


def draw_rivet(image: Image.Image, x: int, y: int, accent: AccentPalette) -> None:
  draw = ImageDraw.Draw(image)
  draw.point((x, y), fill=rgba(accent.light))
  for px, py in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
    if 0 <= px < image.width and 0 <= py < image.height:
      draw.point((px, py), fill=rgba(STEEL_GLINT))
  for px, py in ((x - 1, y - 1), (x + 1, y + 1)):
    if 0 <= px < image.width and 0 <= py < image.height:
      draw.point((px, py), fill=rgba(PANEL_SHADOW))


def draw_grid(
  image: Image.Image,
  minor: int,
  major: int,
  minor_color: tuple[int, int, int, int],
  major_color: tuple[int, int, int, int],
) -> None:
  draw = ImageDraw.Draw(image)
  for x in range(0, image.width, minor):
    draw.line((x, 0, x, image.height), fill=minor_color)
  for y in range(0, image.height, minor):
    draw.line((0, y, image.width, y), fill=minor_color)
  for x in range(0, image.width, major):
    draw.line((x, 0, x, image.height), fill=major_color)
  for y in range(0, image.height, major):
    draw.line((0, y, image.width, y), fill=major_color)


def draw_scanlines(image: Image.Image, color: tuple[int, int, int, int], step: int = 2) -> None:
  draw = ImageDraw.Draw(image)
  for y in range(0, image.height, step):
    draw.line((0, y, image.width, y), fill=color)


def flatten_opaque(image: Image.Image, fill: tuple[int, int, int]) -> Image.Image:
  base = Image.new("RGBA", image.size, rgba(fill))
  base.alpha_composite(image)
  return base


def build_surface_background(size: tuple[int, int], accent: AccentPalette, *, bright: bool = False) -> Image.Image:
  image = Image.new("RGBA", size, rgba((59, 64, 84) if bright else (44, 49, 64)))
  draw = ImageDraw.Draw(image)
  draw.rectangle((0, 0, size[0], size[1]), fill=rgba((78, 84, 104) if bright else (46, 51, 67)))
  draw.rectangle((0, 0, size[0], size[1] // 2), fill=rgba((86, 92, 112) if bright else (52, 57, 73)))
  draw.rectangle((0, size[1] // 2, size[0], size[1]), fill=rgba((63, 68, 87) if bright else (42, 46, 60)))

  draw_grid(
    image,
    minor=8,
    major=40,
    minor_color=rgba((32, 36, 48), 140),
    major_color=rgba(accent.mid, 96),
  )
  draw_scanlines(image, rgba((18, 22, 30), 58))

  for offset in range(-size[1], size[0], 74):
    draw.line(
      (offset, size[1], offset + size[1] // 2, size[1] // 2),
      fill=rgba(accent.light, 160),
      width=1,
    )

  draw.rectangle((0, size[1] - 26, size[0], size[1]), fill=rgba(PANEL_SHADOW, 200))
  draw.line((0, size[1] - 26, size[0], size[1] - 26), fill=rgba(PARCHMENT_DARK))
  return flatten_opaque(image, (46, 51, 67) if bright else (36, 40, 52))


def add_panel_details(image: Image.Image, accent: AccentPalette, *, message_box: bool = False) -> None:
  pixels = image.load()
  stripe_y = 2 if image.height > 14 else 1
  if stripe_y + 1 < image.height:
    for x in range(4, image.width - 4):
      if pixels[x, stripe_y][3]:
        pixels[x, stripe_y] = rgba(accent.light)
      if pixels[x, stripe_y + 1][3]:
        pixels[x, stripe_y + 1] = rgba(accent.dark)

  if image.height > 18:
    rivet_points = [
      (6, 5),
      (image.width - 7, 5),
      (6, image.height - 6),
      (image.width - 7, image.height - 6),
    ]
  else:
    rivet_points = [(5, 5), (image.width - 6, 5)]

  if message_box:
    rivet_points.extend((x, 5) for x in range(24, image.width - 24, 28))

  for point in rivet_points:
    if 0 <= point[0] < image.width and 0 <= point[1] < image.height and pixels[point][3]:
      draw_rivet(image, point[0], point[1], accent)


def build_meter_strip(width: int, height: int, light: tuple[int, int, int], dark: tuple[int, int, int]) -> Image.Image:
  image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
  draw = ImageDraw.Draw(image)
  draw.rectangle((0, 0, width - 1, height - 1), fill=rgba(dark))
  inset_top = 1 if height >= 4 else 0
  inset_bottom = height - 2 if height >= 4 else height - 1
  draw.rectangle((1, inset_top, width - 2, inset_bottom), fill=rgba(light))
  if height >= 4:
    draw.line((1, inset_top, width - 2, inset_top), fill=rgba(PARCHMENT_LIGHT))
  return image


def build_overlay_hp() -> None:
  image = Image.new("RGBA", (48, 6), (0, 0, 0, 0))
  image.paste(build_meter_strip(48, 2, HP_HIGH, HP_HIGH_DARK), (0, 0))
  image.paste(build_meter_strip(48, 2, HP_MED, HP_MED_DARK), (0, 2))
  image.paste(build_meter_strip(48, 2, HP_LOW, HP_LOW_DARK), (0, 4))
  image.save(UI_ROOT / "overlay_hp.png")

  boss = Image.new("RGBA", (96, 12), (0, 0, 0, 0))
  boss.paste(build_meter_strip(86, 4, HP_HIGH, HP_HIGH_DARK), (0, 0))
  boss.paste(build_meter_strip(86, 4, HP_MED, HP_MED_DARK), (0, 4))
  boss.paste(build_meter_strip(86, 4, HP_LOW, HP_LOW_DARK), (0, 8))
  boss.save(UI_ROOT / "overlay_hp_boss.png")

  exp = build_meter_strip(85, 2, EXP_FILL, EXP_FILL_DARK)
  exp.save(UI_ROOT / "overlay_exp.png")


def build_window_tile(accent: AccentPalette, *, thin: bool = False, xthin: bool = False) -> Image.Image:
  image = Image.new("RGBA", (24, 24), (0, 0, 0, 0))
  draw = ImageDraw.Draw(image)
  draw.rounded_rectangle((1, 1, 22, 22), radius=4, fill=rgba(STEEL_DARK), outline=rgba(INK))
  draw.rounded_rectangle((3, 3, 20, 20), radius=3, fill=rgba(PANEL_SHADOW), outline=rgba(STEEL_LIGHT))

  if xthin:
    inset = (5, 5, 18, 18)
  elif thin:
    inset = (4, 4, 19, 19)
  else:
    inset = (4, 4, 19, 19)
    draw.rounded_rectangle((5, 6, 18, 18), radius=2, fill=rgba(WINDOW_FILL), outline=rgba(WINDOW_FILL_DARK))
    draw.line((5, 6, 18, 6), fill=rgba(WINDOW_FILL_LIGHT))

  draw.line((4, 4, 19, 4), fill=rgba(accent.light))
  draw.line((4, 5, 19, 5), fill=rgba(accent.dark))
  draw.line((4, 18, 19, 18), fill=rgba(STEEL_GLINT))
  for point in ((6, 6), (17, 6), (6, 17), (17, 17)):
    draw_rivet(image, point[0], point[1], accent)

  if thin or xthin:
    draw.rounded_rectangle(inset, radius=2, fill=rgba(WINDOW_FILL), outline=rgba(WINDOW_FILL_DARK))
    draw.line((inset[0], inset[1], inset[2], inset[1]), fill=rgba(WINDOW_FILL_LIGHT))

  return image


def build_windows() -> None:
  for index, accent in enumerate(VARIANTS, start=1):
    build_window_tile(accent).save(WINDOW_ROOT / f"window_{index}.png")
    build_window_tile(accent, thin=True).save(WINDOW_ROOT / f"window_{index}_thin.png")
    build_window_tile(accent, xthin=True).save(WINDOW_ROOT / f"window_{index}_xthin.png")


def build_bg_and_namebox() -> None:
  bg = Image.new("RGBA", (320, 240), (0, 0, 0, 0))
  namebox = Image.new("RGBA", (100, 20), (0, 0, 0, 0))

  for index, accent in enumerate(VARIANTS):
    row_y = index * 48
    row = Image.new("RGBA", (320, 48), (0, 0, 0, 0))
    draw = ImageDraw.Draw(row)
    draw.rounded_rectangle((0, 0, 319, 47), radius=0, fill=rgba(STEEL_DARK), outline=rgba(INK))
    draw.line((0, 0, 319, 0), fill=rgba(accent.light))
    draw.line((0, 1, 319, 1), fill=rgba(accent.dark))
    draw.rectangle((0, 12, 319, 47), fill=rgba((20, 25, 34)))
    draw.rectangle((8, 18, 311, 42), fill=rgba(WINDOW_FILL), outline=rgba(WINDOW_FILL_DARK))
    draw.line((8, 18, 311, 18), fill=rgba(WINDOW_FILL_LIGHT))
    for y in range(19, 42, 2):
      draw.line((9, y, 310, y), fill=rgba((12, 16, 22), 34))
    for x in range(16, 304, 32):
      draw_rivet(row, x, 6, accent)
    bg.paste(row, (0, row_y))

    box = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
    box_draw = ImageDraw.Draw(box)
    box_draw.rounded_rectangle((0, 0, 19, 19), radius=4, fill=rgba(STEEL_DARK), outline=rgba(INK))
    box_draw.rounded_rectangle((3, 3, 16, 16), radius=3, fill=rgba(WINDOW_FILL), outline=rgba(WINDOW_FILL_DARK))
    box_draw.line((3, 2, 16, 2), fill=rgba(accent.light))
    box_draw.line((3, 3, 16, 3), fill=rgba(accent.dark))
    box_draw.line((3, 4, 16, 4), fill=rgba(WINDOW_FILL_LIGHT))
    draw_rivet(box, 5, 5, accent)
    draw_rivet(box, 14, 5, accent)
    namebox.paste(box, (index * 20, 0))

  bg.save(UI_ROOT / "bg.png")
  namebox.save(UI_ROOT / "namebox.png")


def build_starter_container_bg() -> None:
  image = Image.new("RGBA", (173, 159), (0, 0, 0, 0))
  accent = VARIANTS[4]
  draw = ImageDraw.Draw(image)
  draw.rounded_rectangle((0, 0, 172, 158), radius=8, fill=rgba(STEEL_DARK), outline=rgba(INK))
  draw.rounded_rectangle((3, 3, 169, 155), radius=7, fill=rgba(PANEL_SHADOW), outline=rgba(STEEL_LIGHT))
  draw.rounded_rectangle((6, 9, 166, 126), radius=5, fill=rgba(PARCHMENT), outline=rgba(PARCHMENT_DARK))
  draw.rounded_rectangle((6, 130, 166, 151), radius=4, fill=rgba(PARCHMENT_LIGHT), outline=rgba(PARCHMENT_DARK))
  draw.line((6, 8, 166, 8), fill=rgba(accent.light))
  draw.line((6, 9, 166, 9), fill=rgba(accent.dark))
  for x in range(14, 160, 28):
    draw_rivet(image, x, 6, accent)
  inner = image.crop((8, 12, 164, 124))
  draw_grid(
    inner,
    minor=6,
    major=24,
    minor_color=rgba((184, 176, 154), 120),
    major_color=rgba((154, 144, 121), 120),
  )
  image.alpha_composite(inner, (8, 12))
  image.save(UI_ROOT / "starter_container_bg.png")


def build_starter_and_archive_backgrounds() -> None:
  starter_bg = build_surface_background((320, 180), VARIANTS[4], bright=True)
  starter_bg.save(UI_ROOT / "starter_select_bg.png")

  archive_bg = build_surface_background((320, 180), VARIANTS[1], bright=False)
  archive_bg.save(UI_ROOT / "pokedex_summary_bg.png")


def build_battle_backgrounds() -> None:
  default_bg = Image.new("RGBA", (320, 180), (0, 0, 0, 0))
  draw = ImageDraw.Draw(default_bg)

  sky_top = (82, 114, 149)
  sky_mid = (98, 133, 167)
  sky_low = (112, 118, 144)
  for y in range(0, 84):
    if y < 26:
      color = sky_top
    elif y < 54:
      color = sky_mid
    else:
      color = sky_low
    draw.line((0, y, 319, y), fill=rgba(color))

  draw.line((0, 30, 319, 30), fill=rgba((158, 202, 221), 180))
  draw.line((0, 50, 319, 50), fill=rgba((122, 173, 205), 160))
  draw.line((0, 70, 319, 70), fill=rgba((214, 168, 102), 92))

  skyline = [
    (18, 58, 36, 72),
    (46, 54, 71, 72),
    (78, 50, 96, 72),
    (112, 60, 139, 72),
    (152, 44, 175, 72),
    (205, 56, 232, 72),
    (244, 48, 268, 72),
    (282, 58, 307, 72),
  ]
  for left, top, right, bottom in skyline:
    draw.rectangle((left, top, right, bottom), fill=rgba((55, 69, 86), 210))

  for y in range(84, 172):
    if y < 120:
      color = (117, 93, 82)
    elif y < 150:
      color = (95, 80, 82)
    else:
      color = (76, 72, 86)
    draw.line((0, y, 319, y), fill=rgba(color))

  horizon_y = 84
  draw.line((0, horizon_y, 319, horizon_y), fill=rgba((234, 194, 116), 180))
  draw.line((0, horizon_y + 1, 319, horizon_y + 1), fill=rgba((56, 78, 102), 200))

  for y in (96, 118, 142, 164):
    draw.line((0, y, 319, y), fill=rgba((61, 74, 96), 170))

  vanishing_x = 160
  for target_x in range(-36, 356, 28):
    draw.line((vanishing_x, horizon_y + 2, target_x, 171), fill=rgba((126, 177, 208), 78))

  for x in range(18, 320, 36):
    draw.line((x, 90, x + 8, 170), fill=rgba((43, 54, 71), 74))

  for x in range(24, 304, 72):
    draw.rounded_rectangle((x, 104, x + 44, 118), radius=4, fill=rgba((58, 73, 89), 180), outline=rgba((27, 33, 44)))
    draw.line((x + 4, 108, x + 40, 108), fill=rgba((157, 216, 233), 136))

  draw.ellipse((30, 120, 124, 170), fill=rgba((56, 62, 78), 88), outline=rgba((142, 191, 217), 96))
  draw.ellipse((200, 100, 296, 156), fill=rgba((65, 70, 84), 82), outline=rgba((229, 177, 108), 92))

  draw.rectangle((0, 172, 319, 179), fill=rgba((229, 195, 134)))
  draw_scanlines(default_bg, rgba((20, 24, 32), 30))
  flatten_opaque(default_bg, sky_top).save(ARENA_ROOT / "default_bg.png")

  loading_bg = build_surface_background((320, 180), VARIANTS[1], bright=False)
  loading_bg.save(ARENA_ROOT / "loading_bg.png")

  title_bg = Image.new("RGBA", (320, 180), (0, 0, 0, 0))
  draw = ImageDraw.Draw(title_bg)
  sky_top = (47, 50, 70)
  sky_mid = (58, 73, 96)
  sky_low = (86, 108, 136)
  for y in range(0, 104):
    if y < 18:
      color = sky_top
    elif y < 54:
      color = sky_mid
    else:
      color = sky_low
    draw.line((0, y, 319, y), fill=rgba(color))

  draw.rectangle((0, 104, 319, 179), fill=rgba((44, 57, 74)))
  draw.line((0, 104, 319, 104), fill=rgba((241, 199, 119), 220))
  draw.line((0, 105, 319, 105), fill=rgba((32, 43, 57), 220))

  for y in (116, 128, 142, 156, 170):
    draw.line((0, y, 319, y), fill=rgba((29, 38, 49), 70))
  for x in range(-40, 360, 24):
    draw.line((160, 106, x, 179), fill=rgba((129, 201, 219), 54))

  skyline = [
    (8, 50, 32, 92),
    (38, 58, 56, 92),
    (62, 40, 92, 92),
    (98, 48, 120, 92),
    (128, 34, 162, 92),
    (169, 55, 188, 92),
    (195, 29, 225, 92),
    (232, 47, 252, 92),
    (260, 38, 290, 92),
    (296, 60, 314, 92),
  ]
  for left, top, right, bottom in skyline:
    draw.rectangle((left, top, right, bottom), fill=rgba((27, 35, 46), 240))
    draw.line((left, top, right, top), fill=rgba((121, 174, 202), 110))

  for x in range(18, 302, 26):
    draw.line((x, 112, x + 4, 176), fill=rgba((21, 28, 37), 58))

  draw.ellipse((24, 116, 126, 172), fill=rgba((52, 68, 89), 94), outline=rgba((145, 215, 228), 104))
  draw.ellipse((198, 110, 298, 166), fill=rgba((57, 74, 92), 86), outline=rgba((238, 177, 104), 100))
  draw_scanlines(title_bg, rgba((14, 18, 24), 26))
  flatten_opaque(title_bg, sky_mid).save(ARENA_ROOT / "title_bg.png")


def style_pbinfo_asset(name: str, accent: AccentPalette) -> None:
  image = recolor_image(Image.open(UI_ROOT / name).convert("RGBA"))
  add_panel_details(image, accent)
  image.save(UI_ROOT / name)


def style_message_overlay() -> None:
  image = Image.new("RGBA", (512, 96), (0, 0, 0, 0))
  draw = ImageDraw.Draw(image)
  accent = VARIANTS[1]
  draw.rounded_rectangle((0, 0, 511, 95), radius=0, fill=rgba(STEEL_DARK), outline=rgba(INK))
  draw.line((0, 0, 511, 0), fill=rgba(accent.light))
  draw.line((0, 1, 511, 1), fill=rgba(accent.dark))
  draw.rectangle((0, 18, 511, 95), fill=rgba((30, 37, 49)))
  draw.rectangle((16, 30, 495, 80), fill=rgba((51, 69, 89)), outline=rgba((18, 23, 31)))
  draw.line((16, 30, 495, 30), fill=rgba(accent.light))
  draw.line((16, 31, 495, 31), fill=rgba(accent.dark))
  draw.rectangle((23, 37, 488, 72), fill=rgba((64, 88, 112)))
  draw.line((23, 37, 488, 37), fill=rgba((183, 233, 234), 220))
  draw.line((23, 72, 488, 72), fill=rgba((21, 29, 39), 220))
  for y in range(38, 72, 2):
    draw.line((24, y, 487, y), fill=rgba((18, 25, 34), 28))
  for x in range(24, 488, 40):
    draw_rivet(image, x, 8, accent)
  image.save(UI_ROOT / "overlay_message.png")


TYPE_ACCENTS = {
  "fire": AccentPalette((121, 51, 42), (211, 100, 66), (247, 182, 94)),
  "water": AccentPalette((39, 78, 109), (73, 156, 210), (171, 228, 255)),
  "grass": AccentPalette((47, 97, 66), (88, 186, 118), (175, 234, 169)),
  "electric": AccentPalette((119, 91, 29), (235, 188, 61), (255, 239, 156)),
  "ice": AccentPalette((62, 119, 145), (108, 214, 230), (203, 248, 255)),
  "fighting": AccentPalette((126, 60, 43), (214, 110, 86), (253, 193, 165)),
  "poison": AccentPalette((96, 56, 112), (182, 106, 212), (237, 188, 255)),
  "ground": AccentPalette((117, 86, 48), (192, 146, 76), (244, 211, 152)),
  "flying": AccentPalette((85, 103, 156), (149, 177, 231), (225, 240, 255)),
  "psychic": AccentPalette((137, 67, 100), (229, 117, 183), (255, 205, 238)),
  "bug": AccentPalette((86, 109, 39), (155, 191, 62), (224, 247, 145)),
  "rock": AccentPalette((108, 93, 73), (181, 161, 119), (229, 214, 181)),
  "ghost": AccentPalette((64, 65, 115), (108, 121, 214), (207, 214, 255)),
  "dragon": AccentPalette((70, 79, 145), (112, 124, 236), (198, 208, 255)),
  "dark": AccentPalette((60, 57, 70), (109, 105, 134), (195, 190, 213)),
  "steel": AccentPalette((83, 95, 116), (149, 166, 190), (228, 236, 246)),
  "fairy": AccentPalette((138, 90, 131), (229, 145, 206), (255, 220, 245)),
  "normal": AccentPalette((95, 92, 98), (162, 158, 171), (225, 223, 231)),
  "gold": AccentPalette((124, 92, 26), (221, 174, 56), (255, 231, 165)),
  "silver": AccentPalette((93, 102, 116), (171, 182, 198), (236, 241, 248)),
}

CATEGORY_DEFAULTS = {
  "snack": TYPE_ACCENTS["grass"],
  "brew": TYPE_ACCENTS["water"],
  "relic": TYPE_ACCENTS["steel"],
  "module": TYPE_ACCENTS["electric"],
  "seal": TYPE_ACCENTS["fairy"],
  "token": TYPE_ACCENTS["normal"],
  "egg": TYPE_ACCENTS["gold"],
  "gear": TYPE_ACCENTS["dark"],
  "capture": TYPE_ACCENTS["psychic"],
}


def add_rgb(color: tuple[int, int, int], amount: int) -> tuple[int, int, int]:
  return tuple(max(0, min(255, channel + amount)) for channel in color)


def name_hash(name: str) -> int:
  return zlib.crc32(name.encode("utf-8")) & 0xFFFFFFFF


def infer_item_category(name: str) -> str:
  lname = name.lower()
  if "egg" in lname:
    return "egg"
  if any(token in lname for token in ("berry", "zaza", "pill", "packet", "dose", "seed", "sweet", "apple", "mushroom", "juice", "honey", "herb")):
    return "snack"
  if any(token in lname for token in ("potion", "ether", "elixir", "spray", "vitamin", "zinc", "protein", "carbos", "iron", "calcium")):
    return "brew"
  if any(token in lname for token in ("tm", "braince", "memory", "drive", "disc", "disk", "upgrade", "dubious", "capsule", "lens", "specs", "scope", "scarf")):
    return "module"
  if any(token in lname for token in ("ribbon", "voucher", "ticket", "coupon", "coin", "nugget", "star")):
    return "seal"
  if any(token in lname for token in ("ball", "cryptank", "tank", "tag", "lock", "lure")):
    return "capture"
  if any(token in lname for token in ("band", "bracelet", "belt", "claw", "fang", "mask", "orb", "charm", "amulet", "policy", "plate", "stone", "gem", "shard", "crystal", "core", "alloy", "armor", "cord", "cloth", "scale", "teacup", "pot")):
    return "relic"
  if any(token in lname for token in ("candy", "jar")):
    return "gear"
  return "token"


def infer_item_palette(name: str, category: str) -> AccentPalette:
  lname = name.lower()
  for token, accent in TYPE_ACCENTS.items():
    if token in lname:
      return accent
  return CATEGORY_DEFAULTS[(list(CATEGORY_DEFAULTS.keys())[name_hash(name) % len(CATEGORY_DEFAULTS)]) if category == "token" else category]


def draw_shadow(draw: ImageDraw.ImageDraw, x1: int, y1: int, x2: int, y2: int, *, radius: int = 4) -> None:
  draw.rounded_rectangle((x1, y1, x2, y2), radius=radius, fill=rgba(RELIC_SHADOW, 130))


def draw_snack_icon(draw: ImageDraw.ImageDraw, frame: tuple[int, int, int, int], accent: AccentPalette, variant: int) -> None:
  x1, y1, x2, y2 = frame
  draw_shadow(draw, x1 + 3, y1 + 6, x2 - 4, y2 - 4, radius=4)
  draw.rounded_rectangle((x1 + 3, y1 + 6, x2 - 4, y2 - 4), radius=4, fill=rgba(RELIC_METAL), outline=rgba(RELIC_SHADOW))
  draw.rounded_rectangle((x1 + 5, y1 + 8, x2 - 6, y2 - 6), radius=3, fill=rgba(add_rgb(accent.mid, 12)), outline=rgba(accent.dark))
  draw.line((x1 + 6, y1 + 9, x2 - 7, y1 + 9), fill=rgba(accent.light))
  cap_fill = add_rgb(accent.light, 18)
  stem_fill = add_rgb(TYPE_ACCENTS["grass"].light, 28)
  mushrooms = [
    ((x1 + 8, y1 + 12), 4),
    ((x1 + 14, y1 + 11), 5),
    ((x1 + 20, y1 + 12), 4),
  ]
  if variant % 2 == 1:
    mushrooms = [
      ((x1 + 10, y1 + 12), 4),
      ((x1 + 16, y1 + 10), 6),
      ((x1 + 22, y1 + 12), 4),
    ]
  for (cx, cy), radius in mushrooms:
    stem_w = max(2, radius // 2)
    draw.rounded_rectangle((cx - stem_w // 2, cy + 1, cx + stem_w // 2, cy + radius + 2), radius=1, fill=rgba(stem_fill), outline=rgba(accent.dark))
    draw.pieslice((cx - radius, cy - radius, cx + radius, cy + radius), 180, 360, fill=rgba(cap_fill), outline=rgba(accent.dark))
    draw.line((cx - radius + 1, cy, cx + radius - 1, cy), fill=rgba(accent.light))
    if radius >= 5:
      draw.ellipse((cx - 1, cy - 2, cx + 1, cy), fill=rgba(RELIC_INNER))


def draw_brew_icon(draw: ImageDraw.ImageDraw, frame: tuple[int, int, int, int], accent: AccentPalette, variant: int) -> None:
  x1, y1, x2, y2 = frame
  draw_shadow(draw, x1 + 5, y1 + 4, x2 - 4, y2 - 2, radius=4)
  draw.rectangle((x1 + 8, y1 + 2, x2 - 8, y1 + 5), fill=rgba(RELIC_METAL), outline=rgba(RELIC_SHADOW))
  draw.rounded_rectangle((x1 + 5, y1 + 5, x2 - 5, y2 - 4), radius=4, fill=rgba(accent.dark), outline=rgba(RELIC_SHADOW))
  draw.rounded_rectangle((x1 + 7, y1 + 8, x2 - 7, y2 - 6), radius=3, fill=rgba(accent.mid), outline=rgba(accent.light))
  draw.line((x1 + 7, y1 + 8, x2 - 7, y1 + 8), fill=rgba(RELIC_INNER))
  fill_top = y1 + 10 if variant % 2 == 0 else y1 + 12
  draw.rectangle((x1 + 8, fill_top, x2 - 8, y2 - 7), fill=rgba(add_rgb(accent.light, -10)))
  draw.line((x1 + 8, fill_top, x2 - 8, fill_top), fill=rgba(RELIC_INNER))


def draw_relic_icon(draw: ImageDraw.ImageDraw, frame: tuple[int, int, int, int], accent: AccentPalette, variant: int) -> None:
  x1, y1, x2, y2 = frame
  cx = (x1 + x2) // 2
  cy = (y1 + y2) // 2
  pts = [(cx, y1 + 1), (x2 - 2, cy), (cx, y2 - 2), (x1 + 1, cy)]
  draw.polygon([(px + 1, py + 1) for px, py in pts], fill=rgba(RELIC_SHADOW, 150))
  draw.polygon(pts, fill=rgba(accent.mid), outline=rgba(accent.dark))
  draw.polygon([(cx, y1 + 3), (x2 - 4, cy), (cx, y2 - 4), (x1 + 3, cy)], fill=rgba(accent.light))
  if variant % 3 == 0:
    draw.line((cx, y1 + 4, cx, y2 - 5), fill=rgba(accent.dark))
  elif variant % 3 == 1:
    draw.line((x1 + 4, cy, x2 - 5, cy), fill=rgba(accent.dark))
  else:
    draw.line((x1 + 4, y2 - 5, x2 - 5, y1 + 4), fill=rgba(accent.dark))


def draw_module_icon(draw: ImageDraw.ImageDraw, frame: tuple[int, int, int, int], accent: AccentPalette, variant: int) -> None:
  x1, y1, x2, y2 = frame
  draw_shadow(draw, x1 + 3, y1 + 4, x2 - 2, y2 - 3, radius=4)
  draw.rounded_rectangle((x1 + 3, y1 + 4, x2 - 3, y2 - 4), radius=4, fill=rgba(accent.dark), outline=rgba(RELIC_SHADOW))
  draw.rounded_rectangle((x1 + 5, y1 + 6, x2 - 5, y2 - 6), radius=3, fill=rgba(accent.mid), outline=rgba(accent.light))
  inset = max(4, min((x2 - x1) // 4, (y2 - y1) // 4))
  disc_box = (x1 + inset, y1 + inset, x2 - inset, y2 - inset)
  draw.ellipse(disc_box, fill=rgba(RELIC_INNER), outline=rgba(accent.dark))
  ring1 = max(2, min(4, (disc_box[2] - disc_box[0]) // 5))
  inner_box = (disc_box[0] + ring1, disc_box[1] + ring1, disc_box[2] - ring1, disc_box[3] - ring1)
  if inner_box[2] > inner_box[0] and inner_box[3] > inner_box[1]:
    draw.ellipse(inner_box, fill=rgba(accent.light), outline=rgba(accent.dark))
  ring2 = max(1, min(3, (disc_box[2] - disc_box[0]) // 8))
  core_box = (inner_box[0] + ring2, inner_box[1] + ring2, inner_box[2] - ring2, inner_box[3] - ring2)
  if core_box[2] > core_box[0] and core_box[3] > core_box[1]:
    draw.ellipse(core_box, fill=rgba(accent.dark), outline=rgba(RELIC_INNER))
  if variant % 2 == 0:
    draw.line((x1 + 7, y1 + 7, x2 - 7, y2 - 7), fill=rgba(add_rgb(accent.light, 12)))
  else:
    draw.line((x2 - 7, y1 + 7, x1 + 7, y2 - 7), fill=rgba(add_rgb(accent.light, 12)))
  draw.rectangle((x1 + 5, y2 - 8, x2 - 6, y2 - 6), fill=rgba(RELIC_METAL))


def draw_seal_icon(draw: ImageDraw.ImageDraw, frame: tuple[int, int, int, int], accent: AccentPalette, variant: int) -> None:
  x1, y1, x2, y2 = frame
  draw_shadow(draw, x1 + 5, y1 + 4, x2 - 4, y2 - 2, radius=4)
  draw.rounded_rectangle((x1 + 5, y1 + 4, x2 - 5, y2 - 8), radius=4, fill=rgba(accent.mid), outline=rgba(accent.dark))
  draw.line((x1 + 6, y1 + 5, x2 - 6, y1 + 5), fill=rgba(accent.light))
  left_tail = [(x1 + 8, y2 - 9), (x1 + 12, y2 - 2), (x1 + 16, y2 - 9)]
  right_tail = [(x2 - 16, y2 - 9), (x2 - 12, y2 - 2), (x2 - 8, y2 - 9)]
  draw.polygon(left_tail, fill=rgba(accent.dark), outline=rgba(RELIC_SHADOW))
  draw.polygon(right_tail, fill=rgba(accent.dark), outline=rgba(RELIC_SHADOW))
  if variant % 2 == 0:
    inner_margin_x = max(2, (x2 - x1) // 5)
    inner_margin_y = max(2, (y2 - y1) // 5)
    draw.ellipse((x1 + inner_margin_x, y1 + inner_margin_y, x2 - inner_margin_x, y2 - inner_margin_y - 4), outline=rgba(RELIC_INNER))
  else:
    draw.line((x1 + 10, y1 + 10, x2 - 10, y2 - 13), fill=rgba(RELIC_INNER))
    draw.line((x1 + 10, y2 - 13, x2 - 10, y1 + 10), fill=rgba(RELIC_INNER))


def draw_token_icon(draw: ImageDraw.ImageDraw, frame: tuple[int, int, int, int], accent: AccentPalette, variant: int) -> None:
  x1, y1, x2, y2 = frame
  width = x2 - x1
  height = y2 - y1
  outer = max(1, min(width, height) // 6)
  inner = max(1, outer + 1)
  radius = max(1, min(width, height) // 5)
  draw_shadow(draw, x1 + outer + 1, y1 + outer + 1, x2 - outer, y2 - outer, radius=radius)
  draw.rounded_rectangle((x1 + outer, y1 + outer, x2 - outer - 1, y2 - outer - 1), radius=radius, fill=rgba(accent.dark), outline=rgba(RELIC_SHADOW))
  draw.rounded_rectangle((x1 + inner, y1 + inner, x2 - inner - 1, y2 - inner - 1), radius=max(1, radius - 1), fill=rgba(accent.mid), outline=rgba(accent.light))
  stripe_count = max(1, min(variant % 4 + 1, max(1, (width - inner * 2) // 4)))
  start_x = x1 + inner + 2
  for idx in range(stripe_count):
    px = start_x + idx * 4
    if px < x2 - inner - 1:
      draw.line((px, y1 + inner + 2, px, y2 - inner - 2), fill=rgba(RELIC_INNER))


def draw_egg_icon(draw: ImageDraw.ImageDraw, frame: tuple[int, int, int, int], accent: AccentPalette, variant: int) -> None:
  x1, y1, x2, y2 = frame
  pts = [(x1 + 8, y2 - 5), (x1 + 5, y1 + 10), (x1 + 8, y1 + 5), (x2 - 8, y1 + 2), (x2 - 5, y1 + 8), (x2 - 6, y2 - 5)]
  draw.polygon([(px + 1, py + 1) for px, py in pts], fill=rgba(RELIC_SHADOW, 140))
  draw.polygon(pts, fill=rgba(accent.mid), outline=rgba(accent.dark))
  draw.polygon([(x1 + 9, y2 - 7), (x1 + 7, y1 + 11), (x1 + 10, y1 + 7), (x2 - 8, y1 + 4), (x2 - 7, y1 + 9), (x2 - 8, y2 - 7)], fill=rgba(accent.light))
  crack_y = y1 + 11 if variant % 2 == 0 else y1 + 9
  draw.line((x1 + 9, crack_y, x1 + 13, crack_y + 2, x1 + 16, crack_y - 1, x2 - 9, crack_y + 2), fill=rgba(accent.dark), width=1)


def draw_gear_icon(draw: ImageDraw.ImageDraw, frame: tuple[int, int, int, int], accent: AccentPalette, variant: int) -> None:
  x1, y1, x2, y2 = frame
  draw_shadow(draw, x1 + 4, y1 + 4, x2 - 3, y2 - 3, radius=4)
  draw.rounded_rectangle((x1 + 3, y1 + 3, x2 - 4, y2 - 4), radius=4, fill=rgba(accent.dark), outline=rgba(RELIC_SHADOW))
  draw.rounded_rectangle((x1 + 5, y1 + 5, x2 - 6, y2 - 6), radius=3, fill=rgba(accent.mid), outline=rgba(accent.light))
  draw.rectangle((x1 + 9, y1 + 1, x2 - 10, y1 + 5), fill=rgba(RELIC_METAL), outline=rgba(RELIC_SHADOW))
  draw.rectangle((x1 + 10, y1 + 7, x2 - 11, y2 - 8), fill=rgba(accent.light))
  if variant % 2 == 0:
    draw.rectangle((x1 + 7, y2 - 9, x2 - 8, y2 - 7), fill=rgba(RELIC_INNER))
  else:
    draw.line((x1 + 7, y1 + 9, x2 - 8, y2 - 8), fill=rgba(RELIC_INNER))


def draw_capture_icon(draw: ImageDraw.ImageDraw, frame: tuple[int, int, int, int], accent: AccentPalette, variant: int) -> None:
  x1, y1, x2, y2 = frame
  draw_shadow(draw, x1 + 5, y1 + 3, x2 - 5, y2 - 2, radius=6)
  draw.rounded_rectangle((x1 + 7, y1 + 3, x2 - 8, y2 - 4), radius=6, fill=rgba(accent.dark), outline=rgba(RELIC_SHADOW))
  draw.rounded_rectangle((x1 + 9, y1 + 7, x2 - 10, y2 - 8), radius=5, fill=rgba(add_rgb(accent.mid, 18)), outline=rgba(accent.light))
  draw.line((x1 + 10, y1 + 8, x2 - 11, y1 + 8), fill=rgba(RELIC_INNER))
  fluid_top = y1 + 15 if variant % 2 == 0 else y1 + 13
  draw.rectangle((x1 + 10, fluid_top, x2 - 11, y2 - 9), fill=rgba(accent.mid))
  draw.line((x1 + 10, fluid_top, x2 - 11, fluid_top), fill=rgba(accent.light))
  brain = [(x1 + 12, y1 + 12), (x1 + 16, y1 + 10), (x2 - 16, y1 + 11), (x2 - 12, y1 + 14), (x2 - 13, y1 + 18), (x1 + 14, y1 + 18)]
  draw.polygon(brain, fill=rgba(RELIC_INNER), outline=rgba(accent.dark))
  draw.rectangle((x1 + 12, y2 - 6, x2 - 13, y2 - 4), fill=rgba(RELIC_METAL))
  draw.rectangle((x1 + 14, y1 + 1, x2 - 15, y1 + 4), fill=rgba(RELIC_METAL), outline=rgba(RELIC_SHADOW))


def render_item_frame(name: str, width: int, height: int) -> Image.Image:
  image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
  draw = ImageDraw.Draw(image)
  category = infer_item_category(name)
  if min(width, height) < 24:
    category = "token"
  accent = infer_item_palette(name, category)
  variant = name_hash(name) % 7
  frame = (1, 1, width - 1, height - 1)
  if category == "snack":
    draw_snack_icon(draw, frame, accent, variant)
  elif category == "brew":
    draw_brew_icon(draw, frame, accent, variant)
  elif category == "relic":
    draw_relic_icon(draw, frame, accent, variant)
  elif category == "module":
    draw_module_icon(draw, frame, accent, variant)
  elif category == "seal":
    draw_seal_icon(draw, frame, accent, variant)
  elif category == "egg":
    draw_egg_icon(draw, frame, accent, variant)
  elif category == "gear":
    draw_gear_icon(draw, frame, accent, variant)
  elif category == "capture":
    draw_capture_icon(draw, frame, accent, variant)
  else:
    draw_token_icon(draw, frame, accent, variant)
  return image


PB_VARIANT_ACCENTS = {
  "pb": TYPE_ACCENTS["psychic"],
  "gb": TYPE_ACCENTS["water"],
  "ub": TYPE_ACCENTS["electric"],
  "rb": TYPE_ACCENTS["dark"],
  "mb": TYPE_ACCENTS["ghost"],
  "lb": TYPE_ACCENTS["fairy"],
}


def render_cryptank_tile(accent: AccentPalette, state: str) -> Image.Image:
  tile = Image.new("RGBA", (12, 16), (0, 0, 0, 0))
  draw = ImageDraw.Draw(tile)
  body = (2, 4, 9, 13)
  draw.rounded_rectangle((1, 3, 10, 14), radius=3, fill=rgba(RELIC_SHADOW, 120))
  if state == "open":
    draw.rectangle((4, 0, 7, 2), fill=rgba(RELIC_METAL), outline=rgba(RELIC_SHADOW))
    draw.line((5, 2, 5, 5), fill=rgba(RELIC_INNER))
    draw.line((6, 2, 6, 5), fill=rgba(RELIC_INNER))
    draw.rounded_rectangle(body, radius=3, fill=rgba(accent.dark), outline=rgba(RELIC_SHADOW))
    draw.rounded_rectangle((3, 6, 8, 12), radius=2, fill=rgba(add_rgb(accent.mid, 16)), outline=rgba(accent.light))
    draw.rectangle((3, 8, 8, 12), fill=rgba(accent.mid))
    draw.line((3, 8, 8, 8), fill=rgba(accent.light))
    draw.line((5, 5, 5, 15), fill=rgba(RELIC_INNER))
    draw.line((6, 5, 6, 15), fill=rgba(RELIC_INNER))
  elif state == "opening":
    draw.polygon([(4, 1), (8, 1), (9, 4), (5, 4)], fill=rgba(RELIC_METAL), outline=rgba(RELIC_SHADOW))
    draw.rounded_rectangle(body, radius=3, fill=rgba(accent.dark), outline=rgba(RELIC_SHADOW))
    draw.rounded_rectangle((3, 7, 8, 12), radius=2, fill=rgba(add_rgb(accent.mid, 18)), outline=rgba(accent.light))
    draw.rectangle((3, 9, 8, 12), fill=rgba(accent.mid))
    draw.line((3, 9, 8, 9), fill=rgba(accent.light))
    draw.line((5, 5, 5, 12), fill=rgba(RELIC_INNER))
    draw.line((6, 5, 6, 12), fill=rgba(RELIC_INNER))
  else:
    draw.rectangle((4, 1, 7, 3), fill=rgba(RELIC_METAL), outline=rgba(RELIC_SHADOW))
    draw.rounded_rectangle(body, radius=3, fill=rgba(accent.dark), outline=rgba(RELIC_SHADOW))
    draw.rounded_rectangle((3, 6, 8, 12), radius=2, fill=rgba(add_rgb(accent.mid, 18)), outline=rgba(accent.light))
    draw.rectangle((3, 8, 8, 12), fill=rgba(accent.mid))
    draw.line((3, 8, 8, 8), fill=rgba(accent.light))
    draw.ellipse((4, 7, 7, 9), fill=rgba(RELIC_INNER), outline=rgba(accent.dark))
  return tile


def style_capture_device_atlas() -> None:
  atlas_json = ROOT / "assets" / "images" / "pb.json"
  atlas_meta = json.loads(atlas_json.read_text())
  texture = atlas_meta["textures"][0]
  size = texture["size"]
  dst = Image.new("RGBA", (size["w"], size["h"]), (0, 0, 0, 0))

  for frame in texture["frames"]:
    name = frame["filename"]
    variant = name.split("_", 1)[0]
    state = "closed"
    if name.endswith("_open"):
      state = "open"
    elif name.endswith("_opening"):
      state = "opening"
    tile = render_cryptank_tile(PB_VARIANT_ACCENTS.get(variant, TYPE_ACCENTS["psychic"]), state)
    source = frame["spriteSourceSize"]
    cropped = tile.crop((source["x"], source["y"], source["x"] + source["w"], source["y"] + source["h"]))
    rect = frame["frame"]
    dst.alpha_composite(cropped, (rect["x"], rect["y"]))

  dst.save(ROOT / "assets" / "images" / "pb.png")


def draw_mini_cryptank(accent: AccentPalette, *, fill: tuple[int, int, int] | None = None) -> Image.Image:
  tile = Image.new("RGBA", (7, 7), (0, 0, 0, 0))
  draw = ImageDraw.Draw(tile)
  body_fill = fill if fill is not None else accent.mid
  draw.rounded_rectangle((1, 1, 5, 6), radius=2, fill=rgba(accent.dark), outline=rgba(RELIC_SHADOW))
  draw.rounded_rectangle((2, 2, 4, 5), radius=1, fill=rgba(body_fill), outline=rgba(accent.light if fill is None else body_fill))
  draw.rectangle((2, 0, 4, 1), fill=rgba(RELIC_METAL))
  return tile


def style_capture_tray_icons() -> None:
  tray = Image.new("RGBA", (28, 7), (0, 0, 0, 0))
  tray.alpha_composite(draw_mini_cryptank(PB_VARIANT_ACCENTS["pb"]), (0, 0))
  tray.alpha_composite(draw_mini_cryptank(TYPE_ACCENTS["steel"], fill=(90, 98, 112)), (7, 0))
  tray.alpha_composite(draw_mini_cryptank(TYPE_ACCENTS["fire"], fill=(126, 63, 63)), (14, 0))
  tray.alpha_composite(draw_mini_cryptank(TYPE_ACCENTS["electric"], fill=(214, 180, 82)), (21, 0))
  tray.save(ROOT / "assets" / "images" / "ui" / "pb_tray_ball.png")


def style_item_icons() -> None:
  atlas_json = ROOT / "assets" / "images" / "items.json"
  atlas_meta = json.loads(atlas_json.read_text())
  texture = atlas_meta["textures"][0]
  size = texture["size"]
  dst = Image.new("RGBA", (size["w"], size["h"]), (0, 0, 0, 0))

  for frame in texture["frames"]:
    name = frame["filename"]
    rect = frame["frame"]
    icon = render_item_frame(name, rect["w"], rect["h"])
    dst.alpha_composite(icon, (rect["x"], rect["y"]))

  dst.save(ROOT / "assets" / "images" / "items.png")


def main() -> None:
  battle_accent = VARIANTS[3]

  for name in [
    "pbinfo_player.png",
    "pbinfo_player_stats.png",
    "pbinfo_player_mini.png",
    "pbinfo_player_mini_stats.png",
    "pbinfo_enemy_mini.png",
    "pbinfo_enemy_mini_stats.png",
    "pbinfo_enemy_boss.png",
    "pbinfo_enemy_boss_stats.png",
  ]:
    style_pbinfo_asset(name, battle_accent)

  build_overlay_hp()
  build_windows()
  build_bg_and_namebox()
  build_starter_container_bg()
  build_starter_and_archive_backgrounds()
  build_battle_backgrounds()
  style_message_overlay()
  style_capture_device_atlas()
  style_capture_tray_icons()
  style_item_icons()


if __name__ == "__main__":
  main()
