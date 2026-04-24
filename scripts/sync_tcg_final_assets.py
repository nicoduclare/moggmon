#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import re
import shutil
from pathlib import Path

from PIL import Image, ImageChops, ImageOps

ROOT = Path(__file__).resolve().parents[1]
CARD_SIZE = (768, 1061)
MASK_OFFSET = (8, 4)
CARD_RE = re.compile(r"^(\d{3})-.+\.png$")

try:
    RESAMPLE = Image.Resampling.LANCZOS
except AttributeError:
    RESAMPLE = Image.LANCZOS


def repo_path(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def parse_dex_values(raw_values: list[str]) -> set[str]:
    dexes: set[str] = set()
    for raw_value in raw_values:
        for part in raw_value.split(","):
            part = part.strip()
            if not part:
                continue
            if not part.isdigit():
                raise ValueError(f"Invalid dex value: {part}")
            dexes.add(f"{int(part):03d}")
    return dexes


def load_card_to_source_map(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        rows = csv.DictReader(handle, delimiter="\t")
        mapping: dict[str, str] = {}
        for row in rows:
            raw_card = (row.get("card") or row.get("dex") or "").strip()
            raw_source = (row.get("sourceDex") or raw_card).strip()
            if not raw_card or not raw_source:
                continue
            mapping[f"{int(raw_card):03d}"] = str(int(raw_source))
        return mapping


def discover_cards(final_dir: Path, selected_dexes: set[str]) -> dict[str, Path]:
    candidates_by_dex: dict[str, list[Path]] = {}
    for path in final_dir.rglob("*.png"):
        if path.name == "preview-grid.png" or path.name.endswith("-mask.png"):
            continue
        match = CARD_RE.match(path.name)
        if not match:
            continue
        dex = match.group(1)
        if selected_dexes and dex not in selected_dexes:
            continue
        candidates_by_dex.setdefault(dex, []).append(path)

    cards: dict[str, Path] = {}
    for dex, candidates in candidates_by_dex.items():
        # A single-card rerender may live at the output root while older grouped
        # renders still exist. Prefer the newest source for that dex.
        cards[dex] = max(candidates, key=lambda candidate: candidate.stat().st_mtime_ns)
    return dict(sorted(cards.items()))


def build_border_card_mask(border_dir: Path) -> Image.Image:
    border_mask_path = border_dir / "mask.png"
    if not border_mask_path.exists():
        raise FileNotFoundError(f"Missing card border mask: {border_mask_path}")

    border_mask = Image.open(border_mask_path).convert("RGBA").getchannel("A")
    card_mask = Image.new("L", CARD_SIZE, 0)
    card_mask.paste(border_mask, MASK_OFFSET)
    return card_mask


def find_raw_holo_mask(raw_dir: Path, dex: str) -> Path | None:
    dex_dir = raw_dir / dex
    for name in ("holo-mask-2.png", "holo-mask.png"):
        path = dex_dir / name
        if path.exists():
            return path
    return None


def find_raw_holo_mask_for_card(raw_dir: Path, card: str, card_to_source: dict[str, str]) -> Path | None:
    source_dex = card_to_source.get(card, card)
    return find_raw_holo_mask(raw_dir, source_dex)


def render_card_space_mask(raw_mask_path: Path, border_card_mask: Image.Image) -> Image.Image:
    raw_mask = Image.open(raw_mask_path).convert("L")
    fitted = ImageOps.fit(raw_mask, CARD_SIZE, method=RESAMPLE, centering=(0.5, 0.44))
    return ImageChops.multiply(fitted, border_card_mask)


def find_existing_grouped_mask(card_path: Path) -> Path | None:
    mask_path = card_path.with_name(f"{card_path.stem}-mask.png")
    return mask_path if mask_path.exists() else None


def clean_numeric_targets(assets_dir: Path, dexes: set[str], dry_run: bool) -> None:
    for dex in sorted(dexes):
        flat_path = assets_dir / f"{dex}.png"
        nested_dir = assets_dir / dex
        for path in (flat_path, nested_dir):
            if not path.exists():
                continue
            print(f"remove {path.relative_to(ROOT)}")
            if dry_run:
                continue
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()


def sync_one(
    dex: str,
    card_path: Path,
    assets_dir: Path,
    raw_dir: Path,
    card_to_source: dict[str, str],
    border_card_mask: Image.Image,
    dry_run: bool,
) -> None:
    target_dir = assets_dir / dex
    flat_target = assets_dir / f"{dex}.png"
    nested_card_target = target_dir / "card.png"
    nested_mask_target = target_dir / "mask.png"

    raw_mask_path = find_raw_holo_mask_for_card(raw_dir, dex, card_to_source)
    grouped_mask_path = find_existing_grouped_mask(card_path)

    if raw_mask_path is None and grouped_mask_path is None:
        raise FileNotFoundError(
            f"Missing mask for {dex}: expected {raw_dir / dex / 'holo-mask-2.png'} "
            f"or {card_path.with_name(card_path.stem + '-mask.png')}"
        )

    print(f"sync {dex}: {card_path.relative_to(ROOT)} -> {target_dir.relative_to(ROOT)}")
    if dry_run:
        return

    target_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(card_path, flat_target)
    shutil.copy2(card_path, nested_card_target)

    if raw_mask_path is not None:
        mask = render_card_space_mask(raw_mask_path, border_card_mask)
        mask.save(nested_mask_target)
    else:
        assert grouped_mask_path is not None
        shutil.copy2(grouped_mask_path, nested_mask_target)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Flatten grouped Rotmon TCG final renders into assets/tcg/final.",
    )
    parser.add_argument(
        "--final-dir",
        type=Path,
        default=Path("output/private-generation-prompts/mogger-mon-tcg/cards/final"),
        help="Grouped final render directory. Default: output/private-generation-prompts/mogger-mon-tcg/cards/final",
    )
    parser.add_argument(
        "--assets-dir",
        type=Path,
        default=Path("assets/tcg/final"),
        help="Destination for flattened final card assets. Default: assets/tcg/final",
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path("tcg/raw"),
        help="Raw per-dex TCG source directory used for rebuilding card-space masks. Default: tcg/raw",
    )
    parser.add_argument(
        "--border-dir",
        type=Path,
        default=Path("tcg/borders"),
        help="TCG border directory containing mask.png. Default: tcg/borders",
    )
    parser.add_argument(
        "--evolution-paths",
        type=Path,
        default=Path("tcg/evolution-paths.tsv"),
        help="Human-editable card/source dex mapping. Default: tcg/evolution-paths.tsv",
    )
    parser.add_argument(
        "--dex",
        action="append",
        default=[],
        help="Dex number to sync. Repeat or pass comma-separated values. Default: all discovered cards.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove selected numeric targets before writing them.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned sync without writing files.",
    )
    args = parser.parse_args()

    final_dir = repo_path(args.final_dir)
    assets_dir = repo_path(args.assets_dir)
    raw_dir = repo_path(args.raw_dir)
    border_dir = repo_path(args.border_dir)
    evolution_paths = repo_path(args.evolution_paths)
    selected_dexes = parse_dex_values(args.dex)

    if not final_dir.exists():
        raise FileNotFoundError(f"Missing final render directory: {final_dir}")
    if not raw_dir.exists():
        raise FileNotFoundError(f"Missing raw source directory: {raw_dir}")

    cards = discover_cards(final_dir, selected_dexes)
    missing = sorted(selected_dexes - set(cards))
    if missing:
        raise FileNotFoundError(f"No final card render found for dex: {', '.join(missing)}")
    if not cards:
        raise SystemExit(f"No final card renders found in {final_dir}")

    if args.clean:
        clean_numeric_targets(assets_dir, set(cards), args.dry_run)

    card_to_source = load_card_to_source_map(evolution_paths)
    border_card_mask = build_border_card_mask(border_dir)
    for dex, card_path in cards.items():
        sync_one(dex, card_path, assets_dir, raw_dir, card_to_source, border_card_mask, args.dry_run)

    print(f"synced {len(cards)} card(s) into {assets_dir.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
