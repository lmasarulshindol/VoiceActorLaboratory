"""audio_devices のテスト（sounddevice をモック）。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from stream_soundboard.audio_devices import (
    DeviceInfo,
    find_device_by_name,
    get_default_input_device,
    get_default_output_device,
    list_input_devices,
    list_output_devices,
)


def _make_device(
    name: str,
    *,
    max_in: int = 0,
    max_out: int = 0,
    sr: float = 48000.0,
) -> dict:
    return {
        "name": name,
        "max_input_channels": max_in,
        "max_output_channels": max_out,
        "default_samplerate": sr,
    }


FAKE_DEVICES = [
    _make_device("Built-in Mic", max_in=1, max_out=0, sr=44100.0),
    _make_device("Speakers", max_in=0, max_out=2, sr=48000.0),
    _make_device("USB Headset", max_in=1, max_out=2, sr=48000.0),
    _make_device("Virtual Cable", max_in=2, max_out=0, sr=48000.0),
    _make_device("Disabled Port", max_in=0, max_out=0, sr=8000.0),
]


@pytest.fixture
def mock_sd():
    """sounddevice モジュールをモックする。"""
    sd = MagicMock()
    sd.query_devices.side_effect = lambda *args, **kwargs: (
        FAKE_DEVICES[args[0]] if args else FAKE_DEVICES
    )
    sd.default = SimpleNamespace(device=(0, 1))
    with patch("stream_soundboard.audio_devices._require_sounddevice", return_value=sd):
        yield sd


class TestListDevices:
    def test_入力デバイスは入力チャンネルがあるものだけ(self, mock_sd):
        devices = list_input_devices()
        names = [d.name for d in devices]
        assert names == ["Built-in Mic", "USB Headset", "Virtual Cable"]
        assert all(d.max_input_channels > 0 for d in devices)
        assert all(isinstance(d, DeviceInfo) for d in devices)

    def test_出力デバイスは出力チャンネルがあるものだけ(self, mock_sd):
        devices = list_output_devices()
        names = [d.name for d in devices]
        assert names == ["Speakers", "USB Headset"]
        assert all(d.max_output_channels > 0 for d in devices)

    def test_デバイス情報のフィールドが正しく変換される(self, mock_sd):
        devices = list_input_devices()
        mic = devices[0]
        assert mic.index == 0
        assert mic.name == "Built-in Mic"
        assert mic.max_input_channels == 1
        assert mic.max_output_channels == 0
        assert mic.default_samplerate == 44100.0


class TestDefaultDevices:
    def test_デフォルト入力デバイスを取得(self, mock_sd):
        device = get_default_input_device()
        assert device is not None
        assert device.index == 0
        assert device.name == "Built-in Mic"

    def test_デフォルト出力デバイスを取得(self, mock_sd):
        device = get_default_output_device()
        assert device is not None
        assert device.index == 1
        assert device.name == "Speakers"

    def test_デフォルト入力が無効ならNone(self, mock_sd):
        mock_sd.default.device = (-1, 1)
        assert get_default_input_device() is None

    def test_デフォルト出力が入力専用ならNone(self, mock_sd):
        # index 0 は入力専用
        mock_sd.default.device = (0, 0)
        assert get_default_output_device() is None


class TestFindDeviceByName:
    def test_部分一致で入力デバイスを探す(self, mock_sd):
        device = find_device_by_name("headset", kind="input")
        assert device is not None
        assert device.name == "USB Headset"

    def test_大小無視で一致する(self, mock_sd):
        device = find_device_by_name("SPEAKERS", kind="output")
        assert device is not None
        assert device.name == "Speakers"

    def test_一致しなければNone(self, mock_sd):
        assert find_device_by_name("存在しない", kind="input") is None

    def test_kindが不正ならValueError(self, mock_sd):
        with pytest.raises(ValueError, match="kind"):
            find_device_by_name("mic", kind="both")  # type: ignore[arg-type]


class TestImportError:
    def test_sounddevice無しではImportError(self):
        with patch(
            "stream_soundboard.audio_devices._require_sounddevice",
            side_effect=ImportError("sounddevice がありません"),
        ):
            with pytest.raises(ImportError, match="sounddevice"):
                list_input_devices()
