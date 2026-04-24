#!/usr/bin/env python3
"""Run Fal generation + atlas install + icon repack for a dex range."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PYTHON = os.environ.get("MOGMON_PIPELINE_PYTHON", "python3")
TCG_ROOT = ROOT / "output" / "private-generation-prompts" / "mogger-mon-tcg"
POKEMON_ROOT = ROOT / "assets" / "images" / "pokemon"


SPECIAL_CASES: dict[int, dict[str, object]] = {
    25: {
        "meta_file": "meta-2.json",
        "reference_file": "full-art-2.jpg",
        "omit_identity_text": True,
        "output_root": "output/tcg-reroll-25-meta2-nano-banana-2",
        "model": "fal-ai/nano-banana-2/edit",
    }
}


def run_command(label: str, command: list[str]) -> None:
    print(f"\n== {label} ==")
    print(" ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def parse_dex_csv(raw_value: str) -> list[int]:
    return [int(part.strip()) for part in raw_value.split(",") if part.strip()]


def iter_tcg_dexes() -> list[int]:
    return sorted(int(path.name) for path in TCG_ROOT.iterdir() if path.is_dir() and path.name.isdigit())


def has_generated_install(dex: int) -> bool:
    return (
        (POKEMON_ROOT / "_backup" / f"{dex}.png").exists()
        and (POKEMON_ROOT / "_backup" / "back" / f"{dex}.png").exists()
    )


def discover_pending_tcg_dexes() -> list[int]:
    return [dex for dex in iter_tcg_dexes() if not has_generated_install(dex)]


def generate_one(dex: int, output_root: str, special: dict[str, object] | None, model: str | None) -> None:
    command = [
        PYTHON,
        str(ROOT / "scripts" / "generate_fal_tcg_sprites.py"),
        "--dex",
        str(dex),
        "--output-root",
        output_root,
    ]
    resolved_model = str(special.get("model")) if special and special.get("model") else (model or "").strip()
    if resolved_model:
        command.extend(["--model", resolved_model])
    if special:
        meta_file = special.get("meta_file")
        reference_file = special.get("reference_file")
        if meta_file:
            command.extend(["--meta-file", str(meta_file)])
        if reference_file:
            command.extend(["--reference-file", str(reference_file)])
        if special.get("omit_identity_text"):
            command.append("--omit-identity-text")
    run_command(f"generate dex {dex}", command)


def install_one(dex: int, output_root: str) -> None:
    run_command(
        f"install dex {dex}",
        [
            PYTHON,
            str(ROOT / "scripts" / "install_mogmon.py"),
            "--dex",
            str(dex),
            "--source-root",
            str(ROOT / output_root),
        ],
    )
    run_command(
        f"icons dex {dex}",
        [
            PYTHON,
            str(ROOT / "scripts" / "install_mogmon_icons.py"),
            "--dex",
            str(dex),
        ],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Mogger Mon Fal sprite pipeline for a dex range or sparse dex list.")
    parser.add_argument("--start", type=int, help="First dex to process.")
    parser.add_argument("--end", type=int, help="Last dex to process, inclusive.")
    parser.add_argument(
        "--dex-list",
        default="",
        help="Optional comma-separated dex list. When set, overrides --start/--end.",
    )
    parser.add_argument(
        "--pending-tcg",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Process TCG dex entries that have not yet been installed through the Mogger Mon pipeline.",
    )
    parser.add_argument(
        "--default-output-root",
        default="output/tcg-batch-auto-nano-banana-2",
        help="Output root for non-special-case dex values.",
    )
    parser.add_argument(
        "--model",
        default="fal-ai/nano-banana-2/edit",
        help="Fal model override to pass through to generate_fal_tcg_sprites.py. Default: fal-ai/nano-banana-2/edit",
    )
    parser.add_argument(
        "--state-path",
        default="output/pipeline/mogmon-fal-pipeline-state.json",
        help="Where to write progress state.",
    )
    parser.add_argument(
        "--continue-on-error",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Record failures and continue with later dex values. Default: enabled.",
    )
    return parser.parse_args()


def resolve_requested_dexes(args: argparse.Namespace) -> list[int]:
    if args.dex_list:
        return parse_dex_csv(args.dex_list)
    if args.pending_tcg:
        return discover_pending_tcg_dexes()
    if args.start is None or args.end is None:
        raise SystemExit("Provide --start/--end, or use --dex-list, or use --pending-tcg.")
    if args.start > args.end:
        raise SystemExit("--start must be <= --end")
    return list(range(args.start, args.end + 1))


def main() -> None:
    args = parse_args()
    dex_values = resolve_requested_dexes(args)

    if not (os.environ.get("FAL_KEY") or os.environ.get("FAL_API_KEY")):
        raise SystemExit("FAL_KEY or FAL_API_KEY is required.")
    if not dex_values:
        print("No dex values selected. Nothing to do.")
        return

    state_path = ROOT / args.state_path
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "start": min(dex_values),
        "end": max(dex_values),
        "dexes": dex_values,
        "completed": [],
        "failed": [],
    }
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    for dex in dex_values:
        special = SPECIAL_CASES.get(dex)
        output_root = str(special.get("output_root")) if special else args.default_output_root
        try:
            generate_one(dex, output_root, special, args.model)
            install_one(dex, output_root)
            state["completed"].append({"dex": dex, "output_root": output_root})
        except subprocess.CalledProcessError as error:
            state["failed"].append(
                {
                    "dex": dex,
                    "output_root": output_root,
                    "returncode": error.returncode,
                    "command": error.cmd,
                }
            )
            state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
            if not args.continue_on_error:
                raise
            continue

        state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    print("\nPipeline finished.")
    print(state_path)


if __name__ == "__main__":
    main()
