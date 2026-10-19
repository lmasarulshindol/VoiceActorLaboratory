"""同梱台本がスキーマと構成どおりかを確認する。"""

from collections import Counter
from pathlib import Path

import pytest

from serifu_kuji.catalog import Catalog, load_catalog

DATA = Path(__file__).resolve().parents[1] / "data" / "lines"
EXPECTED_FILES = {
    "セリフ_男性.yaml": ("dialogue", "male"),
    "セリフ_女性.yaml": ("dialogue", "female"),
    "セリフ_不問.yaml": ("dialogue", "any"),
    "ナレーション_男性.yaml": ("narration", "male"),
    "ナレーション_女性.yaml": ("narration", "female"),
    "ナレーション_不問.yaml": ("narration", "any"),
}

NARRATION_GENRES = [
    "企業VP", "商品・サービス紹介", "テレビCM", "ラジオCM", "ドキュメンタリー",
    "情報番組", "バラエティ", "旅・グルメ番組", "スポーツ", "映画・作品予告",
    "教育・eラーニング", "医療・科学技術", "オーディオブック", "観光・施設ガイド",
    "アナウンス", "イベント・式典", "Web・YouTube動画", "ゲーム内ナレーション",
]
DIALOGUE_GENRES = [
    "日常", "恋愛", "友情", "対立", "バトル", "悲哀",
    "励まし", "命令・指示", "独白", "コメディ", "ホラー", "ビジネス",
]
TONES = [
    "ストレート", "シリアス", "ダイナミック", "ソフト", "クール", "ゴージャス",
    "エモーショナル", "コミカル", "ミステリアス", "フレンドリー", "ハイテンション", "ウィスパー",
]
TAGS = ["静", "動", "笑", "涙", "緊張", "温"]
GENDERS = ["male", "female", "any"]
TEXT_RANGE = {10: (35, 55), 20: (80, 110), 30: (125, 170)}

# 単体で絞ったとき、各性別で最低これだけ候補が残ること
MIN_PER_GENDER = 5
MIN_GENDER_TOTAL = 30


def _lines(kind: str):
    return [line for line in load_catalog(DATA) if line.kind == kind]


def test_ファイルはジャンルと性別で分かれている():
    assert {p.name for p in DATA.glob("*.yaml")} == set(EXPECTED_FILES)
    for name, (kind, gender) in EXPECTED_FILES.items():
        lines = load_catalog(DATA / name)
        assert lines, name
        assert {(line.kind, line.gender) for line in lines} == {(kind, gender)}, name


def test_ジャンルと読み方の一覧():
    catalog = Catalog(load_catalog(DATA))
    assert catalog.categories("narration") == NARRATION_GENRES
    assert catalog.categories("dialogue") == DIALOGUE_GENRES
    assert set(catalog.tones()) == set(TONES)
    assert set(catalog.tags()) == set(TAGS)


def test_各行に読み方と状況があり字数が秒数に合う():
    seen: set[str] = set()
    for line in load_catalog(DATA):
        assert line.id not in seen, line.id
        seen.add(line.id)
        assert line.tone in TONES, line.id
        assert 20 <= len(line.situation) <= 40, line.id
        assert line.seconds in TEXT_RANGE, line.id
        low, high = TEXT_RANGE[line.seconds]
        assert low <= len(line.text) <= high, (line.id, len(line.text))
        assert 1 <= len(line.tags) <= 2 and set(line.tags) <= set(TAGS), line.id


@pytest.mark.parametrize(
    ("kind", "genres"),
    [("dialogue", DIALOGUE_GENRES), ("narration", NARRATION_GENRES)],
    ids=["セリフ", "ナレーション"],
)
def test_単体で絞っても各性別に候補が残る(kind: str, genres: list[str]):
    lines = _lines(kind)
    by_gender = Counter(line.gender for line in lines)
    for gender in GENDERS:
        assert by_gender[gender] >= MIN_GENDER_TOTAL, (kind, gender, by_gender[gender])

    category_gender = Counter((line.category, line.gender) for line in lines)
    tone_gender = Counter((line.tone, line.gender) for line in lines)
    tag_gender = Counter((tag, line.gender) for line in lines for tag in line.tags)
    short = []
    for gender in GENDERS:
        short += [(c, gender, category_gender[(c, gender)]) for c in genres if category_gender[(c, gender)] < MIN_PER_GENDER]
        short += [(t, gender, tone_gender[(t, gender)]) for t in TONES if tone_gender[(t, gender)] < MIN_PER_GENDER]
        short += [(t, gender, tag_gender[(t, gender)]) for t in TAGS if tag_gender[(t, gender)] < MIN_PER_GENDER]
    assert not short, (kind, short)


@pytest.mark.parametrize("kind", ["dialogue", "narration"], ids=["セリフ", "ナレーション"])
def test_想定時間が偏っていない(kind: str):
    lines = _lines(kind)
    by_seconds = Counter(line.seconds for line in lines)
    assert set(by_seconds) == {10, 20, 30}
    assert min(by_seconds.values()) >= len(lines) // 4
