"""
アプリ設定の永続化。QSettings でテーマ・フォント・最近開いたプロジェクト等を保存する。
"""
from PyQt6.QtCore import QSettings

ORG = "VoiceActorLaboratory"
APP = "VoiceActorLaboratory"


def get_settings() -> QSettings:
    return QSettings(ORG, APP)


def get_theme() -> str:
    """light / dark"""
    return get_settings().value("theme", "light", type=str)


def set_theme(theme: str) -> None:
    get_settings().setValue("theme", theme)


def get_script_font_size() -> int:
    return get_settings().value("script_font_size", 14, type=int)


def set_script_font_size(size: int) -> None:
    get_settings().setValue("script_font_size", size)


def get_recent_projects() -> list[str]:
    v = get_settings().value("recent_projects", [])
    if isinstance(v, str):
        return [v] if v else []
    return list(v) if v else []


def add_recent_project(path: str, max_count: int = 5) -> None:
    rec = get_recent_projects()
    if path in rec:
        rec.remove(path)
    rec.insert(0, path)
    get_settings().setValue("recent_projects", rec[:max_count])


def get_export_use_friendly_names() -> bool:
    return get_settings().value("export_friendly_names", True, type=bool)


def set_export_use_friendly_names(value: bool) -> None:
    get_settings().setValue("export_friendly_names", value)


def get_input_device_id() -> int | None:
    """録音入力デバイス番号（sounddevice）。未設定は None（デフォルト）。"""
    v = get_settings().value("input_device_id", None)
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def set_input_device_id(device_id: int | None) -> None:
    get_settings().setValue("input_device_id", device_id)


def get_output_device_id() -> str | None:
    """再生出力デバイス ID（Qt QAudioDevice.id() のバイト列を base64 などで保存）。未設定は None。"""
    return get_settings().value("output_device_id", None, type=str)


def set_output_device_id(device_id: str | None) -> None:
    get_settings().setValue("output_device_id", device_id)


def get_waveform_design() -> int:
    """波形デザイン ID（0 〜 9）。"""
    v = get_settings().value("waveform_design", 0, type=int)
    return max(0, min(9, v))


def set_waveform_design(design_id: int) -> None:
    get_settings().setValue("waveform_design", max(0, min(9, design_id)))
