"""adult_anime_samples のシーン別 MP3 をキャラ（声質 key）ごとに1本に結合する."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IN_DIR = ROOT / "output" / "adult_anime_samples"
OUT_DIR = IN_DIR / "combined"

SCENE_IDS = ("01_kiss", "02_caress", "03_oral", "04_sex", "05_after")
VOICE_KEYS = ("Hina", "Romaco", "Kuon", "Sumire", "Yuko")
# シーン間の無音（秒）。最終シーン後は余白なし。
SCENE_PAD = 0.85


def concat(paths: list[Path], dest: Path, *, pad: float) -> None:
    filters: list[str] = []
    labels: list[str] = []
    last = len(paths) - 1
    for index, _path in enumerate(paths):
        label = f"a{index}"
        pad_dur = 0.0 if index == last else pad
        filters.append(
            f"[{index}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=mono,"
            f"apad=pad_dur={pad_dur}[{label}]"
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


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for key in VOICE_KEYS:
        paths = [IN_DIR / f"{scene}_{key}.mp3" for scene in SCENE_IDS]
        missing = [str(p) for p in paths if not p.is_file() or p.stat().st_size < 1000]
        if missing:
            raise FileNotFoundError(f"{key} missing:\n" + "\n".join(missing))
        dest = OUT_DIR / f"{key}_全シーン.mp3"
        concat(paths, dest, pad=SCENE_PAD)
        print(f"saved: {dest.name} bytes={dest.stat().st_size} duration={duration(dest)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
