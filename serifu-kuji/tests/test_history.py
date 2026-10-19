"""抽選履歴とお気に入りのテスト。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from serifu_kuji.history import DrawHistory, Favorites, FavoritesError


def test_履歴は新しい順で同じidも残る() -> None:
    history = DrawHistory(limit=10)
    for line_id in ("a", "a", "b"):
        history.record(line_id)
    assert history.recent() == ["b", "a", "a"]


@pytest.mark.parametrize(
    ("limit", "recorded", "expected"),
    [
        (2, ["a", "b", "c"], ["c", "b"]),
        (1, ["a", "b"], ["b"]),
        (3, ["a", "b"], ["b", "a"]),
    ],
)
def test_上限を超えると古い履歴が落ちる(
    limit: int, recorded: list[str], expected: list[str]
) -> None:
    history = DrawHistory(limit=limit)
    for line_id in recorded:
        history.record(line_id)
    assert history.recent() == expected


@pytest.mark.parametrize(
    ("recorded", "n", "expected"),
    [
        (["a", "b", "c", "d"], 2, {"d", "c"}),
        (["a"], 5, {"a"}),
        (["a", "a", "b"], 2, {"b", "a"}),
    ],
)
def test_avoid_idsは直近n件を返す(
    recorded: list[str], n: int, expected: set[str]
) -> None:
    history = DrawHistory()
    for line_id in recorded:
        history.record(line_id)
    assert history.avoid_ids(n) == expected


def test_空のidは記録できない() -> None:
    history = DrawHistory()
    with pytest.raises(ValueError):
        history.record("")
    assert history.recent() == []


@pytest.mark.parametrize("limit", [0, -1, -30])
def test_limitが1未満ならValueError(limit: int) -> None:
    with pytest.raises(ValueError):
        DrawHistory(limit=limit)


@pytest.mark.parametrize("n", [0, -1])
def test_avoid_idsのnが1未満ならValueError(n: int) -> None:
    history = DrawHistory()
    history.record("a")
    with pytest.raises(ValueError):
        history.avoid_ids(n)


def test_お気に入りファイルが無ければ空(tmp_path: Path) -> None:
    favorites = Favorites(tmp_path / "nested" / "favorites.json")
    assert favorites.ids() == []
    assert favorites.contains("n001") is False


def test_toggleで追加と解除ができる(tmp_path: Path) -> None:
    path = tmp_path / "favorites.json"
    favorites = Favorites(path)
    assert favorites.toggle("n001") is True
    assert favorites.toggle("おはよう") is True
    assert favorites.ids() == ["n001", "おはよう"]
    assert favorites.contains("おはよう") is True
    assert favorites.toggle("n001") is False
    assert favorites.ids() == ["おはよう"]
    assert favorites.contains("n001") is False


def test_お気に入りは再読み込み後も残る(tmp_path: Path) -> None:
    path = tmp_path / "box" / "favorites.json"
    favorites = Favorites(path)
    favorites.toggle("n001")
    favorites.toggle("夜更かし")
    reloaded = Favorites(path)
    assert reloaded.ids() == ["n001", "夜更かし"]
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved == {"ids": ["n001", "夜更かし"]}
    assert "夜更かし" in path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "raw",
    ["{", "not-json", "", "[]", "null", '{"ids":'],
)
def test_壊れたJSONはFavoritesError(tmp_path: Path, raw: str) -> None:
    path = tmp_path / "favorites.json"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(FavoritesError):
        Favorites(path)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"ids": "n001"},
        {"ids": {"n001": True}},
        {"ids": None},
    ],
)
def test_idsがlistでなければFavoritesError(tmp_path: Path, payload: object) -> None:
    path = tmp_path / "favorites.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(FavoritesError):
        Favorites(path)


@pytest.mark.parametrize(
    "ids",
    [
        ["n001", 1],
        [None],
        [True],
        [{"id": "n001"}],
    ],
)
def test_idsに文字列以外があればFavoritesError(tmp_path: Path, ids: list[object]) -> None:
    path = tmp_path / "favorites.json"
    path.write_text(json.dumps({"ids": ids}), encoding="utf-8")
    with pytest.raises(FavoritesError):
        Favorites(path)


def test_読み込み時に重複idを除き追加順を保つ(tmp_path: Path) -> None:
    path = tmp_path / "favorites.json"
    path.write_text(
        json.dumps({"ids": ["n002", "n001", "n002", "n003", "n001"]}),
        encoding="utf-8",
    )
    assert Favorites(path).ids() == ["n002", "n001", "n003"]


def test_空文字のtoggleはValueError(tmp_path: Path) -> None:
    path = tmp_path / "favorites.json"
    favorites = Favorites(path)
    with pytest.raises(ValueError):
        favorites.toggle("")
    assert favorites.ids() == []
    assert path.exists() is False
