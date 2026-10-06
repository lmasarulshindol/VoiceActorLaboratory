"""P0 クリップを ID 順に1本の MP3 に結合."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from synth_adult_anime_p0 import CLIP_ORDER  # noqa: E402

IN_DIR = ROOT / "output" / "adult_anime_p0" / "Romaco"
OUT_FILE = IN_DIR / "Romaco_全編P0.mp3"
CLIP_PAD = 0.38
# シーン末尾 ID の後は少し長めの間
SCENE_ENDS = {
    "01-08", "02-10", "03-11", "04-08", "05-05", "06-03", "07-06", "08-10", "09-04",
}
SCENE_PAD = 0.85


def pad_for(cid: str, index: int, last: int) -> float:
    if index == last:
        return 0.0
    if cid in SCENE_ENDS:
        return SCENE_PAD
    return CLIP_PAD


def concat(paths: list[Path], dest: Path, cids: list[str]) -> None:
    filters: list[str] = []
    labels: list[str] = []
    last = len(paths) - 1
    for index, cid in enumerate(cids):
        label = f"a{index}"
        pad_dur = pad_for(cid, index, last)
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
    paths = [IN_DIR / f"{cid}.mp3" for cid in CLIP_ORDER]
    missing = [str(p) for p in paths if not p.is_file() or p.stat().st_size < 800]
    if missing:
        raise FileNotFoundError("missing:\n" + "\n".join(missing[:20]) + f"\n... total {len(missing)}")
    concat(paths, OUT_FILE, list(CLIP_ORDER))
    print(f"saved: {OUT_FILE} bytes={OUT_FILE.stat().st_size} duration={duration(OUT_FILE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
