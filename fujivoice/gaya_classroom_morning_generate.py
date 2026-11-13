#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""朝の教室ガヤ: 短尺クリップを Eleven v4 で合成し、数パターンにミックスする.

- 同時に聞こえる「人数感」は最大10人程度に抑える
- 全クリップ同時再生はしない（ずらして薄く重ねる）
- 課金あり。先に --dry-run / --estimate を推奨
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT.parent / "gemini-tts" / ".env"
API_BASE = "https://api.elevenlabs.io"
MODEL = "eleven_v4"
TAG_RE = re.compile(r"\[[^\[\]]+\]")

# 高校生っぽい若い日本語ボイス（主役キャストとは別）
VOICE = {
    "F1": "dp4HJlekKt0HZFHL2jQg",  # Ayaka
    "F2": "5hxwoDKwOHAYjdu9RO9Z",  # Riko
    "F3": "8PfKHL4nZToWC3pbz9U9",  # Aoi
    "F4": "xwDy9oDEtzWzFo6FqAI9",  # scene_sumika
    "F5": "etp1PCA4xqEUOa61C7BP",  # aud_riri_V02
    "F6": "3fjRiFR1qpMZpeqXtmwX",  # aud_riri_V05
    "M1": "vY4PC2kSleyw73YRUOI6",  # Haru
    "M2": "CtUbzbpXB2NakSL8sYID",  # AKIRA warm
    "M3": "xQpTJhLkPZnRFTV4mc3k",  # Ren
    "M4": "tBfOvWrqvlfBiyUGpSAS",  # Nao
    "M5": "F8ocrZHRdjmRh0HR6mJL",  # Ryou
    "M6": "6wdSVG3CMjPfAthsnMv9",  # Makoto
}

CLIPS: dict[str, list[tuple[str, str]]] = {
    "G01": [
        ("F1", "[softly] おはよー。"),
        ("F2", "[brightly] おはよ。早いね、今日。"),
    ],
    "G03": [
        ("F3", "[curious] 昨日のドラマ、見た？"),
        ("F4", "[excited] 見た見た！　最後、なにそれ。"),
    ],
    "G04": [
        ("F1", "[quietly] お昼、どこ行く？"),
        ("F5", "[softly] 屋上？　いや、購買かな。"),
    ],
    "G06": [
        ("F5", "[teasing] また寝癖ついてる。"),
        ("F6", "[flustered] えっ、どこ？　うそでしょ。"),
    ],
    "B01": [
        ("M1", "[casual] おっす。"),
        ("M2", "[sleepy] おはよ……きつか。"),
    ],
    "B03": [
        ("M3", "[curious] 昨日の試合、見た？"),
        ("M4", "[excited] 見た見た。あの逆転、やばくね。"),
    ],
    "B06": [
        ("M5", "[teasing] また寝坊ルートかよ。"),
        ("M6", "[defensive] ギリギリセーフだろ。うるさいな。"),
    ],
    # 独り言・相づちは上と別声（混合10人で声が足りるように）
    "M02": [("F5", "[yawning] ねむい……あと五分ほしい。")],
    "M05": [("M5", "[quietly] 今日、提出あったよな。……あったよな？")],
    "X01": [("F4", "[softly] え、マジで？")],
    "X04": [("M2", "[laughing softly] あはは。")],
    # --- 10人版・長尺（各会話の読み上げ本文 roughly 150字 / 約30秒床用）---
    "G01L": [
        ("F1", "[softly] おはよー。……ねえ、今日早いね。何時に起きたの？"),
        ("F2", "[brightly] おはよ。六時半。……うそ、うそ、七時ちょっと前。"),
        ("F1", "[curious] 朝ごはん食べた？　私、パンだけ。"),
        ("F2", "[softly] ヨーグルトだけ。あとで購買、行こ。チャイムまでまだあるし。"),
        ("F1", "[quietly] うん。席、こっち空いてるよ。"),
    ],
    "G06L": [
        ("F5", "[teasing] また寝癖ついてる。後ろ、ぐちゃってなってる。"),
        ("F6", "[flustered] えっ、どこ？　うそでしょ。鏡、貸して。"),
        ("F5", "[giggles] ほら、ここ。手、かして。……ん、まだ残ってる。"),
        ("F6", "[embarrassed] やだ、気づかなかった。朝ダッシュしてきたから。"),
        ("F5", "[playful] 大丈夫、前から見たらわかんない。……たぶん。"),
        ("F6", "[laughing softly] たぶんって言うな！"),
    ],
    "B03L": [
        ("M3", "[curious] 昨日の試合、見た？　あの逆転、やばくね。"),
        ("M4", "[excited] 見た見た。後半のあのパス、神だったわ。"),
        ("M3", "[casual] おれ途中までしか見れなくて。スコアどうなった？"),
        ("M4", "[brightly] 三対二。最後の一分、教室中うるさかったろ。"),
        ("M3", "[laughing softly] 隣のやつ、机叩いてた。先生、まだ来てなくてよかった。"),
        ("M4", "[quietly] 今日の体育、関連あるかな。……ないか。"),
    ],
    "B06L": [
        ("M5", "[teasing] また寝坊ルートかよ。顔、まだ寝てる。"),
        ("M6", "[defensive] ギリギリセーフだろ。うるさいな。改札で走った。"),
        ("M5", "[playful] 靴紐ほどけてたぞ、今。"),
        ("M6", "[flustered] マジか。……直した、直した。"),
        ("M5", "[casual] 宿題やった？　数学。"),
        ("M6", "[sighs] 半分。あと休憩時間にやる。……やるつもり。"),
        ("M5", "[laughing softly] つもり枠、いつものやつだな。"),
    ],
    "M02L": [
        (
            "F5",
            "[yawning] ねむい……あと五分ほしい。目、まだ開かない。提出、あったっけ。あったら終わりだ。",
        ),
    ],
    "M05L": [
        (
            "M5",
            "[quietly] 今日、提出あったよな。……あったよな？　プリント、カバンの奥にあるはず。……見つからない。",
        ),
    ],
    "X01L": [
        ("F4", "[softly] え、マジで？　聞いてないんだけど。"),
    ],
    "X04L": [
        ("M2", "[laughing softly] あはは。それな。やめろって。"),
    ],
}


@dataclass(frozen=True)
class MixTrack:
    clip_id: str
    delay_ms: int
    volume: float  # 0..1
    pan: float  # -1 left .. 1 right


# 人数感 = そのパターンで使うユニーク voice 数（上限10）
PATTERNS: dict[str, dict[str, object]] = {
    "01_sparse_4": {
        "title": "疎(4人) - 始業前の薄さ",
        "people": 4,
        "duration_s": 12,
        "tracks": [
            MixTrack("G01", 0, 0.42, -0.55),
            MixTrack("B01", 900, 0.38, 0.50),
        ],
    },
    "02_girls_6": {
        "title": "女子多め（6人）",
        "people": 6,
        "duration_s": 14,
        "tracks": [
            MixTrack("G01", 0, 0.36, -0.60),
            MixTrack("G03", 700, 0.34, 0.15),
            MixTrack("G06", 1500, 0.32, 0.55),
        ],
    },
    "03_boys_6": {
        "title": "男子多め（6人）",
        "people": 6,
        "duration_s": 14,
        "tracks": [
            MixTrack("B01", 0, 0.36, -0.50),
            MixTrack("B03", 650, 0.34, 0.20),
            MixTrack("B06", 1400, 0.32, 0.55),
        ],
    },
    "04_mixed_10": {
        "title": "混合(10人上限) - やや賑やか",
        "people": 10,
        "duration_s": 16,
        "tracks": [
            MixTrack("G01", 0, 0.30, -0.65),
            MixTrack("G06", 500, 0.28, -0.25),
            MixTrack("B03", 900, 0.28, 0.25),
            MixTrack("B06", 1400, 0.26, 0.60),
            MixTrack("M02", 400, 0.22, -0.40),
            MixTrack("M05", 1800, 0.20, 0.45),
            MixTrack("X01", 2200, 0.18, 0.10),
            MixTrack("X04", 2600, 0.18, -0.10),
        ],
    },
    # 10人・長尺会話（各組 roughly 150字、床30秒）
    "05_mixed_10_30s": {
        "title": "混合10人・長尺(30秒)",
        "people": 10,
        "duration_s": 30,
        "tracks": [
            MixTrack("G01L", 0, 0.28, -0.65),
            MixTrack("G06L", 2500, 0.26, -0.20),
            MixTrack("B03L", 4500, 0.26, 0.25),
            MixTrack("B06L", 7000, 0.24, 0.60),
            MixTrack("M02L", 1200, 0.18, -0.40),
            MixTrack("M05L", 9000, 0.17, 0.45),
            MixTrack("X01L", 11000, 0.15, 0.10),
            MixTrack("X04L", 14000, 0.15, -0.10),
            # 後半にも相づちを散らす（同じ短尺を再利用）
            MixTrack("X01L", 20000, 0.14, 0.35),
            MixTrack("X04L", 24000, 0.14, -0.35),
        ],
    },
}


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


def spoken_chars(text: str) -> int:
    return len(TAG_RE.sub("", text).strip())


def estimate_chars(clip_ids: set[str]) -> int:
    total = 0
    for cid in clip_ids:
        for _, text in CLIPS[cid]:
            total += len(text.strip())
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
            with urllib.request.urlopen(req, timeout=120) as res:
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
    """stereo pan approx: pan -1..1 -> left/right gains."""
    # left=1 when pan=-1, right=1 when pan=1
    left = max(0.0, min(1.0, (1.0 - pan) / 2.0)) * 2.0  # 0..2 peaking at sides oddly
    # simpler equal-power-ish:
    import math

    angle = (pan + 1.0) * (math.pi / 4.0)  # 0..pi/2
    l = math.cos(angle)
    r = math.sin(angle)
    return f"pan=stereo|c0={l:.4f}*c0+{l:.4f}*c1|c1={r:.4f}*c0+{r:.4f}*c1"


def mix_pattern(
    name: str,
    meta: dict[str, object],
    clip_mp3: dict[str, Path],
    out_dir: Path,
) -> Path:
    tracks: list[MixTrack] = meta["tracks"]  # type: ignore[assignment]
    duration_s = int(meta["duration_s"])  # type: ignore[arg-type]
    inputs: list[str] = []
    filters: list[str] = []
    labels: list[str] = []
    for i, tr in enumerate(tracks):
        src = clip_mp3[tr.clip_id]
        inputs.extend(["-i", str(src)])
        lab = f"a{i}"
        # adelay needs L|R; volume; light lowpass for distance when volume low
        lp = "lowpass=f=4500," if tr.volume < 0.25 else ""
        filters.append(
            f"[{i}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
            f"volume={tr.volume:.3f},{lp}adelay={tr.delay_ms}|{tr.delay_ms},"
            f"{pan_filter(tr.pan)},apad=whole_dur={duration_s}[{lab}]"
        )
        labels.append(f"[{lab}]")
    n = len(tracks)
    filters.append(
        f"{''.join(labels)}amix=inputs={n}:duration=longest:dropout_transition=0:normalize=0[out]"
    )
    out_path = out_dir / f"{name}.mp3"
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        *inputs,
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[out]",
        "-t",
        str(duration_s),
        "-c:a",
        "libmp3lame",
        "-b:a",
        "192k",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    return out_path


def unique_voices_for(tracks: list[MixTrack]) -> set[str]:
    roles: set[str] = set()
    for tr in tracks:
        for role, _ in CLIPS[tr.clip_id]:
            roles.add(role)
    return roles


def main() -> int:
    parser = argparse.ArgumentParser(description="教室ガヤを数パターン合成")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="クリップ再生成（追加課金）")
    parser.add_argument(
        "--patterns",
        default="all",
        help="カンマ区切り、または all",
    )
    args = parser.parse_args()

    if not shutil.which("ffmpeg"):
        print("ffmpeg が PATH にありません", file=sys.stderr)
        return 1

    wanted = list(PATTERNS.keys()) if args.patterns == "all" else [p.strip() for p in args.patterns.split(",") if p.strip()]
    for p in wanted:
        if p not in PATTERNS:
            print(f"未知のパターン: {p}", file=sys.stderr)
            return 1

    needed_clips: set[str] = set()
    for p in wanted:
        for tr in PATTERNS[p]["tracks"]:  # type: ignore[union-attr]
            needed_clips.add(tr.clip_id)

    chars = estimate_chars(needed_clips)
    print(f"必要クリップ: {sorted(needed_clips)}")
    print(f"推定課金文字数（タグ込み）: 約 {chars}")

    for p in wanted:
        meta = PATTERNS[p]
        voices = unique_voices_for(meta["tracks"])  # type: ignore[arg-type]
        print(f"  {p}: {meta['title']} / 人数感={len(voices)} / tracks={len(meta['tracks'])}")  # type: ignore[arg-type]

    if args.dry_run:
        print("ドライラン完了（APIなし）")
        return 0

    key = load_api_key()
    if not key:
        print("ELEVENLABS_API_KEY がありません", file=sys.stderr)
        return 1

    used, limit, remain = check_quota(key)
    print(f"文字枠: {used}/{limit}（残り {remain}）")
    if remain < chars + 200:
        print("残り枠が足りません", file=sys.stderr)
        return 1

    cache = ROOT / "gaya_morning_cache"
    out_dir = ROOT / "gaya_morning_patterns"
    cache.mkdir(exist_ok=True)
    out_dir.mkdir(exist_ok=True)

    clip_mp3: dict[str, Path] = {}
    for cid in sorted(needed_clips):
        path = cache / f"{cid}.mp3"
        clip_mp3[cid] = path
        if path.exists() and not args.force:
            print(f"cache hit {cid}")
            continue
        lines = CLIPS[cid]
        print(f"synth {cid} ({len(lines)} turn)")
        audio = synthesize_dialogue(lines, key)
        path.write_bytes(audio)
        time.sleep(0.4)

    manifest = []
    for p in wanted:
        meta = PATTERNS[p]
        print(f"mix {p} …")
        out = mix_pattern(p, meta, clip_mp3, out_dir)
        voices = sorted(unique_voices_for(meta["tracks"]))  # type: ignore[arg-type]
        manifest.append(
            {
                "pattern": p,
                "title": meta["title"],
                "people": len(voices),
                "voices": voices,
                "clips": [t.clip_id for t in meta["tracks"]],  # type: ignore[union-attr]
                "file": out.name,
            }
        )
        print(f"  -> {out}")

    man_path = out_dir / "manifest.json"
    man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    used2, limit2, remain2 = check_quota(key)
    print(f"完了。文字枠: {used2}/{limit2}（残り {remain2}）")
    print(f"出力: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
