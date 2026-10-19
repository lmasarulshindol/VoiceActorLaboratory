"""台本カタログの読み込み・絞り込み・抽選。"""

from pathlib import Path
import random

import pytest

from serifu_kuji.catalog import Catalog, CatalogError, Line, load_catalog


_SAMPLE = """\
lines:
  - id: n001
    kind: narration
    text: "夜が更けた。"
    tags: [夜, 静]
    mood: calm
  - id: d001
    kind: dialogue
    speaker: 凛
    text: "まだ起きてる。"
    tags: [夜]
    mood: soft
  - id: d002
    kind: dialogue
    speaker: 透
    text: "少しだけ。"
    tags: [朝, 静]
"""

_ALL_IDS = ["n001", "d001", "d002"]


def _write(tmp_path: Path, text: str, name: str = "lines.yaml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _catalog(tmp_path: Path) -> Catalog:
    return Catalog(load_catalog(_write(tmp_path, _SAMPLE)))


def test_正常系_dialogueとnarrationを読み込める(tmp_path: Path) -> None:
    lines = load_catalog(_write(tmp_path, _SAMPLE))
    assert lines == [
        Line(
            id="n001",
            kind="narration",
            text="夜が更けた。",
            speaker="",
            tags=("夜", "静"),
            mood="calm",
        ),
        Line(
            id="d001",
            kind="dialogue",
            text="まだ起きてる。",
            speaker="凛",
            tags=("夜",),
            mood="soft",
        ),
        Line(
            id="d002",
            kind="dialogue",
            text="少しだけ。",
            speaker="透",
            tags=("朝", "静"),
            mood="",
        ),
    ]


def test_省略フィールドは既定値になる(tmp_path: Path) -> None:
    text = """\
lines:
  - id: d010
    kind: dialogue
    text: "うん。"
"""
    line = load_catalog(_write(tmp_path, text))[0]
    assert line == Line(id="d010", kind="dialogue", text="うん。")
    assert line.speaker == ""
    assert line.tags == ()
    assert line.mood == ""


def test_話者タグムードは登場順で一意になる(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    assert catalog.lines == tuple(load_catalog(_write(tmp_path, _SAMPLE, "again.yaml")))
    assert catalog.speakers() == ["凛", "透"]
    assert catalog.tags() == ["夜", "静", "朝"]
    assert catalog.moods() == ["calm", "soft"]


@pytest.mark.parametrize(
    ("kwargs", "expected_ids"),
    [
        ({"kind": "narration"}, ["n001"]),
        ({"kind": "dialogue"}, ["d001", "d002"]),
        ({"speaker": "凛"}, ["d001"]),
        ({"speaker": "透"}, ["d002"]),
        ({"tag": "静"}, ["n001", "d002"]),
        ({"tag": "夜"}, ["n001", "d001"]),
        ({"mood": "soft"}, ["d001"]),
        ({"mood": "calm"}, ["n001"]),
        ({"kind": "dialogue", "tag": "夜"}, ["d001"]),
        ({"kind": "narration", "mood": "calm", "tag": "静"}, ["n001"]),
    ],
)
def test_フィルタ条件に合う行だけ返す(
    tmp_path: Path,
    kwargs: dict[str, str],
    expected_ids: list[str],
) -> None:
    matched = _catalog(tmp_path).filter(**kwargs)
    assert [line.id for line in matched] == expected_ids


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"kind": None, "speaker": None, "tag": None, "mood": None},
        {"kind": "", "speaker": "", "tag": "", "mood": ""},
    ],
)
def test_空文字とNoneは絞り込まない(tmp_path: Path, kwargs: dict[str, str | None]) -> None:
    matched = _catalog(tmp_path).filter(**kwargs)
    assert [line.id for line in matched] == _ALL_IDS


def test_drawはシードで決定的に1件選ぶ(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    drawn = catalog.draw(rng=random.Random(0))
    assert drawn == random.Random(0).choice(list(catalog.lines))
    assert drawn.id == "d001"


def test_avoid_idsで別候補を選ぶ(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    without = catalog.draw(rng=random.Random(0))
    with_avoid = catalog.draw(avoid_ids={without.id}, rng=random.Random(0))
    assert without.id == "d001"
    assert with_avoid.id == "d002"


@pytest.mark.parametrize(
    ("kwargs", "expected_id"),
    [
        ({"avoid_ids": {"n001", "d001", "d002"}}, "d001"),
        ({"speaker": "透", "avoid_ids": {"d002"}}, "d002"),
    ],
)
def test_他に候補が無いときavoidを無視して繰り返す(
    tmp_path: Path,
    kwargs: dict[str, object],
    expected_id: str,
) -> None:
    drawn = _catalog(tmp_path).draw(rng=random.Random(0), **kwargs)
    assert drawn.id == expected_id


def test_空のlinesは読み込めてdrawは該当なし(tmp_path: Path) -> None:
    lines = load_catalog(_write(tmp_path, "lines: []\n"))
    assert lines == []
    catalog = Catalog(lines)
    assert catalog.lines == ()
    assert catalog.speakers() == []
    assert catalog.tags() == []
    assert catalog.moods() == []
    with pytest.raises(CatalogError, match="該当するセリフがありません"):
        catalog.draw(rng=random.Random(0))


def test_フォルダを渡すと中のYAMLを名前順に結合する(tmp_path: Path) -> None:
    folder = tmp_path / "lines"
    folder.mkdir()
    _write(folder, "lines:\n  - {id: b1, kind: narration, text: 'B'}\n", "b.yaml")
    _write(folder, "lines:\n  - {id: a1, kind: dialogue, text: 'A'}\n", "a.yaml")
    _write(folder, "lines:\n  - {id: c1, kind: dialogue, text: 'C'}\n", "c.yml")
    _write(folder, "not yaml", "memo.txt")
    assert [line.id for line in load_catalog(folder)] == ["a1", "b1", "c1"]


def test_フォルダ内でidが重複するとCatalogError(tmp_path: Path) -> None:
    folder = tmp_path / "lines"
    folder.mkdir()
    _write(folder, "lines:\n  - {id: x, kind: narration, text: 'B'}\n", "b.yaml")
    _write(folder, "lines:\n  - {id: x, kind: dialogue, text: 'A'}\n", "a.yaml")
    with pytest.raises(CatalogError, match="id が重複"):
        load_catalog(folder)


def test_空のフォルダはCatalogError(tmp_path: Path) -> None:
    folder = tmp_path / "lines"
    folder.mkdir()
    with pytest.raises(CatalogError, match="YAMLがありません"):
        load_catalog(folder)


def test_ファイルが無いとCatalogError(tmp_path: Path) -> None:
    with pytest.raises(CatalogError, match="台本ファイルを読めません"):
        load_catalog(tmp_path / "missing.yaml")


def test_壊れたYAMLはCatalogError(tmp_path: Path) -> None:
    path = _write(tmp_path, "lines: [\n  - id: [\n")
    with pytest.raises(CatalogError, match="YAMLとして解釈できません"):
        load_catalog(path)


@pytest.mark.parametrize(
    "body",
    [
        "",
        "null\n",
        "[]\n",
        "42\n",
        "title: only\n",
        "lines: {}\n",
        "lines:\n",
    ],
)
def test_カタログ構造が不正ならCatalogError(tmp_path: Path, body: str) -> None:
    with pytest.raises(CatalogError):
        load_catalog(_write(tmp_path, body))


@pytest.mark.parametrize(
    "body",
    [
        """\
lines:
  - id: ""
    kind: narration
    text: "あ"
""",
        """\
lines:
  - id: 1
    kind: narration
    text: "あ"
""",
        """\
lines:
  - kind: narration
    text: "あ"
""",
        """\
lines:
  - id: a
    kind: narration
    text: "あ"
  - id: a
    kind: dialogue
    text: "い"
""",
        """\
lines:
  - id: a
    kind: monologue
    text: "あ"
""",
        """\
lines:
  - id: a
    kind: narration
    text: ""
""",
        """\
lines:
  - id: a
    kind: narration
""",
        """\
lines:
  - id: a
    kind: narration
    text: 1
""",
        """\
lines:
  - id: a
    kind: narration
    text: "あ"
    tags: [1]
""",
        """\
lines:
  - id: a
    kind: narration
    text: "あ"
    tags: 夜
""",
        """\
lines:
  - "nope"
""",
        """\
lines:
  - id: a
    kind: dialogue
    speaker: 1
    text: "あ"
""",
        """\
lines:
  - id: a
    kind: narration
    text: "あ"
    mood: 1
""",
    ],
)
def test_行の内容が不正ならCatalogError(tmp_path: Path, body: str) -> None:
    with pytest.raises(CatalogError):
        load_catalog(_write(tmp_path, body))


def test_該当ゼロでdrawはCatalogError(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    assert catalog.filter(speaker="存在しない") == []
    with pytest.raises(CatalogError, match="該当するセリフがありません"):
        catalog.draw(speaker="存在しない", rng=random.Random(0))


@pytest.mark.parametrize("kind", ["monologue", "DIALOGUE", "narration "])
@pytest.mark.parametrize("method", ["filter", "draw"])
def test_不正なkindはCatalogError(tmp_path: Path, kind: str, method: str) -> None:
    catalog = _catalog(tmp_path)
    with pytest.raises(CatalogError, match="kind"):
        getattr(catalog, method)(kind=kind)


def test_rng未指定でも1件抽選できる(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[random.Random] = []

    class _TrackingRandom(random.Random):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)
            created.append(self)

    monkeypatch.setattr("serifu_kuji.catalog.random.Random", _TrackingRandom)
    catalog = _catalog(tmp_path)
    drawn = catalog.draw()
    assert len(created) == 1
    assert drawn in catalog.lines


def test_想定時間と性別とサブカテゴリで絞れる(tmp_path: Path) -> None:
    catalog = Catalog(
        load_catalog(
            _write(
                tmp_path,
                """
lines:
  - id: n1
    kind: narration
    text: "夜。"
    seconds: 10
    gender: female
    category: 情景
  - id: d1
    kind: dialogue
    speaker: リン
    text: "待って。"
    seconds: 30
    gender: male
    category: 緊迫
  - id: d2
    kind: dialogue
    speaker: 語り
    text: "進んでください。"
    seconds: "20"
    gender: any
    category: 案内
""",
            )
        )
    )
    assert [line.seconds for line in catalog.lines] == [10, 30, 20]
    assert catalog.categories("narration") == ["情景"]
    assert catalog.categories("dialogue") == ["緊迫", "案内"]
    # 並びは id 順（d1, d2, n1）
    assert catalog.categories() == ["緊迫", "案内", "情景"]
    assert [line.id for line in catalog.filter(seconds=10)] == ["n1"]
    assert [line.id for line in catalog.filter(seconds="30")] == ["d1"]
    assert [line.id for line in catalog.filter(gender="any")] == ["d2"]
    assert [line.id for line in catalog.filter(category="緊迫")] == ["d1"]
    assert catalog.tones() == []
    assert catalog.filter(tone="ソフト") == []
    drawn = catalog.draw(seconds=20, gender="any", category="案内", rng=random.Random(0))
    assert drawn.id == "d2"


@pytest.mark.parametrize(
    "body",
    [
        "lines:\n  - id: a\n    kind: narration\n    text: あ\n    seconds: 15\n",
        "lines:\n  - id: a\n    kind: narration\n    text: あ\n    seconds: 十\n",
        "lines:\n  - id: a\n    kind: narration\n    text: あ\n    gender: other\n",
    ],
)
def test_想定時間と性別が不正ならCatalogError(tmp_path: Path, body: str) -> None:
    with pytest.raises(CatalogError):
        load_catalog(_write(tmp_path, body))


def test_読み方で絞れる(tmp_path: Path) -> None:
    catalog = Catalog(
        load_catalog(
            _write(
                tmp_path,
                """
lines:
  - id: a
    kind: dialogue
    text: "ねえ。"
    tone: ソフト
    situation: 夜の部屋で
  - id: b
    kind: dialogue
    text: "行くぞ。"
    tone: ダイナミック
  - id: c
    kind: narration
    text: "朝が来る。"
    tone: ソフト
""",
            )
        )
    )
    assert catalog.tones() == ["ソフト", "ダイナミック"]
    assert [line.id for line in catalog.filter(tone="ソフト")] == ["a", "c"]
    assert catalog.lines[0].situation == "夜の部屋で"
    assert catalog.lines[1].situation == ""
    drawn = catalog.draw(tone="ダイナミック", rng=random.Random(0))
    assert drawn.id == "b"


def test_絞り込みの想定時間と性別が不正ならCatalogError(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    with pytest.raises(CatalogError, match="想定時間"):
        catalog.filter(seconds=15)
    with pytest.raises(CatalogError, match="gender"):
        catalog.draw(gender="other")
