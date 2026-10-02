"""台本の解析と、行番号ベースの演出データ（声・演技タグ・場面・SE・BGM・フラッシュ）."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPT_PATH = ROOT.parents[2] / "台本" / "txt" / "魔法少女は夜明けを知らない_ボイストランド.txt"

TITLE = "魔法少女は夜明けを知らない"

RUBY_RE = re.compile(r"[＊*](?P<base>[^＊*《]+?)《(?P<yomi>[^》]+)》")
KATAKANA_RE = re.compile(r"^[ァ-ヶー・]+$")
SILENT_RE = re.compile(r"^[…。、\s]+$")

READINGS = {
    "魂核": "ソウルコア",
    "災禍級": "さいかきゅう",
    "虚獣": "きょじゅう",
    "灯里": "あかり",
    "澪": "みお",
    "詩織": "しおり",
    "穿て": "うがて",
}

VOICES = {
    "灯里": "EkK6wL8GaH8IgBZTTDGJ",
    "澪": "dhGvgIx0X6G3xzSWqOye",
    "ノクス": "pUgmTF2V1ptIKsYb6qON",
    "災禍": "hMK7c1GPJmptCzI4bQIu",
}

VOICE_NAMES = {
    "灯里": "Akari",
    "澪": "Kana",
    "ノクス": "RYO-A",
    "災禍": "Sameno",
}

STABILITY = {"灯里": 0.35, "澪": 0.45, "ノクス": 0.5, "災禍": 0.3}

SPEAKER_COLORS = {
    "灯里": "&H00A8E8FF",
    "澪": "&H00FFC870",
    "ノクス": "&H00C8A0B4",
    "災禍": "&H006060E0",
}

BASE_TAGS = {
    "灯里": "",
    "澪": "",
    "ノクス": "[calm][low voice]",
    "災禍": "[whispers][trembling]",
}

NO_BASE_TAGS = {88, 151}

STATE_TAGS: list[tuple[str, int, int, str]] = [
    ("澪", 50, 145, "[in pain]"),
    ("澪", 156, 172, "[exhausted]"),
    ("灯里", 91, 153, "[in pain][breathless]"),
    ("灯里", 155, 172, "[exhausted]"),
]

LINE_TAGS: dict[int, str] = {
    2: "[dreamy][relaxed]",
    4: "[playful]",
    5: "[deadpan]",
    7: "[serious][flat]",
    8: "[surprised]",
    10: "[determined][shouting]",
    11: "[determined][commanding]",
    13: "[flat]",
    14: "[playful]",
    16: "[battle cry][shouting]",
    18: "[in pain][gasps]",
    19: "[shouting][urgent]",
    21: "[angry][scolding]",
    22: "[in pain][apologetic]",
    23: "[gruff][softly]",
    24: "[sharp][quickly]",
    25: "[grunts][focused]",
    27: "[suspicious][quietly]",
    29: "[ominous][quietly]",
    33: "[serious][commanding]",
    35: "[scared][trembling]",
    36: "[gasps][shocked]",
    37: "[cold]",
    38: "[desperate]",
    39: "[cold][flat]",
    40: "[angry][shouting]",
    41: "[eerie]",
    42: "[confused][quietly]",
    43: "[scared][whispers]",
    45: "[screaming][urgent]",
    47: "[screaming][crying]",
    49: "[panicking][crying]",
    50: "[weak][strained]",
    51: "[crying][relieved]",
    52: "[strained]",
    53: "[clinical][flat]",
    54: "[sarcastic][strained]",
    55: "[annoyed][flat]",
    56: "[weak laugh]",
    58: "[eerie][pleading]",
    59: "[stunned][quietly]",
    60: "[trembling][whispers]",
    61: "[gasps][shocked]",
    62: "[distressed][urgent]",
    64: "[crying][shouting]",
    65: "[heavy][quietly]",
    66: "[stunned][whispers]",
    67: "[cold][matter-of-fact]",
    68: "[stunned][whispers]",
    69: "[cold][quietly]",
    71: "[trembling][quietly]",
    72: "[flat]",
    73: "[furious][crying]",
    74: "[flat]",
    75: "[crying][shouting]",
    76: "[serious]",
    77: "[choked up]",
    78: "[cold][urgent]",
    80: "[weak][pleading]",
    81: "[quietly][firm]",
    82: "[desperate]",
    83: "[crying][determined][shouting]",
    85: "[battle cry][shouting]",
    87: "[screaming][straining]",
    88: "[alarmed][shouting]",
    89: "[strained][through gritted teeth]",
    91: "[coughing][gasps]",
    92: "[screaming]",
    94: "[serious][quietly]",
    95: "[weak laugh]",
    96: "[sharp]",
    97: "[laughs softly][crying]",
    98: "[crying][whispers]",
    99: "[tender][sad]",
    100: "[sad][softly]",
    102: "[determined][quietly]",
    104: "[firm][quietly]",
    105: "[reluctant][quietly]",
    106: "[serious][grave]",
    107: "[grave][quietly]",
    108: "[crying][weak]",
    109: "[calm][accepting]",
    110: "[firm]",
    111: "[quietly][scared]",
    112: "[heavy]",
    113: "[sad laugh][softly]",
    114: "[crying][angry][shouting]",
    115: "[soft laugh][apologetic]",
    117: "[quietly]",
    118: "[firm][quietly]",
    119: "[firm]",
    120: "[surprised][weak laugh]",
    122: "[quietly][reflective]",
    123: "[regretful][quietly]",
    124: "[quietly][to himself]",
    125: "[moved][softly]",
    126: "[emotional][softly][sincere]",
    127: "[crying][accusing]",
    128: "[softly]",
    129: "[crying][confused]",
    130: "[determined][quietly]",
    131: "[surprised]",
    133: "[resolute][quietly]",
    134: "[panicking][shouting]",
    135: "[nonchalant]",
    136: "[crying][shouting]",
    137: "[wry smile][softly]",
    138: "[laughing through tears]",
    139: "[strained][determined]",
    140: "[moved]",
    141: "[strained][battle cry][shouting]",
    143: "[eerie][weak]",
    144: "[tender][determined]",
    145: "[shouting]",
    146: "[calm][firm]",
    147: "[battle cry][screaming]",
    149: "[eerie][fading]",
    151: "[gentle][smiling][softly]",
    152: "[sobbing]",
    155: "[panting]",
    156: "[weak][worried]",
    157: "[dazed]",
    158: "[relieved][crying]",
    159: "[worried][quietly]",
    160: "[anxious][trembling]",
    162: "[crying][pleading]",
    164: "[embarrassed][softly]",
    165: "[gasps]",
    166: "[deadpan][warm]",
    167: "[sobbing][happy]",
    168: "[laughing through tears]",
    169: "[softly][tender]",
    170: "[sniffles]",
    171: "[softly][warm]",
}

SCENES: list[tuple[int, str]] = [
    (1, "01_rotary"),
    (12, "02_transform"),
    (15, "03_battle"),
    (34, "04_saika"),
    (44, "05_rubble"),
    (58, "06_truth"),
    (80, "07_ring"),
    (101, "08_resolve"),
    (132, "09_lastdawn"),
    (150, "10_shiori"),
    (154, "11_dawn"),
]

BGM_SECTIONS: list[tuple[int, str | None]] = [
    (1, "night"),
    (12, "battle"),
    (34, None),
    (41, "dread"),
    (44, "battle"),
    (58, "truth"),
    (80, "battle"),
    (101, "sorrow"),
    (132, "climax"),
    (150, None),
    (154, "dawn"),
]

SFX: dict[int, list[str]] = {
    6: ["mist"],
    12: ["transform"],
    15: ["growl"],
    16: ["beam_small"],
    17: ["slash", "impact"],
    19: ["shield"],
    20: ["impact"],
    26: ["slash", "burst"],
    34: ["rumble", "crumble"],
    44: ["whoosh", "impact_big"],
    46: ["impact_big", "crumble"],
    48: ["rubble"],
    57: ["rumble"],
    79: ["charge_dark"],
    84: ["crack"],
    85: ["shield"],
    86: ["thunder", "impact_big"],
    90: ["shatter", "impact_big"],
    93: ["crack"],
    117: ["charge"],
    132: ["charge_dark"],
    142: ["shield", "charge"],
    148: ["beam_big"],
    150: ["shimmer"],
    153: ["shatter"],
    154: ["birds"],
    163: ["train"],
}

FLASH: dict[int, str] = {
    16: "white",
    17: "red",
    44: "white",
    46: "white",
    86: "white",
    90: "red",
    148: "white_long",
    153: "white",
}

SHAKE: set[int] = {17, 34, 44, 46, 86, 90, 148}


@dataclass
class Line:
    """台本の1行."""

    no: int
    speaker: str
    display: str
    spoken: str
    is_direction: bool
    silent: bool = False
    voice: str | None = None
    tags: str = ""
    sfx: list[str] = field(default_factory=list)

    @property
    def tts_text(self) -> str:
        """ElevenLabs v4 に渡す文字列（演技タグ + 読み）."""
        return f"{self.tags} {self.spoken}".strip()


def _ruby_display(m: re.Match[str]) -> str:
    base, yomi = m.group("base"), m.group("yomi")
    if KATAKANA_RE.match(yomi):
        return f"{base}（{yomi}）"
    return base


def to_display(text: str) -> str:
    """字幕用: ルビ記法を外す（カタカナ読みは括弧で残す）."""
    return RUBY_RE.sub(_ruby_display, text)


def to_spoken(text: str) -> str:
    """読み上げ用: ルビは読みに置き換え、ダッシュを除く."""
    out = RUBY_RE.sub(lambda m: m.group("yomi"), text)
    for kanji, yomi in READINGS.items():
        out = out.replace(kanji, yomi)
    return out.replace("――", "").replace("—", "").strip()


def tags_for(no: int, speaker: str) -> str:
    """基本タグ + 状態タグ + 行ごとのタグを連結する（重複は除く）."""
    parts = ["" if no in NO_BASE_TAGS else BASE_TAGS.get(speaker, "")]
    for who, start, end, state in STATE_TAGS:
        if who == speaker and start <= no <= end:
            parts.append(state)
    parts.append(LINE_TAGS.get(no, ""))
    seen: list[str] = []
    for tag in re.findall(r"\[[^\]]+\]", "".join(parts)):
        if tag not in seen:
            seen.append(tag)
    return "".join(seen)


def parse_script(path: Path = SCRIPT_PATH) -> list[Line]:
    """ボイストランド形式の txt を Line のリストにする."""
    lines: list[Line] = []
    for no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if "：" not in raw:
            raise ValueError(f"{no}行目にコロンがありません: {raw!r}")
        speaker, text = raw.split("：", 1)
        speaker = speaker.strip()
        is_dir = speaker in {"0", "０"}
        spoken = "" if is_dir else to_spoken(text)
        line = Line(
            no=no,
            speaker="" if is_dir else speaker,
            display=to_display(text),
            spoken=spoken,
            is_direction=is_dir,
            silent=is_dir or bool(SILENT_RE.match(spoken)),
            sfx=list(SFX.get(no, [])),
        )
        if not is_dir:
            if speaker not in VOICES:
                raise ValueError(f"{no}行目: 未知の役名 {speaker!r}")
            line.voice = VOICES[speaker]
            line.tags = tags_for(no, speaker)
        lines.append(line)
    return lines


def section_at(no: int, table: list[tuple[int, str | None]]) -> str | None:
    """行番号に対応する区間の値（SCENES / BGM_SECTIONS 用）."""
    current: str | None = None
    for start, value in table:
        if no >= start:
            current = value
        else:
            break
    return current


def voice_filename(line: Line) -> str:
    return f"{line.no:03d}_{line.speaker}.wav"
