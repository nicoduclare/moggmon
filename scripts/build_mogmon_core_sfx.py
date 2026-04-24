#!/usr/bin/env python3
"""Build a small original Mogger Mon core SFX set for launch-facing UI and battle actions."""

from __future__ import annotations

import argparse
import math
import random
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SAMPLE_RATE = 22050
RNG = random.Random(424242)


def clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def write_wav(path: Path, samples: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = bytearray()
    for sample in samples:
        value = int(clamp(sample) * 32767)
        pcm += int(value).to_bytes(2, "little", signed=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(bytes(pcm))


def envelope(length: int, attack: float, decay: float, sustain: float, release: float) -> list[float]:
    attack_n = max(1, int(length * attack))
    decay_n = max(1, int(length * decay))
    release_n = max(1, int(length * release))
    sustain_n = max(0, length - attack_n - decay_n - release_n)
    env = []
    for i in range(attack_n):
        env.append(i / attack_n)
    for i in range(decay_n):
        t = i / decay_n
        env.append(1.0 - (1.0 - sustain) * t)
    env.extend([sustain] * sustain_n)
    for i in range(release_n):
        t = i / release_n
        env.append(sustain * (1.0 - t))
    if len(env) < length:
        env.extend([0.0] * (length - len(env)))
    return env[:length]


def synth_tone(
    duration: float,
    freq_start: float,
    freq_end: float | None = None,
    waveform: str = "sine",
    volume: float = 0.5,
    attack: float = 0.05,
    decay: float = 0.2,
    sustain: float = 0.4,
    release: float = 0.25,
) -> list[float]:
    length = max(1, int(duration * SAMPLE_RATE))
    env = envelope(length, attack, decay, sustain, release)
    freq_end = freq_end if freq_end is not None else freq_start
    samples = []
    phase = 0.0
    for i in range(length):
        freq = freq_start + (freq_end - freq_start) * (i / max(1, length - 1))
        phase += (2.0 * math.pi * freq) / SAMPLE_RATE
        if waveform == "square":
            raw = 1.0 if math.sin(phase) >= 0 else -1.0
        elif waveform == "triangle":
            raw = (2 / math.pi) * math.asin(math.sin(phase))
        elif waveform == "saw":
            raw = 2.0 * ((phase / (2.0 * math.pi)) % 1.0) - 1.0
        else:
            raw = math.sin(phase)
        samples.append(raw * env[i] * volume)
    return samples


def synth_noise(
    duration: float,
    volume: float = 0.4,
    attack: float = 0.01,
    decay: float = 0.15,
    sustain: float = 0.1,
    release: float = 0.2,
) -> list[float]:
    length = max(1, int(duration * SAMPLE_RATE))
    env = envelope(length, attack, decay, sustain, release)
    return [RNG.uniform(-1.0, 1.0) * env[i] * volume for i in range(length)]


def mix(layers: list[list[float]], gain: float = 1.0) -> list[float]:
    length = max(len(layer) for layer in layers)
    mixed = [0.0] * length
    for layer in layers:
        for i, sample in enumerate(layer):
            mixed[i] += sample
    peak = max(0.001, max(abs(sample) for sample in mixed))
    norm = gain / peak
    return [sample * norm for sample in mixed]


def blip_up() -> list[float]:
    return mix(
        [
            synth_tone(0.08, 620, 900, waveform="square", volume=0.5, attack=0.02, decay=0.2, sustain=0.15, release=0.25),
            synth_tone(0.08, 1240, 1800, waveform="triangle", volume=0.18, attack=0.02, decay=0.18, sustain=0.1, release=0.22),
        ],
        0.9,
    )


def blip_down() -> list[float]:
    return mix(
        [
            synth_tone(0.12, 540, 240, waveform="square", volume=0.42, attack=0.02, decay=0.2, sustain=0.18, release=0.3),
            synth_noise(0.07, volume=0.06),
        ],
        0.9,
    )


def soft_click() -> list[float]:
    return mix([synth_noise(0.03, volume=0.5), synth_tone(0.04, 900, 700, waveform="triangle", volume=0.16)], 0.8)


def icy_click() -> list[float]:
    return mix(
        [
            synth_noise(0.028, volume=0.22, attack=0.0, decay=0.12, sustain=0.0, release=0.08),
            synth_tone(0.055, 1180, 820, waveform="triangle", volume=0.16, attack=0.0, decay=0.22, sustain=0.06, release=0.18),
            synth_tone(0.032, 1760, 1480, waveform="sine", volume=0.08, attack=0.0, decay=0.18, sustain=0.0, release=0.1),
        ],
        0.86,
    )


def bright_chime() -> list[float]:
    return mix(
        [
            synth_tone(0.22, 880, 1320, waveform="triangle", volume=0.36, attack=0.01, decay=0.22, sustain=0.12, release=0.4),
            synth_tone(0.28, 1320, 1760, waveform="sine", volume=0.18, attack=0.01, decay=0.18, sustain=0.08, release=0.5),
        ],
        0.9,
    )


def stat_up() -> list[float]:
    parts = [synth_tone(0.06, f, f * 1.08, waveform="square", volume=0.34) for f in (480, 640, 820)]
    gap = [0.0] * int(0.012 * SAMPLE_RATE)
    result = []
    for part in parts:
        result.extend(part)
        result.extend(gap)
    return mix([result], 0.9)


def stat_down() -> list[float]:
    parts = [synth_tone(0.06, f, f * 0.92, waveform="square", volume=0.34) for f in (820, 640, 460)]
    gap = [0.0] * int(0.012 * SAMPLE_RATE)
    result = []
    for part in parts:
        result.extend(part)
        result.extend(gap)
    return mix([result], 0.9)


def hit(heavy: bool = False, light: bool = False) -> list[float]:
    duration = 0.12 if heavy else 0.07 if light else 0.09
    noise = synth_noise(duration, volume=0.55 if heavy else 0.34 if light else 0.42, attack=0.0, decay=0.18, sustain=0.05, release=0.18)
    tone = synth_tone(duration * 0.9, 180 if heavy else 420 if light else 260, 90 if heavy else 240 if light else 160, waveform="saw", volume=0.18 if heavy else 0.12)
    return mix([noise, tone], 0.9)


def alarm_pulse() -> list[float]:
    part_a = synth_tone(0.14, 740, 700, waveform="square", volume=0.35)
    gap = [0.0] * int(0.05 * SAMPLE_RATE)
    part_b = synth_tone(0.14, 740, 700, waveform="square", volume=0.35)
    return mix([part_a + gap + part_b], 0.9)


def beam() -> list[float]:
    return mix(
        [
            synth_tone(0.24, 220, 1500, waveform="saw", volume=0.24, attack=0.0, decay=0.18, sustain=0.3, release=0.24),
            synth_noise(0.2, volume=0.08, attack=0.0, decay=0.3, sustain=0.08, release=0.2),
        ],
        0.9,
    )


def charge() -> list[float]:
    return mix(
        [
            synth_tone(0.28, 180, 860, waveform="triangle", volume=0.34, attack=0.02, decay=0.18, sustain=0.25, release=0.2),
            synth_tone(0.28, 320, 1280, waveform="sine", volume=0.12, attack=0.04, decay=0.2, sustain=0.18, release=0.22),
        ],
        0.9,
    )


def cryo_throw_whoosh() -> list[float]:
    return mix(
        [
            synth_noise(0.11, volume=0.18, attack=0.0, decay=0.18, sustain=0.03, release=0.18),
            synth_tone(0.09, 960, 410, waveform="triangle", volume=0.18, attack=0.0, decay=0.18, sustain=0.04, release=0.18),
            synth_tone(0.06, 1680, 1120, waveform="sine", volume=0.07, attack=0.0, decay=0.14, sustain=0.0, release=0.12),
        ],
        0.88,
    )


def capture_throw() -> list[float]:
    return mix([icy_click(), cryo_throw_whoosh(), synth_tone(0.08, 840, 520, waveform="triangle", volume=0.12)], 0.9)


def capture_lock() -> list[float]:
    return mix(
        [
            icy_click(),
            synth_tone(0.08, 480, 760, waveform="square", volume=0.18, attack=0.0, decay=0.18, sustain=0.02, release=0.12),
            synth_tone(0.07, 1280, 980, waveform="triangle", volume=0.1, attack=0.0, decay=0.2, sustain=0.03, release=0.14),
        ],
        0.9,
    )


def capture_catch() -> list[float]:
    parts = [synth_tone(0.06, f, f * 1.05, waveform="triangle", volume=0.24) for f in (460, 610, 820)]
    gap = [0.0] * int(0.025 * SAMPLE_RATE)
    result = []
    for part in parts:
        result.extend(part)
        result.extend(gap)
    return mix(
        [
            result,
            synth_tone(0.22, 980, 1620, waveform="sine", volume=0.08, attack=0.0, decay=0.18, sustain=0.06, release=0.22),
        ],
        0.9,
    )


def capture_bounce() -> list[float]:
    return mix(
        [
            synth_tone(0.11, 300, 180, waveform="triangle", volume=0.18, attack=0.0, decay=0.18, sustain=0.04, release=0.14),
            synth_tone(0.06, 920, 680, waveform="sine", volume=0.08, attack=0.0, decay=0.16, sustain=0.0, release=0.12),
            synth_noise(0.03, volume=0.06),
        ],
        0.88,
    )


def faint() -> list[float]:
    return mix([synth_tone(0.34, 360, 70, waveform="saw", volume=0.32), synth_noise(0.18, volume=0.12)], 0.9)


def flee() -> list[float]:
    return mix([synth_tone(0.16, 720, 180, waveform="triangle", volume=0.28), synth_noise(0.06, volume=0.08)], 0.85)


def egg_crack() -> list[float]:
    return mix([synth_noise(0.08, volume=0.55), synth_tone(0.05, 240, 120, waveform="triangle", volume=0.12)], 0.9)


def egg_hatch() -> list[float]:
    return mix([bright_chime(), synth_tone(0.18, 540, 1080, waveform="sine", volume=0.18)], 0.9)


def gacha_dial() -> list[float]:
    return mix(
        [
            synth_tone(0.12, 240, 420, waveform="square", volume=0.12),
            synth_tone(0.1, 980, 880, waveform="triangle", volume=0.08, attack=0.0, decay=0.16, sustain=0.02, release=0.1),
            synth_noise(0.04, volume=0.08),
        ],
        0.82,
    )


def gacha_running() -> list[float]:
    burst = []
    gap = [0.0] * int(0.01 * SAMPLE_RATE)
    for _ in range(8):
        burst.extend(synth_noise(0.018, volume=0.16, attack=0.0, decay=0.12, sustain=0.0, release=0.05))
        burst.extend(gap)
    return mix([burst], 0.8)


def gacha_dispense() -> list[float]:
    return mix([capture_bounce(), bright_chime()], 0.92)


def transform() -> list[float]:
    return mix(
        [
            synth_tone(0.42, 260, 1240, waveform="triangle", volume=0.25, attack=0.02, decay=0.18, sustain=0.3, release=0.24),
            synth_noise(0.25, volume=0.06, attack=0.0, decay=0.22, sustain=0.05, release=0.22),
        ],
        0.9,
    )


def alert() -> list[float]:
    return mix([synth_tone(0.12, 880, 1260, waveform="square", volume=0.34), synth_tone(0.06, 1680, 1520, waveform="triangle", volume=0.12)], 0.9)


FILE_BUILDERS = {
    ROOT / "assets" / "audio" / "ui" / "select.wav": lambda: mix([icy_click(), synth_tone(0.05, 760, 1120, waveform="triangle", volume=0.1)], 0.88),
    ROOT / "assets" / "audio" / "ui" / "menu_open.wav": lambda: mix([bright_chime(), synth_tone(0.15, 520, 840, waveform="triangle", volume=0.12)], 0.9),
    ROOT / "assets" / "audio" / "ui" / "error.wav": blip_down,
    ROOT / "assets" / "audio" / "se" / "hit.wav": hit,
    ROOT / "assets" / "audio" / "se" / "hit_strong.wav": lambda: hit(heavy=True),
    ROOT / "assets" / "audio" / "se" / "hit_weak.wav": lambda: hit(light=True),
    ROOT / "assets" / "audio" / "se" / "stat_up.wav": stat_up,
    ROOT / "assets" / "audio" / "se" / "stat_down.wav": stat_down,
    ROOT / "assets" / "audio" / "se" / "faint.wav": faint,
    ROOT / "assets" / "audio" / "se" / "flee.wav": flee,
    ROOT / "assets" / "audio" / "se" / "low_hp.wav": alarm_pulse,
    ROOT / "assets" / "audio" / "se" / "exp.wav": bright_chime,
    ROOT / "assets" / "audio" / "se" / "level_up.wav": lambda: mix([bright_chime(), stat_up()], 0.9),
    ROOT / "assets" / "audio" / "se" / "sparkle.wav": bright_chime,
    ROOT / "assets" / "audio" / "se" / "restore.wav": lambda: mix([bright_chime(), synth_tone(0.12, 420, 620, waveform="triangle", volume=0.18)], 0.9),
    ROOT / "assets" / "audio" / "se" / "shine.wav": bright_chime,
    ROOT / "assets" / "audio" / "se" / "shing.wav": lambda: synth_tone(0.08, 1320, 980, waveform="triangle", volume=0.42),
    ROOT / "assets" / "audio" / "se" / "charge.wav": charge,
    ROOT / "assets" / "audio" / "se" / "beam.wav": beam,
    ROOT / "assets" / "audio" / "se" / "upgrade.wav": lambda: mix([stat_up(), bright_chime()], 0.9),
    ROOT / "assets" / "audio" / "se" / "buy.wav": soft_click,
    ROOT / "assets" / "audio" / "se" / "achv.wav": lambda: mix([bright_chime(), stat_up(), synth_tone(0.12, 960, 1440, waveform="triangle", volume=0.16)], 0.92),
    ROOT / "assets" / "audio" / "se" / "pb_rel.wav": icy_click,
    ROOT / "assets" / "audio" / "se" / "pb_throw.wav": capture_throw,
    ROOT / "assets" / "audio" / "se" / "pb_bounce_1.wav": capture_bounce,
    ROOT / "assets" / "audio" / "se" / "pb_bounce_2.wav": lambda: mix([capture_bounce(), synth_tone(0.05, 260, 180, waveform="triangle", volume=0.1)], 0.86),
    ROOT / "assets" / "audio" / "se" / "pb_move.wav": lambda: mix([synth_tone(0.09, 540, 760, waveform="triangle", volume=0.18), synth_tone(0.07, 1180, 920, waveform="sine", volume=0.08)], 0.9),
    ROOT / "assets" / "audio" / "se" / "pb_catch.wav": capture_catch,
    ROOT / "assets" / "audio" / "se" / "pb_lock.wav": capture_lock,
    ROOT / "assets" / "audio" / "se" / "crit_throw.wav": lambda: mix([capture_throw(), bright_chime()], 0.92),
    ROOT / "assets" / "audio" / "se" / "pb_tray_enter.wav": icy_click,
    ROOT / "assets" / "audio" / "se" / "pb_tray_ball.wav": capture_bounce,
    ROOT / "assets" / "audio" / "se" / "pb_tray_empty.wav": blip_down,
    ROOT / "assets" / "audio" / "se" / "egg_crack.wav": egg_crack,
    ROOT / "assets" / "audio" / "se" / "egg_hatch.wav": egg_hatch,
    ROOT / "assets" / "audio" / "se" / "gacha_dial.wav": gacha_dial,
    ROOT / "assets" / "audio" / "se" / "gacha_running.wav": gacha_running,
    ROOT / "assets" / "audio" / "se" / "gacha_dispense.wav": gacha_dispense,
    ROOT / "assets" / "audio" / "se" / "save.wav": lambda: mix([soft_click(), synth_tone(0.12, 700, 940, waveform="triangle", volume=0.18)], 0.88),
    ROOT / "assets" / "audio" / "se" / "danger.wav": alarm_pulse,
    ROOT / "assets" / "audio" / "battle_anims" / "PRSFX- Transform.wav": transform,
    ROOT / "assets" / "audio" / "battle_anims" / "GEN8- Exclaim.wav": alert,
    ROOT / "assets" / "audio" / "battle_anims" / "PRSFX- Spotlight2.wav": lambda: mix([bright_chime(), synth_tone(0.14, 760, 1120, waveform="sine", volume=0.18)], 0.9),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build original Mogger Mon core SFX files.")
    parser.add_argument(
        "--output-root",
        default="output/core-sfx-preview",
        help="Optional preview directory to mirror generated sounds into.",
    )
    args = parser.parse_args()

    preview_root = (ROOT / args.output_root).resolve()
    preview_root.mkdir(parents=True, exist_ok=True)

    for output_path, builder in FILE_BUILDERS.items():
        samples = builder()
        write_wav(output_path, samples)
        preview_path = preview_root / output_path.relative_to(ROOT / "assets" / "audio")
        write_wav(preview_path, samples)
        print(output_path)


if __name__ == "__main__":
    main()
