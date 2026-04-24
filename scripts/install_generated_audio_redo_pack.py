#!/usr/bin/env python3
"""Install generated redo-pack audio into assets/audio with ffmpeg normalization."""

from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
AUDIO_ROOT = ROOT / "assets" / "audio"
PACK_AUDIO_ROOT = ROOT / "output" / "original-art-redo-pack" / "audio"
DEFAULT_MANIFESTS = (
    PACK_AUDIO_ROOT / "fal-mpp" / "manifest.json",
    PACK_AUDIO_ROOT / "fal-direct" / "manifest.json",
    PACK_AUDIO_ROOT / "suno-mpp" / "manifest.json",
)
DEFAULT_REPORT = ROOT / "output" / "audio-install-qc" / "generated-audio-install-report.json"
AUDIO_EXTENSIONS = {".m4a", ".mp3", ".ogg", ".wav"}


def fail(message: str) -> None:
    raise SystemExit(message)


def parse_csv(value: str) -> set[str] | None:
    parts = {part.strip() for part in value.split(",") if part.strip()}
    if not parts or any(part.lower() == "all" for part in parts):
        return None
    return parts


def load_manifest(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        fail(f"Manifest is not a list: {path}")
    return data


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{json.dumps(data, indent=2)}\n", encoding="utf-8")


def safe_target_path(output_root: Path, target: str) -> Path:
    relative = Path(target)
    if relative.is_absolute() or ".." in relative.parts:
        fail(f"Unsafe target path in manifest: {target}")
    if relative.suffix.lower() not in AUDIO_EXTENSIONS:
        fail(f"Unsupported target audio extension: {target}")
    resolved = (output_root / relative).resolve()
    output_root_resolved = output_root.resolve()
    if output_root_resolved not in resolved.parents:
        fail(f"Target escapes output root: {target}")
    return resolved


def probe_duration(path: Path) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, check=False, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    try:
        duration = float(completed.stdout.strip())
    except ValueError:
        return None
    return round(duration, 3) if duration > 0 else None


def ffmpeg_args_for(destination: Path) -> list[str]:
    suffix = destination.suffix.lower()
    if suffix == ".wav":
        return ["-ac", "1", "-ar", "44100", "-sample_fmt", "s16"]
    if suffix == ".mp3":
        return ["-ar", "44100", "-codec:a", "libmp3lame", "-b:a", "128k"]
    if suffix == ".m4a":
        return ["-ar", "44100", "-codec:a", "aac", "-b:a", "128k"]
    if suffix == ".ogg":
        return ["-ar", "44100", "-codec:a", "libvorbis", "-q:a", "4"]
    fail(f"Unsupported output extension: {destination}")


def convert_entry(entry: dict, output_root: Path, dry_run: bool) -> dict:
    target = str(entry.get("target") or "")
    category = str(entry.get("category") or Path(target).parts[0] if target else "")
    raw_output = Path(str(entry.get("raw_output") or ""))
    installed_path = safe_target_path(output_root, target)

    result = {
        "target": target,
        "category": category,
        "provider": entry.get("provider"),
        "model": entry.get("model"),
        "raw_output": str(raw_output),
        "installed_path": str(installed_path),
        "status": "pending",
    }

    if not raw_output.exists():
        result.update({"status": "error", "error": f"Raw output not found: {raw_output}"})
        return result

    source_duration = probe_duration(raw_output)
    result["source_duration_seconds"] = source_duration
    if source_duration is None:
        result.update({"status": "error", "error": "Raw output could not be decoded"})
        return result

    if dry_run:
        result["status"] = "dry-run"
        return result

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        fail("ffmpeg not found on PATH")
    installed_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(raw_output),
        "-vn",
        *ffmpeg_args_for(installed_path),
        str(installed_path),
    ]
    completed = subprocess.run(command, capture_output=True, check=False, text=True, timeout=90)
    if completed.returncode != 0:
        result.update(
            {
                "status": "error",
                "error": (completed.stderr or completed.stdout or "ffmpeg failed").strip()[:1200],
            }
        )
        return result

    installed_duration = probe_duration(installed_path)
    result["installed_duration_seconds"] = installed_duration
    if installed_duration is None:
        result.update({"status": "error", "error": "Installed output could not be decoded"})
        return result

    result["status"] = "ok"
    return result


def selected_entries(manifests: list[Path], categories: set[str] | None) -> list[dict]:
    entries_by_target: dict[str, dict] = {}
    for manifest in manifests:
        for entry in load_manifest(manifest):
            if entry.get("status") != "ok":
                continue
            target = str(entry.get("target") or "")
            if not target:
                continue
            category = str(entry.get("category") or Path(target).parts[0])
            if categories is not None and category not in categories:
                continue
            entries_by_target[target] = {**entry, "manifest_path": str(manifest)}
    return [entries_by_target[target] for target in sorted(entries_by_target)]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install generated redo-pack audio under assets/audio.")
    parser.add_argument(
        "--manifest",
        action="append",
        default=[],
        help="Generated audio manifest. Can be repeated. Defaults to fal-mpp and fal-direct manifests.",
    )
    parser.add_argument("--categories", default="all", help="Comma-separated categories to install. Default: all")
    parser.add_argument("--output-root", default=str(AUDIO_ROOT), help="Destination audio root. Default: assets/audio")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="JSON install/QC report path")
    parser.add_argument("--concurrency", type=int, default=4, help="Parallel ffmpeg conversions. Default: 4")
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs without writing assets")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    manifests = [Path(path).resolve() for path in args.manifest] or list(DEFAULT_MANIFESTS)
    categories = parse_csv(args.categories)
    output_root = Path(args.output_root).resolve()
    entries = selected_entries(manifests, categories)
    if not entries:
        fail("No ok generated audio entries matched the requested manifests/categories")

    results: list[dict] = []
    pending_iter = iter(entries)
    futures = {}

    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as executor:
        def submit_next() -> bool:
            try:
                entry = next(pending_iter)
            except StopIteration:
                return False
            print(f"[audio-install] convert {entry.get('target')}", flush=True)
            futures[executor.submit(convert_entry, entry, output_root, args.dry_run)] = entry.get("target")
            return True

        for _ in range(max(1, args.concurrency)):
            submit_next()

        while futures:
            done, _not_done = wait(futures, return_when=FIRST_COMPLETED)
            for future in done:
                target = futures.pop(future)
                try:
                    result = future.result()
                except Exception as error:
                    result = {"target": target, "status": "error", "error": str(error)}
                results.append(result)
                print(f"[audio-install] {result.get('status')} {target}", flush=True)
                submit_next()

    totals: dict[str, int] = {}
    categories_summary: dict[str, dict[str, int]] = {}
    for result in results:
        status = str(result.get("status") or "unknown")
        category = str(result.get("category") or "(unknown)")
        totals[status] = totals.get(status, 0) + 1
        bucket = categories_summary.setdefault(category, {})
        bucket[status] = bucket.get(status, 0) + 1

    report = {
        "manifests": [str(path) for path in manifests],
        "output_root": str(output_root),
        "total_entries": len(results),
        "totals": dict(sorted(totals.items())),
        "categories": dict(sorted(categories_summary.items())),
        "files": sorted(results, key=lambda item: str(item.get("target") or "")),
    }
    write_json(Path(args.report), report)
    print(f"[audio-install] report={args.report} totals={report['totals']}", flush=True)
    if totals.get("error"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
