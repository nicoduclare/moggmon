#!/usr/bin/env python3
"""Install generated Mogger Mon sprites into the game asset tree."""

import argparse
import os
import shutil

from mogmon_normalizer import normalize_battle_sprite_best_effort

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POKEMON = os.path.join(ROOT, "assets", "images", "pokemon")
MOGMON = os.path.join(ROOT, "assets", "images", "mogmon")
BACKUP = os.path.join(POKEMON, "_backup")


def install_species(dex, view, source_root, template_root=None, mode="auto", grid_dims=None, centered=False):
    """Install one mogmon sprite (one view) into the game."""
    subdir = "" if view == "front" else "back/"
    source_subdir = "front" if view == "front" else "back"

    orig_png = os.path.join(POKEMON, f"{subdir}{dex}.png")
    orig_json = os.path.join(POKEMON, f"{subdir}{dex}.json")
    mogmon_png = os.path.join(source_root, f"{subdir}{dex}.png")
    if not os.path.exists(mogmon_png):
        nested_candidate = os.path.join(source_root, source_subdir, f"{dex}.png")
        if os.path.exists(nested_candidate):
            mogmon_png = nested_candidate

    if not os.path.exists(mogmon_png):
        print(f"  ⏭  No mogmon {view} sprite for dex {dex} at {mogmon_png}")
        return False

    if not os.path.exists(orig_png) or not os.path.exists(orig_json):
        print(f"  ⏭  No original {view} sprite for dex {dex}")
        return False

    backup_dir = os.path.join(BACKUP, subdir)
    os.makedirs(backup_dir, exist_ok=True)

    backup_png = os.path.join(backup_dir, f"{dex}.png")
    backup_json = os.path.join(backup_dir, f"{dex}.json")

    if not os.path.exists(backup_png):
        shutil.copy2(orig_png, backup_png)
        shutil.copy2(orig_json, backup_json)
        print(f"  📦 Backed up originals to _backup/{subdir}")

    if template_root:
        template_json = os.path.join(template_root, f"{subdir}{dex}.json")
    else:
        template_json = backup_json if os.path.exists(backup_json) else orig_json

    if not os.path.exists(template_json):
        print(f"  ⏭  No template {view} sprite json for dex {dex} at {template_json}")
        return False

    result = normalize_battle_sprite_best_effort(
        mogmon_png,
        template_json,
        orig_png,
        orig_json,
        clip_to_template_mask=False,
        mode=mode,
        grid_dims=grid_dims,
        centered=centered,
    )

    print(
        "  ✅ Installed"
        f" {view} using {result['method']} detection"
        f" ({result['detected_count']} raw frames -> {result['expected_count']} atlas frames,"
        f" sheet {result['sheet_w']}x{result['sheet_h']},"
        f" score {result['quality_score']:.3f}, avg IoU {result['avg_iou']:.3f})"
    )
    if result["fallback_used"]:
        print("  ↪️  Auto-fallback selected the cleanest extraction plan:")
        for method in result["tried_methods"][:3]:
            print(f"     - {method}")
    if result["tiny_frame_count"] or result["excess_edge_touches"]:
        print(
            "  ⚠️  Fragment risk flags:"
            f" tiny-frames={result['tiny_frame_count']},"
            f" excess-edge-touches={result['excess_edge_touches']}"
        )
    return True


def parse_grid_dims(raw_value):
    normalized = raw_value.lower().replace(" ", "")
    cols, rows = normalized.split("x", 1)
    return (int(cols), int(rows))


def parse_grid_map(raw_value):
    if not raw_value:
        return {}

    grid_map = {}
    for token in raw_value.split(","):
        token = token.strip()
        if not token:
            continue
        key, raw_dims = token.split("=", 1)
        key = key.strip().lower()
        if ":" not in key:
            raise ValueError(f"Invalid grid-map entry '{token}'. Expected view:dex=COLSxROWS")
        view, dex = key.split(":", 1)
        if view not in ("front", "back"):
            raise ValueError(f"Invalid view '{view}' in grid-map entry '{token}'")
        grid_map[(view, int(dex))] = parse_grid_dims(raw_dims)

    return grid_map


def parse_args():
    parser = argparse.ArgumentParser(description="Install generated Mogger Mon sprites into battle assets.")
    parser.add_argument(
        "--dex",
        default="1,4,7",
        help="Comma-separated dex list. Default keeps the legacy starter trio: 1,4,7",
    )
    parser.add_argument(
        "--views",
        default="front,back",
        help="Comma-separated views to install. Default: front,back",
    )
    parser.add_argument(
        "--source-root",
        default=MOGMON,
        help="Root directory containing generated raw sprite sheets.",
    )
    parser.add_argument(
        "--template-root",
        default="",
        help="Optional root directory containing template atlas json files.",
    )
    parser.add_argument(
        "--mode",
        default="components",
        help="Normalization mode to pass through to mogmon_normalizer. Options: auto, components, row-column, regular-grid, slot-grid. Default: components",
    )
    parser.add_argument(
        "--grid",
        default="",
        help="Optional exact grid in COLSxROWS form, for example 8x7. When provided, bypasses heuristic frame detection.",
    )
    parser.add_argument(
        "--grid-map",
        default="",
        help="Optional per-view grid overrides in view:dex=COLSxROWS form, for example front:1=4x6,back:1=4x6.",
    )
    parser.add_argument(
        "--centered",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Anchor normalized frames to a shared bottom-center fit instead of inheriting template per-frame offsets. Default: enabled.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    dex_values = [int(item.strip()) for item in args.dex.split(",") if item.strip()]
    views = [item.strip() for item in args.views.split(",") if item.strip()]
    source_root = os.path.abspath(args.source_root)
    template_root = os.path.abspath(args.template_root) if args.template_root else None
    grid_dims = None
    if args.grid:
        grid_dims = parse_grid_dims(args.grid)
    grid_map = parse_grid_map(args.grid_map)

    print("\n🔧 Installing Mogger Mon sprites into game assets")
    print(f"   Source root: {source_root}")
    if template_root:
        print(f"   Template root: {template_root}")
    if grid_dims:
        print(f"   Exact grid: {grid_dims[0]}x{grid_dims[1]}")
    if grid_map:
        preview = ", ".join(
            f"{view}:{dex}={cols}x{rows}"
            for (view, dex), (cols, rows) in sorted(grid_map.items(), key=lambda item: (item[0][0], item[0][1]))
        )
        print(f"   Grid map: {preview}")
    print(f"   Anchor mode: {'centered' if args.centered else 'template-layout'}")
    print(f"   Backup dir: {BACKUP}\n")

    installed = 0
    for dex in dex_values:
        print(f"[{dex}] Installing...")
        for view in views:
            view_grid_dims = grid_map.get((view, dex), grid_dims)
            if install_species(
                dex,
                view,
                source_root,
                template_root=template_root,
                mode=args.mode,
                grid_dims=view_grid_dims,
                centered=args.centered,
            ):
                installed += 1

    print(f"\n🏁 Installed {installed} sprites. Originals backed up to _backup/")
    print("   To restore: copy matching files from assets/images/pokemon/_backup/")


if __name__ == "__main__":
    main()
