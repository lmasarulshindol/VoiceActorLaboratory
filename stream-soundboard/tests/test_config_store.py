"""ConfigStore のテスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from stream_soundboard.config_store import SLOT_COUNT, ConfigStore, SlotConfig


@pytest.fixture
def store(tmp_path: Path) -> ConfigStore:
    s = ConfigStore(tmp_path / "config.json")
    s.load()
    return s


class TestSlotConfig:
    def test_未割当はis_assignedがFalse(self):
        assert SlotConfig().is_assigned() is False

    def test_パスありはis_assignedがTrue(self):
        assert SlotConfig(audio_path="a.wav").is_assigned() is True

    def test_display_labelはカスタム優先(self):
        s = SlotConfig(label="挨拶", audio_path="x/hello.wav")
        assert s.display_label(0) == "挨拶"

    def test_display_labelはファイル名フォールバック(self):
        s = SlotConfig(audio_path="x/thanks.mp3")
        assert s.display_label(2) == "thanks"

    def test_display_labelはデフォルト番号(self):
        assert SlotConfig().display_label(4) == "スロット 5"


class TestConfigStore:
    def test_初期リスナーと10スロット(self, store: ConfigStore):
        assert store.state.listeners == ["デフォルト"]
        assert store.state.current_listener == "デフォルト"
        slots = store.get_slots()
        assert len(slots) == SLOT_COUNT
        assert all(isinstance(s, SlotConfig) for s in slots)

    def test_リスナー追加と切替(self, store: ConfigStore):
        store.add_listener("太郎")
        store.set_current_listener("太郎")
        assert store.state.current_listener == "太郎"
        assert len(store.get_slots("太郎")) == SLOT_COUNT

    def test_空のリスナー名はエラー(self, store: ConfigStore):
        with pytest.raises(ValueError):
            store.add_listener("  ")

    def test_最後のリスナーは削除不可(self, store: ConfigStore):
        with pytest.raises(ValueError):
            store.remove_listener("デフォルト")

    def test_リスナー削除でカレントが移る(self, store: ConfigStore):
        store.add_listener("花子")
        store.set_current_listener("花子")
        store.remove_listener("花子")
        assert store.state.current_listener == "デフォルト"
        assert "花子" not in store.state.listeners

    def test_スロット割当とクリア(self, store: ConfigStore):
        slot = store.assign_slot(0, r"C:\sounds\hello.wav")
        assert slot.audio_path.endswith("hello.wav")
        assert slot.label == "hello"
        store.clear_slot(0)
        assert store.get_slots()[0].is_assigned() is False

    def test_スロットラベル変更(self, store: ConfigStore):
        store.assign_slot(1, "a/b/c.mp3", label="旧")
        store.set_slot_label(1, "新ラベル")
        assert store.get_slots()[1].label == "新ラベル"

    def test_不正スロット番号(self, store: ConfigStore):
        with pytest.raises(IndexError):
            store.assign_slot(-1, "x.wav")
        with pytest.raises(IndexError):
            store.assign_slot(SLOT_COUNT, "x.wav")

    def test_空パス割当はエラー(self, store: ConfigStore):
        with pytest.raises(ValueError):
            store.assign_slot(0, "  ")

    def test_保存と読込(self, tmp_path: Path):
        path = tmp_path / "cfg.json"
        s1 = ConfigStore(path)
        s1.load()
        s1.add_listener("配信A")
        s1.set_current_listener("配信A")
        s1.assign_slot(3, "/tmp/se.wav", label="効果音")
        s1.set_volume(0.4)
        s1.state.always_on_top = False
        s1.save()

        s2 = ConfigStore(path)
        s2.load()
        assert s2.state.current_listener == "配信A"
        assert s2.state.volume == pytest.approx(0.4)
        assert s2.state.always_on_top is False
        slot = s2.get_slots()[3]
        assert slot.label == "効果音"
        assert slot.audio_path == "/tmp/se.wav"

    def test_壊れたJSONは初期化(self, tmp_path: Path):
        path = tmp_path / "bad.json"
        path.write_text("{broken", encoding="utf-8")
        s = ConfigStore(path)
        s.load()
        assert s.state.listeners == ["デフォルト"]

    def test_音量クランプ(self, store: ConfigStore):
        assert store.set_volume(1.5) == 1.0
        assert store.set_volume(-0.2) == 0.0

    def test_リスナー別スロットは独立(self, store: ConfigStore):
        store.assign_slot(0, "a.wav", label="A")
        store.add_listener("別")
        store.set_current_listener("別")
        store.assign_slot(0, "b.wav", label="B")
        assert store.get_slots("デフォルト")[0].label == "A"
        assert store.get_slots("別")[0].label == "B"

    def test_snapshotは独立コピー(self, store: ConfigStore):
        snap = store.snapshot()
        store.assign_slot(0, "x.wav")
        assert snap.slots_by_listener["デフォルト"][0].is_assigned() is False

    def test_新フィールドの保存と読込(self, tmp_path: Path):
        path = tmp_path / "devices.json"
        s1 = ConfigStore(path)
        s1.load()
        assert s1.set_input_device_name("マイクA") == "マイクA"
        assert s1.set_output_device_name("CABLE Input") == "CABLE Input"
        assert s1.set_mic_volume(0.55) == pytest.approx(0.55)
        assert s1.set_playback_volume(0.3) == pytest.approx(0.3)
        assert s1.set_mix_enabled(False) is False
        assert s1.set_confirm_before_play(False) is False
        s1.save()

        s2 = ConfigStore(path)
        s2.load()
        assert s2.state.input_device_name == "マイクA"
        assert s2.state.output_device_name == "CABLE Input"
        assert s2.state.mic_volume == pytest.approx(0.55)
        assert s2.state.playback_volume == pytest.approx(0.3)
        assert s2.state.volume == pytest.approx(0.3)
        assert s2.state.mix_enabled is False
        assert s2.state.confirm_before_play is False

        import json

        raw = json.loads(path.read_text(encoding="utf-8"))
        assert raw["volume"] == pytest.approx(0.3)
        assert raw["playback_volume"] == pytest.approx(0.3)

    def test_旧JSONのvolumeからplayback_volumeへ移行(self, tmp_path: Path):
        path = tmp_path / "legacy.json"
        path.write_text(
            '{"listeners": ["デフォルト"], "current_listener": "デフォルト",'
            ' "slots_by_listener": {}, "always_on_top": true, "volume": 0.7}',
            encoding="utf-8",
        )
        s = ConfigStore(path)
        s.load()
        assert s.state.playback_volume == pytest.approx(0.7)
        assert s.state.volume == pytest.approx(0.7)
        # 新フィールドはデフォルト
        assert s.state.input_device_name == ""
        assert s.state.output_device_name == ""
        assert s.state.mic_volume == pytest.approx(1.0)
        assert s.state.mix_enabled is True
        assert s.state.confirm_before_play is True

        s.save()
        import json

        raw = json.loads(path.read_text(encoding="utf-8"))
        assert raw["playback_volume"] == pytest.approx(0.7)
        assert raw["volume"] == pytest.approx(0.7)

    def test_playback_volume優先で旧volumeより勝つ(self, tmp_path: Path):
        path = tmp_path / "both.json"
        path.write_text(
            '{"listeners": ["デフォルト"], "current_listener": "デフォルト",'
            ' "slots_by_listener": {}, "volume": 0.2, "playback_volume": 0.9}',
            encoding="utf-8",
        )
        s = ConfigStore(path)
        s.load()
        assert s.state.playback_volume == pytest.approx(0.9)
        assert s.state.volume == pytest.approx(0.9)

    def test_micとplaybackの音量クランプ(self, store: ConfigStore):
        assert store.set_mic_volume(1.8) == 1.0
        assert store.set_mic_volume(-0.5) == 0.0
        assert store.set_playback_volume(2.0) == 1.0
        assert store.set_playback_volume(-1.0) == 0.0
        # set_volume も playback と同期
        assert store.set_volume(0.25) == pytest.approx(0.25)
        assert store.state.playback_volume == pytest.approx(0.25)
        assert store.state.volume == pytest.approx(0.25)
