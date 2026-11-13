#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ガヤライブラリ一括生成: scenes/*.json -> Eleven v4 -> 30秒ミックス."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FUJI = ROOT.parent
ENV_PATH = FUJI.parent / "gemini-tts" / ".env"
SCENES_DIR = ROOT / "scenes"
OUT_DIR = ROOT / "patterns"
CACHE_DIR = ROOT / "cache"
SCRIPTS_DIR = ROOT / "scripts"
API_BASE = "https://api.elevenlabs.io"
MODEL = "eleven_v4"
TAG_RE = re.compile(r"\[[^\[\]]+\]")
SFX_ONLY = re.compile(
    r"(キーボード|コピー機|グラス|ざわめき|きしむ|動作音|置く音|トレイ|ドア開|beep)",
    re.I,
)

VOICE = {
    "F1": "dp4HJlekKt0HZFHL2jQg",
    "F2": "5hxwoDKwOHAYjdu9RO9Z",
    "F3": "8PfKHL4nZToWC3pbz9U9",
    "F4": "xwDy9oDEtzWzFo6FqAI9",
    "F5": "etp1PCA4xqEUOa61C7BP",
    "F6": "3fjRiFR1qpMZpeqXtmwX",
    "M1": "vY4PC2kSleyw73YRUOI6",
    "M2": "CtUbzbpXB2NakSL8sYID",
    "M3": "xQpTJhLkPZnRFTV4mc3k",
    "M4": "tBfOvWrqvlfBiyUGpSAS",
    "M5": "F8ocrZHRdjmRh0HR6mJL",
    "M6": "6wdSVG3CMjPfAthsnMv9",
}

# delay_ms, volume, pan
NORMAL_LAYOUT = [
    ("P1", 0, 0.28, -0.65),
    ("P2", 2500, 0.26, -0.20),
    ("P3", 4500, 0.26, 0.25),
    ("P4", 7000, 0.24, 0.60),
    ("M1", 1200, 0.18, -0.40),
    ("M2", 9000, 0.17, 0.45),
    ("X1", 11000, 0.15, 0.10),
    ("X2", 14000, 0.15, -0.10),
    ("X1", 20000, 0.14, 0.35),
    ("X2", 24000, 0.14, -0.35),
]
SPARSE_LAYOUT = [
    ("P1", 0, 0.18, -0.40),
    ("P2", 8000, 0.16, 0.35),
    ("M1", 4000, 0.12, 0.10),
    ("X1", 15000, 0.10, -0.20),
    ("X1", 25000, 0.08, 0.30),
]


def load_api_key() -> str:
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if key:
        return key
    if ENV_PATH.is_file():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if line.startswith("ELEVENLABS_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def api_json_get(url: str, key: str) -> dict:
    req = urllib.request.Request(url, headers={"xi-api-key": key, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.load(r)


def check_quota(key: str) -> tuple[int, int, int]:
    sub = api_json_get(f"{API_BASE}/v1/user/subscription", key)
    used = int(sub.get("character_count") or 0)
    limit = int(sub.get("character_limit") or 0)
    return used, limit, limit - used


def spoken(text: str) -> str:
    return TAG_RE.sub("", text).strip()


def is_speech_line(text: str) -> bool:
    s = spoken(text)
    if len(s) < 2:
        return False
    if SFX_ONLY.search(s) and len(s) <= 12:
        return False
    if s.endswith("音") and len(s) <= 10:
        return False
    return True


def clean_clip(lines: list) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for item in lines or []:
        v = item.get("v") or item.get("voice")
        t = item.get("t") or item.get("text") or ""
        if not v or v not in VOICE:
            continue
        if not is_speech_line(t):
            continue
        out.append((v, t.strip()))
    return out


def load_all_scenes() -> list[dict]:
    scenes: list[dict] = []
    for path in sorted(SCENES_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for sc in data.get("scenes") or []:
            clips = {}
            for key, lines in (sc.get("clips") or {}).items():
                cleaned = clean_clip(lines)
                if cleaned:
                    clips[key] = cleaned
            sc = dict(sc)
            sc["clips"] = clips
            sc["_source"] = path.name
            scenes.append(sc)
    return scenes


def estimate_chars(scene: dict) -> int:
    total = 0
    for lines in scene["clips"].values():
        for _, t in lines:
            total += len(t)
    return total


def synthesize_dialogue(lines: list[tuple[str, str]], key: str) -> bytes:
    inputs = [{"text": text, "voice_id": VOICE[role]} for role, text in lines]
    payload = {
        "model_id": MODEL,
        "language_code": "ja",
        "inputs": inputs,
        "settings": {"stability": 0.35, "similarity": 0.75},
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    url = f"{API_BASE}/v1/text-to-dialogue?output_format=mp3_44100_128"
    headers = {
        "xi-api-key": key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    for attempt in range(4):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=180) as res:
                audio = res.read()
                if not audio or len(audio) < 100:
                    raise RuntimeError("空の音声応答")
                return audio
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            if exc.code in (429, 503) and attempt < 3:
                delay = (2**attempt) * 3
                print(f"  HTTP {exc.code}、{delay}秒後に再試行", file=sys.stderr)
                time.sleep(delay)
                continue
            raise RuntimeError(f"ElevenLabs HTTP {exc.code}: {detail}") from None
        except urllib.error.URLError as exc:
            raise RuntimeError(f"通信エラー: {exc}") from None
    raise RuntimeError("合成失敗")


def pan_filter(pan: float) -> str:
    angle = (pan + 1.0) * (math.pi / 4.0)
    l = math.cos(angle)
    r = math.sin(angle)
    return f"pan=stereo|c0={l:.4f}*c0+{l:.4f}*c1|c1={r:.4f}*c0+{r:.4f}*c1"


def mix_scene(scene_id: str, tracks: list[tuple[Path, int, float, float]], duration_s: int, out_path: Path) -> None:
    inputs: list[str] = []
    filters: list[str] = []
    labels: list[str] = []
    for i, (src, delay_ms, volume, pan) in enumerate(tracks):
        inputs.extend(["-i", str(src)])
        lab = f"a{i}"
        lp = "lowpass=f=4200," if volume < 0.20 else ""
        filters.append(
            f"[{i}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
            f"volume={volume:.3f},{lp}adelay={delay_ms}|{delay_ms},"
            f"{pan_filter(pan)},apad=whole_dur={duration_s}[{lab}]"
        )
        labels.append(f"[{lab}]")
    filters.append(
        f"{''.join(labels)}amix=inputs={len(tracks)}:duration=longest:dropout_transition=0:normalize=0[out]"
    )
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        *inputs,
        "-filter_complex", ";".join(filters),
        "-map", "[out]", "-t", str(duration_s),
        "-c:a", "libmp3lame", "-b:a", "192k", str(out_path),
    ]
    subprocess.run(cmd, check=True)


def export_script_txt(scene: dict) -> Path:
    SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    path = SCRIPTS_DIR / f"{scene['id']}.txt"
    lines = [
        f"# ガヤ台本: {scene.get('title')} ({scene['id']})",
        f"# density={scene.get('density')} / ElevenLabs v4",
        "",
    ]
    for key, clip in scene["clips"].items():
        lines.append(f"@clip {key}")
        for v, t in clip:
            lines.append(f"{v}:")
            lines.append(t)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def build_tracks(scene: dict, clip_files: dict[str, Path]) -> list[tuple[Path, int, float, float]]:
    density = (scene.get("density") or "normal").lower()
    layout = SPARSE_LAYOUT if density == "sparse" else NORMAL_LAYOUT
    tracks = []
    for key, delay, vol, pan in layout:
        if key not in scene["clips"]:
            continue
        path = clip_files.get(f"{scene['id']}__{key}")
        if path and path.exists():
            tracks.append((path, delay, vol, pan))
    return tracks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--only", default="", help="カンマ区切り scene id")
    parser.add_argument("--export-scripts-only", action="store_true")
    args = parser.parse_args()

    scenes = load_all_scenes()
    if args.only:
        wanted = {x.strip() for x in args.only.split(",") if x.strip()}
        scenes = [s for s in scenes if s["id"] in wanted]
    if not scenes:
        print("シーンがありません", file=sys.stderr)
        return 1

    total_chars = sum(estimate_chars(s) for s in scenes)
    print(f"シーン数: {len(scenes)} / 推定文字: {total_chars}")
    for s in scenes:
        nclips = len(s["clips"])
        print(f"  - {s['id']}: {s.get('title')} dens={s.get('density')} clips={nclips} chars={estimate_chars(s)}")

    for s in scenes:
        export_script_txt(s)
    print(f"台本TXT: {SCRIPTS_DIR}")

    if args.export_scripts_only or args.dry_run:
        if args.dry_run:
            print("ドライラン完了")
        return 0

    if not shutil.which("ffmpeg"):
        print("ffmpeg がありません", file=sys.stderr)
        return 1
    key = load_api_key()
    if not key:
        print("ELEVENLABS_API_KEY なし", file=sys.stderr)
        return 1

    used, limit, remain = check_quota(key)
    print(f"文字枠: {used}/{limit} 残り {remain}")
    if remain < total_chars + 500:
        print("残り枠不足", file=sys.stderr)
        return 1

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []

    for s in scenes:
        sid = s["id"]
        clip_files: dict[str, Path] = {}
        print(f"\n=== {sid} ===")
        for ckey, lines in s["clips"].items():
            cache_name = f"{sid}__{ckey}.mp3"
            path = CACHE_DIR / cache_name
            clip_files[f"{sid}__{ckey}"] = path
            if path.exists() and not args.force:
                print(f"  cache {ckey}")
                continue
            # Text-to-dialogue は request あたり概ね 2000 字まで
            char_n = sum(len(t) for _, t in lines)
            if char_n > 1900:
                print(f"  skip {ckey}: too long ({char_n})", file=sys.stderr)
                continue
            print(f"  synth {ckey} ({len(lines)} turns, {char_n} chars)")
            audio = synthesize_dialogue(lines, key)
            path.write_bytes(audio)
            time.sleep(0.35)

        tracks = build_tracks(s, clip_files)
        if len(tracks) < 1:
            print(f"  mix skip: no tracks", file=sys.stderr)
            continue
        duration = 30
        out = OUT_DIR / f"{sid}_30s.mp3"
        print(f"  mix -> {out.name} ({len(tracks)} tracks)")
        mix_scene(sid, tracks, duration, out)
        manifest.append(
            {
                "id": sid,
                "title": s.get("title"),
                "density": s.get("density"),
                "file": out.name,
                "tracks": len(tracks),
                "chars": estimate_chars(s),
            }
        )

    man = OUT_DIR / "manifest.json"
    man.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    readme = ROOT / "README.md"
    rows = ["| ID | タイトル | 密度 | ファイル |", "|---|---|---|---|"]
    for m in manifest:
        rows.append(f"| {m['id']} | {m['title']} | {m['density']} | `{m['file']}` |")
    rows.append("")
    rows.append("教室ガヤ（既存）: `../gaya_morning_patterns/05_mixed_10_30s.mp3`")
    readme.write_text(
        "# ガヤライブラリ\n\n"
        "ElevenLabs v4 / 日本語ボイス / 各約30秒ミックス。\n\n"
        + "\n".join(rows)
        + "\n\n再生成: `py -3 generate_gaya_library.py`\n",
        encoding="utf-8",
    )
    used2, limit2, remain2 = check_quota(key)
    print(f"\n完了: {len(manifest)} 本 / 文字枠 {used2}/{limit2} 残り {remain2}")
    print(f"出力: {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
