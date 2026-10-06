"""サンプル15本を、声質ごと・演目ごとの MP3 に結合する."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IN_DIR = ROOT / "output" / "sample-voice-15_2026-10-06"
OUT_DIR = IN_DIR / "combined"
VOICE_KEYS = ("kiyo", "hiro", "ryo", "nayuta", "sawaro", "akira")
CLIP_PAD = 0.85
COMPARE_PAD = 1.1
CATEGORY_PAD = 1.4


def clip_files(voice: str) -> list[Path]:
    folder = IN_DIR / voice
    paths = sorted(folder.glob("*.mp3"))
    if len(paths) != 15:
        raise FileNotFoundError(f"{voice}: expected 15 mp3, got {len(paths)}")
    return paths


def concat(paths: list[Path], dest: Path, pads: list[float]) -> None:
    if len(paths) != len(pads):
        raise ValueError("pads と入力数が一致しません")
    filters: list[str] = []
    labels: list[str] = []
    for index, pad in enumerate(pads):
        label = f"a{index}"
        filters.append(
            f"[{index}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=mono,"
            f"apad=pad_dur={pad}[{label}]"
        )
        labels.append(f"[{label}]")
    filters.append(f"{''.join(labels)}concat=n={len(paths)}:v=0:a=1[out]")
    command = ["ffmpeg", "-y"]
    for path in paths:
        command.extend(["-i", str(path)])
    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[out]",
            "-codec:a",
            "libmp3lame",
            "-qscale:a",
            "2",
            str(dest),
        ]
    )
    result = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-2000:])


def duration(path: Path) -> str:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return f"{float(result.stdout.strip()):.1f}s"


def pads_for_full(count: int) -> list[float]:
    pads = [CLIP_PAD] * count
    pads[-1] = 0.0
    if count >= 10:
        pads[4] = CATEGORY_PAD
        pads[9] = CATEGORY_PAD
    return pads


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    compare_dir = OUT_DIR / "compare"
    compare_dir.mkdir(parents=True, exist_ok=True)
    by_voice = {key: clip_files(key) for key in VOICE_KEYS}

    for key, paths in by_voice.items():
        dest = OUT_DIR / f"{key}_全15本.mp3"
        concat(paths, dest, pads_for_full(len(paths)))
        print(f"saved: {dest.name} bytes={dest.stat().st_size} duration={duration(dest)}")
        groups = (
            ("キャラ", paths[:5]),
            ("ナレ", paths[5:10]),
            ("朗読", paths[10:]),
        )
        for label, group in groups:
            dest = OUT_DIR / f"{key}_{label}.mp3"
            pads = [CLIP_PAD] * len(group)
            pads[-1] = 0.0
            concat(group, dest, pads)
            print(f"saved: {dest.name} bytes={dest.stat().st_size} duration={duration(dest)}")

    names = [p.name for p in by_voice[VOICE_KEYS[0]]]
    for index, name in enumerate(names):
        paths = [by_voice[key][index] for key in VOICE_KEYS]
        dest = compare_dir / name.replace(".mp3", "_6声.mp3")
        pads = [COMPARE_PAD] * len(paths)
        pads[-1] = 0.0
        concat(paths, dest, pads)
        print(f"saved: compare/{dest.name} bytes={dest.stat().st_size} duration={duration(dest)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
