"""子どもっぽいセリフをタグ違い・声質違いで Eleven v4 合成し、試聴ページを作る.

使い方:
    py -3 scripts/child_tag_matrix.py              # 全組み合わせ（合成済みはスキップ）
    py -3 scripts/child_tag_matrix.py --dry-run    # 本数と文字数だけ表示
    py -3 scripts/child_tag_matrix.py --voice Hina --line 04 --variant e
    py -3 scripts/child_tag_matrix.py --index-only # 合成せず index.html と CSV を作り直す
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eleven_tts import ElevenV4Client  # noqa: E402
from eleven_tts.tag_matrix import (  # noqa: E402
    Clip, build_matrix, clip_row, estimated_chars, filter_matrix, median_f0,
    render_index, write_manifest,
)

OUT = ROOT / "output" / "child_tag_matrix"
STABILITY = 0.35
SEED = 7


def remaining_chars(key: str) -> int:
    req = Request("https://api.elevenlabs.io/v1/user/subscription", headers={"xi-api-key": key})
    with urlopen(req, timeout=30) as res:
        data = json.load(res)
    return int(data["character_limit"]) - int(data["character_count"])


def decode(mp3: Path, sr: int = 22050) -> np.ndarray:
    raw = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(mp3), "-ac", "1", "-ar", str(sr),
         "-f", "s16le", "-"],
        check=True, capture_output=True,
    ).stdout
    return np.frombuffer(raw, np.int16) / 32768.0


def synth_one(client: ElevenV4Client, clip: Clip) -> str:
    dest = OUT / clip.relpath
    if dest.is_file() and dest.stat().st_size > 1000:
        return "skip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    last: Exception | None = None
    for attempt in range(3):
        try:
            dest.write_bytes(client.synthesize(clip.text, clip.voice.voice_id,
                                               stability=STABILITY, seed=SEED))
            return "saved"
        except RuntimeError as exc:
            last = exc
            if "401" in str(exc) or "quota" in str(exc).lower():
                break
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(str(last))


def analyse(clips: list[Clip]) -> tuple[list[dict[str, object]], dict[str, float]]:
    rows, f0 = [], {}
    for clip in clips:
        path = OUT / clip.relpath
        if not path.is_file():
            continue
        x = decode(path)
        hz = median_f0(x, 22050)
        f0[clip.relpath] = hz
        rows.append(clip_row(clip, duration=len(x) / 22050, f0=hz))
    return rows, f0


def write_summary(rows: list[dict[str, object]]) -> None:
    """声 × タグパターンごとの F0 平均（セリフ平均）を表示・保存."""
    acc: dict[tuple[str, str], list[float]] = defaultdict(list)
    for r in rows:
        if r["f0_hz"]:
            acc[(str(r["voice"]), str(r["variant"]))].append(float(r["f0_hz"]))
    voices = list(dict.fromkeys(str(r["voice"]) for r in rows))
    variants = list(dict.fromkeys(str(r["variant"]) for r in rows))
    lines = ["voice," + ",".join(variants)]
    print("\nF0平均[Hz]  " + "  ".join(f"{v:>12s}" for v in variants))
    for v in voices:
        vals = [np.mean(acc[(v, var)]) if acc[(v, var)] else 0 for var in variants]
        lines.append(v + "," + ",".join(f"{x:.0f}" for x in vals))
        print(f"{v:10s}  " + "  ".join(f"{x:12.0f}" for x in vals))
    (OUT / "summary.csv").write_text("\n".join(lines) + "\n", encoding="utf-8-sig")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--voice", nargs="*", default=[])
    ap.add_argument("--line", nargs="*", default=[])
    ap.add_argument("--variant", nargs="*", default=[])
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--index-only", action="store_true")
    args = ap.parse_args()

    everything = build_matrix()
    clips = filter_matrix(everything, voices=args.voice, lines=args.line, variants=args.variant)
    todo = [c for c in clips if not (OUT / c.relpath).is_file()]
    need = estimated_chars(todo)
    print(f"対象 {len(clips)} 本 / 未合成 {len(todo)} 本 / 推定 {need} 文字")
    if args.dry_run:
        return 0

    failed: list[str] = []
    if not args.index_only and todo:
        try:
            from dotenv import load_dotenv
            load_dotenv(ROOT / ".env")
        except ImportError:
            pass
        key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
        if not key:
            print("ELEVENLABS_API_KEY が未設定です。gemini-tts/.env に記入してください。")
            return 2
        left = remaining_chars(key)
        print(f"残り文字数枠: {left}")
        if left < need:
            print("文字数枠が足りません。--voice / --line で絞ってください。")
            return 3
        client = ElevenV4Client(key)
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            jobs = {pool.submit(synth_one, client, c): c for c in todo}
            for n, fut in enumerate(as_completed(jobs), 1):
                clip = jobs[fut]
                try:
                    print(f"[{n}/{len(todo)}] {fut.result()}: {clip.relpath}")
                except Exception as exc:  # noqa: BLE001
                    failed.append(f"{clip.relpath}: {exc}")
                    print(f"[{n}/{len(todo)}] fail: {clip.relpath}: {exc}")

    rows, f0 = analyse(everything)
    OUT.mkdir(parents=True, exist_ok=True)
    write_manifest(OUT / "manifest.csv", rows)
    done = [c for c in everything if c.relpath in f0]
    (OUT / "index.html").write_text(render_index(done, f0), encoding="utf-8")
    write_summary(rows)
    print(f"\n出力: {OUT}")
    if failed:
        print("FAILED")
        for item in failed:
            print(item)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
