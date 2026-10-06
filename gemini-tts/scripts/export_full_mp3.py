"""マニフェスト順に WAV を結合し MP3 化する."""

from __future__ import annotations

import json
import subprocess
import wave
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1] / "projects" / "異常な日常の物語_最適化された男"
    out_dir = root / "export"
    out_dir.mkdir(exist_ok=True)

    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    items = [
        i
        for i in manifest["items"]
        if i.get("tts") and (i.get("spoken_text") or "").strip()
    ]
    paths = [root / i["output"] for i in items]
    missing = [str(p) for p in paths if not p.is_file() or p.stat().st_size == 0]
    if missing:
        print("missing:", len(missing))
        for m in missing[:10]:
            print(" ", m)
        return 1

    rates: set[int] = set()
    for p in paths:
        with wave.open(str(p), "rb") as wf:
            rates.add(wf.getframerate())
    print(f"files={len(paths)} rates={rates}")

    list_path = out_dir / "concat_list.txt"
    lines: list[str] = []
    for p in paths:
        # ffmpeg concat: escape single quotes in path
        posix = p.resolve().as_posix().replace("'", r"'\''")
        lines.append(f"file '{posix}'")
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    wav_out = out_dir / "最適化された男_full.wav"
    mp3_out = out_dir / "最適化された男_full.mp3"

    cmd1 = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
        "-c",
        "copy",
        str(wav_out),
    ]
    print("concat...")
    r1 = subprocess.run(cmd1, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r1.returncode != 0:
        print(r1.stderr[-2000:])
        return r1.returncode

    cmd2 = [
        "ffmpeg",
        "-y",
        "-i",
        str(wav_out),
        "-codec:a",
        "libmp3lame",
        "-qscale:a",
        "2",
        str(mp3_out),
    ]
    print("mp3...")
    r2 = subprocess.run(cmd2, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r2.returncode != 0:
        print(r2.stderr[-2000:])
        return r2.returncode

    with wave.open(str(wav_out), "rb") as wf:
        dur = wf.getnframes() / float(wf.getframerate())
    print(f"duration_sec={dur:.1f}")
    print(f"wav={wav_out} ({wav_out.stat().st_size} bytes)")
    print(f"mp3={mp3_out} ({mp3_out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
