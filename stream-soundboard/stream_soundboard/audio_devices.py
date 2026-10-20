"""音声入出力デバイスの列挙・検索。

sounddevice を遅延 import する。未インストール環境でもモジュール import は成功し、
各関数呼び出し時に ImportError を出す。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class DeviceInfo:
    """音声デバイス情報。"""

    index: int
    name: str
    max_input_channels: int
    max_output_channels: int
    default_samplerate: float


def _require_sounddevice():
    """sounddevice を import する。無ければ ImportError。"""
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise ImportError(
            "sounddevice がインストールされていません。"
            " pip install sounddevice を実行してください。"
        ) from exc
    return sd


def _to_device_info(index: int, raw: dict) -> DeviceInfo:
    """sounddevice の query_devices 結果を DeviceInfo に変換。"""
    return DeviceInfo(
        index=int(index),
        name=str(raw.get("name", "")),
        max_input_channels=int(raw.get("max_input_channels", 0)),
        max_output_channels=int(raw.get("max_output_channels", 0)),
        default_samplerate=float(raw.get("default_samplerate", 0.0)),
    )


def _all_devices() -> list[DeviceInfo]:
    """全デバイスを DeviceInfo のリストで返す。"""
    sd = _require_sounddevice()
    devices = sd.query_devices()
    # query_devices() は list-like（DeviceList）または単一 dict
    if isinstance(devices, dict):
        return [_to_device_info(0, devices)]
    return [_to_device_info(i, d) for i, d in enumerate(devices)]


def list_input_devices() -> list[DeviceInfo]:
    """入力チャンネルを持つデバイス一覧を返す。"""
    return [d for d in _all_devices() if d.max_input_channels > 0]


def list_output_devices() -> list[DeviceInfo]:
    """出力チャンネルを持つデバイス一覧を返す。"""
    return [d for d in _all_devices() if d.max_output_channels > 0]


def _default_device_indices() -> tuple[int | None, int | None]:
    """sd.default.device から (input_idx, output_idx) を取り出す。

    sounddevice の _InputOutputPair は list/tuple ではないがインデックス可能。
    """
    sd = _require_sounddevice()
    raw = sd.default.device
    try:
        # (in, out) 形式（_InputOutputPair / list / tuple）
        in_idx = raw[0]
        out_idx = raw[1]
    except (TypeError, IndexError, KeyError):
        in_idx = raw
        out_idx = raw

    def _as_idx(value) -> int | None:
        if value is None:
            return None
        try:
            i = int(value)
        except (TypeError, ValueError):
            return None
        return i if i >= 0 else None

    return _as_idx(in_idx), _as_idx(out_idx)


def get_default_input_device() -> DeviceInfo | None:
    """システムのデフォルト入力デバイスを返す。無ければ None。"""
    sd = _require_sounddevice()
    idx, _ = _default_device_indices()
    if idx is None:
        return None
    info = sd.query_devices(idx)
    device = _to_device_info(idx, info)
    if device.max_input_channels <= 0:
        return None
    return device


def get_default_output_device() -> DeviceInfo | None:
    """システムのデフォルト出力デバイスを返す。無ければ None。"""
    sd = _require_sounddevice()
    _, idx = _default_device_indices()
    if idx is None:
        return None
    info = sd.query_devices(idx)
    device = _to_device_info(idx, info)
    if device.max_output_channels <= 0:
        return None
    return device


def find_device_by_name(
    name: str,
    *,
    kind: Literal["input", "output"] = "input",
) -> DeviceInfo | None:
    """名前の部分一致（大小無視）でデバイスを探す。

    Args:
        name: 検索文字列
        kind: "input" または "output"

    Returns:
        最初に一致した DeviceInfo。無ければ None。
    """
    if kind not in ("input", "output"):
        raise ValueError(f'kind は "input" または "output" である必要があります: {kind!r}')

    needle = name.casefold()
    candidates = list_input_devices() if kind == "input" else list_output_devices()
    for device in candidates:
        if needle in device.name.casefold():
            return device
    return None
