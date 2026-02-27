"""
アプリ設定の永続化。QSettings でテーマ・フォント・最近開いたプロジェクト等を保存する。
"""
from PyQt6.QtCore import QSettings, QByteArray

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


def get_export_last_dir() -> str:
    """前回エクスポートで選んだフォルダ。未設定は空文字。"""
    v = get_settings().value("export_last_dir", "", type=str)
    return v or ""


def set_export_last_dir(path: str) -> None:
    """エクスポート先として選んだフォルダを記憶する。"""
    get_settings().setValue("export_last_dir", path or "")


def get_last_project_dialog_dir() -> str:
    """前回「新規プロジェクト」「プロジェクトを開く」で選んだフォルダ。未設定は空文字。"""
    v = get_settings().value("last_project_dialog_dir", "", type=str)
    return v or ""


def set_last_project_dialog_dir(path: str) -> None:
    """「新規プロジェクト」「プロジェクトを開く」で選んだフォルダを記憶する。"""
    get_settings().setValue("last_project_dialog_dir", path or "")


def get_last_script_dialog_dir() -> str:
    """前回「台本を開く」で選んだファイルの親フォルダ。未設定は空文字。"""
    v = get_settings().value("last_script_dialog_dir", "", type=str)
    return v or ""


def set_last_script_dialog_dir(path: str) -> None:
    """「台本を開く」で選んだファイルの親フォルダを記憶する。"""
    get_settings().setValue("last_script_dialog_dir", path or "")


def get_main_window_geometry() -> bytes | None:
    """メインウィンドウの geometry（位置・サイズ）。未設定は None。"""
    v = get_settings().value("main_window_geometry", None)
    if v is None:
        return None
    if isinstance(v, QByteArray):
        return bytes(v.data())
    if isinstance(v, (bytes, bytearray)):
        return bytes(v)
    return None


def set_main_window_geometry(data: bytes | None) -> None:
    """メインウィンドウの geometry を保存する。"""
    if data is None:
        get_settings().remove("main_window_geometry")
    else:
        get_settings().setValue("main_window_geometry", QByteArray(data))


def get_recording_mode() -> str:
    """bulk（台本一括） / individual（セリフ個別）"""
    return get_settings().value("recording_mode", "bulk", type=str)


def set_recording_mode(mode: str) -> None:
    get_settings().setValue("recording_mode", mode)


def get_auto_play_after_record() -> bool:
    """録音終了後に自動再生するかどうか"""
    return get_settings().value("auto_play_after_record", False, type=bool)


def set_auto_play_after_record(value: bool) -> None:
    get_settings().setValue("auto_play_after_record", value)


def get_take_list_filter() -> str:
    """テイク一覧のフィルタ: all / favorite / adopted"""
    return get_settings().value("take_list_filter", "all", type=str)


def set_take_list_filter(value: str) -> None:
    get_settings().setValue("take_list_filter", value)


def get_take_list_sort() -> str:
    """テイク一覧の並び順: date_desc / date_asc / favorite_first / adopted_first"""
    return get_settings().value("take_list_sort", "date_desc", type=str)


def set_take_list_sort(value: str) -> None:
    get_settings().setValue("take_list_sort", value)
