"""
アプリ全体フォントサイズ設定の永続化と、app_font ヘルパーの動作を検証する。
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QFont


@pytest.fixture
def temp_settings():
    with tempfile.TemporaryDirectory() as tmp:
        ini = Path(tmp) / "test.ini"
        ts = QSettings(str(ini), QSettings.Format.IniFormat)
        with patch("src.ui.settings.get_settings", return_value=ts):
            yield ts
        ts.sync()


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


class TestAppFontSizeSetting:
    def test_未設定は0(self, temp_settings) -> None:
        from src.ui.settings import get_app_font_size
        assert get_app_font_size() == 0

    def test_0は上書きなし(self, temp_settings) -> None:
        from src.ui.settings import get_app_font_size, set_app_font_size
        set_app_font_size(0)
        temp_settings.sync()
        assert get_app_font_size() == 0

    def test_範囲外は丸められる_下(self, temp_settings) -> None:
        from src.ui.settings import get_app_font_size, set_app_font_size
        set_app_font_size(4)  # 4 → 8 へ丸め
        temp_settings.sync()
        assert get_app_font_size() == 8

    def test_範囲外は丸められる_上(self, temp_settings) -> None:
        from src.ui.settings import get_app_font_size, set_app_font_size
        set_app_font_size(100)
        temp_settings.sync()
        assert get_app_font_size() == 24

    def test_正常範囲は保持(self, temp_settings) -> None:
        from src.ui.settings import get_app_font_size, set_app_font_size
        for v in (8, 10, 14, 20, 24):
            set_app_font_size(v)
            temp_settings.sync()
            assert get_app_font_size() == v

    def test_負値は0として扱う(self, temp_settings) -> None:
        from src.ui.settings import get_app_font_size, set_app_font_size
        set_app_font_size(-5)
        temp_settings.sync()
        assert get_app_font_size() == 0


class TestAppFontHelper:
    def test_remember_and_restore(self, qapp) -> None:
        from src.ui import app_font
        # モジュール変数をテスト毎にリセット
        app_font._default_font = None
        original = QFont(qapp.font())
        app_font.remember_default_app_font()
        app_font.apply_override(20)
        assert qapp.font().pointSize() == 20
        app_font.restore_default()
        assert qapp.font().pointSize() == original.pointSize()

    def test_apply_from_settings_0でリストア(self, qapp, temp_settings) -> None:
        from src.ui import app_font
        from src.ui.settings import set_app_font_size
        app_font._default_font = None
        app_font.remember_default_app_font()
        original_size = qapp.font().pointSize()
        # 一旦上書き
        set_app_font_size(18)
        app_font.apply_from_settings()
        assert qapp.font().pointSize() == 18
        # 0 でリストア
        set_app_font_size(0)
        app_font.apply_from_settings()
        assert qapp.font().pointSize() == original_size
