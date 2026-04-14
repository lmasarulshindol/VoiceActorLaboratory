"""theme_loader の単体テスト。"""
import pytest
from src.ui.theme_loader import load_stylesheet, apply_app_theme


class TestLoadStylesheet:
    def test_存在するテーマ名で内容を返す(self) -> None:
        css = load_stylesheet("light")
        assert isinstance(css, str)
        assert "WINDOW_BG" not in css or "{{" not in css

    def test_darkで内容を返す(self) -> None:
        css = load_stylesheet("dark")
        assert isinstance(css, str)

    def test_存在しないテーマ名はlightにフォールバック(self) -> None:
        css = load_stylesheet("unknown")
        assert isinstance(css, str)
        css2 = load_stylesheet("light")
        assert css == css2

    def test_空文字テーマはlight(self) -> None:
        css = load_stylesheet("")
        assert load_stylesheet("light") == css
