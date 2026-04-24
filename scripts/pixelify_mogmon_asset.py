#!/usr/bin/env python3
"""Nearest-neighbor pixelify helper for Mogger Mon assets."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from PIL import Image

SHARP_PIXELIFY_HELPER = Path(__file__).with_name("sharp_pixelify.mjs")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Downscale then nearest-neighbor upscale an image for a chunkier Mogger Mon look.",
    )
    parser.add_argument("input", help="Input image path.")
    parser.add_argument("output", nargs="?", help="Optional output path. Defaults to overwriting the input path.")
    parser.add_argument(
        "--base-width",
        type=int,
        default=64,
        help="Intermediate width used before nearest-neighbor upscale. Default: 64",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=0,
        help="Optional final width. Defaults to the input width.",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=0,
        help="Optional final height. Defaults to preserving aspect ratio from the chosen width.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve() if args.output else input_path
    image = Image.open(input_path).convert("RGBA")

    output_width = args.width if args.width > 0 else image.width
    output_height = args.height if args.height > 0 else max(1, int(round(image.height * output_width / image.width)))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "node",
        str(SHARP_PIXELIFY_HELPER),
        "--base-width",
        str(max(1, args.base_width)),
        "--width",
        str(max(1, output_width)),
        "--height",
        str(max(1, output_height)),
        str(input_path),
        str(output_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "unknown sharp pixelify failure").strip()
        raise RuntimeError(f"Sharp pixelify failed: {detail}")
    print(output_path)


if __name__ == "__main__":
    main()
