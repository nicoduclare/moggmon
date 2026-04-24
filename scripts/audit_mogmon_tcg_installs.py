#!/usr/bin/env python3
"""Audit installed Mogger Mon TCG atlases and rank suspicious installs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

from mogmon_normalizer import load_template_atlas, summarize_frame_quality


ROOT = Path(__file__).resolve().parent.parent
TCG_ROOT = ROOT / "output" / "private-generation-prompts" / "mogger-mon-tcg"
POKEMON_ROOT = ROOT / "assets" / "images" / "pokemon"


def parse_dex_list(raw_value: str) -> list[int]:
    return [int(part.strip()) for part in raw_value.split(",") if part.strip()]


def iter_tcg_dexes() -> list[int]:
    return sorted(int(path.name) for path in TCG_ROOT.iterdir() if path.is_dir() and path.name.isdigit())


def render_unique_frames_from_atlas(atlas_json_path: Path) -> tuple[dict, list[Image.Image]]:
    atlas = load_template_atlas(atlas_json_path)
    atlas_image = Image.open(atlas_json_path.parent / atlas["image"]).convert("RGBA")
    full_frames: list[Image.Image] = []
    for frame in atlas["unique_frames"]:
        rect = frame["frame"]
        sprite_source = frame["spriteSourceSize"]
        crop = atlas_image.crop(
            (
                rect["x"],
                rect["y"],
                rect["x"] + rect["w"],
                rect["y"] + rect["h"],
            )
        )
        full = Image.new("RGBA", (atlas["source_w"], atlas["source_h"]), (0, 0, 0, 0))
        full.paste(crop, (sprite_source["x"], sprite_source["y"]), crop)
        full_frames.append(full)
    return atlas, full_frames


def audit_view(dex: int, view: str) -> dict:
    subdir = Path() if view == "front" else Path("back")
    current_png = POKEMON_ROOT / subdir / f"{dex}.png"
    current_json = POKEMON_ROOT / subdir / f"{dex}.json"
    backup_png = POKEMON_ROOT / "_backup" / subdir / f"{dex}.png"
    backup_json = POKEMON_ROOT / "_backup" / subdir / f"{dex}.json"

    if not backup_png.exists() or not backup_json.exists():
        return {
            "dex": dex,
            "view": view,
            "status": "not-installed",
        }

    template = load_template_atlas(backup_json)
    _current_atlas, current_frames = render_unique_frames_from_atlas(current_json)
    quality = summarize_frame_quality(current_frames, template, detected_count=len(current_frames))
    return {
        "dex": dex,
        "view": view,
        "status": "audited",
        "changed_from_backup": current_png.read_bytes() != backup_png.read_bytes(),
        "quality_score": quality["score"],
        "avg_iou": quality["avg_iou"],
        "min_iou": quality["min_iou"],
        "avg_area_ratio": quality["avg_area_ratio"],
        "min_area_ratio": quality["min_area_ratio"],
        "tiny_frame_count": quality["tiny_frame_count"],
        "blank_frame_count": quality["blank_frame_count"],
        "excess_edge_touches": quality["excess_edge_touches"],
        "unique_count": len(current_frames),
    }


def print_summary(results: list[dict], limit: int, score_threshold: float) -> None:
    audited = [result for result in results if result["status"] == "audited"]
    pending = [result for result in results if result["status"] == "not-installed"]
    suspicious = [
        result
        for result in audited
        if result["quality_score"] < score_threshold
        or result["tiny_frame_count"] > 0
        or result["blank_frame_count"] > 0
        or result["excess_edge_touches"] > 0
    ]
    suspicious.sort(
        key=lambda result: (
            result["quality_score"],
            -result["tiny_frame_count"],
            -result["blank_frame_count"],
            -result["excess_edge_touches"],
            result["dex"],
            result["view"],
        )
    )

    print(f"audited views: {len(audited)}")
    print(f"not-installed views: {len(pending)}")
    print(f"suspicious views: {len(suspicious)}")
    print("")
    for result in suspicious[:limit]:
        print(
            f"dex {result['dex']:>3} {result['view']:<5}"
            f" score={result['quality_score']:.3f}"
            f" avg_iou={result['avg_iou']:.3f}"
            f" min_iou={result['min_iou']:.3f}"
            f" tiny={result['tiny_frame_count']}"
            f" blank={result['blank_frame_count']}"
            f" edge={result['excess_edge_touches']}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit installed Mogger Mon TCG atlases and rank suspicious installs.")
    parser.add_argument(
        "--dex-list",
        default="",
        help="Optional comma-separated dex list. Default audits every TCG dex folder.",
    )
    parser.add_argument(
        "--score-threshold",
        type=float,
        default=0.25,
        help="Flag audited views below this quality score. Default: 0.25",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=40,
        help="How many suspicious views to print. Default: 40",
    )
    parser.add_argument(
        "--json-out",
        default="",
        help="Optional JSON output path relative to the repo root.",
    )
    args = parser.parse_args()

    dex_values = parse_dex_list(args.dex_list) if args.dex_list else iter_tcg_dexes()
    results = []
    for dex in dex_values:
        results.append(audit_view(dex, "front"))
        results.append(audit_view(dex, "back"))

    print_summary(results, limit=args.limit, score_threshold=args.score_threshold)

    if args.json_out:
        output_path = (ROOT / args.json_out).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
        print("")
        print(output_path)


if __name__ == "__main__":
    main()
