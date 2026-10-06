"""子どもっぽいセリフ × 音声タグ × 声質 の検証マトリクス."""

from __future__ import annotations

import csv
import html
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class Voice:
    key: str
    voice_id: str
    kind: str


@dataclass(frozen=True)
class Line:
    key: str
    label: str
    text: str
    emotion: str


@dataclass(frozen=True)
class Variant:
    key: str
    label: str
    childlike: bool
    emotion: bool
    extra: str = ""


@dataclass(frozen=True)
class Clip:
    voice: Voice
    line: Line
    variant: Variant

    @property
    def tags(self) -> str:
        parts = []
        if self.variant.childlike:
            parts.append("[childlike]")
        if self.variant.extra:
            parts.append(self.variant.extra)
        if self.variant.emotion:
            parts.append(self.line.emotion)
        return "".join(parts)

    @property
    def text(self) -> str:
        return f"{self.tags} {self.line.text}".strip()

    @property
    def relpath(self) -> str:
        return f"{self.voice.key}/{self.line.key}_{self.variant.key}.mp3"


VOICES: tuple[Voice, ...] = (
    Voice("Hina", "lhTvHflPVOqgSWyuWQry", "ロリ本命・アイドル系"),
    Voice("Sumire", "KtSs8OSniRPofXnr5PeA", "息っぽい・儚い"),
    Voice("Kuon", "B8gJV1IhpuegLxdpXFOE", "元気な萌えヒロイン"),
    Voice("Romaco", "KgETZ36CCLD1Cob4xpkv", "明るいアニメ声"),
    Voice("Yuki", "JTlYtJrcTzPC71hMLOxo", "クールなティーン"),
    Voice("Sameno", "hMK7c1GPJmptCzI4bQIu", "甘い・おっとり"),
)

LINES: tuple[Line, ...] = (
    Line("01_genki", "はしゃぐ",
         "ねえねえ、見て見て！　おっきいカブトムシつかまえたよ！　すごいでしょー！",
         "[excited]"),
    Line("02_amae", "甘える",
         "おにいちゃん……きょうはいっしょにねてもいい？　ちょっとだけ、こわいゆめ見ちゃったの。",
         "[timid][soft]"),
    Line("03_sulk", "すねる",
         "むー！　やくそくしたのに！　もう知らない！　おにいちゃんなんか、だいっきらい！",
         "[pouting][angry]"),
    Line("04_cry", "泣く",
         "うえぇん……ころんじゃった……ひざ、いたいよぉ……",
         "[crying][sniffles]"),
    Line("05_secret", "ないしょ話",
         "えへへ、ひみつだよ？　ママにはないしょね。……ふふっ、ぜったいだよ！",
         "[whispers][giggles]"),
    Line("06_sleepy", "ねむい",
         "ふぁ……もうねむい……あしたも、いっぱいあそぼうね……おやすみぃ……",
         "[sleepy][yawns]"),
)

VARIANTS: tuple[Variant, ...] = (
    Variant("a_plain", "タグなし", childlike=False, emotion=False),
    Variant("b_emo", "感情タグのみ", childlike=False, emotion=True),
    Variant("c_child", "[childlike]のみ", childlike=True, emotion=False),
    Variant("d_child_emo", "[childlike]+感情", childlike=True, emotion=True),
    Variant("e_max", "[childlike][high-pitched]+感情", childlike=True, emotion=True,
            extra="[high-pitched]"),
)


def build_matrix(
    voices: Sequence[Voice] = VOICES,
    lines: Sequence[Line] = LINES,
    variants: Sequence[Variant] = VARIANTS,
) -> list[Clip]:
    """声 → セリフ → タグの順に全組み合わせを返す."""
    return [Clip(v, ln, var) for v in voices for ln in lines for var in variants]


def filter_matrix(
    clips: Iterable[Clip],
    *,
    voices: Sequence[str] = (),
    lines: Sequence[str] = (),
    variants: Sequence[str] = (),
) -> list[Clip]:
    """キー（前方一致）で絞り込む. 空の条件は全件扱い."""

    def ok(key: str, wanted: Sequence[str]) -> bool:
        return not wanted or any(key.lower().startswith(w.lower()) for w in wanted)

    return [
        c for c in clips
        if ok(c.voice.key, voices) and ok(c.line.key, lines) and ok(c.variant.key, variants)
    ]


def estimated_chars(clips: Iterable[Clip]) -> int:
    return sum(len(c.text) for c in clips)


def median_f0(samples: np.ndarray, sr: int, *, fmin: float = 120, fmax: float = 800) -> float:
    """自己相関で有声フレームの F0 中央値を返す. 有声が無ければ 0."""
    x = np.asarray(samples, dtype=np.float64)
    frame = int(sr * 0.04)
    if frame <= 0 or len(x) < frame:
        return 0.0
    hop = frame // 2
    window = np.hanning(frame)
    lo, hi = int(sr / fmax), int(sr / fmin)
    found = []
    for i in range(0, len(x) - frame + 1, hop):
        seg = x[i:i + frame] * window
        if np.sqrt(np.mean(seg ** 2)) < 0.02:
            continue
        ac = np.correlate(seg, seg, "full")[frame - 1:]
        k = lo + int(np.argmax(ac[lo:hi]))
        if ac[0] > 0 and ac[k] > 0.45 * ac[0]:
            found.append(sr / k)
    return float(np.median(found)) if found else 0.0


MANIFEST_FIELDS = ("voice", "kind", "line", "label", "variant", "variant_label",
                   "tags", "text", "file", "duration_s", "f0_hz")


def write_manifest(path: Path, rows: Sequence[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in MANIFEST_FIELDS})


def clip_row(clip: Clip, *, duration: float = 0.0, f0: float = 0.0) -> dict[str, object]:
    return {
        "voice": clip.voice.key, "kind": clip.voice.kind,
        "line": clip.line.key, "label": clip.line.label,
        "variant": clip.variant.key, "variant_label": clip.variant.label,
        "tags": clip.tags, "text": clip.line.text, "file": clip.relpath,
        "duration_s": round(duration, 2), "f0_hz": round(f0),
    }


def render_index(clips: Sequence[Clip], f0: dict[str, float] | None = None) -> str:
    """セリフごとに「タグ × 声」の表を並べた試聴ページ."""
    f0 = f0 or {}
    voices = list(dict.fromkeys(c.voice for c in clips))
    lines = list(dict.fromkeys(c.line for c in clips))
    variants = list(dict.fromkeys(c.variant for c in clips))
    by_key = {(c.voice.key, c.line.key, c.variant.key): c for c in clips}
    e = html.escape
    out = [
        "<!doctype html><html lang='ja'><meta charset='utf-8'>",
        "<title>子どもっぽさ × タグ検証</title>",
        "<style>body{font-family:sans-serif;margin:24px;background:#fafafa}"
        "table{border-collapse:collapse;margin-bottom:32px}"
        "th,td{border:1px solid #ccc;padding:6px;font-size:13px;vertical-align:top;background:#fff}"
        "th{background:#f0e6ff}audio{width:190px;height:32px}.f0{color:#888;font-size:11px}"
        "code{background:#eee;padding:1px 4px}</style>",
        "<h1>子どもっぽいセリフ × 音声タグ × 声質</h1>",
        "<p>Eleven v4 / seed 固定。F0 は声の高さの中央値（目安）。</p>",
    ]
    for ln in lines:
        out.append(f"<h2>{e(ln.label)}（{e(ln.key)}）</h2><p>{e(ln.text)}<br>"
                   f"感情タグ: <code>{e(ln.emotion)}</code></p>")
        out.append("<table><tr><th>タグ</th>")
        out += [f"<th>{e(v.key)}<br><small>{e(v.kind)}</small></th>" for v in voices]
        out.append("</tr>")
        for var in variants:
            sample = next((by_key[(v.key, ln.key, var.key)] for v in voices
                           if (v.key, ln.key, var.key) in by_key), None)
            tag_text = sample.tags if sample and sample.tags else "（なし）"
            out.append(f"<tr><th>{e(var.label)}<br><code>{e(tag_text)}</code></th>")
            for v in voices:
                clip = by_key.get((v.key, ln.key, var.key))
                if clip is None:
                    out.append("<td>-</td>")
                    continue
                hz = f0.get(clip.relpath, 0.0)
                note = f"<div class='f0'>F0 {hz:.0f}Hz</div>" if hz else ""
                out.append(f"<td><audio controls preload='none' src='{e(clip.relpath)}'></audio>"
                           f"{note}</td>")
            out.append("</tr>")
        out.append("</table>")
    out.append("</html>")
    return "\n".join(out)
