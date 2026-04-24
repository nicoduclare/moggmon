#!/usr/bin/env python3

import argparse
import shutil
from pathlib import Path


VALID_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def copy_file(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def main():
    parser = argparse.ArgumentParser(
        description="Mirror the brainrot reference set into the TCG workspace and seed the shared style-lesson files."
    )
    parser.add_argument(
        "--source-dir",
        default="output/private-generation-prompts/brainrot-wiki/images",
        help="Directory containing the canonical full-art brainrot references.",
    )
    parser.add_argument(
        "--out-dir",
        default="output/private-generation-prompts/mogger-mon-tcg/references/original",
        help="Directory to mirror the canonical references into.",
    )
    parser.add_argument(
        "--style-origin-source",
        default="output/private-generation-prompts/brainrot-wiki/images/brr-brr-patapim.webp",
        help="Solved-example original brainrot reference to copy into the shared style-lesson folder.",
    )
    parser.add_argument(
        "--style-reference-source",
        default="output/private-generation-prompts/mogger-mon-tcg/patapim-sprout-v2/reference-style.jpg",
        help="Solved-example Pokemon-style image to copy into the shared style-lesson folder.",
    )
    parser.add_argument(
        "--style-dir",
        default="output/private-generation-prompts/mogger-mon-tcg/references/style-lesson",
        help="Directory that stores the shared before/after style lesson files.",
    )
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    out_dir = Path(args.out_dir)
    style_dir = Path(args.style_dir)
    style_origin_source = Path(args.style_origin_source)
    style_reference_source = Path(args.style_reference_source)

    if not source_dir.exists():
        raise SystemExit(f"Source directory not found: {source_dir}")
    if not style_origin_source.exists():
        raise SystemExit(f"Style origin source not found: {style_origin_source}")
    if not style_reference_source.exists():
        raise SystemExit(f"Style reference source not found: {style_reference_source}")

    out_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for source in sorted(source_dir.iterdir()):
        if not source.is_file() or source.suffix.lower() not in VALID_IMAGE_SUFFIXES:
            continue
        copy_file(source, out_dir / source.name)
        copied += 1

    copy_file(style_origin_source, style_dir / f"reference{style_origin_source.suffix.lower()}")
    copy_file(style_reference_source, style_dir / f"reference-style{style_reference_source.suffix.lower()}")

    print(f"Mirrored {copied} reference images into {out_dir}")
    print(f"Seeded style lesson into {style_dir}")


if __name__ == "__main__":
    main()
