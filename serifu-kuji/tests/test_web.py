"""ブラウザ配信用のAPIを確認する。"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

import pytest

from serifu_kuji.web import WEB_ROOT, create_server

SAMPLE = """
lines:
  - id: n001
    kind: narration
    speaker: ""
    text: "夜が深い。"
    tags: [夜]
    mood: calm
    seconds: 10
  - id: d001
    kind: dialogue
    speaker: リン
    text: "まだ、ここにいる。"
    tags: [夜, 静]
    mood: warm
    tone: ソフト
    situation: 夜の部屋で隣の人に
  - id: d002
    kind: dialogue
    speaker: ケン
    text: "音を、落とそう。"
    tags: [静]
    mood: calm
"""


@pytest.fixture
def base(tmp_path: Path):
    data = tmp_path / "lines.yaml"
    data.write_text(SAMPLE, encoding="utf-8")
    fav = tmp_path / "favorites.json"
    server = create_server("127.0.0.1", 0, data, fav, WEB_ROOT)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    yield url
    server.shutdown()
    server.server_close()


def test_トップページに画面がある(base: str):
    body = urlopen(f"{base}/").read().decode("utf-8")
    assert "今日のひとこと" in body
    css = urlopen(f"{base}/styles.css")
    assert css.status == 200


def test_想定時間で抽選できる(base: str):
    payload = _post(base, "/api/draw", {"seconds": 10, "avoid_ids": []})
    assert payload["line"]["seconds"] == 10


def test_読み方で絞って引ける(base: str):
    soft = _get(base, f"/api/lines?tone={quote('ソフト')}")["lines"]
    assert [line["id"] for line in soft] == ["d001"]
    assert soft[0]["situation"] == "夜の部屋で隣の人に"
    payload = _post(base, "/api/draw", {"tone": "ソフト", "avoid_ids": []})
    assert payload["line"]["id"] == "d001"


def test_台本一覧と絞り込み(base: str):
    lines = _get(base, "/api/lines")["lines"]
    assert [line["id"] for line in lines] == ["n001", "d001", "d002"]
    narration = _get(base, "/api/lines?kind=narration")["lines"]
    assert [line["id"] for line in narration] == ["n001"]


def test_抽選は候補を避けて残った1件を返す(base: str):
    payload = _post(
        base,
        "/api/draw",
        {"kind": "dialogue", "avoid_ids": ["d001"]},
    )
    assert payload["line"]["id"] == "d002"


def test_該当なしと不正な種類はエラー(base: str):
    missing = _post(base, "/api/draw", {"speaker": "いない人"}, expect=400)
    assert missing["error"] == "該当するセリフがありません"
    broken = _get(base, "/api/lines?kind=monologue", expect=400)
    assert "kind" in broken["error"]


def test_お気に入りを付け外しできる(base: str):
    assert _get(base, "/api/favorites")["ids"] == []
    added = _post(base, "/api/favorites", {"id": "d001"})
    assert added["starred"] is True
    assert added["ids"] == ["d001"]
    removed = _post(base, "/api/favorites", {"id": "d001"})
    assert removed["starred"] is False
    assert removed["ids"] == []


def test_台本ファイルの外は配らない(base: str):
    with pytest.raises(HTTPError) as caught:
        urlopen(f"{base}/../data/lines.yaml")
    assert caught.value.code == 404


def _get(base: str, path: str, expect: int = 200) -> dict:
    try:
        with urlopen(f"{base}{path}") as response:
            assert response.status == expect
            return json.load(response)
    except HTTPError as exc:
        assert exc.code == expect
        return json.load(exc)


def _post(base: str, path: str, payload: dict, expect: int = 200) -> dict:
    request = Request(
        f"{base}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request) as response:
            assert response.status == expect
            return json.load(response)
    except HTTPError as exc:
        assert exc.code == expect
        return json.load(exc)
