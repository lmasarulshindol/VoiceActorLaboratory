"""リスナー別スロット割当の永続化。

JSONでリスナー一覧・各リスナーの10スロット（ラベル/音声パス）を保存する。
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


SLOT_COUNT = 10
DEFAULT_LISTENERS = ["デフォルト"]


@dataclass
class SlotConfig:
    """1スロット分の設定。"""

    label: str = ""
    audio_path: str = ""

    def is_assigned(self) -> bool:
        """音声ファイルが割り当て済みか。"""
        return bool(self.audio_path)

    def display_label(self, index: int) -> str:
        """ボタン表示用ラベル。未設定時は「スロット N」。"""
        if self.label.strip():
            return self.label.strip()
        if self.audio_path:
            return Path(self.audio_path).stem
        return f"スロット {index + 1}"


@dataclass
class SoundboardState:
    """アプリ全体の状態。"""

    listeners: list[str] = field(default_factory=lambda: list(DEFAULT_LISTENERS))
    current_listener: str = DEFAULT_LISTENERS[0]
    # listener_name -> list[SlotConfig] (長さ SLOT_COUNT)
    slots_by_listener: dict[str, list[SlotConfig]] = field(default_factory=dict)
    always_on_top: bool = True
    volume: float = 1.0  # 0.0〜1.0（playback_volume のエイリアス）
    input_device_name: str = ""  # 空ならOSデフォルト
    output_device_name: str = ""  # 空ならOSデフォルト（仮想ケーブル名を保存する想定）
    mic_volume: float = 1.0  # 0.0-1.0
    playback_volume: float = 1.0  # 0.0-1.0（BGM/SE側）
    mix_enabled: bool = True  # ミックス出力ON
    confirm_before_play: bool = True  # 再生前確認ダイアログ


def _empty_slots() -> list[SlotConfig]:
    return [SlotConfig() for _ in range(SLOT_COUNT)]


def _clamp_volume(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


class ConfigStore:
    """サウンドボード設定の読み書き。"""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.state = SoundboardState()
        self._ensure_listener(self.state.current_listener)

    def load(self) -> SoundboardState:
        """JSONから読み込み。無い/壊れている場合は初期状態。"""
        if not self.path.exists():
            self._ensure_listener(self.state.current_listener)
            return self.state

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._ensure_listener(self.state.current_listener)
            return self.state

        listeners = raw.get("listeners") or list(DEFAULT_LISTENERS)
        if not isinstance(listeners, list) or not listeners:
            listeners = list(DEFAULT_LISTENERS)
        listeners = [str(x) for x in listeners]

        current = str(raw.get("current_listener") or listeners[0])
        if current not in listeners:
            current = listeners[0]

        slots_raw = raw.get("slots_by_listener") or {}
        slots_by_listener: dict[str, list[SlotConfig]] = {}
        for name in listeners:
            slot_list = slots_raw.get(name) or []
            slots_by_listener[name] = self._parse_slots(slot_list)

        always_on_top = bool(raw.get("always_on_top", True))

        # playback_volume 優先。無ければ旧 volume を使う
        if "playback_volume" in raw:
            playback_volume = _clamp_volume(raw.get("playback_volume", 1.0))
        else:
            playback_volume = _clamp_volume(raw.get("volume", 1.0))

        mic_volume = _clamp_volume(raw.get("mic_volume", 1.0))
        input_device_name = str(raw.get("input_device_name") or "")
        output_device_name = str(raw.get("output_device_name") or "")
        mix_enabled = bool(raw.get("mix_enabled", True))
        confirm_before_play = bool(raw.get("confirm_before_play", True))

        self.state = SoundboardState(
            listeners=listeners,
            current_listener=current,
            slots_by_listener=slots_by_listener,
            always_on_top=always_on_top,
            volume=playback_volume,
            input_device_name=input_device_name,
            output_device_name=output_device_name,
            mic_volume=mic_volume,
            playback_volume=playback_volume,
            mix_enabled=mix_enabled,
            confirm_before_play=confirm_before_play,
        )
        return self.state

    def save(self) -> None:
        """現在の状態をJSONに保存。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # volume は playback_volume と同じ値で保存（後方互換）
        playback = self.state.playback_volume
        self.state.volume = playback
        payload = {
            "listeners": self.state.listeners,
            "current_listener": self.state.current_listener,
            "slots_by_listener": {
                name: [asdict(s) for s in slots]
                for name, slots in self.state.slots_by_listener.items()
            },
            "always_on_top": self.state.always_on_top,
            "volume": playback,
            "input_device_name": self.state.input_device_name,
            "output_device_name": self.state.output_device_name,
            "mic_volume": self.state.mic_volume,
            "playback_volume": playback,
            "mix_enabled": self.state.mix_enabled,
            "confirm_before_play": self.state.confirm_before_play,
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_slots(self, listener: Optional[str] = None) -> list[SlotConfig]:
        """指定リスナー（省略時は現在）のスロット一覧。"""
        name = listener or self.state.current_listener
        self._ensure_listener(name)
        return self.state.slots_by_listener[name]

    def set_current_listener(self, name: str) -> None:
        """現在のリスナーを切り替え。未登録なら追加。"""
        name = name.strip()
        if not name:
            raise ValueError("リスナー名が空です")
        if name not in self.state.listeners:
            self.add_listener(name)
        self.state.current_listener = name

    def add_listener(self, name: str) -> None:
        """リスナーを追加（重複は無視）。"""
        name = name.strip()
        if not name:
            raise ValueError("リスナー名が空です")
        if name not in self.state.listeners:
            self.state.listeners.append(name)
        self._ensure_listener(name)

    def remove_listener(self, name: str) -> None:
        """リスナーを削除。最後の1人は削除不可。"""
        if name not in self.state.listeners:
            raise KeyError(f"リスナーが存在しません: {name}")
        if len(self.state.listeners) <= 1:
            raise ValueError("最後のリスナーは削除できません")
        self.state.listeners.remove(name)
        self.state.slots_by_listener.pop(name, None)
        if self.state.current_listener == name:
            self.state.current_listener = self.state.listeners[0]

    def assign_slot(
        self,
        index: int,
        audio_path: str,
        label: Optional[str] = None,
        listener: Optional[str] = None,
    ) -> SlotConfig:
        """スロットに音声を割り当て。"""
        self._validate_index(index)
        slots = self.get_slots(listener)
        path = str(audio_path).strip()
        if not path:
            raise ValueError("音声パスが空です")
        slots[index].audio_path = path
        if label is not None:
            slots[index].label = label.strip()
        elif not slots[index].label:
            slots[index].label = Path(path).stem
        return slots[index]

    def clear_slot(self, index: int, listener: Optional[str] = None) -> SlotConfig:
        """スロットの割当を解除。"""
        self._validate_index(index)
        slots = self.get_slots(listener)
        slots[index] = SlotConfig()
        return slots[index]

    def set_slot_label(
        self, index: int, label: str, listener: Optional[str] = None
    ) -> SlotConfig:
        """スロットの表示ラベルだけ変更。"""
        self._validate_index(index)
        slots = self.get_slots(listener)
        slots[index].label = label.strip()
        return slots[index]

    def set_volume(self, volume: float) -> float:
        """音量を 0.0〜1.0 にクランプして設定（playback_volume と同期）。"""
        return self.set_playback_volume(volume)

    def set_input_device_name(self, name: str) -> str:
        """入力デバイス名を設定。空文字はOSデフォルト。"""
        self.state.input_device_name = str(name).strip()
        return self.state.input_device_name

    def set_output_device_name(self, name: str) -> str:
        """出力デバイス名を設定。空文字はOSデフォルト。"""
        self.state.output_device_name = str(name).strip()
        return self.state.output_device_name

    def set_mic_volume(self, v: float) -> float:
        """マイク音量を 0.0〜1.0 にクランプして設定。"""
        self.state.mic_volume = _clamp_volume(v)
        return self.state.mic_volume

    def set_playback_volume(self, v: float) -> float:
        """再生音量を 0.0〜1.0 にクランプして設定（volume と同期）。"""
        clamped = _clamp_volume(v)
        self.state.playback_volume = clamped
        self.state.volume = clamped
        return clamped

    def set_mix_enabled(self, enabled: bool) -> bool:
        """ミックス出力のON/OFF。"""
        self.state.mix_enabled = bool(enabled)
        return self.state.mix_enabled

    def set_confirm_before_play(self, enabled: bool) -> bool:
        """再生前確認ダイアログのON/OFF。"""
        self.state.confirm_before_play = bool(enabled)
        return self.state.confirm_before_play

    def snapshot(self) -> SoundboardState:
        """状態のディープコピー。"""
        return deepcopy(self.state)

    def _ensure_listener(self, name: str) -> None:
        if name not in self.state.slots_by_listener:
            self.state.slots_by_listener[name] = _empty_slots()
        else:
            slots = self.state.slots_by_listener[name]
            while len(slots) < SLOT_COUNT:
                slots.append(SlotConfig())
            if len(slots) > SLOT_COUNT:
                self.state.slots_by_listener[name] = slots[:SLOT_COUNT]

    @staticmethod
    def _parse_slots(slot_list: list) -> list[SlotConfig]:
        slots = _empty_slots()
        for i, item in enumerate(slot_list[:SLOT_COUNT]):
            if not isinstance(item, dict):
                continue
            slots[i] = SlotConfig(
                label=str(item.get("label") or ""),
                audio_path=str(item.get("audio_path") or ""),
            )
        return slots

    @staticmethod
    def _validate_index(index: int) -> None:
        if not isinstance(index, int) or index < 0 or index >= SLOT_COUNT:
            raise IndexError(f"スロット番号は 0〜{SLOT_COUNT - 1} です: {index}")
