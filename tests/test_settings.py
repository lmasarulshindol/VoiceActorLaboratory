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


class TestPrerollLevelMeterExportTemplate:
    def test_get_preroll_seconds_既定は0(self, temp_settings) -> None:
        from src.ui.settings import get_preroll_seconds
        assert get_preroll_seconds() == 0

    def test_set_preroll_seconds_0_3_5のみ許容(self, temp_settings) -> None:
        from src.ui.settings import get_preroll_seconds, set_preroll_seconds
        set_preroll_seconds(3)
        temp_settings.sync()
        assert get_preroll_seconds() == 3
        set_preroll_seconds(5)
        temp_settings.sync()
        assert get_preroll_seconds() == 5
        # 7 など不正値は 0 に正規化
        set_preroll_seconds(7)
        temp_settings.sync()
        assert get_preroll_seconds() == 0

    def test_level_meter_enabled_既定True(self, temp_settings) -> None:
        from src.ui.settings import get_level_meter_enabled, set_level_meter_enabled
        assert get_level_meter_enabled() is True
        set_level_meter_enabled(False)
        temp_settings.sync()
        assert get_level_meter_enabled() is False

    def test_export_name_template_往復(self, temp_settings) -> None:
        from src.ui.settings import get_export_name_template, set_export_name_template
        assert get_export_name_template() == ""
        set_export_name_template("{project}_{n}")
        temp_settings.sync()
        assert get_export_name_template() == "{project}_{n}"
        set_export_name_template("")
        temp_settings.sync()
        assert get_export_name_template() == ""


class TestLoudnessAndFormatSettings:
    """A/C 新設の LUFS ターゲット・自動解析・MP3 ビットレート・エクスポート後処理。"""

    def test_get_lufs_target_既定は_minus16(self, temp_settings) -> None:
        from src.ui.settings import get_lufs_target
        assert get_lufs_target() == -16.0

    def test_lufs_target_往復と許容値外の正規化(self, temp_settings) -> None:
        from src.ui.settings import get_lufs_target, set_lufs_target
        set_lufs_target(-23.0)
        temp_settings.sync()
        assert get_lufs_target() == -23.0
        set_lufs_target(-14.0)
        temp_settings.sync()
        assert get_lufs_target() == -14.0
        # 許容値外は -16 に丸める
        set_lufs_target(-99.0)
        temp_settings.sync()
        assert get_lufs_target() == -16.0

    def test_auto_analyze_lufs_既定True(self, temp_settings) -> None:
        from src.ui.settings import get_auto_analyze_lufs, set_auto_analyze_lufs
        assert get_auto_analyze_lufs() is True
        set_auto_analyze_lufs(False)
        temp_settings.sync()
        assert get_auto_analyze_lufs() is False

    def test_mp3_bitrate_既定は192(self, temp_settings) -> None:
        from src.ui.settings import get_mp3_bitrate, set_mp3_bitrate
        assert get_mp3_bitrate() == 192
        set_mp3_bitrate(320)
        temp_settings.sync()
        assert get_mp3_bitrate() == 320
        set_mp3_bitrate(999)
        temp_settings.sync()
        assert get_mp3_bitrate() == 192

    def test_export_format_既定はwav(self, temp_settings) -> None:
        from src.ui.settings import get_export_format, set_export_format
        assert get_export_format() == "wav"
        set_export_format("mp3")
        temp_settings.sync()
        assert get_export_format() == "mp3"
        set_export_format("bogus")
        temp_settings.sync()
        assert get_export_format() == "wav"

    def test_export_apply_flags_既定False_往復(self, temp_settings) -> None:
        from src.ui.settings import (
            get_export_apply_lufs,
            set_export_apply_lufs,
            get_export_apply_trim_silence,
            set_export_apply_trim_silence,
            get_export_apply_noise_reduce,
            set_export_apply_noise_reduce,
        )
        assert get_export_apply_lufs() is False
        assert get_export_apply_trim_silence() is False
        assert get_export_apply_noise_reduce() is False
        set_export_apply_lufs(True)
        set_export_apply_trim_silence(True)
        set_export_apply_noise_reduce(True)
        temp_settings.sync()
        assert get_export_apply_lufs() is True
        assert get_export_apply_trim_silence() is True
        assert get_export_apply_noise_reduce() is True
