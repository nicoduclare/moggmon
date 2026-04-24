#!/usr/bin/env python3
"""Generate replacement BGM through the Suno MPP service."""

from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import fnmatch
import json
import mimetypes
import re
import subprocess
import time
from pathlib import Path
from urllib import request as urllib_request


ROOT = Path(__file__).resolve().parent.parent
AUDIO_ROOT = ROOT / "assets" / "audio"
BGM_ROOT = AUDIO_ROOT / "bgm"
OUTPUT_ROOT = ROOT / "output" / "original-art-redo-pack" / "audio" / "suno-mpp"
MANIFEST_PATH = OUTPUT_ROOT / "manifest.json"
HELPER_PATH = Path(__file__).with_name("suno_mpp_request.mjs")
HELPER_TIMEOUT_SECONDS = 180
DOWNLOAD_TIMEOUT_SECONDS = 180
FAILURE_STATUSES = {"CREATE_TASK_FAILED", "GENERATE_AUDIO_FAILED", "SENSITIVE_WORD_ERROR"}
SUCCESS_STATUSES = {"SUCCESS"}
AUDIO_EXTENSIONS = {".m4a", ".mp3", ".ogg", ".wav"}
REGION_WORDS = {
    "kanto",
    "johto",
    "hoenn",
    "sinnoh",
    "unova",
    "kalos",
    "alola",
    "galar",
    "paldea",
}
FRANCHISE_TERMS = {
    "arceus",
    "aether",
    "aqua",
    "colress",
    "cyrus",
    "flare",
    "galactic",
    "geeta",
    "ghetsis",
    "giratina",
    "iris",
    "kieran",
    "kukui",
    "magma",
    "nemona",
    "plasma",
    "rocket",
    "skull",
    "ultra",
    "yell",
}


def fail(message: str) -> None:
    raise SystemExit(message)


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


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def iter_bgm_assets(patterns: list[str]) -> list[Path]:
    if not BGM_ROOT.exists():
        fail(f"BGM root not found: {BGM_ROOT}")
    paths = []
    for path in BGM_ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        relative = path.relative_to(AUDIO_ROOT).as_posix()
        if patterns and not any(fnmatch.fnmatch(relative, pattern) for pattern in patterns):
            continue
        paths.append(path)
    return sorted(paths, key=lambda candidate: candidate.relative_to(AUDIO_ROOT).as_posix().lower())


def selected_paths(paths: list[Path], start_index: int, limit: int) -> list[Path]:
    selected = paths[max(0, start_index) :]
    return selected[:limit] if limit > 0 else selected


def relative_target(path: Path) -> str:
    return path.relative_to(AUDIO_ROOT).as_posix()


def safe_title(stem: str) -> str:
    words = re.split(r"[_\s-]+", stem.lower())
    title_words = []
    for word in words:
        if not word:
            continue
        if word in REGION_WORDS:
            title_words.append("Region")
        elif word in FRANCHISE_TERMS:
            title_words.append("Rival")
        elif word == "bgm":
            continue
        else:
            title_words.append(word.capitalize())
    title = " ".join(title_words).strip() or "Game Loop"
    return title[:80]


def prompt_for_target(target: str) -> tuple[str, str, str]:
    stem = Path(target).stem
    title = safe_title(stem)
    lowered = stem.lower()
    battle = "battle" in lowered
    town = any(token in lowered for token in ("town", "city", "center", "mart", "shop"))
    cave = any(token in lowered for token in ("cave", "abyss", "ruins", "tower", "lab"))

    if battle:
        style = "instrumental, loopable game battle theme, synth rock, chiptune hybrid, high energy"
        prompt = (
            f"Original loopable monster RPG battle cue for '{title}'. Fast tempo, tight drums, driving bass, "
            "bright lead hooks, dramatic but not orchestral, built for repeated gameplay."
        )
    elif town:
        style = "instrumental, loopable cozy RPG town theme, soft synth, light percussion, warm melody"
        prompt = (
            f"Original seamless RPG town or menu background cue for '{title}'. Warm, compact, memorable, "
            "with gentle rhythm and enough space for UI sounds."
        )
    elif cave:
        style = "instrumental, loopable RPG dungeon ambience, dark synth, sparse percussion, atmospheric"
        prompt = (
            f"Original seamless RPG dungeon or exploration cue for '{title}'. Mysterious, readable, "
            "with restrained low pulse, texture, and a short melodic motif."
        )
    else:
        style = "instrumental, loopable handheld RPG soundtrack, chiptune hybrid, adventure"
        prompt = (
            f"Original seamless handheld-style RPG background loop for '{title}'. Clear motif, compact form, "
            "playful but polished, suitable under gameplay."
        )
    negative = "vocals, lyrics, copyrighted melody, Pokemon, Nintendo, Game Freak, remix, cover song"
    return title, prompt, style + ", no vocals", negative


def run_helper(endpoint: str, body: dict, max_spend: str) -> dict:
    if not HELPER_PATH.exists():
        fail(f"Suno helper not found: {HELPER_PATH}")
    payload = {"endpoint": endpoint, "body": body, "maxSpend": max_spend}
    try:
        completed = subprocess.run(
            ["node", str(HELPER_PATH)],
            input=json.dumps(payload),
            capture_output=True,
            check=False,
            text=True,
            timeout=HELPER_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"Suno MPP request timed out after {error.timeout} seconds") from error
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout).strip() or "Suno MPP helper failed")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Suno MPP helper returned invalid JSON: {completed.stdout[:400]}") from error


def nested_data(response: dict) -> dict:
    data = response.get("raw", response)
    for _ in range(4):
        if not isinstance(data, dict):
            return {}
        next_data = data.get("data")
        if not isinstance(next_data, dict):
            return data
        data = next_data
    return data if isinstance(data, dict) else {}


def response_task_id(response: dict) -> str | None:
    data = nested_data(response)
    task_id = data.get("taskId")
    return str(task_id) if task_id else None


def response_status(response: dict) -> str | None:
    data = nested_data(response)
    status = data.get("status")
    return str(status) if status else None


def response_tracks(response: dict) -> list[dict]:
    data = nested_data(response)
    raw_response = data.get("response") if isinstance(data, dict) else None
    tracks = raw_response.get("sunoData") if isinstance(raw_response, dict) else None
    return [track for track in tracks if isinstance(track, dict)] if isinstance(tracks, list) else []


def audio_url_for_track(track: dict) -> str | None:
    for key in ("audioUrl", "sourceAudioUrl", "streamAudioUrl", "sourceStreamAudioUrl"):
        value = track.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def download_file(url: str) -> tuple[bytes, str | None]:
    request = urllib_request.Request(url, headers={"User-Agent": "mogmon-suno-bgm-redo/1.0"})
    with urllib_request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
        return response.read(), response.headers.get("Content-Type")


def output_extension(content_type: str | None, url: str) -> str:
    suffix = Path(url.split("?", 1)[0]).suffix.lower()
    if suffix in AUDIO_EXTENSIONS:
        return suffix
    if content_type:
        guessed = mimetypes.guess_extension(content_type.split(";", 1)[0].strip())
        if guessed:
            return ".m4a" if guessed == ".mp4" else guessed
    return ".mp3"


def out_dir_for(target: str) -> Path:
    return OUTPUT_ROOT / Path(target).with_suffix("")


def submit_entry(target: str, max_spend: str) -> dict:
    title, prompt, style, negative_tags = prompt_for_target(target)
    body = {
        "customMode": True,
        "instrumental": True,
        "model": "V5",
        "prompt": prompt,
        "style": style[:200],
        "title": title,
        "negativeTags": negative_tags,
    }
    out_dir = out_dir_for(target)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "prompt.txt").write_text(f"{prompt}\n\nstyle: {style}\n", encoding="utf-8")
    response = run_helper("/generate-music", body, max_spend)
    write_json(out_dir / "submit-response.json", response)
    task_id = response_task_id(response)
    if not task_id:
        raise RuntimeError("Suno MPP did not return taskId")
    return {
        "status": "submitted",
        "target": target,
        "category": "bgm",
        "provider": "suno-mpp",
        "model": "suno:V5",
        "task_id": task_id,
        "submitted_at": round(time.time(), 3),
        "prompt_path": str(out_dir / "prompt.txt"),
        "submit_response_path": str(out_dir / "submit-response.json"),
        "body": body,
    }


def poll_entry(entry: dict, max_spend: str) -> dict:
    target = str(entry.get("target") or "")
    task_id = str(entry.get("task_id") or "")
    if not task_id:
        return {**entry, "status": "error", "error": "Missing Suno task_id"}
    out_dir = out_dir_for(target)
    out_dir.mkdir(parents=True, exist_ok=True)
    response = run_helper("/get-music-status", {"taskId": task_id}, max_spend)
    status_response_path = out_dir / "status-response.json"
    write_json(status_response_path, response)
    status = response_status(response)
    updated = {
        **entry,
        "status": "pending" if status not in SUCCESS_STATUSES and status not in FAILURE_STATUSES else entry.get("status"),
        "suno_status": status,
        "status_response_path": str(status_response_path),
        "last_polled_at": round(time.time(), 3),
    }
    if status in FAILURE_STATUSES:
        updated["status"] = "error"
        updated["error"] = status
        return updated
    if status not in SUCCESS_STATUSES:
        return updated

    tracks = response_tracks(response)
    track = next((candidate for candidate in tracks if audio_url_for_track(candidate)), None)
    if not track:
        updated["status"] = "error"
        updated["error"] = "Suno SUCCESS response had no audio URL"
        return updated

    audio_url = audio_url_for_track(track)
    raw_bytes, content_type = download_file(audio_url)
    raw_path = out_dir / f"raw{output_extension(content_type, audio_url)}"
    raw_path.write_bytes(raw_bytes)
    updated.update(
        {
            "status": "ok",
            "raw_output": str(raw_path),
            "mime_type": content_type or mimetypes.guess_type(raw_path.name)[0],
            "remote_url": audio_url,
            "track": track,
            "track_count": len(tracks),
        }
    )
    return updated


def save_manifest(entries_by_target: dict[str, dict]) -> None:
    write_json(MANIFEST_PATH, [entries_by_target[target] for target in sorted(entries_by_target)])


def run_concurrent(items: list, worker, concurrency: int):
    results = []
    pending_iter = iter(items)
    futures = {}
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as executor:
        def submit_next() -> bool:
            try:
                item = next(pending_iter)
            except StopIteration:
                return False
            futures[executor.submit(worker, item)] = item
            return True

        for _ in range(max(1, concurrency)):
            submit_next()
        while futures:
            done, _not_done = wait(futures, return_when=FIRST_COMPLETED)
            for future in done:
                item = futures.pop(future)
                try:
                    results.append((item, future.result(), None))
                except Exception as error:
                    results.append((item, None, error))
                submit_next()
    return results


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate BGM redo-pack assets through Suno MPP.")
    parser.add_argument("--match", action="append", default=[], help="Glob under assets/audio, e.g. 'bgm/abyss.mp3'")
    parser.add_argument("--start-index", type=int, default=0, help="Start index after filtering")
    parser.add_argument("--limit", type=int, default=0, help="Maximum selected BGM assets")
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True, help="Skip ok/submitted targets. Default: true")
    parser.add_argument("--submit", action=argparse.BooleanOptionalAction, default=True, help="Submit missing Suno tasks. Default: true")
    parser.add_argument("--poll", action=argparse.BooleanOptionalAction, default=True, help="Poll submitted Suno tasks. Default: true")
    parser.add_argument("--adopt-task", action="append", default=[], help="Adopt an existing task as target=taskId")
    parser.add_argument("--submit-concurrency", type=int, default=4, help="Parallel task submits. Default: 4")
    parser.add_argument("--poll-concurrency", type=int, default=8, help="Parallel status polls. Default: 8")
    parser.add_argument("--generate-max-spend", default="0.12", help="MPP max spend per generate call")
    parser.add_argument("--status-max-spend", default="0.01", help="MPP max spend per status call")
    parser.add_argument("--initial-poll-delay", type=float, default=90.0, help="Seconds after submit before polling")
    parser.add_argument("--poll-interval", type=float, default=45.0, help="Seconds between poll rounds")
    parser.add_argument("--max-poll-rounds", type=int, default=6, help="Maximum poll rounds in this run")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    existing = load_json(MANIFEST_PATH, [])
    if not isinstance(existing, list):
        fail(f"Manifest is not a list: {MANIFEST_PATH}")
    entries_by_target = {str(entry.get("target")): entry for entry in existing if entry.get("target")}

    for adoption in args.adopt_task:
        if "=" not in adoption:
            fail("--adopt-task must be target=taskId")
        target, task_id = adoption.split("=", 1)
        entries_by_target[target] = {
            "status": "submitted",
            "target": target,
            "category": "bgm",
            "provider": "suno-mpp",
            "model": "suno:V5",
            "task_id": task_id,
            "submitted_at": time.time() - args.initial_poll_delay,
        }
    if args.adopt_task:
        save_manifest(entries_by_target)

    paths = selected_paths(iter_bgm_assets(args.match), args.start_index, args.limit)
    targets = [relative_target(path) for path in paths]

    if args.submit:
        to_submit = []
        for target in targets:
            entry = entries_by_target.get(target)
            if args.resume and entry and entry.get("status") in {"ok", "submitted", "pending"}:
                print(f"[suno-bgm] skip submit {target} status={entry.get('status')}", flush=True)
                continue
            to_submit.append(target)
        for target, result, error in run_concurrent(
            to_submit,
            lambda item: submit_entry(item, args.generate_max_spend),
            args.submit_concurrency,
        ):
            if error:
                result = {
                    "status": "error",
                    "target": target,
                    "category": "bgm",
                    "provider": "suno-mpp",
                    "model": "suno:V5",
                    "error": str(error),
                }
            entries_by_target[target] = result
            print(f"[suno-bgm] submit {result.get('status')} {target}", flush=True)
            save_manifest(entries_by_target)

    if args.poll:
        for round_index in range(1, max(1, args.max_poll_rounds) + 1):
            now = time.time()
            pollable = []
            for target in targets:
                entry = entries_by_target.get(target)
                if not entry or entry.get("status") == "ok":
                    continue
                if entry.get("status") not in {"submitted", "pending"}:
                    continue
                submitted_at = float(entry.get("submitted_at") or 0)
                if now - submitted_at < args.initial_poll_delay:
                    continue
                pollable.append(entry)
            if not pollable:
                print(f"[suno-bgm] poll round {round_index}: nothing ready", flush=True)
            else:
                print(f"[suno-bgm] poll round {round_index}: {len(pollable)} task(s)", flush=True)
                for entry, result, error in run_concurrent(
                    pollable,
                    lambda item: poll_entry(item, args.status_max_spend),
                    args.poll_concurrency,
                ):
                    target = str(entry.get("target") or "")
                    if error:
                        result = {**entry, "status": "error", "error": str(error), "last_polled_at": time.time()}
                    entries_by_target[target] = result
                    print(
                        f"[suno-bgm] poll {result.get('status')} suno={result.get('suno_status')} {target}",
                        flush=True,
                    )
                    save_manifest(entries_by_target)
            unfinished = [
                target
                for target in targets
                if entries_by_target.get(target, {}).get("status") in {"submitted", "pending"}
            ]
            if not unfinished:
                break
            if round_index < args.max_poll_rounds:
                time.sleep(args.poll_interval)

    totals: dict[str, int] = {}
    for entry in entries_by_target.values():
        status = str(entry.get("status") or "unknown")
        totals[status] = totals.get(status, 0) + 1
    print(f"[suno-bgm] manifest={MANIFEST_PATH} totals={dict(sorted(totals.items()))}", flush=True)


if __name__ == "__main__":
    main()
