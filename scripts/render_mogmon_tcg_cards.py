#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFilter, ImageFont, ImageOps

CARD_SIZE = (768, 1061)
ROOT = Path(__file__).resolve().parents[1]
TCG_ROOT = ROOT / "tcg"


def has_numeric_source_dirs(path: Path) -> bool:
    return path.exists() and any(child.is_dir() and child.name.isdigit() for child in path.iterdir())


def default_source_dir() -> Path:
    tcg_raw = Path("tcg/raw")
    if has_numeric_source_dirs(ROOT / tcg_raw):
        return tcg_raw
    return Path("output/private-generation-prompts/mogger-mon-tcg")


def first_existing_path(*paths: Path) -> Path:
    for path in paths:
        if path.exists():
            return path
    return paths[0]


PROMPTS_PATH = Path(
    os.environ.get(
        "MOGGER_MON_PROMPTS_FILE",
        first_existing_path(
            TCG_ROOT / "prompts/mogger-mon-prompts.json",
            ROOT / "output/private-generation-prompts/mogger-mon-prompts.json",
        ),
    )
)
DEFAULT_DEX_COPY_PATHS = [
    ROOT / "output/private-generation-prompts/brainrot-wiki/gen1-dex-copy.tsv",
    ROOT / "output/private-generation-prompts/brainrot-wiki/reference2-dex-supplement.tsv",
]
TCG_DEX_COPY_PATHS = [
    TCG_ROOT / "dex/gen1-dex-copy.tsv",
    TCG_ROOT / "dex/reference2-dex-supplement.tsv",
]
DEX_COPY_PATHS = (
    [Path(path) for path in os.environ["MOGGER_MON_DEX_COPY_FILES"].split(os.pathsep)]
    if os.environ.get("MOGGER_MON_DEX_COPY_FILES")
    else (TCG_DEX_COPY_PATHS if all(path.exists() for path in TCG_DEX_COPY_PATHS) else DEFAULT_DEX_COPY_PATHS)
)
MASK_OFFSET = (8, 4)
TITLE_AREA = (57, 65, 560, 126)
STAGE_POS = (44, 10)
TYPE_ICON_BOX = (631, 26, 715, 110)
EVOLUTION_ART_POS = (30, 121)
EVOLUTION_ART_SIZE = 133
EVOLUTION_INNER_SIZE = 123
EVOLUTION_BADGE_SIZE = (301, 49)
EVOLUTION_BADGE_POS_DELTA = (53, 18)
DESCRIPTION_BOX = (45, 946, 723, 1022)
STAGE_COLORS = {
    "legendary": "#B01D00",
    "mythic": "#0F4099",
    "epic": "#340291",
    "rare": "#111317",
    "common": "#232323",
}
EVOLUTION_TEXT_COLOR = "#404040"
TITLE_FILL = "#000000"
TITLE_STROKE = "#FFFFFF"
DESCRIPTION_FILL = "#FFFFFF"
DESCRIPTION_STROKE = "#000000"
TOP_GRADIENT_HEIGHT = 250
BOTTOM_GRADIENT_HEIGHT = 260
TYPE_RING_COLORS = {
    "bug": "#8BC34A",
    "dark": "#6E6A7E",
    "dragon": "#5D8DFF",
    "electric": "#FFD84F",
    "fairy": "#F39AE7",
    "fighting": "#D96A4A",
    "fire": "#F36C3D",
    "flying": "#9BC2FF",
    "ghost": "#8A63C7",
    "grass": "#59C74E",
    "ground": "#D2A85F",
    "ice": "#AEEBFF",
    "normal": "#C5C0AE",
    "poison": "#B36AE0",
    "psychic": "#EB5BA2",
    "rock": "#B69563",
    "steel": "#A3B3C1",
    "water": "#5DA7FF",
}
STAGE_FALLBACK = {
    "base": 1,
    "mid": 2,
    "final": 3,
    "branch-final": 2,
    "solo": 1,
}
STAGE_PROGRESS = {
    "base": 0,
    "mid": 1,
    "branch-final": 2,
    "final": 2,
    "solo": 0,
}
RARITY_ORDER = ("common", "rare", "epic", "legendary", "mythic")
RARITY_OVERRIDES = {
    47: "mythic",
    3: "legendary",
    6: "legendary",
    9: "legendary",
    475: "mythic",
    571: "mythic",
    197: "mythic",
}
CUSTOM_CARD_FAMILY_LAYOUTS = {
    "coffee-assassino": {
        177: {"stage_number": 1, "prev_card_dex": None, "family_index": 0, "family_size": 3},
        171: {"stage_number": 2, "prev_card_dex": 177, "family_index": 1, "family_size": 3},
        478: {"stage_number": 3, "prev_card_dex": 171, "family_index": 2, "family_size": 3},
        512: {"stage_number": 3, "prev_card_dex": 171, "family_index": 2, "family_size": 3},
    },
    "bombardino-flight": {
        163: {"stage_number": 1, "prev_card_dex": None, "family_index": 0, "family_size": 2},
        106: {"stage_number": 2, "prev_card_dex": 163, "family_index": 1, "family_size": 2},
        164: {"stage_number": 2, "prev_card_dex": 163, "family_index": 1, "family_size": 2},
        237: {"stage_number": 2, "prev_card_dex": 163, "family_index": 1, "family_size": 2},
    }
}
# Dragon-brainrot cards should read as the premium mythic lane even when they
# sit inside normal evolution families.
DRAGON_MYTHIC_DEXES = {
    111,  # Panda Drago
    112,  # Panda Drago Plus
    140,  # Octo Drago
    141,  # Octo Drago Prime
    147,  # Sahur Drago
    148,  # Sahur Drago Plus
    149,  # Sahur Drago Boss
    180,  # Dragon Cannelloni
    181,  # Dragon Gingerini
    185,  # Ice Dragon
}
TOP_STAGE_LABELS = {"final", "branch-final", "solo"}

try:
    RESAMPLE = Image.Resampling.LANCZOS
except AttributeError:
    RESAMPLE = Image.LANCZOS


@dataclass
class SpeciesInfo:
    dex: int
    type1: str
    type2: str | None
    base_total: int
    sub_legendary: bool
    legendary: bool
    mythical: bool


@dataclass
class CardSpec:
    dex: int
    dex_label: str
    meta_dir: Path
    meta: dict[str, Any]
    art_path: Path
    stage_label: str
    family_id: str
    family_index: int = 0
    family_size: int = 1
    stage_number: int = 1
    prev_card_dex: int | None = None
    rarity: str = "common"
    type_key: str = "normal"


@dataclass
class CardEvolutionOverride:
    source_dex: int
    card_label: str
    prev_source_dex: int | None
    stage_label: str | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render Mogger Mon TCG cards from the staged art folders.")
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=default_source_dir(),
        help="Directory containing per-dex TCG art folders.",
    )
    parser.add_argument(
        "--border-dir",
        type=Path,
        default=Path("tcg/borders")
        if (TCG_ROOT / "borders").exists()
        else Path("output/private-generation-prompts/mogger-mon-tcg/borders"),
        help="Directory containing card border PNGs and mask.png.",
    )
    parser.add_argument(
        "--icon-dir",
        type=Path,
        default=Path("tcg/icons") if (TCG_ROOT / "icons").exists() else Path("icons"),
        help="Directory containing extracted type icon PNGs.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Optional destination folder for rendered card PNGs. Defaults to writing card.png inside each dex folder.",
    )
    parser.add_argument(
        "--output-name",
        default="card.png",
        help="Filename to use when writing cards in place inside each dex folder.",
    )
    parser.add_argument(
        "--dex",
        action="append",
        type=int,
        default=[],
        help="Render only the provided dex number. Repeat to render multiple cards.",
    )
    parser.add_argument(
        "--art-name",
        default="full-art-2",
        help="Art stem to render from, e.g. full-art or full-art-2.",
    )
    parser.add_argument(
        "--group-by-rarity",
        action="store_true",
        help="When writing to --out-dir, place card PNGs into rarity subfolders like common/, rare/, epic/, legendary/, and mythic/.",
    )
    return parser.parse_args()


def load_font(size: int, index: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype("/System/Library/Fonts/Supplemental/GillSans.ttc", size=size, index=index)


def parse_species_enum(path: Path) -> dict[str, int]:
    text = path.read_text()
    values: dict[str, int] = {}
    current_value = -1
    inside = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("export enum SpeciesId"):
            inside = True
            continue
        if not inside:
            continue
        if line.startswith("}"):
            break
        if not line or line.startswith("/**") or line.startswith("*") or line.startswith("/*"):
            continue
        match = re.match(r"^([A-Z0-9_]+)(?:\s*=\s*(\d+))?,?$", line)
        if not match:
            continue
        name, explicit = match.groups()
        current_value = int(explicit) if explicit is not None else current_value + 1
        values[name] = current_value
    return values


def parse_species_info(enum_values: dict[str, int], species_path: Path) -> dict[int, SpeciesInfo]:
    text = species_path.read_text()
    pattern = re.compile(
        r"new\s+PokemonSpecies\(\s*SpeciesId\.([A-Z0-9_]+)\s*,\s*\d+\s*,\s*(true|false)\s*,\s*(true|false)\s*,\s*(true|false)"
        r"\s*,\s*\"[^\"]*\"\s*,\s*PokemonType\.([A-Z_]+)\s*,\s*(?:PokemonType\.([A-Z_]+)|null)"
        r"\s*,\s*[0-9.]+\s*,\s*[0-9.]+\s*,\s*AbilityId\.[A-Z0-9_]+\s*,\s*AbilityId\.[A-Z0-9_]+\s*,\s*AbilityId\.[A-Z0-9_]+\s*,\s*(\d+)",
        re.MULTILINE,
    )
    species: dict[int, SpeciesInfo] = {}
    for match in pattern.finditer(text):
        species_name, sub_legendary, legendary, mythical, type1, type2, base_total = match.groups()
        dex = enum_values.get(species_name)
        if dex is None:
            continue
        species[dex] = SpeciesInfo(
            dex=dex,
            type1=type1.lower(),
            type2=type2.lower() if type2 else None,
            base_total=int(base_total),
            sub_legendary=sub_legendary == "true",
            legendary=legendary == "true",
            mythical=mythical == "true",
        )
    return species


def extract_balanced_section(text: str, start: int, open_char: str, close_char: str) -> tuple[str, int]:
    depth = 0
    quote_char = ""
    escaping = False
    for idx in range(start, len(text)):
        char = text[idx]
        if quote_char:
            if escaping:
                escaping = False
            elif char == "\\":
                escaping = True
            elif char == quote_char:
                quote_char = ""
            continue
        if char in {'"', "'", "`"}:
            quote_char = char
            continue
        if char == open_char:
            depth += 1
            continue
        if char == close_char:
            depth -= 1
            if depth == 0:
                return text[start + 1:idx], idx
    raise ValueError(f"Could not find matching {close_char!r} for section starting at {start}")


def parse_pokemon_prevolutions(enum_values: dict[str, int], evolutions_path: Path) -> dict[int, int]:
    text = evolutions_path.read_text()
    anchor = text.find("export const pokemonEvolutions")
    if anchor == -1:
        raise ValueError(f"Could not find pokemonEvolutions in {evolutions_path}")

    object_start = text.find("{", anchor)
    if object_start == -1:
        raise ValueError(f"Could not find pokemonEvolutions object in {evolutions_path}")

    object_body, _ = extract_balanced_section(text, object_start, "{", "}")
    entry_pattern = re.compile(r"\[SpeciesId\.([A-Z0-9_]+)\]\s*:\s*\[")
    evolution_pattern = re.compile(r"new\s+(?:SpeciesEvolution|SpeciesFormEvolution)\(\s*SpeciesId\.([A-Z0-9_]+)")
    prevolutions: dict[int, int] = {}
    cursor = 0

    while True:
        match = entry_pattern.search(object_body, cursor)
        if match is None:
            break

        base_name = match.group(1)
        base_dex = enum_values.get(base_name)
        array_start = match.end() - 1
        array_body, array_end = extract_balanced_section(object_body, array_start, "[", "]")

        if base_dex is not None:
            for evo_name in evolution_pattern.findall(array_body):
                evo_dex = enum_values.get(evo_name)
                if evo_dex is not None:
                    prevolutions[evo_dex] = base_dex

        cursor = array_end + 1

    return prevolutions


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def format_dex_label(raw_value: str | int) -> str:
    return f"{int(raw_value):03d}"


def normalize_species_lookup(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def art_variant_suffix(art_name: str) -> str:
    if art_name == "full-art":
        return ""
    if art_name.startswith("full-art"):
        return art_name[len("full-art"):]
    return f"-{art_name}"


def sidecar_path(meta_dir: Path, base_name: str, extension: str, art_name: str) -> Path:
    suffix = art_variant_suffix(art_name)
    filename = f"{base_name}{suffix}{extension}" if suffix else f"{base_name}{extension}"
    return meta_dir / filename


def find_art_path(meta_dir: Path, art_name: str) -> Path | None:
    for extension in (".jpg", ".png", ".webp", ".jpeg"):
        candidate = sidecar_path(meta_dir, art_name, extension, "full-art")
        if candidate.exists():
            return candidate
    return None


def load_curated_card_overrides() -> dict[int, dict[str, Any]]:
    rows: list[dict[str, str]] = []
    for path in DEX_COPY_PATHS:
        with path.open(encoding="utf-8") as handle:
            rows.extend(list(csv.DictReader(handle, delimiter="\t")))

    row_by_species = {
        normalize_species_lookup(row["speciesKey"]): row
        for row in rows
    }
    prompt_entries = json.loads(PROMPTS_PATH.read_text(encoding="utf-8"))["species"]
    overrides: dict[int, dict[str, Any]] = {}
    for entry in prompt_entries:
        row = row_by_species.get(normalize_species_lookup(entry["original"]))
        if not row:
            continue
        overrides[int(entry["dex"])] = {
            "name": entry["mogmon"],
            "description": row["characterDescription"],
            "flavorText": row["cardDescription"],
            "stageLabel": row["stageLabel"],
            "familyRoot": row["familyRoot"],
        }
    return overrides


def load_tcg_evolution_overrides(
    path: Path = TCG_ROOT / "evolution-paths.tsv",
) -> dict[int, CardEvolutionOverride]:
    if not path.exists():
        return {}

    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))

    card_to_source: dict[str, int] = {}
    for row in rows:
        raw_card = (row.get("card") or row.get("dex") or "").strip()
        raw_source = (row.get("sourceDex") or raw_card).strip()
        if not raw_card or not raw_source:
            continue
        card_to_source[format_dex_label(raw_card)] = int(raw_source)

    overrides: dict[int, CardEvolutionOverride] = {}
    for row in rows:
        raw_card = (row.get("card") or row.get("dex") or "").strip()
        raw_source = (row.get("sourceDex") or raw_card).strip()
        if not raw_card or not raw_source:
            continue

        card_label = format_dex_label(raw_card)
        source_dex = int(raw_source)
        raw_prev_source = (row.get("evolvesFromDex") or "").strip()
        raw_prev_card = (row.get("evolvesFromCard") or row.get("previousCard") or "").strip()
        if raw_prev_source:
            prev_source_dex = int(raw_prev_source)
        elif raw_prev_card:
            prev_source_dex = card_to_source[format_dex_label(raw_prev_card)]
        else:
            prev_source_dex = None

        overrides[source_dex] = CardEvolutionOverride(
            source_dex=source_dex,
            card_label=card_label,
            prev_source_dex=prev_source_dex,
            stage_label=(row.get("stageLabel") or "").strip() or None,
        )

    return overrides


def load_card_specs(source_dir: Path, art_name: str, curated_overrides: dict[int, dict[str, Any]]) -> list[CardSpec]:
    specs: list[CardSpec] = []
    for folder in sorted(source_dir.iterdir()):
        if not folder.is_dir():
            continue
        dex_label = folder.name
        if not dex_label.isdigit():
            continue
        art_path = find_art_path(folder, art_name)
        if art_path is None:
            continue
        meta_path = sidecar_path(folder, "meta", ".json", art_name)
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
        else:
            fallback_meta = folder / "meta.json"
            meta = json.loads(fallback_meta.read_text()) if fallback_meta.exists() else {}
        dex = int(dex_label)
        override = curated_overrides.get(dex)
        if override:
            meta["name"] = override["name"]
            meta["description"] = override["description"]
            meta["flavorText"] = override["flavorText"]
            meta["stageLabel"] = override["stageLabel"]
            meta["familyRoot"] = override["familyRoot"]
        specs.append(
            CardSpec(
                dex=dex,
                dex_label=dex_label,
                meta_dir=folder,
                meta=meta,
                art_path=art_path,
                stage_label=meta.get("stageLabel", "solo"),
                family_id="",
            )
        )
    return specs


def apply_tcg_evolution_overrides(
    specs: list[CardSpec],
    evolution_overrides: dict[int, CardEvolutionOverride],
) -> None:
    if not evolution_overrides:
        return

    spec_by_dex = {spec.dex: spec for spec in specs}
    overrides = {
        dex: override
        for dex, override in evolution_overrides.items()
        if dex in spec_by_dex
    }
    if not overrides:
        return

    def root_source_dex_for(dex: int, seen: set[int] | None = None) -> int:
        seen = seen or set()
        if dex in seen:
            return dex
        seen.add(dex)
        previous_dex = overrides[dex].prev_source_dex
        if previous_dex is None or previous_dex not in overrides or previous_dex not in spec_by_dex:
            return dex
        return root_source_dex_for(previous_dex, seen)

    def stage_number_for(dex: int, seen: set[int] | None = None) -> int:
        seen = seen or set()
        if dex in seen:
            return 1
        seen.add(dex)
        previous_dex = overrides[dex].prev_source_dex
        if previous_dex is None or previous_dex not in overrides or previous_dex not in spec_by_dex:
            return 1
        return stage_number_for(previous_dex, seen) + 1

    for dex, override in overrides.items():
        spec = spec_by_dex[dex]
        spec.dex_label = override.card_label
        if override.stage_label:
            spec.stage_label = override.stage_label
            spec.meta["stageLabel"] = override.stage_label
        spec.prev_card_dex = override.prev_source_dex if override.prev_source_dex in spec_by_dex else None
        spec.stage_number = stage_number_for(dex)
        spec.family_index = spec.stage_number - 1
        root_source_dex = root_source_dex_for(dex)
        root_label = overrides[root_source_dex].card_label
        spec.family_id = f"solo-{override.card_label}" if spec.stage_label == "solo" else f"family-{root_label}"

    family_depth_by_id: defaultdict[str, int] = defaultdict(int)
    for dex in overrides:
        spec = spec_by_dex[dex]
        family_depth_by_id[spec.family_id] = max(family_depth_by_id[spec.family_id], spec.stage_number)

    for dex in overrides:
        spec = spec_by_dex[dex]
        spec.family_size = family_depth_by_id[spec.family_id]


def assign_families(
    specs: list[CardSpec],
    prevolutions: dict[int, int],
    evolution_overrides: dict[int, CardEvolutionOverride],
) -> None:
    spec_by_dex = {spec.dex: spec for spec in specs}
    family_depth_by_root: defaultdict[int, int] = defaultdict(int)
    root_by_dex: dict[int, int] = {}

    for spec in specs:
        lineage: list[int] = []
        seen: set[int] = set()
        current_dex: int | None = spec.dex

        while current_dex is not None and current_dex not in seen:
            lineage.append(current_dex)
            seen.add(current_dex)
            current_dex = prevolutions.get(current_dex)

        lineage.reverse()
        available_lineage = [dex for dex in lineage if dex in spec_by_dex]
        if not available_lineage or available_lineage[-1] != spec.dex:
            available_lineage.append(spec.dex)

        root_dex = lineage[0] if lineage else spec.dex
        stage_number = len(available_lineage)

        spec.family_id = f"family-{root_dex:04d}"
        spec.family_index = stage_number - 1
        spec.family_size = stage_number
        spec.stage_number = stage_number
        spec.prev_card_dex = available_lineage[-2] if stage_number > 1 else None

        root_by_dex[spec.dex] = root_dex
        family_depth_by_root[root_dex] = max(family_depth_by_root[root_dex], stage_number)

    for spec in specs:
        spec.family_size = family_depth_by_root[root_by_dex[spec.dex]]

    # Curated solo brainrots should not inherit a Pokemon evolution chain on the
    # card surface just because their slot happens to evolve in canon.
    for spec in specs:
        if spec.stage_label == "solo":
            spec.family_id = f"solo-{spec.dex:04d}"
            spec.family_index = 0
            spec.family_size = 1
            spec.stage_number = 1
            spec.prev_card_dex = None

    # Some curated branch families intentionally span non-native Pokemon slots.
    # Respect their hand-authored family layout on cards instead of the Pokemon
    # evolution graph.
    for family_root, layout in CUSTOM_CARD_FAMILY_LAYOUTS.items():
        family_specs = [spec for spec in specs if spec.meta.get("familyRoot") == family_root and spec.dex in layout]
        if not family_specs:
            continue
        family_id = f"family-{family_root}"
        for spec in family_specs:
            override = layout[spec.dex]
            spec.family_id = family_id
            spec.family_index = override["family_index"]
            spec.family_size = override["family_size"]
            spec.stage_number = override["stage_number"]
            spec.prev_card_dex = override["prev_card_dex"]

    # Premium dragon-brainrot cards should present as standalone mythics on the
    # card surface, even if their source Pokemon slot sits in an evolution line.
    for spec in specs:
        if spec.dex in DRAGON_MYTHIC_DEXES:
            spec.family_id = f"mythic-standalone-{spec.dex:04d}"
            spec.family_index = 0
            spec.family_size = 1
            spec.stage_number = 1
            spec.prev_card_dex = None

    apply_tcg_evolution_overrides(specs, evolution_overrides)


def determine_rarity(spec: CardSpec, species: SpeciesInfo) -> str:
    if spec.dex in DRAGON_MYTHIC_DEXES:
        return "mythic"
    override = RARITY_OVERRIDES.get(spec.dex)
    if override is not None:
        return override
    if species.mythical:
        return "mythic"
    if spec.stage_label in TOP_STAGE_LABELS and species.base_total >= 600:
        return "mythic"
    if species.legendary:
        return "legendary"
    if species.base_total >= 560:
        return "legendary"
    if spec.stage_label in TOP_STAGE_LABELS and species.base_total >= 540:
        return "legendary"
    if species.sub_legendary:
        return "epic"
    if species.base_total >= 520:
        return "epic"
    if spec.stage_label in TOP_STAGE_LABELS and species.base_total >= 480:
        return "epic"
    if spec.stage_label in {"final", "branch-final"}:
        return "rare"
    if spec.stage_label in {"mid", "solo"} and species.base_total >= 400:
        return "rare"
    if species.base_total >= 440:
        return "rare"
    return "common"


def build_alpha_mask(mask_path: Path) -> Image.Image:
    return Image.open(mask_path).convert("RGBA").getchannel("A")


def place_mask_on_card(mask: Image.Image) -> Image.Image:
    if mask.size == CARD_SIZE:
        return mask.copy()
    card_mask = Image.new("L", CARD_SIZE, 0)
    card_mask.paste(mask, MASK_OFFSET)
    return card_mask


def fit_cover(image: Image.Image, size: tuple[int, int], centering: tuple[float, float] = (0.5, 0.44)) -> Image.Image:
    return ImageOps.fit(image.convert("RGBA"), size, method=RESAMPLE, centering=centering)


def render_art_layer(art_path: Path, card_mask: Image.Image) -> Image.Image:
    art = fit_cover(Image.open(art_path), CARD_SIZE)
    art.putalpha(card_mask)
    return art


def build_overlay() -> Image.Image:
    overlay = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(TOP_GRADIENT_HEIGHT):
        alpha = round(150 * (1 - y / max(1, TOP_GRADIENT_HEIGHT - 1)))
        draw.rectangle((0, y, CARD_SIZE[0], y + 1), fill=(0, 0, 0, alpha))
    bottom_start = CARD_SIZE[1] - BOTTOM_GRADIENT_HEIGHT
    for idx, y in enumerate(range(bottom_start, CARD_SIZE[1])):
        alpha = round(175 * (idx / max(1, BOTTOM_GRADIENT_HEIGHT - 1)))
        draw.rectangle((0, y, CARD_SIZE[0], y + 1), fill=(0, 0, 0, alpha))
    return overlay.filter(ImageFilter.GaussianBlur(6))


def dominant_type_color(type_key: str) -> tuple[int, int, int, int]:
    return ImageColor.getcolor(TYPE_RING_COLORS.get(type_key, "#A3B3C1"), "RGBA")


def circle_mask(size: int) -> Image.Image:
    scale = 4
    large = Image.new("L", (size * scale, size * scale), 0)
    draw = ImageDraw.Draw(large)
    draw.ellipse((0, 0, size * scale - 1, size * scale - 1), fill=255)
    return large.resize((size, size), RESAMPLE)


def draw_text_with_shadow(
    canvas: Image.Image,
    position: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: str,
    stroke_fill: str | None = None,
    stroke_width: int = 0,
    shadow_offset: tuple[int, int] = (0, 3),
    shadow_fill: tuple[int, int, int, int] = (0, 0, 0, 140),
    anchor: str = "la",
) -> None:
    draw = ImageDraw.Draw(canvas)
    shadow_xy = (position[0] + shadow_offset[0], position[1] + shadow_offset[1])
    draw.text(shadow_xy, text, font=font, fill=shadow_fill, anchor=anchor)
    draw.text(
        position,
        text,
        font=font,
        fill=fill,
        stroke_width=stroke_width,
        stroke_fill=stroke_fill,
        anchor=anchor,
    )


def fit_single_line_font(
    text: str,
    max_width: int,
    max_size: int,
    min_size: int,
    font_index: int,
    stroke_width: int = 0,
) -> ImageFont.FreeTypeFont:
    probe = Image.new("RGBA", (10, 10))
    draw = ImageDraw.Draw(probe)
    for size in range(max_size, min_size - 1, -1):
        font = load_font(size, font_index)
        bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
        if bbox[2] - bbox[0] <= max_width:
            return font
    return load_font(min_size, font_index)


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        bbox = draw.textbbox((0, 0), candidate, font=font, stroke_width=2)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def fit_paragraph(
    text: str,
    max_width: int,
    max_height: int,
    max_lines: int,
    max_size: int,
    min_size: int,
    font_index: int,
    line_gap: int = 4,
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    probe = Image.new("RGBA", (10, 10))
    draw = ImageDraw.Draw(probe)
    for size in range(max_size, min_size - 1, -1):
        font = load_font(size, font_index)
        lines = wrap_text(text, font, max_width, draw)
        if len(lines) > max_lines:
            continue
        line_height = font.getbbox("Ag")[3] - font.getbbox("Ag")[1]
        height = len(lines) * line_height + max(0, len(lines) - 1) * line_gap
        if height <= max_height:
            return font, lines
    font = load_font(min_size, font_index)
    lines = wrap_text(text, font, max_width, draw)[:max_lines]
    if len(lines) == max_lines:
        while True:
            bbox = draw.textbbox((0, 0), lines[-1] + "…", font=font, stroke_width=2)
            if bbox[2] - bbox[0] <= max_width or len(lines[-1]) <= 1:
                lines[-1] = lines[-1] + "…"
                break
            lines[-1] = lines[-1][:-1].rstrip()
    return font, lines


def render_evolution_thumbnail(
    current_spec: CardSpec,
    previous_spec: CardSpec | None,
    all_specs: dict[int, CardSpec],
) -> Image.Image | None:
    if previous_spec is None:
        return None
    outer = Image.new("RGBA", (EVOLUTION_ART_SIZE, EVOLUTION_ART_SIZE), (0, 0, 0, 0))
    type_color = dominant_type_color(current_spec.type_key)
    ring = Image.new("RGBA", (EVOLUTION_ART_SIZE, EVOLUTION_ART_SIZE), type_color)
    ring.putalpha(circle_mask(EVOLUTION_ART_SIZE))
    outer.alpha_composite(ring)

    inner = fit_cover(Image.open(previous_spec.art_path), (EVOLUTION_INNER_SIZE, EVOLUTION_INNER_SIZE), centering=(0.5, 0.38))
    inner.putalpha(circle_mask(EVOLUTION_INNER_SIZE))
    inset = (EVOLUTION_ART_SIZE - EVOLUTION_INNER_SIZE) // 2
    outer.alpha_composite(inner, (inset, inset))

    outline = Image.new("RGBA", outer.size, (0, 0, 0, 0))
    outline_draw = ImageDraw.Draw(outline)
    outline_draw.ellipse((2, 2, EVOLUTION_ART_SIZE - 3, EVOLUTION_ART_SIZE - 3), outline=(255, 255, 255, 235), width=4)
    outer.alpha_composite(outline)
    outer.putalpha(ImageChops.multiply(outer.getchannel("A"), circle_mask(EVOLUTION_ART_SIZE)))
    return outer


def paste_centered(canvas: Image.Image, image: Image.Image, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = box
    dest_x = x0 + (x1 - x0 - image.width) // 2
    dest_y = y0 + (y1 - y0 - image.height) // 2
    canvas.alpha_composite(image, (dest_x, dest_y))


def display_card_title(spec: CardSpec) -> str:
    rarity_letter = spec.rarity[:1].upper() if spec.rarity else "C"
    return f"{spec.meta['name']} ({rarity_letter})"


def render_card(
    spec: CardSpec,
    all_specs: dict[int, CardSpec],
    species_map: dict[int, SpeciesInfo],
    border_dir: Path,
    icon_dir: Path,
    card_mask: Image.Image,
) -> Image.Image:
    species = species_map[spec.dex]
    spec.type_key = species.type1
    spec.rarity = determine_rarity(spec, species)

    canvas = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))
    canvas.alpha_composite(render_art_layer(spec.art_path, card_mask))
    canvas.alpha_composite(build_overlay())

    border = Image.open(border_dir / f"{spec.rarity}.png").convert("RGBA")
    canvas.alpha_composite(border)

    stage_font = load_font(32, 3)
    draw_text_with_shadow(
        canvas,
        STAGE_POS,
        f"STAGE {spec.stage_number}",
        stage_font,
        fill=STAGE_COLORS.get(spec.rarity, STAGE_COLORS["common"]),
        stroke_fill="#BFE8FF",
        stroke_width=1,
    )

    type_icon = Image.open(icon_dir / f"{spec.type_key}.png").convert("RGBA").resize((84, 84), RESAMPLE)
    type_shadow = type_icon.copy().filter(ImageFilter.GaussianBlur(8))
    shadow_canvas = Image.new("RGBA", type_icon.size, (0, 0, 0, 0))
    shadow_canvas.alpha_composite(type_shadow, (0, 6))
    shadow_canvas.alpha_composite(type_icon)
    paste_centered(canvas, shadow_canvas, TYPE_ICON_BOX)

    display_title = display_card_title(spec)
    title_font = fit_single_line_font(display_title, TITLE_AREA[2] - TITLE_AREA[0], 48, 24, 1, stroke_width=2)
    draw_text_with_shadow(
        canvas,
        (TITLE_AREA[0], TITLE_AREA[1]),
        display_title,
        title_font,
        fill=TITLE_FILL,
        stroke_fill=TITLE_STROKE,
        stroke_width=2,
    )

    previous_spec = all_specs.get(spec.prev_card_dex) if spec.prev_card_dex is not None else None
    if previous_spec is not None:
        badge = Image.open(border_dir.parent / "icons" / "from-stage.png").convert("RGBA").resize(EVOLUTION_BADGE_SIZE, RESAMPLE)
        badge_shadow = badge.copy().filter(ImageFilter.GaussianBlur(8))
        badge_canvas = Image.new("RGBA", badge.size, (0, 0, 0, 0))
        badge_canvas.alpha_composite(badge_shadow, (0, 4))
        badge_canvas.alpha_composite(badge)
        badge_x = EVOLUTION_ART_POS[0] + EVOLUTION_BADGE_POS_DELTA[0]
        badge_y = EVOLUTION_ART_POS[1] + EVOLUTION_BADGE_POS_DELTA[1]
        canvas.alpha_composite(badge_canvas, (badge_x, badge_y))

        evolution_font = load_font(24, 5)
        evolution_text = f"FROM STAGE {previous_spec.stage_number}"
        probe = ImageDraw.Draw(canvas)
        text_bbox = probe.textbbox((0, 0), evolution_text, font=evolution_font, stroke_width=1)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        overlap = max(0, (EVOLUTION_ART_POS[0] + EVOLUTION_ART_SIZE) - badge_x)
        visible_width = max(1, badge.width - overlap - 10)
        text_x = badge_x + overlap + max(0, (visible_width - text_width) // 2)
        text_y = badge_y + (badge.height - text_height) // 2 - 1
        draw_text_with_shadow(
            canvas,
            (text_x, text_y),
            evolution_text,
            evolution_font,
            fill=EVOLUTION_TEXT_COLOR,
            stroke_fill="#F1F1F1",
            stroke_width=1,
        )

        evolution_thumb = render_evolution_thumbnail(spec, previous_spec, all_specs)
        if evolution_thumb is not None:
            canvas.alpha_composite(evolution_thumb, EVOLUTION_ART_POS)

    flavor = spec.meta.get("flavorText") or spec.meta.get("description") or spec.meta["name"]
    description_font, lines = fit_paragraph(
        flavor,
        DESCRIPTION_BOX[2] - DESCRIPTION_BOX[0],
        DESCRIPTION_BOX[3] - DESCRIPTION_BOX[1],
        max_lines=2,
        max_size=28,
        min_size=18,
        font_index=4,
        line_gap=4,
    )
    desc_draw = ImageDraw.Draw(canvas)
    line_height = description_font.getbbox("Ag")[3] - description_font.getbbox("Ag")[1]
    total_height = len(lines) * line_height + max(0, len(lines) - 1) * 4
    start_y = DESCRIPTION_BOX[1] + ((DESCRIPTION_BOX[3] - DESCRIPTION_BOX[1]) - total_height) // 2
    for idx, line in enumerate(lines):
        y = start_y + idx * (line_height + 4)
        bbox = desc_draw.textbbox((0, 0), line, font=description_font, stroke_width=2)
        x = DESCRIPTION_BOX[0] + ((DESCRIPTION_BOX[2] - DESCRIPTION_BOX[0]) - (bbox[2] - bbox[0])) // 2
        draw_text_with_shadow(
            canvas,
            (x, y),
            line,
            description_font,
            fill=DESCRIPTION_FILL,
            stroke_fill=DESCRIPTION_STROKE,
            stroke_width=2,
            shadow_offset=(0, 2),
            shadow_fill=(0, 0, 0, 150),
        )

    canvas.putalpha(ImageChops.multiply(canvas.getchannel("A"), card_mask))
    return canvas


def build_preview_grid(rendered: list[tuple[CardSpec, Path]], out_path: Path) -> None:
    if not rendered:
        return
    preview_size = (192, 265)
    cols = 4
    rows = math.ceil(len(rendered) / cols)
    margin = 20
    label_height = 26
    canvas = Image.new(
        "RGBA",
        (cols * (preview_size[0] + margin) + margin, rows * (preview_size[1] + label_height + margin) + margin),
        (18, 21, 30, 255),
    )
    draw = ImageDraw.Draw(canvas)
    label_font = load_font(18, 4)
    for idx, (spec, path) in enumerate(rendered):
        card = Image.open(path).convert("RGBA").resize(preview_size, RESAMPLE)
        col = idx % cols
        row = idx // cols
        x = margin + col * (preview_size[0] + margin)
        y = margin + row * (preview_size[1] + label_height + margin)
        canvas.alpha_composite(card, (x, y))
        label = f"{spec.dex_label}  {spec.meta['name']}"
        draw.text((x, y + preview_size[1] + 4), label, font=label_font, fill=(232, 236, 244, 255))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path)


def prepare_grouped_output_dir(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for rarity in RARITY_ORDER:
        rarity_dir = out_dir / rarity
        if rarity_dir.exists():
            shutil.rmtree(rarity_dir)
        rarity_dir.mkdir(parents=True, exist_ok=True)
    for card_path in out_dir.glob("*.png"):
        if card_path.name != "preview-grid.png":
            card_path.unlink()


def main() -> None:
    args = parse_args()
    source_dir = args.source_dir
    border_dir = args.border_dir
    icon_dir = args.icon_dir
    out_dir = args.out_dir

    enum_values = parse_species_enum(Path("src/enums/species-id.ts"))
    species_map = parse_species_info(enum_values, Path("src/data/balance/pokemon-species.ts"))
    prevolutions = parse_pokemon_prevolutions(enum_values, Path("src/data/balance/pokemon-evolutions.ts"))
    curated_overrides = load_curated_card_overrides()
    evolution_overrides = load_tcg_evolution_overrides()
    all_specs_list = load_card_specs(source_dir, args.art_name, curated_overrides)
    assign_families(all_specs_list, prevolutions, evolution_overrides)
    all_specs = {spec.dex: spec for spec in all_specs_list}

    if args.dex:
        selected = set(args.dex)
        specs = [
            spec
            for spec in all_specs_list
            if spec.dex in selected or int(spec.dex_label) in selected
        ]
    else:
        specs = all_specs_list

    alpha_mask = build_alpha_mask(border_dir / "mask.png")
    card_mask = place_mask_on_card(alpha_mask)

    rendered: list[tuple[CardSpec, Path]] = []
    manifest: list[dict[str, Any]] = []

    if out_dir is not None and args.group_by_rarity:
        prepare_grouped_output_dir(out_dir)

    for spec in specs:
        if spec.dex not in species_map:
            raise KeyError(f"Could not find Pokemon species metadata for dex {spec.dex}")
        image = render_card(spec, all_specs, species_map, border_dir, icon_dir, card_mask)
        if out_dir is not None:
            target_dir = out_dir / spec.rarity if args.group_by_rarity else out_dir
            target_dir.mkdir(parents=True, exist_ok=True)
            out_path = target_dir / f"{spec.dex_label}-{slugify(spec.meta['name'])}.png"
        else:
            out_path = spec.meta_dir / args.output_name
        image.save(out_path)
        rendered.append((spec, out_path))
        manifest.append(
            {
                "sequence": int(spec.dex_label),
                "card": int(spec.dex_label),
                "dex": spec.dex,
                "sourceDex": spec.dex,
                "name": spec.meta["name"],
                "output": out_path.as_posix(),
                "type": spec.type_key,
                "rarity": spec.rarity,
                "stageLabel": spec.stage_label,
                "stageNumber": spec.stage_number,
                "previousDex": spec.prev_card_dex,
                "previousCard": int(all_specs[spec.prev_card_dex].dex_label) if spec.prev_card_dex else None,
                "familyId": spec.family_id,
                "familyIndex": spec.family_index,
                "familySize": spec.family_size,
            }
        )

    manifest_path = (out_dir / "manifest.json") if out_dir is not None else (source_dir / "card-manifest.json")
    preview_path = (out_dir / "preview-grid.png") if out_dir is not None else (source_dir / "card-preview-grid.png")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    build_preview_grid(rendered, preview_path)


if __name__ == "__main__":
    main()
