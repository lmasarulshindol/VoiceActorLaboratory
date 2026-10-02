"""台本解析・演出データ・音響合成・字幕生成のテスト."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import audio_fx as fx  # noqa: E402
import cues  # noqa: E402
import render  # noqa: E402


@pytest.fixture(scope="module")
def lines() -> list[cues.Line]:
    return cues.parse_script()


def test_台本は172行で役名がすべて既知(lines):
    assert len(lines) == 172
    assert {ln.speaker for ln in lines if not ln.is_direction} == set(cues.VOICES)


@pytest.mark.parametrize(
    ("raw", "display", "spoken"),
    [
        ("＊穿光《せんこう》っ！！", "穿光っ！！", "せんこうっ！！"),
        ("＊終焉の黎明《ラスト・ドーン》ッ！", "終焉の黎明（ラスト・ドーン）ッ！", "ラスト・ドーンッ！"),
        ("――星よ、廻れ！", "――星よ、廻れ！", "星よ、廻れ！"),
        ("魂核は、灯里の魂だ。", "魂核は、灯里の魂だ。", "ソウルコアは、あかりの魂だ。"),
    ],
)
def test_ルビと読みの変換(raw, display, spoken):
    assert cues.to_display(raw) == display
    assert cues.to_spoken(raw) == spoken


def test_沈黙だけの行は合成しない(lines):
    silent = [ln.no for ln in lines if ln.silent and not ln.is_direction]
    assert silent == [31, 63, 70, 103, 121]


def test_演技タグは基本と状態と行タグを重複なく連結する():
    tags = cues.tags_for(126, "ノクス")
    assert tags.startswith(cues.BASE_TAGS["ノクス"])
    assert cues.LINE_TAGS[126] in tags
    assert "[in pain]" in cues.tags_for(80, "澪")
    assert "[in pain]" not in cues.tags_for(30, "澪")
    assert cues.tags_for(146, "ノクス").count("[calm]") == 1


def test_基本タグを外す行():
    assert "[calm]" not in cues.tags_for(88, "ノクス")
    assert "[whispers]" not in cues.tags_for(151, "災禍")


def test_演技タグはト書き行に付けない(lines):
    directions = {ln.no for ln in lines if ln.is_direction}
    assert not directions & set(cues.LINE_TAGS)


def test_合成テキストはタグと読みを連結する(lines):
    ln = next(x for x in lines if x.no == 16)
    assert ln.tts_text == "[battle cry][shouting] せんこうっ！！"


def test_全役に_ElevenLabs_のボイスIDがある():
    assert set(cues.VOICES) == set(cues.VOICE_NAMES) == set(cues.STABILITY)
    assert all(len(v) == 20 for v in cues.VOICES.values())


@pytest.mark.parametrize(
    ("no", "expected"),
    [(1, "01_rotary"), (33, "03_battle"), (34, "04_saika"), (153, "10_shiori"), (172, "11_dawn")],
)
def test_場面の割り当て(no, expected):
    assert cues.section_at(no, cues.SCENES) == expected


def test_演出データの行番号は台本の範囲内():
    for table in (cues.SFX, cues.FLASH, cues.LINE_TAGS):
        assert all(1 <= no <= 172 for no in table)
    assert all(name in fx.SFX_BANK for names in cues.SFX.values() for name in names)
    assert all(name is None or name in fx.BGM_BANK for _, name in cues.BGM_SECTIONS)


def test_場面画像がすべて存在する():
    for _, image_id in cues.SCENES:
        assert (render.IMAGE_DIR / f"{image_id}.jpg").is_file()


@pytest.mark.parametrize("name", sorted(fx.SFX_BANK))
def test_効果音は有限でクリップしない(name):
    x = fx.SFX_BANK[name]()
    assert len(x) > fx.SR // 10
    assert np.all(np.isfinite(x))
    assert np.max(np.abs(x)) <= 1.0


@pytest.mark.parametrize("name", sorted(fx.BGM_BANK))
def test_BGMは指定の長さで生成される(name):
    x = fx.BGM_BANK[name](5.0)
    assert abs(len(x) - 5 * fx.SR) <= fx.SR // 100
    assert np.all(np.isfinite(x))


def test_災禍の声は低く長くなる():
    x = np.sin(2 * np.pi * 300 * fx.t_axis(1.0))
    y = fx.monster_voice(x)
    assert len(y) > len(x)
    assert np.max(np.abs(y)) <= 1.0


def test_ダッキングは声がある所だけ下げる():
    voice = np.zeros(fx.SR * 4)
    voice[fx.SR : fx.SR * 2] = 0.5
    g = fx.duck_curve(voice, 0.5)
    assert g[int(fx.SR * 1.5)] == pytest.approx(0.5, abs=0.01)
    assert g[int(fx.SR * 3.5)] == pytest.approx(1.0)


@pytest.mark.parametrize(("sec", "text"), [(0, "0:00:00.00"), (61.5, "0:01:01.50"), (3725.25, "1:02:05.25")])
def test_ASSの時刻表記(sec, text):
    assert render.ass_time(sec) == text


@pytest.mark.parametrize(
    ("text", "width", "expected"),
    [
        ("短い。", 10, "短い。"),
        ("やだって言ってるの！　澪を置いていかない。", 12, r"やだって言ってるの！\N澪を置いていかない。"),
        ("あいうえおかきくけこさしすせそ", 10, r"あいうえおかきくけこ\Nさしすせそ"),
        ("ねえ……返事して……！", 6, r"ねえ……\N返事して……！"),
    ],
)
def test_日本語の折り返し(text, width, expected):
    assert render.wrap_jp(text, width) == expected


def test_ASSは波括弧をエスケープする():
    assert render.ass_escape("{x}") == "｛x｝"
