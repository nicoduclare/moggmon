#!/usr/bin/env python3
"""Render Mogger Mon icons from installed battle atlases and update icon sheets."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from PIL import Image

from mogmon_normalizer import render_icon_from_battle_atlas

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets" / "images"
POKEMON = ASSETS / "pokemon"
ICON_SOURCE_ROOT = POKEMON / "icons"
ICON_SHEET_GLOB = "pokemon_icons_[0-9].json"


def parse_dex_list(raw_value: str) -> list[int]:
    return [int(part.strip()) for part in raw_value.split(",") if part.strip()]


def load_sheet_frames(sheet_json_path: Path) -> dict[str, dict]:
    atlas = json.loads(sheet_json_path.read_text(encoding="utf-8"))
    return {frame["filename"]: frame for frame in atlas["textures"][0]["frames"]}


def discover_sheet_paths(sheet_arg: str | None) -> list[Path]:
    if sheet_arg:
        return [ASSETS / f"pokemon_icons_{part.strip()}.json" for part in sheet_arg.split(",") if part.strip()]
    return sorted(ASSETS.glob(ICON_SHEET_GLOB))


def discover_sheet_id(dex: int, sheet_paths: list[Path]) -> str | None:
    valid_sheet_ids = {path.stem.removeprefix("pokemon_icons_") for path in sheet_paths}
    source_match = next(
        (
            path.name
            for path in ICON_SOURCE_ROOT.iterdir()
            if path.is_dir() and path.name in valid_sheet_ids and (path / f"{dex}.png").exists()
        ),
        None,
    )
    if source_match:
        return source_match

    target_frame = str(dex)
    for sheet_json_path in sheet_paths:
        frames = load_sheet_frames(sheet_json_path)
        if target_frame in frames:
            return sheet_json_path.stem.removeprefix("pokemon_icons_")

    return None


def build_source_icon(trimmed_icon: Image.Image, frame_meta: dict) -> Image.Image:
    source_size = frame_meta["sourceSize"]
    sprite_source = frame_meta["spriteSourceSize"]
    source_icon = Image.new("RGBA", (source_size["w"], source_size["h"]), (0, 0, 0, 0))
    source_icon.paste(trimmed_icon, (sprite_source["x"], sprite_source["y"]), trimmed_icon)
    return source_icon


def ensure_backup(sheet_png_path: Path) -> Path:
    backup_path = sheet_png_path.with_suffix(".backup.png")
    if not backup_path.exists():
        shutil.copy2(sheet_png_path, backup_path)
        print(f"📦 Backed up {sheet_png_path.name} -> {backup_path.name}")
    return backup_path


def update_sheet_for_species(dex: int, sheet_id: str, frame_lookup: dict[str, dict], pixelify_base: int) -> bool:
    game_png = POKEMON / f"{dex}.png"
    game_json = POKEMON / f"{dex}.json"
    if not game_png.exists() or not game_json.exists():
        print(f"  ⏭  Missing installed battle atlas for dex {dex}")
        return False

    sheet_png_path = ASSETS / f"pokemon_icons_{sheet_id}.png"
    source_dir = ICON_SOURCE_ROOT / sheet_id
    ensure_backup(sheet_png_path)
    sheet_image = Image.open(sheet_png_path).convert("RGBA")

    updated_any = False
    for suffix in ("", "s"):
        frame_name = f"{dex}{suffix}"
        frame_meta = frame_lookup.get(frame_name)
        if not frame_meta:
            print(f"  ⏭  No icon frame '{frame_name}' in pokemon_icons_{sheet_id}")
            continue

        frame = frame_meta["frame"]
        trimmed_icon = render_icon_from_battle_atlas(
            game_png,
            game_json,
            frame["w"],
            frame["h"],
            pixel_base=max(1, pixelify_base),
        )
        sheet_image.paste(trimmed_icon, (frame["x"], frame["y"]), trimmed_icon)

        source_icon = build_source_icon(trimmed_icon, frame_meta)
        source_path = source_dir / f"{frame_name}.png"
        source_icon.save(source_path)

        print(
            f"  ✅ Updated dex {frame_name} in pokemon_icons_{sheet_id}"
            f" ({frame['w']}x{frame['h']} trimmed, source {source_icon.size[0]}x{source_icon.size[1]})"
        )
        updated_any = True

    if updated_any:
        sheet_image.save(sheet_png_path)
    return updated_any


def main() -> None:
    parser = argparse.ArgumentParser(description="Install Mogger Mon party icons into the packed icon sheets.")
    parser.add_argument(
        "--dex",
        default="1,4,7",
        help="Comma-separated dex list. Default preserves the original starter trio workflow: 1,4,7",
    )
    parser.add_argument(
        "--sheets",
        default="",
        help="Optional comma-separated icon sheet ids to search, for example 1 or 1,2.",
    )
    parser.add_argument(
        "--pixelify-base",
        type=int,
        default=64,
        help="Nearest-neighbor base width used when rebuilding icons. Default: 64",
    )
    args = parser.parse_args()

    dex_values = parse_dex_list(args.dex)
    sheet_paths = discover_sheet_paths(args.sheets or None)
    if not sheet_paths:
        raise SystemExit("No pokemon_icons_*.json atlas files found.")

    frame_cache: dict[str, dict[str, dict]] = {}
    installed_count = 0
    for dex in dex_values:
        sheet_id = discover_sheet_id(dex, sheet_paths)
        if not sheet_id:
            print(f"[{dex}] ⏭  Unable to find icon sheet")
            continue

        if sheet_id not in frame_cache:
            frame_cache[sheet_id] = load_sheet_frames(ASSETS / f"pokemon_icons_{sheet_id}.json")

        print(f"[{dex}] Installing icons into pokemon_icons_{sheet_id}...")
        if update_sheet_for_species(dex, sheet_id, frame_cache[sheet_id], args.pixelify_base):
            installed_count += 1

    print(f"\n🏁 Updated icons for {installed_count} dex entries.")


if __name__ == "__main__":
    main()
