"""
settings モジュールの単体テスト。export_last_dir 等の get/set を検証。
"""
import tempfile
from pathlib import Path
from unittest.mock import patch
import pytest
from PyQt6.QtCore import QSettings


@pytest.fixture
def temp_settings():
    """一時 INI を使う QSettings を返す。get_settings をパッチする。"""
    with tempfile.TemporaryDirectory() as tmp:
        ini = Path(tmp) / "test.ini"
        test_settings = QSettings(str(ini), QSettings.Format.IniFormat)
        with patch("src.ui.settings.get_settings", return_value=test_settings):
            yield test_settings
        test_settings.sync()


class TestExportLastDir:
    def test_get_export_last_dir_未設定は空(self, temp_settings) -> None:
        from src.ui.settings import get_export_last_dir
        assert get_export_last_dir() == ""

    def test_set_get_export_last_dir_往復(self, temp_settings) -> None:
        from src.ui.settings import get_export_last_dir, set_export_last_dir
        set_export_last_dir("/path/to/export")
        temp_settings.sync()
        assert get_export_last_dir() == "/path/to/export"

    def test_set_export_last_dir_空で上書き(self, temp_settings) -> None:
        from src.ui.settings import get_export_last_dir, set_export_last_dir
        set_export_last_dir("/first")
        set_export_last_dir("")
        temp_settings.sync()
        assert get_export_last_dir() == ""


class TestMainWindowGeometry:
    def test_get_main_window_geometry_未設定はNone(self, temp_settings) -> None:
        from src.ui.settings import get_main_window_geometry
        assert get_main_window_geometry() is None

    def test_set_get_main_window_geometry_往復(self, temp_settings) -> None:
        from src.ui.settings import get_main_window_geometry, set_main_window_geometry
        data = b"geometry_data_placeholder_123"
        set_main_window_geometry(data)
        temp_settings.sync()
        assert get_main_window_geometry() == data
