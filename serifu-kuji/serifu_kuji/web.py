"""セリフくじをブラウザで開く。"""

from __future__ import annotations

import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from serifu_kuji.catalog import Catalog, CatalogError, Line, load_catalog
from serifu_kuji.history import Favorites, FavoritesError

APP_ROOT = Path(__file__).resolve().parent.parent
WEB_ROOT = APP_ROOT / "web"
DATA_PATH = APP_ROOT / "data" / "lines"
FAV_PATH = APP_ROOT / "data" / "favorites.json"

_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}


def line_payload(line: Line) -> dict[str, object]:
    """台本1件をJSON向けの辞書にする。"""
    return {
        "id": line.id,
        "kind": line.kind,
        "text": line.text,
        "speaker": line.speaker,
        "tags": list(line.tags),
        "mood": line.mood,
        "seconds": line.seconds,
        "gender": line.gender,
        "category": line.category,
        "tone": line.tone,
        "situation": line.situation,
    }


def create_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    data_path: Path = DATA_PATH,
    fav_path: Path = FAV_PATH,
    web_root: Path = WEB_ROOT,
) -> ThreadingHTTPServer:
    """台本APIとHTMLを配信するサーバーを作る。"""
    handler = _build_handler(data_path, fav_path, web_root)
    ports = [0] if port == 0 else [port, *range(port + 1, port + 20)]
    last_error: OSError | None = None
    for candidate in ports:
        try:
            return ThreadingHTTPServer((host, candidate), handler)
        except OSError as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def main() -> None:
    """ブラウザでセリフくじを開く。"""
    server = create_server()
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(url)
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
        server.server_close()


def _build_handler(
    data_path: Path,
    fav_path: Path,
    web_root: Path,
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        """HTMLと台本APIを返す。"""

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/api/lines":
                self._lines()
                return
            if path == "/api/favorites":
                self._read_favorites()
                return
            self._file("/index.html" if path == "/" else path)

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/api/draw":
                self._draw()
                return
            if path == "/api/favorites":
                self._toggle_favorite()
                return
            self._json(404, {"error": "その操作はありません"})

        def log_message(self, fmt: str, *args: object) -> None:
            return

        def _lines(self) -> None:
            try:
                catalog = _catalog(data_path)
                query = parse_qs(urlparse(self.path).query)
                selected = catalog.filter(
                    kind=_query_value(query, "kind"),
                    speaker=_query_value(query, "speaker"),
                    tag=_query_value(query, "tag"),
                    mood=_query_value(query, "mood"),
                    seconds=_query_value(query, "seconds"),
                    gender=_query_value(query, "gender"),
                    category=_query_value(query, "category"),
                    tone=_query_value(query, "tone"),
                )
            except CatalogError as exc:
                self._json(400, {"error": str(exc)})
                return
            self._json(200, {"lines": [line_payload(line) for line in selected]})

        def _draw(self) -> None:
            body = self._read_json()
            if body is None:
                return
            avoid = body.get("avoid_ids", [])
            if not isinstance(avoid, list) or not all(isinstance(item, str) for item in avoid):
                self._json(400, {"error": "avoid_ids は文字列のリストである必要があります"})
                return
            try:
                catalog = _catalog(data_path)
                line = catalog.draw(
                    kind=_blank_to_none(body.get("kind")),
                    speaker=_blank_to_none(body.get("speaker")),
                    tag=_blank_to_none(body.get("tag")),
                    mood=_blank_to_none(body.get("mood")),
                    seconds=body.get("seconds"),
                    gender=_blank_to_none(body.get("gender")),
                    category=_blank_to_none(body.get("category")),
                    tone=_blank_to_none(body.get("tone")),
                    avoid_ids=set(avoid),
                )
            except CatalogError as exc:
                self._json(400, {"error": str(exc)})
                return
            self._json(200, {"line": line_payload(line)})

        def _read_favorites(self) -> None:
            try:
                favorites = Favorites(fav_path)
            except FavoritesError as exc:
                self._json(400, {"error": str(exc)})
                return
            self._json(200, {"ids": favorites.ids()})

        def _toggle_favorite(self) -> None:
            body = self._read_json()
            if body is None:
                return
            line_id = body.get("id")
            if not isinstance(line_id, str):
                self._json(400, {"error": "id は文字列である必要があります"})
                return
            try:
                favorites = Favorites(fav_path)
                starred = favorites.toggle(line_id)
            except FavoritesError as exc:
                self._json(400, {"error": str(exc)})
                return
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
                return
            self._json(200, {"starred": starred, "ids": favorites.ids()})

        def _file(self, url_path: str) -> None:
            file_path = _safe_file(web_root, url_path)
            if file_path is None:
                self._json(404, {"error": "ページが見つかりません"})
                return
            content = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", _TYPES.get(file_path.suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)

        def _read_json(self) -> dict[str, object] | None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._json(400, {"error": "送信内容を読めませんでした"})
                return None
            raw = self.rfile.read(length)
            try:
                data = json.loads(raw.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                self._json(400, {"error": "送信内容を読めませんでした"})
                return None
            if not isinstance(data, dict):
                self._json(400, {"error": "送信内容を読めませんでした"})
                return None
            return data

        def _json(self, status: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def _catalog(data_path: Path) -> Catalog:
    return Catalog(load_catalog(data_path))


def _query_value(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    return _blank_to_none(values[0])


def _blank_to_none(value: object) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise CatalogError("絞り込みの値は文字列である必要があります")
    return value


def _safe_file(web_root: Path, url_path: str) -> Path | None:
    root = web_root.resolve()
    relative = url_path.lstrip("/")
    if relative == "":
        relative = "index.html"
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        return None
    return candidate
