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


class TestSettingsFallback:
    def test_get_theme_不正値はlight(self, temp_settings) -> None:
        from src.ui.settings import get_theme, set_theme, get_settings
        get_settings().setValue("theme", "invalid")
        temp_settings.sync()
        assert get_theme() == "light"
        set_theme("dark")
        assert get_theme() == "dark"

    def test_get_recording_mode_不正値はbulk(self, temp_settings) -> None:
        from src.ui.settings import get_recording_mode, set_recording_mode, get_settings
        get_settings().setValue("recording_mode", "unknown")
        temp_settings.sync()
        assert get_recording_mode() == "bulk"

    def test_get_take_list_filter_不正値はall(self, temp_settings) -> None:
        from src.ui.settings import get_take_list_filter, get_settings
        get_settings().setValue("take_list_filter", "invalid")
        temp_settings.sync()
        assert get_take_list_filter() == "all"

    def test_get_main_window_splitter_sizes_1要素や3要素やfloatを正規化(self, temp_settings) -> None:
        from src.ui.settings import get_main_window_splitter_sizes, set_main_window_splitter_sizes, get_settings
        get_settings().setValue("main_window_splitter_sizes", [400])
        temp_settings.sync()
        sizes = get_main_window_splitter_sizes()
        assert sizes == [400]
        get_settings().setValue("main_window_splitter_sizes", [300, 500, 100])
        temp_settings.sync()
        sizes = get_main_window_splitter_sizes()
        assert len(sizes) == 3
        assert all(isinstance(x, int) for x in sizes)
