"""オーディション3本を、Gemini と Eleven v4 でそれぞれ1本の MP3 にする."""

from __future__ import annotations

import subprocess
from pathlib import Path

AUDIO = Path(r"c:\Users\MasaruShindo\work2\003_ゲーム\novel-studio\projects\audition\audio")
OUT = AUDIO.parent
ORDER = ["w1", "w2", "w3", "w4", "w5", "c1", "c2", "c3", "c4", "c5", "n1", "n2", "n3", "n4"]
SCENE_END = {"w5", "c5"}


def sources(folder: Path, suffix: str) -> list[Path]:
    paths = [folder / f"{line_id}{suffix}" for line_id in ORDER]
    missing = [str(path) for path in paths if not path.is_file() or path.stat().st_size < 1000]
    if missing:
        raise FileNotFoundError("missing:\n" + "\n".join(missing))
    return paths


def concat(paths: list[Path], dest: Path) -> None:
    filters: list[str] = []
    labels: list[str] = []
    for index, line_id in enumerate(ORDER):
        if line_id in SCENE_END:
            pad = 1.15
        elif line_id == ORDER[-1]:
            pad = 0.0
        else:
            pad = 0.4
        label = f"a{index}"
        filters.append(
            f"[{index}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=mono,"
            f"apad=pad_dur={pad}[{label}]"
        )
        labels.append(f"[{label}]")
    filters.append(f"{''.join(labels)}concat=n={len(ORDER)}:v=0:a=1[out]")
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
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
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


def main() -> int:
    jobs = [
        (sources(AUDIO, ".wav"), OUT / "三つの声_Gemini.mp3"),
        (sources(AUDIO / "eleven", ".mp3"), OUT / "三つの声_Eleven.mp3"),
    ]
    for paths, dest in jobs:
        concat(paths, dest)
        print(f"saved: {dest} bytes={dest.stat().st_size} duration={duration(dest)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
