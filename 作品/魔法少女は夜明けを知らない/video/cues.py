"""台本の解析と、行番号ベースの演出データ（声・演技指示・場面・SE・BGM・フラッシュ）."""

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
    "灯里": "Zephyr",
    "澪": "Kore",
    "ノクス": "Charon",
    "災禍": "Despina",
}

SPEAKER_COLORS = {
    "灯里": "&H00A8E8FF",
    "澪": "&H00FFC870",
    "ノクス": "&H00C8A0B4",
    "災禍": "&H006060E0",
}

BASE_STYLE = {
    "灯里": "日本のアニメの魔法少女。明るく元気な十六歳の少女の声。感情豊かに、自然な演技で。",
    "澪": "日本のアニメの魔法少女。クールで落ち着いた十六歳の少女の声。少し低めで早口、ぶっきらぼうだが芯がある。",
    "ノクス": "低く落ち着いた青年の声。感情を抑えた静かな話し方で、言葉の前の間を大切に。声を張り上げない。",
    "災禍": "壊れかけた少女の声。かすれた囁きで、苦しそうに、途切れ途切れに。",
}

STATE_STYLE: list[tuple[str, int, int, str]] = [
    ("澪", 50, 145, "右脚を骨折していて、痛みに耐えながら息を詰まらせて話す。"),
    ("澪", 156, 172, "疲れ切っているが、安堵がにじむ。"),
    ("灯里", 91, 153, "全身に大怪我を負っていて、息が荒く、声に力が入りにくい。"),
    ("灯里", 155, 172, "戦いが終わって疲れ切り、かすれた声。"),
]

LINE_STYLE: dict[int, str] = {
    2: "夜空を見上げながら、のんびりと。",
    4: "ゆるく、少し詩的に。",
    5: "呆れたように軽くツッコんでから、一瞬で戦闘モードの声に切り替える。",
    7: "冷静に戦況を報告する。",
    8: "驚いて声が裏返る。",
    10: "勢いよく。後半は変身の呪文として、力強く高らかに唱える。",
    11: "凛とした声で、呪文として高らかに唱える。",
    13: "事務的に、淡々と。",
    14: "軽く受け流すように。",
    16: "技名を全力で叫ぶ。気合いの入った攻撃の叫び。",
    18: "脇腹を爪で裂かれた痛みのうめき声。短く鋭く。",
    19: "仲間の名前を必死に叫んでから、防御の技名を鋭く叫ぶ。",
    21: "怒って強く叱る。",
    22: "痛みをこらえながら、言い訳するように。",
    23: "ぶっきらぼうだが、優しさが少しにじむ。",
    24: "短く鋭い警告。",
    25: "息を詰めて、攻撃しながら。",
    27: "低く、何かを警戒するように。",
    29: "静かに、不穏な予感を込めて。",
    31: "言葉を失う沈黙。",
    33: "低く、しかし強い圧で命令する。緊迫感。",
    35: "恐怖で声が震え、かすれる。",
    36: "驚愕と恐怖で息をのむ。",
    37: "冷たく突き放すように。",
    38: "必死に食い下がる。",
    39: "冷酷なほど淡々と。",
    40: "感情的に、強く言い返す。",
    41: "低くひび割れた、人ではないものの声。凍えるように震えて。",
    42: "戸惑って、小さく。",
    43: "恐る恐る。",
    45: "全力で叫ぶ。切迫した悲鳴に近い声。",
    47: "絶叫。親友の名前を泣き叫ぶ。",
    49: "パニックになって泣きそうに、早口で。",
    50: "瓦礫の下から、苦しそうに、途切れ途切れに。",
    51: "泣きながら安堵する。",
    52: "痛みで顔をしかめながら。",
    53: "医者のように冷静に、事実だけを告げる。",
    54: "痛みの中で、無理に皮肉を言う。",
    55: "即座に、少しむっとして。",
    56: "痛みの中で、思わず小さく笑う。",
    58: "低くひび割れた声。寒さに凍え、すがるように。",
    59: "信じられないという呆然とした声。",
    60: "震える声で、恐る恐る名前を呼ぶ。",
    61: "息をのんで、言葉にならない。",
    62: "動揺して、必死に問いかける。",
    64: "泣き叫ぶように、強く。",
    65: "長い沈黙のあと、静かに、重く認める。",
    66: "呆然と、かすれた声で。",
    67: "淡々と、残酷な真実を告げる。感情を一切出さない。",
    68: "理解が追いつかず、かすれた声で。",
    69: "静かに、とどめを刺すように。",
    71: "低く、震えを押し殺した声で。",
    72: "短く、否定しない。",
    73: "怒りと絶望で声が震え、最後は叫ぶ。",
    74: "静かに、言い訳をしない。",
    75: "泣きながら、怒りをぶつけるように叫ぶ。",
    76: "冷静に、だが少しだけ重く。",
    77: "言葉に詰まる。",
    78: "突き放すように淡々と。最後は緊迫して。",
    80: "痛みに耐えながら、弱々しく懇願する。",
    81: "小さく、でもはっきりと拒む。",
    82: "必死に呼び止める。",
    83: "泣きながら、強い決意を込めて叫ぶ。",
    85: "全身の力を振り絞って、防御の技名を叫ぶ。",
    86: "雷を受け止める苦痛の絶叫。長く。",
    87: "初めて焦りを見せて、強く叫ぶ。",
    88: "歯を食いしばって、押し出すように。",
    91: "叩きつけられた衝撃で、息が詰まって血を吐くような声。",
    92: "悲鳴のように叫ぶ。",
    94: "静かに、だが声の奥に動揺が隠れている。",
    95: "力なく、無理に笑うように。",
    96: "短く、苦しげに。",
    97: "笑いながら、泣き出しそうに。",
    98: "苦痛に満ちた、助けを求める囁き。泣いている。",
    99: "優しく、悲しげに。",
    100: "涙をこらえながら、静かに。",
    102: "静かに、覚悟を決めた声で。",
    103: "迷いの沈黙。",
    104: "静かに、しかし逃がさないように。",
    105: "長い迷いのあと、低く。",
    106: "淡々と説明するが、技名は重々しく。",
    107: "最後に一番重く、静かに告げる。",
    108: "泣きながら、か細く止める。",
    109: "穏やかに、受け入れるように。",
    110: "わずかに語気が強まる。",
    111: "静かに、怖さを押し隠して。",
    112: "長い間のあと、重く。",
    113: "冗談めかして、寂しげに笑う。",
    114: "泣き叫ぶように、怒って。",
    115: "小さく笑って、謝る。",
    117: "静かに、名前だけを呼ぶ。",
    118: "静かに、きっぱりと。",
    119: "静かに、しかしはっきりと拒む。",
    120: "少し驚いて、弱々しく笑いながら。",
    121: "言葉を探す沈黙。",
    122: "初めて心の内を語りはじめる。抑えた声で、静かに。",
    123: "淡々と、しかし言葉の端に重い後悔がにじむ。",
    124: "静かに、自分に言い聞かせるように。",
    125: "胸を打たれて、小さく。",
    126: "張り上げず、静かな声に想いの全てを込める。この作品で最も感情がこもった一言。",
    127: "泣きながら、責めるように。",
    128: "少しだけ柔らかく。後半はいつもの淡々とした調子に戻して。",
    129: "涙声で、聞き返す。",
    130: "静かに、迷いのない決意で。",
    131: "驚いて。",
    133: "静かに、覚悟を込めて。",
    134: "取り乱して、叫ぶように。",
    135: "あっさりと、少しとぼけて。",
    136: "泣きながら叫ぶ。",
    137: "少しだけ笑みを含んで、穏やかに。",
    138: "泣き笑いで。",
    139: "痛みをこらえ、力を振り絞って。",
    140: "胸を打たれて。",
    141: "苦痛をこらえながら、最後は技名を力強く叫ぶ。",
    143: "苦しげに、名前を呼ぶ。",
    144: "涙をこらえて、優しく、力強く。",
    145: "強く、名前を叫ぶ。",
    146: "静かに応え、最後の一言は力強く。",
    147: "全ての魔力を込めた最大の叫び。必殺技の名前を魂から叫ぶ。",
    149: "崩れていく、言葉にならない声。",
    151: "穏やかで優しい、本来の少女の声に戻って。消え入りそうに、微笑みながら。",
    152: "泣き崩れる。",
    155: "荒い息。",
    156: "弱々しく、心配して。",
    157: "放心したように。",
    158: "泣きそうに、安堵して。",
    159: "ふと気づいて、不安そうに。",
    160: "不安が募って、声が震える。",
    162: "泣きながら、すがるように。",
    164: "少し照れくさそうに、安堵をにじませて柔らかく。",
    165: "息をのむ。",
    166: "照れ隠しに淡々と。でも声はどこか温かい。",
    167: "泣きじゃくりながら。嬉し泣き。",
    168: "涙まじりに、優しく笑う。",
    169: "静かに、優しく呼ぶ。",
    170: "鼻をすすりながら。",
    171: "穏やかに、静かに、優しく。最後の一言。",
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
    style: str | None = None
    sfx: list[str] = field(default_factory=list)


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


def style_for(no: int, speaker: str) -> str:
    """基本スタイル + 状態 + 行ごとの指示を連結する."""
    parts = [BASE_STYLE.get(speaker, "")]
    for who, start, end, state in STATE_STYLE:
        if who == speaker and start <= no <= end:
            parts.append(state)
    if no in LINE_STYLE:
        parts.append(LINE_STYLE[no])
    return "".join(p for p in parts if p)


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
            line.style = style_for(no, speaker)
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
