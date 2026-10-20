"""配信向けサウンドボード（マイク + BGM/SE ミックス）の起動エントリ。"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path

from stream_soundboard.audio_mixer import AudioMixer
from stream_soundboard.audio_player import AudioPlayer
from stream_soundboard.config_store import ConfigStore
from stream_soundboard.widget_gui import StreamSoundboardWidget


def default_config_path() -> Path:
    """ユーザーホーム配下に設定を保存。"""
    return Path.home() / ".stream_soundboard" / "config.json"


def main() -> None:
    config_path = default_config_path()
    store = ConfigStore(config_path)
    store.load()

    mixer = AudioMixer()
    mixer.set_mic_volume(store.state.mic_volume)
    mixer.set_playback_volume(store.state.playback_volume)

    player = AudioPlayer(
        mixer=mixer,
        volume=store.state.playback_volume,
    )

    root = tk.Tk()
    StreamSoundboardWidget(root, store, player=player, mixer=mixer)
    root.mainloop()


if __name__ == "__main__":
    main()
