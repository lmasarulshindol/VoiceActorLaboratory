"""台本Markdownからセリフ・ナレ・Caption等を抽出する."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable


SCENE_RE = re.compile(
    r"^(?:シーン|Scene)\s*([0-9０-９一二三四五六七八九十]+)[：:．.\s]*(.*)$"
)
EPILOGUE_RE = re.compile(r"^エピローグ[：:．.\s]*(.*)$")
PROLOGUE_RE = re.compile(r"^プロローグ[：:．.\s]*(.*)$")
LOCATION_RE = re.compile(r"^＜(?P<label>[^＞]+)＞\s*$")
PAREN_LINE_RE = re.compile(r"^（(?P<body>.+)）\s*$")
DIALOGUE_RE = re.compile(
    r"^(?P<speaker>[^\s「（(<＜]+)"
    r"(?P<notes>(?:[（(][^）)]*[）)])*)"
    r"\s*「(?P<text>.*)」\s*$"
)
SPEED_RE = re.compile(r"(?P<num>\d+(?:\.\d+)?)\s*倍速")
EQUAL_SPEED_RE = re.compile(r"等倍")
ACTING_PREFIX_RE = re.compile(r"^（(?P<act>[^）]+)）\s*")
POPUP_RE = re.compile(r"【(?P<body>[^】]+)】")

# ト書き／効果音／キャプション風の判定キーワード
SFX_KEYWORDS = (
    "電子音",
    "ピピッ",
    "ピロリン",
    "カチッ",
    "アラーム",
    "BGM",
    "効果音",
    "バイタル",
    "心電図",
    "ノイズ",
    "車内音",
    "ドアが",
    "ジョッキ",
    "水道",
    "通知音",
)
CAPTION_KEYWORDS = (
    "テロップ",
    "ポップアップ",
    "画面に",
    "画面が",
    "画面には",
    "表示",
)
SKIP_BODY_PREFIXES = (
    "## ",
    "### ",
    "|",
    "- ",
    "脚本",
    "#### ",
)


@dataclass
class ScriptLine:
    """抽出された1行分の台本要素."""

    id: str
    scene: str
    kind: str  # dialogue / narration / caption / sfx / direction
    speaker: str | None
    text: str
    spoken_text: str
    style_hints: list[str] = field(default_factory=list)
    speed: float | None = None
    raw: str = ""
    tts: bool = True
    notes: list[str] = field(default_factory=list)
    location: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize_scene_num(raw: str) -> str:
    table = str.maketrans("０１２３４５６７８９", "0123456789")
    s = raw.translate(table)
    kanji = {
        "一": "1",
        "二": "2",
        "三": "3",
        "四": "4",
        "五": "5",
        "六": "6",
        "七": "7",
        "八": "8",
        "九": "9",
        "十": "10",
    }
    if s in kanji:
        return kanji[s]
    return s


def _split_notes(notes_blob: str) -> list[str]:
    if not notes_blob:
        return []
    return re.findall(r"[（(]([^）)]*)[）)]", notes_blob)


def _parse_speed(notes: Iterable[str]) -> tuple[float | None, list[str]]:
    speed: float | None = None
    rest: list[str] = []
    for note in notes:
        m = SPEED_RE.search(note)
        if m:
            speed = float(m.group("num"))
            leftover = SPEED_RE.sub("", note)
            leftover = re.sub(r"^[・､、\s]+|[・､、\s]+$", "", leftover)
            if leftover:
                rest.append(leftover)
            continue
        if EQUAL_SPEED_RE.search(note):
            speed = 1.0
            leftover = EQUAL_SPEED_RE.sub("", note)
            leftover = re.sub(r"^[・､、\s]+|[・､、\s]+$", "", leftover)
            if leftover:
                rest.append(leftover)
            continue
        rest.append(note)
    return speed, rest


def _strip_acting_prefix(text: str) -> tuple[str, list[str]]:
    hints: list[str] = []
    rest = text
    while True:
        m = ACTING_PREFIX_RE.match(rest)
        if not m:
            break
        hints.append(m.group("act").strip())
        rest = rest[m.end() :]
    return rest.strip(), hints


def _classify_paren_body(body: str) -> str:
    if any(k in body for k in CAPTION_KEYWORDS) or POPUP_RE.search(body):
        return "caption"
    if any(k in body for k in SFX_KEYWORDS):
        return "sfx"
    return "direction"


def _caption_text_from_body(body: str) -> str:
    popups = POPUP_RE.findall(body)
    if popups:
        return " / ".join(p.strip() for p in popups)
    # 「3日後」のような引用を優先
    quoted = re.findall(r"「([^」]+)」", body)
    if quoted:
        return " / ".join(quoted)
    return body.strip()


def _should_skip_line(line: str) -> bool:
    if not line.strip():
        return True
    if line.strip() == "---":
        return True
    return any(line.startswith(p) for p in SKIP_BODY_PREFIXES)


def parse_script_text(text: str, *, start_at_body: bool = True) -> list[ScriptLine]:
    """台本テキストを ScriptLine のリストに変換する."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    items: list[ScriptLine] = []
    scene = "準備"
    location: str | None = None
    started = not start_at_body
    seq = 0

    for raw in lines:
        line = raw.strip()
        if not started:
            if SCENE_RE.match(line) or EPILOGUE_RE.match(line) or PROLOGUE_RE.match(line):
                started = True
            elif DIALOGUE_RE.match(line):
                started = True
            else:
                continue

        if _should_skip_line(line):
            continue

        m_scene = SCENE_RE.match(line)
        if m_scene:
            num = _normalize_scene_num(m_scene.group(1))
            title = (m_scene.group(2) or "").strip()
            scene = f"S{num}" + (f"_{title}" if title else "")
            location = None
            continue

        if EPILOGUE_RE.match(line):
            scene = "エピローグ"
            location = None
            continue

        if PROLOGUE_RE.match(line):
            scene = "プロローグ"
            location = None
            continue

        m_loc = LOCATION_RE.match(line)
        if m_loc:
            location = m_loc.group("label").strip()
            seq += 1
            items.append(
                ScriptLine(
                    id=f"{seq:04d}",
                    scene=scene,
                    kind="caption",
                    speaker=None,
                    text=location,
                    spoken_text=location,
                    raw=line,
                    tts=True,
                    notes=["location"],
                    location=location,
                )
            )
            continue

        m_paren = PAREN_LINE_RE.match(line)
        if m_paren:
            body = m_paren.group("body").strip()
            kind = _classify_paren_body(body)
            seq += 1
            spoken = _caption_text_from_body(body) if kind == "caption" else body
            items.append(
                ScriptLine(
                    id=f"{seq:04d}",
                    scene=scene,
                    kind=kind,
                    speaker=None,
                    text=body,
                    spoken_text=spoken,
                    raw=line,
                    tts=(kind == "caption"),
                    location=location,
                )
            )
            continue

        m_dlg = DIALOGUE_RE.match(line)
        if m_dlg:
            speaker = m_dlg.group("speaker").strip()
            note_parts = _split_notes(m_dlg.group("notes") or "")
            speed, notes = _parse_speed(note_parts)
            spoken, acting = _strip_acting_prefix(m_dlg.group("text"))
            # 兼任注釈は notes から除外寄りに残す
            notes = [n for n in notes if not n.startswith("※")]
            # 「（ノイズ描写）」だけ＝発話なし → ト書き扱い
            if not spoken and acting:
                body = acting[0]
                kind = _classify_paren_body(body)
                seq += 1
                items.append(
                    ScriptLine(
                        id=f"{seq:04d}",
                        scene=scene if scene != "準備" else "プロローグ",
                        kind=kind if kind != "caption" else "direction",
                        speaker=speaker,
                        text=m_dlg.group("text"),
                        spoken_text="",
                        style_hints=acting,
                        speed=speed,
                        raw=line,
                        tts=False,
                        notes=notes,
                        location=location,
                    )
                )
                continue
            kind = "narration" if speaker == "語り手" else "dialogue"
            # 謎の女性 / 女性（S7）はサキ扱いのヒント
            if speaker in {"謎の女性", "女性"}:
                notes = [*notes, "alias:サキ"]
            seq += 1
            items.append(
                ScriptLine(
                    id=f"{seq:04d}",
                    scene=scene if scene != "準備" else "プロローグ",
                    kind=kind,
                    speaker=speaker,
                    text=m_dlg.group("text"),
                    spoken_text=spoken,
                    style_hints=acting,
                    speed=speed,
                    raw=line,
                    tts=True,
                    notes=notes,
                    location=location,
                )
            )
            continue

        # ポップアップだけの行（括弧なし）
        if line.startswith("【") and line.endswith("】"):
            seq += 1
            body = line.strip("【】")
            items.append(
                ScriptLine(
                    id=f"{seq:04d}",
                    scene=scene,
                    kind="caption",
                    speaker=None,
                    text=body,
                    spoken_text=body,
                    raw=line,
                    tts=True,
                    notes=["popup"],
                    location=location,
                )
            )
            continue

    return items


def summarize(items: list[ScriptLine]) -> dict[str, Any]:
    """抽出結果のサマリ."""
    by_kind: dict[str, int] = {}
    speakers: dict[str, int] = {}
    tts_count = 0
    for it in items:
        by_kind[it.kind] = by_kind.get(it.kind, 0) + 1
        if it.tts:
            tts_count += 1
        if it.speaker:
            speakers[it.speaker] = speakers.get(it.speaker, 0) + 1
    return {
        "total": len(items),
        "tts_targets": tts_count,
        "by_kind": by_kind,
        "speakers": speakers,
    }
