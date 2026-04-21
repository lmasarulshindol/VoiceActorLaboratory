"""
アプリ設定の永続化。QSettings でテーマ・フォント・最近開いたプロジェクト等を保存する。

設定キー一覧: theme, script_font_size, recent_projects, export_friendly_names,
input_device_id, output_device_id, waveform_design, export_last_dir,
last_project_dialog_dir, last_script_dialog_dir, main_window_geometry,
main_window_splitter_sizes, recording_mode, auto_play_after_record,
take_list_filter, take_list_sort, confirm_before_delete_take, last_session_project_path.
"""
from PyQt6.QtCore import QSettings, QByteArray

ORG = "VoiceActorLaboratory"
APP = "VoiceActorLaboratory"


def get_settings() -> QSettings:
    return QSettings(ORG, APP)


def get_theme() -> str:
    """light / dark。不正な値は light に正規化する。"""
    v = get_settings().value("theme", "light", type=str)
    return v if v in ("light", "dark") else "light"


def set_theme(theme: str) -> None:
    get_settings().setValue("theme", theme)


def get_script_font_size() -> int:
    return get_settings().value("script_font_size", 14, type=int)


def set_script_font_size(size: int) -> None:
    get_settings().setValue("script_font_size", size)


def get_app_font_size() -> int:
    """
    アプリ全体フォントの pt サイズ。

    0 = システム既定（上書きしない）。それ以外は 8〜24 にクランプして返す。
    """
    v = get_settings().value("app_font_size", 0, type=int)
    try:
        v = int(v)
    except (TypeError, ValueError):
        return 0
    if v <= 0:
        return 0
    return max(8, min(24, v))


def set_app_font_size(size: int) -> None:
    """アプリ全体フォントの pt サイズを保存する。0 は上書き解除。"""
    try:
        size = int(size)
    except (TypeError, ValueError):
        size = 0
    if size <= 0:
        size = 0
    else:
        size = max(8, min(24, size))
    get_settings().setValue("app_font_size", size)


def get_recent_projects() -> list[str]:
    """最近開いたプロジェクトのパスリスト。QSettings の型揺れを正規化する。"""
    v = get_settings().value("recent_projects", [])
    if isinstance(v, str):
        return [v.strip()] if v.strip() else []
    if not v:
        return []
    return [str(x).strip() for x in v if str(x).strip()]


def add_recent_project(path: str, max_count: int = 5) -> None:
    """最近開いたプロジェクトに追加。空パス・重複は入れない。"""
    path = path.strip()
    if not path:
        return
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
    """bulk（台本一括） / individual（セリフ個別）。不正値は bulk にフォールバック。"""
    v = get_settings().value("recording_mode", "bulk", type=str)
    return v if v in ("bulk", "individual") else "bulk"


def set_recording_mode(mode: str) -> None:
    get_settings().setValue("recording_mode", mode)


def get_auto_play_after_record() -> bool:
    """録音終了後に自動再生するかどうか"""
    return get_settings().value("auto_play_after_record", False, type=bool)


def set_auto_play_after_record(value: bool) -> None:
    get_settings().setValue("auto_play_after_record", value)


def get_take_list_filter() -> str:
    """テイク一覧のフィルタ: all / favorite / adopted。不正値は all にフォールバック。"""
    v = get_settings().value("take_list_filter", "all", type=str)
    return v if v in ("all", "favorite", "adopted") else "all"


def set_take_list_filter(value: str) -> None:
    get_settings().setValue("take_list_filter", value)


def get_take_list_sort() -> str:
    """テイク一覧の並び順: date_desc / date_asc / favorite_first / adopted_first。不正値は date_desc にフォールバック。"""
    v = get_settings().value("take_list_sort", "date_desc", type=str)
    if v in ("date_desc", "date_asc", "favorite_first", "adopted_first"):
        return v
    return "date_desc"


def set_take_list_sort(value: str) -> None:
    get_settings().setValue("take_list_sort", value)


def get_confirm_before_delete_take() -> bool:
    """テイク削除前に確認メッセージを表示するか。True=表示する（既定）。"""
    return get_settings().value("confirm_before_delete_take", True, type=bool)


def set_confirm_before_delete_take(value: bool) -> None:
    get_settings().setValue("confirm_before_delete_take", value)


def get_last_session_project_path() -> str:
    """前回開いていたプロジェクトフォルダのパス。未設定は空文字。"""
    v = get_settings().value("last_session_project_path", "", type=str)
    return v or ""


def set_last_session_project_path(path: str | None) -> None:
    """前回開いていたプロジェクトパスを保存する（起動時に復元用）。"""
    get_settings().setValue("last_session_project_path", path or "")


def get_preroll_seconds() -> int:
    """録音開始前のカウントダウン秒数。0/3/5 のいずれか。既定は 0（無効）。"""
    v = get_settings().value("preroll_seconds", 0, type=int)
    if v in (0, 3, 5):
        return v
    return 0


def set_preroll_seconds(value: int) -> None:
    get_settings().setValue("preroll_seconds", int(value) if value in (0, 3, 5) else 0)


def get_level_meter_enabled() -> bool:
    """録音/再生コントロールの上に常時レベルメーターを表示するか。"""
    return get_settings().value("level_meter_enabled", True, type=bool)


def set_level_meter_enabled(value: bool) -> None:
    get_settings().setValue("level_meter_enabled", bool(value))


def get_export_name_template() -> str:
    """エクスポート時のファイル名テンプレート。空文字は「テンプレート未使用」扱い。

    例: ``{project}_{n}_{text}``。既定は空。
    """
    v = get_settings().value("export_name_template", "", type=str)
    return v or ""


def set_export_name_template(value: str) -> None:
    get_settings().setValue("export_name_template", value or "")


def get_main_window_splitter_sizes() -> list[int]:
    """メインウィンドウのスプリッター（台本|テイク）のサイズ。未設定は空リスト。要素は int に正規化。"""
    v = get_settings().value("main_window_splitter_sizes", [])
    if not isinstance(v, list):
        return []
    try:
        return [int(x) for x in v]
    except (TypeError, ValueError):
        return []


def set_main_window_splitter_sizes(sizes: list[int]) -> None:
    """スプリッターのサイズを保存する。"""
    get_settings().setValue("main_window_splitter_sizes", sizes)


# ---------- 後処理・フォーマット（A/B/C 実装分） ----------

_LUFS_ALLOWED = (-14.0, -16.0, -18.0, -23.0)


def get_lufs_target() -> float:
    """
    エクスポート時の LUFS 目標値。既定は -16.0（YouTube/Spotify 相当）。
    許容値: -14.0（Apple Music）, -16.0, -18.0, -23.0（放送）。
    """
    v = get_settings().value("lufs_target", -16.0, type=float)
    try:
        v = float(v)
    except (TypeError, ValueError):
        return -16.0
    for allowed in _LUFS_ALLOWED:
        if abs(v - allowed) < 0.01:
            return allowed
    return -16.0


def set_lufs_target(value: float) -> None:
    """LUFS 目標値を保存する。許容値外は -16.0 にフォールバック。"""
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = -16.0
    matched = -16.0
    for allowed in _LUFS_ALLOWED:
        if abs(v - allowed) < 0.01:
            matched = allowed
            break
    get_settings().setValue("lufs_target", matched)


def get_auto_analyze_lufs() -> bool:
    """録音直後に LUFS を自動解析するか。既定 True。"""
    return get_settings().value("auto_analyze_lufs", True, type=bool)


def set_auto_analyze_lufs(value: bool) -> None:
    get_settings().setValue("auto_analyze_lufs", bool(value))


_MP3_BITRATES_ALLOWED = (128, 192, 256, 320)


def get_mp3_bitrate() -> int:
    """MP3 エクスポートのビットレート（kbps）。既定 192。"""
    v = get_settings().value("mp3_bitrate", 192, type=int)
    try:
        v = int(v)
    except (TypeError, ValueError):
        return 192
    return v if v in _MP3_BITRATES_ALLOWED else 192


def set_mp3_bitrate(value: int) -> None:
    try:
        v = int(value)
    except (TypeError, ValueError):
        v = 192
    if v not in _MP3_BITRATES_ALLOWED:
        v = 192
    get_settings().setValue("mp3_bitrate", v)


def get_export_format() -> str:
    """エクスポートのデフォルトフォーマット。wav/flac/mp3。"""
    v = get_settings().value("export_format", "wav", type=str)
    return v if v in ("wav", "flac", "mp3") else "wav"


def set_export_format(value: str) -> None:
    v = (value or "wav").lower()
    if v not in ("wav", "flac", "mp3"):
        v = "wav"
    get_settings().setValue("export_format", v)


def get_export_apply_lufs() -> bool:
    """エクスポートダイアログで LUFS 正規化を既定でONにするか。"""
    return get_settings().value("export_apply_lufs", False, type=bool)


def set_export_apply_lufs(value: bool) -> None:
    get_settings().setValue("export_apply_lufs", bool(value))


def get_export_apply_trim_silence() -> bool:
    """エクスポートダイアログで無音トリムを既定でONにするか。"""
    return get_settings().value("export_apply_trim", False, type=bool)


def set_export_apply_trim_silence(value: bool) -> None:
    get_settings().setValue("export_apply_trim", bool(value))


def get_export_apply_noise_reduce() -> bool:
    """エクスポートダイアログでノイズ除去を既定でONにするか。"""
    return get_settings().value("export_apply_noise", False, type=bool)


def set_export_apply_noise_reduce(value: bool) -> None:
    get_settings().setValue("export_apply_noise", bool(value))
