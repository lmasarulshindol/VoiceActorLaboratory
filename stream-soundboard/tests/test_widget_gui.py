"""StreamSoundboardWidget のテスト。"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from stream_soundboard.audio_devices import DeviceInfo
from stream_soundboard.audio_player import AudioPlayer
from stream_soundboard.config_store import ConfigStore
from stream_soundboard.widget_gui import StreamSoundboardWidget


def _fake_devices():
    mic = DeviceInfo(0, "Test Mic", 1, 0, 48000.0)
    out = DeviceInfo(1, "CABLE Input", 0, 2, 48000.0)
    return [mic], [out], mic, out


@pytest.fixture
def tk_root():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("GUI環境がありません")
    root.withdraw()
    yield root
    try:
        root.destroy()
    except tk.TclError:
        pass


@pytest.fixture
def widget(tk_root, tmp_path: Path):
    store = ConfigStore(tmp_path / "config.json")
    store.load()
    store.state.mix_enabled = False
    player = MagicMock(spec=AudioPlayer)
    player.is_playing.return_value = False
    mixer = MagicMock()
    mixer.is_running.return_value = False
    inputs, outputs, default_in, default_out = _fake_devices()
    with (
        patch("stream_soundboard.widget_gui.list_input_devices", return_value=inputs),
        patch("stream_soundboard.widget_gui.list_output_devices", return_value=outputs),
        patch(
            "stream_soundboard.widget_gui.get_default_input_device",
            return_value=default_in,
        ),
        patch(
            "stream_soundboard.widget_gui.get_default_output_device",
            return_value=default_out,
        ),
        patch("stream_soundboard.widget_gui.find_device_by_name", return_value=default_out),
    ):
        w = StreamSoundboardWidget(tk_root, store, player=player, mixer=mixer)
    return w


class TestWidgetInit:
    def test_ボタンが10個(self, widget: StreamSoundboardWidget):
        assert len(widget._slot_buttons) == 10

    def test_初期ステータス(self, widget: StreamSoundboardWidget):
        assert widget._status_var.get() in ("準備完了", "デバイス一覧を更新")

    def test_未割当ボタン表示(self, widget: StreamSoundboardWidget):
        text = widget._slot_buttons[0].cget("text")
        assert "スロット 1" in text
        assert "○" in text


class TestLeftClickPlay:
    def test_未割当はinfoダイアログ(self, widget: StreamSoundboardWidget):
        with patch("stream_soundboard.widget_gui.messagebox.showinfo") as info:
            widget._on_left_click(0)
            info.assert_called_once()
        widget.player.play.assert_not_called()

    def test_キャンセルなら再生しない(self, widget: StreamSoundboardWidget, tmp_path: Path):
        wav = tmp_path / "hi.wav"
        wav.write_bytes(b"RIFF")
        widget.store.assign_slot(0, str(wav), label="挨拶")
        with patch(
            "stream_soundboard.widget_gui.messagebox.askokcancel", return_value=False
        ):
            widget._on_left_click(0)
        widget.player.play.assert_not_called()
        assert widget._status_var.get() == "キャンセル"

    def test_OKなら再生する(self, widget: StreamSoundboardWidget, tmp_path: Path):
        wav = tmp_path / "hi.wav"
        wav.write_bytes(b"RIFF")
        widget.store.assign_slot(0, str(wav), label="挨拶")
        with patch(
            "stream_soundboard.widget_gui.messagebox.askokcancel", return_value=True
        ):
            widget._on_left_click(0)
        widget.player.play.assert_called_once()
        assert "再生中" in widget._status_var.get()

    def test_欠落ファイルはエラー(self, widget: StreamSoundboardWidget):
        widget.store.assign_slot(0, str(Path("Z:/no/such/file.wav")), label="欠")
        with patch("stream_soundboard.widget_gui.messagebox.showerror") as err:
            widget._on_left_click(0)
            err.assert_called_once()
        widget.player.play.assert_not_called()


class TestRightClickMenus:
    def test_割当(self, widget: StreamSoundboardWidget, tmp_path: Path):
        path = str(tmp_path / "a.mp3")
        Path(path).write_bytes(b"x")
        widget._context_index = 2
        with patch(
            "stream_soundboard.widget_gui.filedialog.askopenfilename",
            return_value=path,
        ):
            widget._menu_assign()
        slot = widget.store.get_slots()[2]
        assert slot.audio_path == path
        assert "▶" in widget._slot_buttons[2].cget("text")

    def test_割当キャンセル(self, widget: StreamSoundboardWidget):
        widget._context_index = 0
        with patch(
            "stream_soundboard.widget_gui.filedialog.askopenfilename",
            return_value="",
        ):
            widget._menu_assign()
        assert widget.store.get_slots()[0].is_assigned() is False

    def test_ラベル変更(self, widget: StreamSoundboardWidget, tmp_path: Path):
        widget.store.assign_slot(1, str(tmp_path / "x.wav"))
        widget._context_index = 1
        with patch(
            "stream_soundboard.widget_gui.simpledialog.askstring",
            return_value="カスタム",
        ):
            widget._menu_rename()
        assert widget.store.get_slots()[1].label == "カスタム"

    def test_割当削除(self, widget: StreamSoundboardWidget, tmp_path: Path):
        widget.store.assign_slot(0, str(tmp_path / "x.wav"), label="消す")
        widget._context_index = 0
        with patch(
            "stream_soundboard.widget_gui.messagebox.askokcancel", return_value=True
        ):
            widget._menu_clear()
        assert widget.store.get_slots()[0].is_assigned() is False


class TestListenerUI:
    def test_リスナー切替でボタン更新(
        self, widget: StreamSoundboardWidget, tmp_path: Path
    ):
        widget.store.assign_slot(0, str(tmp_path / "a.wav"), label="A音")
        widget.store.add_listener("ゲスト")
        widget.store.set_current_listener("ゲスト")
        widget.store.assign_slot(0, str(tmp_path / "b.wav"), label="B音")
        widget.store.set_current_listener("デフォルト")
        widget._listener_var.set("デフォルト")
        widget._on_listener_selected()
        assert "A音" in widget._slot_buttons[0].cget("text")

    def test_リスナー追加(self, widget: StreamSoundboardWidget):
        with patch(
            "stream_soundboard.widget_gui.simpledialog.askstring",
            return_value="新規リスナー",
        ):
            widget._add_listener()
        assert "新規リスナー" in widget.store.state.listeners
        assert widget.store.state.current_listener == "新規リスナー"


class TestOptions:
    def test_停止ボタン(self, widget: StreamSoundboardWidget):
        widget._stop_playback()
        widget.player.stop.assert_called()
        assert "停止" in widget._status_var.get()

    def test_最前面トグル(self, widget: StreamSoundboardWidget):
        widget._always_on_top_var.set(False)
        widget._toggle_always_on_top()
        assert widget.store.state.always_on_top is False
        assert widget._status_var.get() == "最前面: OFF"
        assert widget.root.attributes("-topmost") in (0, False, "0")

        widget._always_on_top_var.set(True)
        widget._toggle_always_on_top()
        assert widget.store.state.always_on_top is True
        assert widget._status_var.get() == "最前面: ON"
        assert widget.root.attributes("-topmost") in (1, True, "1")
