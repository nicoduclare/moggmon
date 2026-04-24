#!/usr/bin/env python3

import argparse
import csv
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROMPTS_PATH = Path(
    os.environ.get("MOGGER_MON_PROMPTS_FILE", ROOT / "output/private-generation-prompts/mogger-mon-prompts.json")
)
DEX_COPY_PATHS = [
    ROOT / "output/private-generation-prompts/brainrot-wiki/gen1-dex-copy.tsv",
    ROOT / "output/private-generation-prompts/brainrot-wiki/reference2-dex-supplement.tsv",
]
GENERATOR_PATH = ROOT / "scripts/generate_gemini_example_tcg.py"
DEFAULT_ORIGINAL_DIR = ROOT / "output/private-generation-prompts/mogger-mon-tcg/references2/original"
DEFAULT_STYLE_DIR = ROOT / "output/private-generation-prompts/mogger-mon-tcg/references2/pokemon-style"
DEFAULT_OUT_BASE = ROOT / "output/private-generation-prompts/mogger-mon-tcg"
DEFAULT_STYLE_LESSON_IMAGE = (
    ROOT / "output/private-generation-prompts/mogger-mon-tcg/references2/style-lesson/reference-style.jpg"
)
DIRECT_STYLE_RENDER_MODE = "use-style-reference-as-full-art"
PROMPT_ONLY_RENDER_MODE = "generate-from-prompt-only"
MASK_SCRIPT_PATH = ROOT / "scripts/generate_tcg_holo_masks.swift"
FAMILY_REFERENCE_SLUG_OVERRIDES = {
    "bombardino-flight": "bombardiro-crocodilo",
}

DEX_DESCRIPTION_APPEND = {
    2: "Important anatomy: this form is anatomically one-legged. Show exactly one complete leg ending in exactly one foot attached to the body. Do not depict a second foot, a second leg, a mirrored partner limb, a stump, or an implied hidden opposite foot. The opposite side must not become a second support column. It should taper into hanging roots, robe mass, or foliage that stays visibly off the ground and does not read as another leg or planted limb.",
}

STAGE_DESCRIPTION_APPEND = {
    "base": "Only include the early-stage anatomy explicitly described here. Do not add later-stage limbs, heads, armor, ornament, or full-form mass that this stage has not earned yet.",
    "mid": "Treat this as a real transition stage. Add the stage-specific upgrade described here, but do not skip ahead to the full final-form anatomy. Keep it visibly unfinished relative to the last stage, as a bridge form rather than an almost-complete final.",
    "final": "This is the completed family form. It should include the full anatomy and silhouette complexity described here.",
    "branch-final": "This is a completed end-route form. It should feel fully realized and distinct for its branch.",
}


def slugify_title(value):
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def normalize_species_lookup(value):
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def art_variant_suffix(art_name):
    if art_name == "full-art":
        return ""
    if art_name.startswith("full-art"):
        return art_name[len("full-art"):]
    return f"-{art_name}"


def sidecar_path(out_dir, base_name, extension, art_name):
    suffix = art_variant_suffix(art_name)
    filename = f"{base_name}{suffix}{extension}" if suffix else f"{base_name}{extension}"
    return out_dir / filename


def art_path_for_variant(out_dir, art_name):
    for suffix in (".jpg", ".png", ".webp", ".jpeg"):
        candidate = sidecar_path(out_dir, art_name, suffix, "full-art")
        if candidate.exists():
            return candidate
    return None


def load_prompt_entries():
    data = json.loads(PROMPTS_PATH.read_text(encoding="utf-8"))
    species = data["species"] if isinstance(data, dict) else data
    return {int(entry["dex"]): entry for entry in species}


def load_dex_rows():
    rows = []
    for path in DEX_COPY_PATHS:
        with path.open(encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            rows.extend(reader)
    return rows


def prompt_to_description(prompt_entry):
    description = prompt_entry["prompt"].strip()
    prefix = re.compile(
        r"^Redesign this pixel-art sprite sheet\.\s*The creature is\s*"
        + re.escape(prompt_entry["mogmon"])
        + r":\s*",
        re.IGNORECASE,
    )
    description = prefix.sub("", description)
    description = re.sub(
        r"\s*Keep the exact same sprite sheet grid layout, frame count, animation poses, pixel art style, and transparent background\.\s*$",
        "",
        description,
        flags=re.IGNORECASE,
    )
    return description.strip()


def prompt_to_flavor_text(prompt_entry):
    return (
        f'The formula held: {prompt_entry["formula"]}. '
        f'{prompt_entry["mogmon"]} showed up battle-ready anyway, as if this had always been a sensible idea.'
    )


def synthesize_prompt_only_rows(prompts_by_dex, rows):
    existing_dexes = {int(row["dex"]) for row in rows if row.get("dex")}
    synthetic_rows = []
    for dex, prompt_entry in prompts_by_dex.items():
        if dex in existing_dexes:
            continue
        synthetic_rows.append(
            {
                "familyRoot": slugify_title(prompt_entry["mogmon"]),
                "canonicalBrainrot": prompt_entry["mogmon"],
                "speciesKey": slugify_title(prompt_entry["original"]),
                "generatedName": prompt_entry["mogmon"].lower(),
                "stageLabel": "solo",
                "renderMode": PROMPT_ONLY_RENDER_MODE,
                "characterDescription": prompt_to_description(prompt_entry),
                "cardDescription": prompt_to_flavor_text(prompt_entry),
                "dex": str(dex),
            }
        )
    rows.extend(synthetic_rows)
    return rows


def build_rows_by_family(rows):
    rows_by_family = {}
    for row in rows:
        rows_by_family.setdefault(row["familyRoot"], []).append(row)
    return rows_by_family


def stage_note(stage_label):
    mapping = {
        "base": "Base-stage art. Keep it smaller, cuter, and more compact than later evolutions. This should feel like the first readable version of the family, with the simplest silhouette, the fewest exaggerated features, and the softest overall attitude. Do not borrow later-stage anatomy just because it appears in the reference image.",
        "mid": "Middle-evolution art. Make it more mature, stronger, and more battle-ready than the base form. This should feel like a real transition, not just a size increase: push the silhouette, add one new secondary shape or anatomical idea, and make the stance clearly more confident. Keep it visibly incomplete compared with the final evolution: roughly two-thirds evolved, not nearly finished. Reserve the family's full payoff silhouette, ultimate ornament, apex weapon scale, and boss-level presence for the final stage only.",
        "final": "Final-evolution art. Make it larger, more dramatic, and more imposing while keeping the same identity. This should feel like the culmination of the family: full silhouette complexity, full ornamentation, stronger contrast, and a much heavier presence in the scene.",
        "branch-final": "Advanced final-form art. Treat it like a fully powered end-stage creature with strong presence, a clear final-form silhouette, and dramatic scene impact.",
    }
    return mapping.get(stage_label, "Keep it card-art ready and faithful to this evolution stage.")


def camera_note(stage_label):
    mapping = {
        "base": "Show the whole creature in a dramatic full-art Pokemon card scene with clear silhouette, a youthful action pose, a smaller-scale environment, and room around the body for a card crop. The scene should feel agile, curious, and early-stage rather than overpowering.",
        "mid": "Show the whole creature in a dramatic full-art Pokemon card scene with clear silhouette, a confident advancing or striking action pose, a richer character-specific background, and room around the body for a card crop. The scene should feel like a meaningful step up from the base form, but still local and transitional rather than legendary or world-shaking.",
        "final": "Show the whole creature in a dramatic full-art Pokemon card scene with clear silhouette, a dominant high-impact action pose, a large environment reacting to the creature, and room around the body for a card crop. The scene should feel like the final and most powerful form in the family.",
        "branch-final": "Show the whole creature in a dramatic full-art Pokemon card scene with a commanding final-form pose, a distinct environment, and strong visual scale.",
    }
    return mapping.get(
        stage_label,
        "Show the whole creature in a dramatic full-art Pokemon card scene with clear silhouette, a distinctive action pose, a varied character-specific background, and room around the body for a card crop.",
    )


def description_for_row(dex, row):
    description = row["characterDescription"].strip()
    stage_extra = STAGE_DESCRIPTION_APPEND.get(row["stageLabel"])
    if stage_extra:
        description = f"{description} {stage_extra}"
    extra = DEX_DESCRIPTION_APPEND.get(dex)
    if extra:
        description = f"{description} {extra}"
    return description


def family_contrast_note(row, rows_by_family):
    if row["stageLabel"] != "mid":
        return ""
    family_rows = rows_by_family.get(row["familyRoot"], [])
    has_base = any(item["stageLabel"] == "base" for item in family_rows)
    final_row = next(
        (item for item in family_rows if item["stageLabel"] in {"final", "branch-final"}),
        None,
    )
    if not has_base or not final_row or len(family_rows) < 3:
        return ""
    final_summary = final_row["characterDescription"].strip()
    return (
        "This is the middle member of a three-stage family. It must visibly hold back at least one major structural payoff from the final form. "
        f"The final form later becomes: {final_summary} "
        "In this middle stage, keep one obvious final trait missing, reduced, or only half-formed so the progression reads clearly at a glance. "
        "Typical ways to do this are one fewer arm, leg, eye, head, wing, horn cluster, tentacle set, support limb, or one incomplete weaponized limb, whichever best fits the family."
    )


def stage_rank(stage_label):
    return {
        "final": 0,
        "branch-final": 1,
        "mid": 2,
        "base": 3,
        "solo": 4,
    }.get(stage_label, 99)


def reference_slug_candidates(row, rows_by_family):
    candidates = []
    seen = set()

    def push(value):
        if not value:
            return
        slug = slugify_title(value)
        if slug and slug not in seen:
            seen.add(slug)
            candidates.append(slug)

    push(row["canonicalBrainrot"])
    family_rows = sorted(rows_by_family.get(row["familyRoot"], []), key=lambda item: stage_rank(item["stageLabel"]))
    for family_row in family_rows:
        push(family_row["canonicalBrainrot"])
    return candidates


def expected_metadata(dex, row, prompt_entry, rows_by_family, effective_render_mode, art_name):
    return {
        "artName": art_name,
        "name": prompt_entry["mogmon"],
        "description": description_for_row(dex, row),
        "flavorText": row["cardDescription"],
        "stageNote": stage_note(row["stageLabel"]),
        "stageLabel": row["stageLabel"],
        "familyContrastNote": family_contrast_note(row, rows_by_family),
        "renderMode": effective_render_mode,
    }


def stale_output_reason(out_dir, dex, row, prompt_entry, rows_by_family, effective_render_mode, art_name):
    full_art = art_path_for_variant(out_dir, art_name)
    if not full_art:
        return f"missing {art_name} image"

    meta_path = sidecar_path(out_dir, "meta", ".json", art_name)
    if not meta_path.exists():
        return f"missing metadata for {art_name}"

    try:
        existing = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "invalid meta.json"

    expected = expected_metadata(dex, row, prompt_entry, rows_by_family, effective_render_mode, art_name)
    for key, expected_value in expected.items():
        actual_value = existing.get(key, "")
        if actual_value != expected_value:
            return f"stale {key}: expected {expected_value!r}, found {actual_value!r}"

    return ""


def find_original_reference(original_dir, slug):
    for suffix in (".webp", ".png", ".jpg", ".jpeg"):
        candidate = original_dir / f"{slug}{suffix}"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Missing original reference for slug '{slug}' in {original_dir}")


def find_style_reference(style_dir, slug):
    folder = style_dir / slug
    if not folder.exists():
        raise FileNotFoundError(f"Missing style folder for slug '{slug}' in {style_dir}")
    for suffix in (".jpg", ".png", ".webp", ".jpeg"):
        candidate = folder / f"pokemon-style{suffix}"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Missing pokemon-style image for slug '{slug}' in {folder}")


def find_style_lesson_image(path):
    if not path.exists():
        raise FileNotFoundError(f"Missing style lesson image: {path}")
    return path


def try_find_original_reference(original_dir, slug):
    try:
        return find_original_reference(original_dir, slug)
    except FileNotFoundError:
        return None


def try_find_style_reference(style_dir, slug):
    try:
        return find_style_reference(style_dir, slug)
    except FileNotFoundError:
        return None


def resolve_reference_images(row, rows_by_family, original_dir, style_dir, style_lesson_image):
    family_override_slug = FAMILY_REFERENCE_SLUG_OVERRIDES.get(row["familyRoot"])
    if family_override_slug:
        original_reference = try_find_original_reference(original_dir, family_override_slug)
        style_reference = try_find_style_reference(style_dir, family_override_slug)
        if original_reference or style_reference:
            return original_reference, style_reference or style_lesson_image
    for slug in reference_slug_candidates(row, rows_by_family):
        original_reference = try_find_original_reference(original_dir, slug)
        style_reference = try_find_style_reference(style_dir, slug)
        if original_reference or style_reference:
            return original_reference, style_reference or style_lesson_image
    return None, style_lesson_image


def write_direct_style_output(out_dir, row, prompt_entry, original_reference, style_reference, rows_by_family, art_name):
    out_dir.mkdir(parents=True, exist_ok=True)

    existing_output = art_path_for_variant(out_dir, art_name)
    if existing_output:
        existing_output.unlink()

    reference_copy = out_dir / f"reference{original_reference.suffix.lower()}"
    shutil.copy2(original_reference, reference_copy)

    style_copy = out_dir / f"reference-style{style_reference.suffix.lower()}"
    shutil.copy2(style_reference, style_copy)

    output_path = sidecar_path(out_dir, art_name, style_reference.suffix.lower(), "full-art")
    shutil.copy2(style_reference, output_path)

    prompt = f"""Direct full-art mode.

Character name: {prompt_entry["mogmon"]}
Formula: {prompt_entry["formula"]}

Description:
{description_for_row(int(row["dex"]), row)}

Reason:
This OG brainrot entry is being kept as its existing Pokemon-style reference art instead of running a second Gemini full-art generation pass.

Source usage:
- IMAGE 1 / reference: original full-art brainrot source
- IMAGE 2 / reference-style: existing Pokemon-style full-art reference
- Final output: copy IMAGE 2 directly as the tcg/{int(row["dex"]):03d} full-art
"""
    sidecar_path(out_dir, "prompt", ".txt", art_name).write_text(prompt, encoding="utf-8")

    meta = {
        "model": "direct-style-reference",
        "artName": art_name,
        "renderMode": DIRECT_STYLE_RENDER_MODE,
        "name": prompt_entry["mogmon"],
        "formula": prompt_entry["formula"],
        "description": description_for_row(int(row["dex"]), row),
        "flavorText": row["cardDescription"],
        "stageNote": stage_note(row["stageLabel"]),
        "stageLabel": row["stageLabel"],
        "familyContrastNote": family_contrast_note(row, rows_by_family),
        "referenceImage": str(original_reference),
        "savedReferenceImage": str(reference_copy),
        "styleReferenceImage": str(style_reference),
        "savedStyleReferenceImage": str(style_copy),
        "outputImage": str(output_path),
        "outputMimeType": mimetypes.guess_type(output_path.name)[0] or "image/jpeg",
    }
    sidecar_path(out_dir, "meta", ".json", art_name).write_text(f"{json.dumps(meta, indent=2)}\n", encoding="utf-8")


def build_targets(rows, dex_values, family_roots):
    selected = []
    seen = set()
    dex_filter = set(dex_values)
    family_filter = set(family_roots)
    for row in rows:
        row_dex = row.get("dex")
        matched = False
        if row_dex and int(row_dex) in dex_filter:
            matched = True
        if family_filter and row["familyRoot"] in family_filter:
            matched = True
        if matched:
            row_id = (row.get("dex", ""), row["speciesKey"])
            if row_id not in seen:
                selected.append(row)
                seen.add(row_id)
    if dex_filter:
        present = {int(row["dex"]) for row in selected if row.get("dex")}
        missing = sorted(dex_filter - present)
        if missing:
            raise SystemExit(f"Missing dex rows for: {', '.join(str(value) for value in missing)}")
    return selected


def attach_dex(rows, prompts_by_dex):
    for row in rows:
        if row.get("dex"):
            continue
        key = normalize_species_lookup(row["speciesKey"])
        for dex, prompt in prompts_by_dex.items():
            if (
                normalize_species_lookup(prompt["original"]) == key
                or normalize_species_lookup(prompt["mogmon"]) == key
            ):
                row["dex"] = str(dex)
                break
        if not row.get("dex"):
            match = next(
                (
                    dex
                    for dex, prompt in prompts_by_dex.items()
                    if normalize_species_lookup(prompt["original"]) == key
                ),
                None,
            )
            if match is not None:
                row["dex"] = str(match)
    return rows


def main():
    parser = argparse.ArgumentParser(
        description="Generate final TCG full-art folders like tcg/001 from the mirrored Pokemon-style reference sets."
    )
    parser.add_argument("--dex", action="append", type=int, default=[], help="Dex number to generate. Repeatable.")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Generate every curated Mogger Mon row in the dex tables.",
    )
    parser.add_argument(
        "--family-root",
        action="append",
        default=[],
        help="Family root from the curated dex TSVs, e.g. bulbasaur. Repeatable.",
    )
    parser.add_argument(
        "--original-dir",
        default=str(DEFAULT_ORIGINAL_DIR),
        help="Directory containing the mirrored original full-art references.",
    )
    parser.add_argument(
        "--style-dir",
        default=str(DEFAULT_STYLE_DIR),
        help="Directory containing the per-slug Pokemon-style references.",
    )
    parser.add_argument(
        "--out-base",
        default=str(DEFAULT_OUT_BASE),
        help="Base TCG output directory.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Regenerate even if a tcg/<dex>/full-art image already exists.",
    )
    parser.add_argument(
        "--art-name",
        default="full-art",
        help="Art stem to generate, e.g. full-art or full-art-2.",
    )
    parser.add_argument(
        "--transport",
        choices=["mpp", "direct", "fal"],
        default="mpp",
        help="Image transport to use for generated variants.",
    )
    parser.add_argument(
        "--force-generate",
        action="store_true",
        help="Ignore direct-style shortcut rows and generate art for every selected Mogger Mon.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue the batch if one dex generation fails.",
    )
    args = parser.parse_args()

    prompts_by_dex = load_prompt_entries()
    rows = load_dex_rows()
    rows = attach_dex(rows, prompts_by_dex)

    if args.all:
        args.dex = sorted(int(row["dex"]) for row in rows if row.get("dex"))

    if not args.dex and not args.family_root:
        raise SystemExit("Pass at least one --dex or --family-root.")

    rows_by_family = build_rows_by_family(rows)
    selected = build_targets(rows, args.dex, args.family_root)
    if not selected:
        raise SystemExit("No matching dex rows found.")

    original_dir = Path(args.original_dir)
    style_dir = Path(args.style_dir)
    out_base = Path(args.out_base)
    style_lesson_image = find_style_lesson_image(DEFAULT_STYLE_LESSON_IMAGE)
    generated_dexes = []
    failures = []

    for row in selected:
        dex = int(row["dex"])
        prompt_entry = prompts_by_dex.get(dex)
        if not prompt_entry:
            raise SystemExit(f"Missing mogmon prompt entry for dex {dex}")

        out_dir = out_base / f"{dex:03d}"
        render_mode = "" if args.force_generate else row.get("renderMode", "")
        stale_reason = stale_output_reason(
            out_dir,
            dex,
            row,
            prompt_entry,
            rows_by_family,
            render_mode,
            args.art_name,
        )
        if not args.overwrite and not stale_reason:
            existing = art_path_for_variant(out_dir, args.art_name)
            print(f"Skipping {dex:03d}: {existing.name} already matches current family/stage data")
            continue

        try:
            if stale_reason:
                print(f"Regenerating {dex:03d} {prompt_entry['mogmon']}: {stale_reason}")
            if render_mode == DIRECT_STYLE_RENDER_MODE:
                slug = slugify_title(row["canonicalBrainrot"])
                original_reference = find_original_reference(original_dir, slug)
                style_reference = find_style_reference(style_dir, slug)
                print(f"Using style reference as full art for {dex:03d} {prompt_entry['mogmon']}")
                write_direct_style_output(out_dir, row, prompt_entry, original_reference, style_reference, rows_by_family, args.art_name)
                generated_dexes.append(dex)
                continue

            cmd = [
                sys.executable,
                str(GENERATOR_PATH),
                "--out-dir",
                str(out_dir),
                "--name",
                prompt_entry["mogmon"],
                "--formula",
                prompt_entry["formula"],
                "--description",
                description_for_row(dex, row),
                "--flavor-text",
                row["cardDescription"],
                "--stage-note",
                stage_note(row["stageLabel"]),
                "--stage-label",
                row["stageLabel"],
                "--family-contrast-note",
                family_contrast_note(row, rows_by_family),
                "--camera-note",
                camera_note(row["stageLabel"]),
                "--transport",
                args.transport,
                "--art-name",
                args.art_name,
            ]
            if render_mode:
                cmd.extend(["--render-mode", render_mode])
            original_reference, style_reference = resolve_reference_images(
                row, rows_by_family, original_dir, style_dir, style_lesson_image
            )
            if original_reference:
                cmd.extend(["--reference-image", str(original_reference)])
            if style_reference:
                cmd.extend(["--style-reference-image", str(style_reference)])

            print(f"Generating {dex:03d} {prompt_entry['mogmon']}")
            subprocess.run(cmd, check=True)
            generated_dexes.append(dex)
        except Exception as exc:
            failures.append((dex, prompt_entry["mogmon"], str(exc)))
            print(f"Failed {dex:03d} {prompt_entry['mogmon']}: {exc}", file=sys.stderr)
            if not args.continue_on_error:
                raise

    if generated_dexes and MASK_SCRIPT_PATH.exists():
        mask_cmd = [
            "swift",
            str(MASK_SCRIPT_PATH),
            "--source-dir",
            str(out_base),
            "--art-name",
            args.art_name,
            "--overwrite",
        ]
        for dex in generated_dexes:
            mask_cmd.extend(["--dex", str(dex)])
        try:
            subprocess.run(mask_cmd, check=True)
        except subprocess.CalledProcessError as exc:
            print(f"Mask generation failed: {exc}", file=sys.stderr)
            if not args.continue_on_error:
                raise

    if failures:
        raise SystemExit(
            "Some dex generations failed: "
            + ", ".join(f"{dex:03d} {name}" for dex, name, _error in failures)
        )


if __name__ == "__main__":
    main()
