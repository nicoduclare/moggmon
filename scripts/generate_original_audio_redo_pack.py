#!/usr/bin/env python3
"""Extract source audio into the redo pack and optionally regenerate SFX through Fal MPP."""

from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import fnmatch
import json
import mimetypes
import re
import shutil
import subprocess
import time
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request


ROOT = Path(__file__).resolve().parent.parent
AUDIO_ROOT = ROOT / "assets" / "audio"
PACK_ROOT = ROOT / "output" / "original-art-redo-pack"
PACK_AUDIO_ROOT = PACK_ROOT / "audio"
SOURCE_OUTPUT_ROOT = PACK_AUDIO_ROOT / "source"
FAL_MPP_OUTPUT_ROOT = PACK_AUDIO_ROOT / "fal-mpp"
FAL_DIRECT_OUTPUT_ROOT = PACK_AUDIO_ROOT / "fal-direct"
SOURCE_MANIFEST = PACK_AUDIO_ROOT / "source-manifest.json"
FAL_MPP_MANIFEST = FAL_MPP_OUTPUT_ROOT / "manifest.json"
FAL_DIRECT_MANIFEST = FAL_DIRECT_OUTPUT_ROOT / "manifest.json"
FAL_MPP_HELPER = Path(__file__).with_name("fal_mpp_generate.mjs")
FAL_DIRECT_HELPER = Path(__file__).with_name("fal_direct_generate.mjs")

DEFAULT_MODEL = "fal-ai/elevenlabs/sound-effects/v2"
DEFAULT_GENERATE_CATEGORIES = ("se", "ui", "battle_anims", "cry")
DEFAULT_MAX_SPEND = "0.03"
HELPER_TIMEOUT_SECONDS = 600
DOWNLOAD_TIMEOUT_SECONDS = 120
NETWORK_RETRY_ATTEMPTS = 4
NETWORK_RETRY_BASE_SECONDS = 3
AUDIO_EXTENSIONS = {".m4a", ".mp3", ".ogg", ".wav"}
FUNDING_ERROR_TOKENS = (
    "insufficient funds",
    "no viable swap route",
    "payment verification failed",
)

TOKEN_REPLACEMENTS = {
    "PRSFX": "",
    "pb": "capture capsule",
    "bgm": "background music",
    "se": "sound effect",
    "ui": "interface",
    "gacha": "capsule machine",
    "gigantamax": "giant powered form",
    "mega": "powered form",
    "primal": "ancient form",
    "crowned": "royal armored form",
}


def fail(message: str) -> None:
    raise SystemExit(message)


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_categories(value: str) -> set[str] | None:
    categories = parse_csv(value)
    if not categories or any(category.lower() == "all" for category in categories):
        return None
    return set(categories)


def audio_category(relative_path: Path) -> str:
    return relative_path.parts[0] if relative_path.parts else "(root)"


def matches_any(relative_path: Path, patterns: list[str]) -> bool:
    if not patterns:
        return True
    value = relative_path.as_posix()
    return any(fnmatch.fnmatch(value, pattern) for pattern in patterns)


def iter_audio_assets(source_root: Path, categories: set[str] | None, patterns: list[str]) -> list[Path]:
    if not source_root.exists():
        fail(f"Audio source root not found: {source_root}")

    assets: list[Path] = []
    for path in source_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        relative_path = path.relative_to(source_root)
        if categories is not None and audio_category(relative_path) not in categories:
            continue
        if not matches_any(relative_path, patterns):
            continue
        assets.append(path)
    return sorted(assets, key=lambda candidate: candidate.relative_to(source_root).as_posix().lower())


def select_window(paths: list[Path], start_index: int, limit: int) -> list[Path]:
    selected = paths[max(start_index, 0) :]
    if limit > 0:
        selected = selected[:limit]
    return selected


def mime_type_for(path: Path) -> str:
    mime_type, _encoding = mimetypes.guess_type(path.name)
    return mime_type or "application/octet-stream"


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
        completed = subprocess.run(command, capture_output=True, check=False, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    try:
        duration = float(completed.stdout.strip())
    except ValueError:
        return None
    if duration <= 0:
        return None
    return round(duration, 3)


def load_json(path: Path, fallback):
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{json.dumps(data, indent=2)}\n", encoding="utf-8")


def copy_source_assets(paths: list[Path], source_root: Path, output_root: Path, force: bool, probe: bool) -> dict:
    entries = []
    totals_by_category: dict[str, dict[str, int]] = {}
    copied = 0
    skipped = 0
    total_bytes = 0

    for source_path in paths:
        relative_path = source_path.relative_to(source_root)
        category = audio_category(relative_path)
        output_path = output_root / relative_path
        size_bytes = source_path.stat().st_size
        total_bytes += size_bytes
        bucket = totals_by_category.setdefault(category, {"files": 0, "bytes": 0})
        bucket["files"] += 1
        bucket["bytes"] += size_bytes

        if output_path.exists() and not force and output_path.stat().st_size == size_bytes:
            skipped += 1
        else:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, output_path)
            copied += 1

        entries.append(
            {
                "target": relative_path.as_posix(),
                "category": category,
                "source_path": str(source_path),
                "pack_path": str(output_path),
                "mime_type": mime_type_for(source_path),
                "size_bytes": size_bytes,
                "duration_seconds": probe_duration(source_path) if probe else None,
            }
        )

    manifest = {
        "source_root": str(source_root),
        "pack_source_root": str(output_root),
        "total_files": len(entries),
        "copied_files": copied,
        "skipped_files": skipped,
        "total_bytes": total_bytes,
        "totals_by_category": dict(sorted(totals_by_category.items())),
        "files": entries,
    }
    write_json(SOURCE_MANIFEST, manifest)
    return manifest


def humanize_stem(path: Path) -> str:
    stem = path.stem
    stem = re.sub(r"^PRSFX-\s*", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"[_-]+", " ", stem)
    stem = re.sub(r"(?<=[A-Za-z])(?=\d+$)", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    for source, replacement in TOKEN_REPLACEMENTS.items():
        stem = re.sub(rf"\b{re.escape(source)}\b", replacement, stem, flags=re.IGNORECASE)
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem or path.stem


def prompt_for_asset(relative_path: Path, duration: float | None) -> str:
    category = audio_category(relative_path)
    label = humanize_stem(relative_path)
    duration_text = f" Target length: {duration:.2f} seconds." if duration else ""

    if category == "battle_anims":
        return (
            f"Create a short original non-infringing game sound effect for a turn-based monster battle move named "
            f"'{label}'. Make it punchy, readable in a busy battle scene, with clean transient impact, no music, "
            f"no voices, and no recognizable franchise audio.{duration_text}"
        )
    if category == "se":
        return (
            f"Create a short original non-infringing arcade RPG sound effect for '{label}'. It should be crisp, "
            f"game-ready, dry enough to layer under music, and not resemble any known game asset.{duration_text}"
        )
    if category == "ui":
        return (
            f"Create a tiny original game interface sound for '{label}'. Make it clean, tactile, retro-modern, "
            f"and suitable for menu feedback without music or voice.{duration_text}"
        )
    if category == "cry":
        return (
            f"Create an original stylized fantasy creature cry for game use. Use a brief expressive organic-synthetic "
            f"chirp, growl, trill, or call suggested only by '{label}', with no recognizable existing character audio."
            f"{duration_text}"
        )
    if category == "bgm":
        return (
            f"Create a short original seamless game audio loop inspired by the cue name '{label}'. Keep it clean and "
            f"non-infringing. This sound-effects model is best for stingers or ambience, not full music.{duration_text}"
        )
    return (
        f"Create a short original non-infringing game audio effect for '{label}', cleanly mixed and ready for gameplay."
        f"{duration_text}"
    )


def clamp_duration(duration: float | None) -> float | None:
    if duration is None:
        return None
    return max(0.5, min(22.0, round(duration, 3)))


def default_duration(relative_path: Path) -> float:
    category = audio_category(relative_path)
    if category == "ui":
        return 0.5
    if category == "cry":
        return 1.2
    if category == "battle_anims":
        return 1.6
    if category == "bgm":
        return 22.0
    return 1.0


def resolve_duration(raw_value: str, source_path: Path, relative_path: Path, probe: bool) -> float | None:
    normalized = raw_value.strip().lower()
    if normalized in {"", "none", "off"}:
        return None
    if normalized == "auto":
        return clamp_duration(probe_duration(source_path) if probe else default_duration(relative_path))
    try:
        return clamp_duration(float(raw_value))
    except ValueError:
        fail(f"Invalid --duration value: {raw_value}")


def output_extension(output_format: str, content_type: str | None, url: str) -> str:
    url_suffix = Path(url.split("?", 1)[0]).suffix.lower()
    if url_suffix in AUDIO_EXTENSIONS:
        return url_suffix
    if content_type:
        guessed = mimetypes.guess_extension(content_type.split(";", 1)[0].strip())
        if guessed:
            return ".m4a" if guessed == ".mp4" else guessed
    if output_format.startswith("mp3_"):
        return ".mp3"
    if output_format.startswith("opus_"):
        return ".opus"
    if output_format.startswith(("pcm_", "ulaw_", "alaw_")):
        return ".wav"
    return ".mp3"


def generation_manifest_path(args) -> Path:
    return FAL_DIRECT_MANIFEST if args.transport == "direct" else FAL_MPP_MANIFEST


def generation_output_root(args) -> Path:
    return FAL_DIRECT_OUTPUT_ROOT if args.transport == "direct" else FAL_MPP_OUTPUT_ROOT


def generation_helper_path(args) -> Path:
    return FAL_DIRECT_HELPER if args.transport == "direct" else FAL_MPP_HELPER


def generation_provider(args) -> str:
    return "fal-direct" if args.transport == "direct" else "fal-mpp"


def generation_model_name(args, response: dict | None = None) -> str:
    if response and response.get("model"):
        return response["model"]
    prefix = "fal:" if args.transport == "direct" else "mpp:"
    return f"{prefix}{args.model}"


def run_json_helper(payload: dict, resolve_only: bool, args) -> dict:
    helper_path = generation_helper_path(args)
    if not helper_path.exists():
        fail(f"Fal helper not found: {helper_path}")
    command = ["node", str(helper_path)]
    if resolve_only:
        command.append("--resolve-only")
    try:
        completed = subprocess.run(
            command,
            input=json.dumps(payload),
            capture_output=True,
            check=False,
            text=True,
            timeout=HELPER_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"Fal request timed out after {error.timeout} seconds") from error

    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout).strip() or "Fal helper failed")
    stdout = completed.stdout.strip()
    if not stdout:
        raise RuntimeError("Fal helper returned no output")
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Fal helper returned invalid JSON: {stdout[:400]}") from error


def candidate_files(response: dict) -> list[dict]:
    candidates: list[dict] = []
    for key in ("audio", "files", "images"):
        value = response.get(key)
        if isinstance(value, list):
            candidates.extend(item for item in value if isinstance(item, dict))
        elif isinstance(value, dict):
            candidates.append(value)
    raw = response.get("raw")
    if isinstance(raw, dict):
        for key in ("audio", "file", "files"):
            value = raw.get(key)
            if isinstance(value, list):
                candidates.extend(item for item in value if isinstance(item, dict))
            elif isinstance(value, dict):
                candidates.append(value)
    return candidates


def download_file(url: str) -> tuple[bytes, str | None]:
    request = urllib_request.Request(url, headers={"User-Agent": "mogmon-audio-redo/1.0"})
    with urllib_request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
        return response.read(), response.headers.get("Content-Type")


def is_retryable_error(error: Exception) -> bool:
    text = str(error).lower()
    return any(token in text for token in ("429", "500", "502", "503", "504", "timeout", "temporarily"))


def is_funding_error(result: dict) -> bool:
    error_text = str(result.get("error") or "").lower()
    return any(token in error_text for token in FUNDING_ERROR_TOKENS)


def manifest_key(relative_path: Path) -> str:
    return relative_path.as_posix()


def output_dir_for(relative_path: Path, root: Path) -> Path:
    return root / relative_path.with_suffix("")


def generate_asset(source_path: Path, source_root: Path, args) -> dict:
    relative_path = source_path.relative_to(source_root)
    category = audio_category(relative_path)
    duration = resolve_duration(args.duration, source_path, relative_path, not args.no_probe_duration)
    prompt = prompt_for_asset(relative_path, duration)
    body = {
        "text": prompt,
        "prompt_influence": args.prompt_influence,
        "output_format": args.output_format,
    }
    if duration is not None:
        body["duration_seconds"] = duration
    if args.loop or audio_category(relative_path) == "bgm":
        body["loop"] = True

    payload = {
        "model": args.model,
        "body": body,
        "maxSpend": args.max_spend,
    }

    out_dir = output_dir_for(relative_path, generation_output_root(args))
    if args.dry_run:
        return {
            "status": "dry-run",
            "target": manifest_key(relative_path),
            "category": category,
            "provider": generation_provider(args),
            "model": generation_model_name(args),
            "source_path": str(source_path),
            "prompt": prompt,
            "body": body,
            "transport": args.transport,
        }

    out_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = out_dir / "prompt.txt"
    response_path = out_dir / "response.json"
    prompt_path.write_text(f"{prompt}\n", encoding="utf-8")

    last_error: Exception | None = None
    for attempt in range(1, NETWORK_RETRY_ATTEMPTS + 1):
        try:
            response = run_json_helper(payload, args.resolve_only, args)
            write_json(response_path, response)
            if args.resolve_only:
                return {
                    "status": "resolved",
                    "target": manifest_key(relative_path),
                    "category": category,
                    "provider": generation_provider(args),
                    "model": generation_model_name(args, response),
                    "source_path": str(source_path),
                    "prompt_path": str(prompt_path),
                    "response_path": str(response_path),
                    "payer_address": response.get("payerAddress"),
                    "max_spend": response.get("maxSpend"),
                    "transport": args.transport,
                }

            files = candidate_files(response)
            generated = next((item for item in files if item.get("url")), None)
            if not generated:
                raise RuntimeError("Fal returned no generated audio URL")
            raw_bytes, content_type = download_file(generated["url"])
            raw_path = out_dir / f"raw{output_extension(args.output_format, content_type, generated['url'])}"
            raw_path.write_bytes(raw_bytes)
            return {
                "status": "ok",
                "target": manifest_key(relative_path),
                "category": category,
                "provider": generation_provider(args),
                "model": generation_model_name(args, response),
                "source_path": str(source_path),
                "source_duration_seconds": probe_duration(source_path) if not args.no_probe_duration else None,
                "prompt_path": str(prompt_path),
                "raw_output": str(raw_path),
                "response_path": str(response_path),
                "mime_type": content_type or mime_type_for(raw_path),
                "remote_url": generated["url"],
                "duration_seconds": duration,
                "prompt_influence": args.prompt_influence,
                "output_format": args.output_format,
                "transport": args.transport,
            }
        except (RuntimeError, urllib_error.URLError) as error:
            last_error = error
            if attempt >= NETWORK_RETRY_ATTEMPTS or not is_retryable_error(error):
                break
            time.sleep(NETWORK_RETRY_BASE_SECONDS * attempt)

    return {
        "status": "error",
        "target": manifest_key(relative_path),
        "category": category,
        "provider": generation_provider(args),
        "model": generation_model_name(args),
        "source_path": str(source_path),
        "prompt_path": str(out_dir / "prompt.txt"),
        "error": str(last_error) if last_error else "Fal request failed",
        "transport": args.transport,
    }


def generate_assets(paths: list[Path], source_root: Path, args) -> list[dict]:
    manifest_path = generation_manifest_path(args)
    existing_entries = load_json(manifest_path, [])
    if not isinstance(existing_entries, list):
        existing_entries = []
    completed = {entry.get("target") for entry in existing_entries if entry.get("status") == "ok"}
    if args.resume and args.transport == "direct":
        mpp_entries = load_json(FAL_MPP_MANIFEST, [])
        if isinstance(mpp_entries, list):
            completed.update(entry.get("target") for entry in mpp_entries if entry.get("status") == "ok")
    results = list(existing_entries)
    pending: list[tuple[int, Path, str]] = []

    for index, source_path in enumerate(paths, start=1):
        relative_path = source_path.relative_to(source_root)
        target = manifest_key(relative_path)
        if args.resume and target in completed:
            print(f"[audio-redo] {index}/{len(paths)} skip {target}", flush=True)
            continue
        pending.append((index, source_path, target))

    if args.concurrency <= 1:
        for index, source_path, target in pending:
            print(f"[audio-redo] {index}/{len(paths)} generate {target}", flush=True)
            result = generate_asset(source_path, source_root, args)
            results = [entry for entry in results if entry.get("target") != target]
            results.append(result)
            write_json(manifest_path, results)
            if result.get("status") == "error":
                print(f"[audio-redo] error {target}: {result.get('error')}", flush=True)
        return results

    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        pending_iter = iter(pending)
        futures = {}
        completed_count = 0
        stop_submitting = False
        cancel_requested = False

        def submit_next() -> bool:
            if stop_submitting:
                return False
            try:
                index, source_path, target = next(pending_iter)
            except StopIteration:
                return False
            print(f"[audio-redo] {index}/{len(paths)} generate {target}", flush=True)
            futures[executor.submit(generate_asset, source_path, source_root, args)] = (index, target)
            return True

        for _ in range(args.concurrency):
            submit_next()

        while futures:
            done, _not_done = wait(futures, return_when=FIRST_COMPLETED)
            for future in done:
                index, target = futures.pop(future)
                if future.cancelled():
                    print(
                        f"[audio-redo] canceled source-index={index}/{len(paths)} {target}",
                        flush=True,
                    )
                    continue
                completed_count += 1
                try:
                    result = future.result()
                except Exception as error:  # Defensive catch for unexpected worker failures.
                    result = {
                        "status": "error",
                        "target": target,
                        "category": audio_category(Path(target)),
                        "provider": generation_provider(args),
                        "model": generation_model_name(args),
                        "error": str(error),
                        "transport": args.transport,
                    }
                results = [entry for entry in results if entry.get("target") != target]
                results.append(result)
                write_json(manifest_path, results)
                status = result.get("status")
                print(
                    f"[audio-redo] complete {completed_count}/{len(pending)} "
                    f"source-index={index}/{len(paths)} status={status} {target}",
                    flush=True,
                )
                if status == "error":
                    print(f"[audio-redo] error {target}: {result.get('error')}", flush=True)
                    if args.stop_on_error or is_funding_error(result):
                        stop_submitting = True
                if not stop_submitting:
                    submit_next()
            if stop_submitting and not cancel_requested:
                for future in futures:
                    future.cancel()
                cancel_requested = True
    return results


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract and regenerate original audio redo pack assets.")
    parser.add_argument("--source-root", default=str(AUDIO_ROOT), help="Source audio root. Default: assets/audio")
    parser.add_argument(
        "--categories",
        default="all",
        help="Comma-separated categories to extract from assets/audio. Use all for every category. Default: all",
    )
    parser.add_argument(
        "--generate-categories",
        default=",".join(DEFAULT_GENERATE_CATEGORIES),
        help="Comma-separated categories to generate when --generate is set. Default: se,ui,battle_anims,cry",
    )
    parser.add_argument(
        "--match",
        action="append",
        default=[],
        help="Glob against the path under assets/audio, e.g. 'battle_anims/PRSFX- Thunderbolt*'. Can be repeated.",
    )
    parser.add_argument("--start-index", type=int, default=0, help="Start index after filtering. Default: 0")
    parser.add_argument("--limit", type=int, default=0, help="Maximum assets after start-index. Default: 0 (no limit)")
    parser.add_argument("--extract", action=argparse.BooleanOptionalAction, default=True, help="Copy source audio into the pack. Default: true")
    parser.add_argument("--generate", action="store_true", help="Generate replacement audio through Fal.")
    parser.add_argument("--force", action="store_true", help="Overwrite extracted source files.")
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True, help="Skip generated targets already marked ok. Default: true")
    parser.add_argument("--dry-run", action="store_true", help="Build prompts and manifest entries without calling Fal.")
    parser.add_argument("--resolve-only", action="store_true", help="Resolve MPP payer/model without spending or generating media.")
    parser.add_argument("--transport", choices=("mpp", "direct"), default="mpp", help="Fal transport. Use direct for FAL_KEY/FAL_API_KEY. Default: mpp")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Fal model. Default: {DEFAULT_MODEL}")
    parser.add_argument("--max-spend", default=DEFAULT_MAX_SPEND, help="MPP max spend per Fal request. Default: 0.03")
    parser.add_argument("--concurrency", type=int, default=1, help="Parallel Fal MPP requests. Default: 1")
    parser.add_argument("--stop-on-error", action="store_true", help="Stop submitting more MPP work after the first error.")
    parser.add_argument("--output-format", default="mp3_44100_128", help="Fal audio output format. Default: mp3_44100_128")
    parser.add_argument("--prompt-influence", type=float, default=0.35, help="ElevenLabs prompt influence. Default: 0.35")
    parser.add_argument("--duration", default="auto", help="Duration seconds, auto, or none. Default: auto")
    parser.add_argument("--loop", action="store_true", help="Ask for seamless looping output.")
    parser.add_argument("--no-probe-duration", action="store_true", help="Skip ffprobe duration metadata.")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    source_root = Path(args.source_root).resolve()

    extract_categories = parse_categories(args.categories)
    extract_paths = select_window(iter_audio_assets(source_root, extract_categories, args.match), args.start_index, args.limit)
    if args.extract:
        manifest = copy_source_assets(extract_paths, source_root, SOURCE_OUTPUT_ROOT, args.force, not args.no_probe_duration)
        print(
            f"[audio-redo] extracted={manifest['copied_files']} skipped={manifest['skipped_files']} "
            f"total={manifest['total_files']} manifest={SOURCE_MANIFEST}",
            flush=True,
        )

    if args.generate:
        generate_categories = parse_categories(args.generate_categories)
        generate_paths = select_window(iter_audio_assets(source_root, generate_categories, args.match), args.start_index, args.limit)
        results = generate_assets(generate_paths, source_root, args)
        ok_count = len([entry for entry in results if entry.get("status") == "ok"])
        error_count = len([entry for entry in results if entry.get("status") == "error"])
        print(f"[audio-redo] generated_ok={ok_count} generated_errors={error_count} manifest={generation_manifest_path(args)}", flush=True)


if __name__ == "__main__":
    main()
