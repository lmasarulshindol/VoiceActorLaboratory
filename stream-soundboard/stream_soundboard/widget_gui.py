"""配信向け縦長サウンドボードGUI。

- マイク入力 + BGM/SE を仮想出力へミックス
- リスナー別10スロット
- 左クリック: 再生（確認ダイアログは設定次第）
- 右クリック: 音声割当 / ラベル変更 / 削除
"""

from __future__ import annotations

import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import TYPE_CHECKING, Optional

from stream_soundboard.audio_devices import (
    DeviceInfo,
    find_device_by_name,
    get_default_input_device,
    get_default_output_device,
    list_input_devices,
    list_output_devices,
)
from stream_soundboard.audio_mixer import AudioMixer, AudioMixerError
from stream_soundboard.audio_player import AudioPlayer, AudioPlayerError
from stream_soundboard.config_store import SLOT_COUNT, ConfigStore
from stream_soundboard.help_content import (
    HELP_TOPICS,
    VB_CABLE_URL,
)

if TYPE_CHECKING:
    pass


WINDOW_WIDTH = 280
WINDOW_HEIGHT = 820
AUDIO_FILETYPES = [
    ("音声ファイル", "*.wav *.mp3 *.m4a *.aac *.ogg *.flac *.wma"),
    ("WAV", "*.wav"),
    ("MP3", "*.mp3"),
    ("すべて", "*.*"),
]
BG = "#1a1d24"
FG = "#c8cdd6"
FG_DIM = "#7a8494"
BTN_BG = "#2d3340"


class StreamSoundboardWidget:
    """縦長サウンドボードウィジェット。"""

    def __init__(
        self,
        root: tk.Tk,
        store: ConfigStore,
        player: Optional[AudioPlayer] = None,
        mixer: Optional[AudioMixer] = None,
    ):
        self.root = root
        self.store = store
        self.mixer = mixer or AudioMixer()
        self.player = player or AudioPlayer(
            mixer=self.mixer,
            volume=store.state.playback_volume,
        )
        self.player.set_mixer(self.mixer)

        self._listener_var = tk.StringVar(value=store.state.current_listener)
        self._status_var = tk.StringVar(value="準備完了")
        self._always_on_top_var = tk.BooleanVar(value=store.state.always_on_top)
        self._mix_enabled_var = tk.BooleanVar(value=store.state.mix_enabled)
        self._confirm_var = tk.BooleanVar(value=store.state.confirm_before_play)
        self._mic_mute_var = tk.BooleanVar(value=False)
        self._mic_vol_var = tk.DoubleVar(value=store.state.mic_volume * 100)
        self._play_vol_var = tk.DoubleVar(value=store.state.playback_volume * 100)
        self._input_var = tk.StringVar(value="")
        self._output_var = tk.StringVar(value="")
        self._slot_buttons: list[tk.Button] = []
        self._context_index: Optional[int] = None
        self._input_devices: list[DeviceInfo] = []
        self._output_devices: list[DeviceInfo] = []

        self._help_windows: list[tk.Toplevel] = []

        self._setup_window()
        self._build_menu()
        self._build_ui()
        self._refresh_listener_combo()
        self._refresh_buttons()
        self._apply_always_on_top()
        # デバイス列挙（~1s）は初回描画後に回し、ウィンドウ表示を優先する
        self._input_var.set("読込中…")
        self._output_var.set("読込中…")
        self._set_status("起動中…")
        self.root.after_idle(self._deferred_startup)

    def _setup_window(self) -> None:
        self.root.title("Stream Soundboard")
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.minsize(240, 640)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_menu(self) -> None:
        """メニューバー（ヘルプ）を構築。"""
        menubar = tk.Menu(self.root)
        help_menu = tk.Menu(menubar, tearoff=0)
        for label, title, body in HELP_TOPICS:
            help_menu.add_command(
                label=label,
                command=lambda t=title, b=body: self._show_help_window(t, b),
            )
        help_menu.add_separator()
        help_menu.add_command(
            label="VB-CABLEのサイトを開く",
            command=self._open_vb_cable_site,
        )
        menubar.add_cascade(label="ヘルプ", menu=help_menu)
        self.root.config(menu=menubar)
        self._menubar = menubar
        self._help_menu = help_menu

    def _open_vb_cable_site(self) -> None:
        """VB-CABLE 公式ページをブラウザで開く。"""
        try:
            webbrowser.open(VB_CABLE_URL)
            self._set_status("VB-CABLEサイトを開きました")
        except Exception as exc:
            messagebox.showerror(
                "開けませんでした",
                f"ブラウザを開けませんでした。\n{VB_CABLE_URL}\n\n{exc}",
                parent=self.root,
            )

    def _show_help_window(self, title: str, body: str) -> None:
        """スクロール可能なヘルプウィンドウを表示。"""
        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry("420x520")
        win.minsize(320, 360)
        win.configure(bg=BG)
        win.transient(self.root)

        header = tk.Frame(win, bg=BG)
        header.pack(fill="x", padx=10, pady=(10, 4))
        tk.Label(
            header,
            text=title,
            fg="#e8ecf2",
            bg=BG,
            font=("Segoe UI", 11, "bold"),
            anchor="w",
        ).pack(fill="x")

        frame = tk.Frame(win, bg=BG)
        frame.pack(fill="both", expand=True, padx=10, pady=4)

        text = tk.Text(
            frame,
            wrap="word",
            bg="#12151c",
            fg=FG,
            insertbackground=FG,
            relief="flat",
            font=("Segoe UI", 9),
            padx=8,
            pady=8,
            highlightthickness=0,
        )
        scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)
        text.insert("1.0", body)
        text.configure(state="disabled")

        footer = tk.Frame(win, bg=BG)
        footer.pack(fill="x", padx=10, pady=(4, 10))
        if "VB-CABLE" in title or "初期設定" in title:
            tk.Button(
                footer,
                text="VB-CABLEのサイトを開く",
                command=self._open_vb_cable_site,
                bg="#2a4050",
                fg="#e8ecf2",
                relief="flat",
                cursor="hand2",
                font=("Segoe UI", 9),
            ).pack(side="left")
        tk.Button(
            footer,
            text="閉じる",
            command=win.destroy,
            bg=BTN_BG,
            fg="#e8ecf2",
            relief="flat",
            cursor="hand2",
            font=("Segoe UI", 9),
        ).pack(side="right")

        self._help_windows.append(win)
        win.protocol(
            "WM_DELETE_WINDOW",
            lambda w=win: self._on_help_close(w),
        )

    def _on_help_close(self, win: tk.Toplevel) -> None:
        if win in self._help_windows:
            self._help_windows.remove(win)
        win.destroy()

    def _label(self, parent, text: str, **kw) -> tk.Label:
        opts = {"fg": FG, "bg": BG, "font": ("Segoe UI", 9), "anchor": "w"}
        opts.update(kw)
        return tk.Label(parent, text=text, **opts)

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 3}

        # --- ミックスデバイス ---
        devices = tk.Frame(self.root, bg=BG)
        devices.pack(fill="x", **pad)

        self._label(devices, "マイク入力").pack(fill="x")
        self.input_combo = ttk.Combobox(
            devices, textvariable=self._input_var, state="readonly", width=28
        )
        self.input_combo.pack(fill="x", pady=(1, 4))
        self.input_combo.bind("<<ComboboxSelected>>", self._on_devices_changed)

        self._label(devices, "ミックス出力（仮想ケーブル推奨）").pack(fill="x")
        self.output_combo = ttk.Combobox(
            devices, textvariable=self._output_var, state="readonly", width=28
        )
        self.output_combo.pack(fill="x", pady=(1, 2))
        self.output_combo.bind("<<ComboboxSelected>>", self._on_devices_changed)

        dev_btns = tk.Frame(devices, bg=BG)
        dev_btns.pack(fill="x", pady=(4, 0))
        tk.Button(
            dev_btns,
            text="再読込",
            command=self._refresh_device_lists,
            bg=BTN_BG,
            fg="#e8ecf2",
            relief="flat",
            cursor="hand2",
            font=("Segoe UI", 8),
        ).pack(side="left")
        tk.Button(
            dev_btns,
            text="ミックス開始",
            command=self._start_mix,
            bg="#2a4050",
            fg="#e8ecf2",
            relief="flat",
            cursor="hand2",
            font=("Segoe UI", 8),
        ).pack(side="left", padx=(4, 0))
        tk.Button(
            dev_btns,
            text="停止",
            command=self._stop_mix,
            bg="#4a3038",
            fg="#f0d0d8",
            relief="flat",
            cursor="hand2",
            font=("Segoe UI", 8),
        ).pack(side="left", padx=(4, 0))

        # --- リスナー ---
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", **pad)
        self._label(header, "リスナー").pack(fill="x")
        row = tk.Frame(header, bg=BG)
        row.pack(fill="x", pady=(2, 0))
        self.listener_combo = ttk.Combobox(
            row, textvariable=self._listener_var, state="readonly", width=14
        )
        self.listener_combo.pack(side="left", fill="x", expand=True)
        self.listener_combo.bind("<<ComboboxSelected>>", self._on_listener_selected)
        for text, cmd in (("+", self._add_listener), ("−", self._remove_listener)):
            tk.Button(
                row,
                text=text,
                width=3,
                command=cmd,
                bg=BTN_BG,
                fg="#e8ecf2",
                relief="flat",
                cursor="hand2",
            ).pack(side="left", padx=(4 if text == "+" else 2, 0))

        # --- オプション / 音量 ---
        opts = tk.Frame(self.root, bg=BG)
        opts.pack(fill="x", **pad)

        for text, var, cmd in (
            ("常に最前面に表示", self._always_on_top_var, self._toggle_always_on_top),
            ("ミックス出力", self._mix_enabled_var, self._toggle_mix_enabled),
            ("再生前に確認", self._confirm_var, self._toggle_confirm),
            ("マイクミュート", self._mic_mute_var, self._toggle_mic_mute),
        ):
            tk.Checkbutton(
                opts,
                text=text,
                variable=var,
                command=cmd,
                fg=FG,
                bg=BG,
                selectcolor=BTN_BG,
                activebackground=BG,
                activeforeground="#e8ecf2",
                font=("Segoe UI", 8),
            ).pack(anchor="w")

        for label, var, handler in (
            ("マイク", self._mic_vol_var, self._on_mic_volume),
            ("BGM/SE", self._play_vol_var, self._on_play_volume),
        ):
            vol_row = tk.Frame(opts, bg=BG)
            vol_row.pack(fill="x", pady=(2, 0))
            tk.Label(
                vol_row, text=label, fg=FG_DIM, bg=BG, font=("Segoe UI", 8), width=6
            ).pack(side="left")
            tk.Scale(
                vol_row,
                from_=0,
                to=100,
                orient="horizontal",
                variable=var,
                command=handler,
                bg=BG,
                fg=FG,
                highlightthickness=0,
                troughcolor=BTN_BG,
                length=160,
                showvalue=False,
            ).pack(side="left", fill="x", expand=True, padx=(4, 0))

        # --- スロット ---
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=10, pady=4)

        self._context_menu = tk.Menu(self.root, tearoff=0)
        self._context_menu.add_command(
            label="音声ファイルを割り当て…", command=self._menu_assign
        )
        self._context_menu.add_command(
            label="ラベルを変更…", command=self._menu_rename
        )
        self._context_menu.add_separator()
        self._context_menu.add_command(label="割当を削除", command=self._menu_clear)
        self._context_menu.add_separator()
        self._context_menu.add_command(label="再生を停止", command=self._stop_playback)

        for i in range(SLOT_COUNT):
            btn = tk.Button(
                body,
                text=f"スロット {i + 1}",
                anchor="w",
                justify="left",
                font=("Segoe UI", 10),
                bg="#2a3140",
                fg="#e8ecf2",
                activebackground="#3d4660",
                activeforeground="#ffffff",
                relief="flat",
                bd=0,
                padx=12,
                pady=6,
                cursor="hand2",
                wraplength=WINDOW_WIDTH - 40,
            )
            btn.pack(fill="x", pady=2, ipady=1)
            btn.bind("<Button-1>", lambda e, idx=i: self._on_left_click(idx))
            btn.bind("<Button-3>", lambda e, idx=i: self._on_right_click(e, idx))
            btn.bind("<Button-2>", lambda e, idx=i: self._on_right_click(e, idx))
            btn.configure(command=lambda: None)
            self._slot_buttons.append(btn)

        footer = tk.Frame(self.root, bg=BG)
        footer.pack(fill="x", padx=10, pady=(0, 8))
        tk.Button(
            footer,
            text="再生停止",
            command=self._stop_playback,
            bg="#4a3038",
            fg="#f0d0d8",
            relief="flat",
            cursor="hand2",
            font=("Segoe UI", 9),
        ).pack(fill="x", pady=(0, 4))
        tk.Label(
            footer,
            textvariable=self._status_var,
            fg=FG_DIM,
            bg=BG,
            font=("Segoe UI", 8),
            anchor="w",
            wraplength=WINDOW_WIDTH - 24,
        ).pack(fill="x")
        tk.Label(
            footer,
            text="左クリック:再生 / 右クリック:設定",
            fg="#5a6474",
            bg=BG,
            font=("Segoe UI", 7),
            anchor="w",
        ).pack(fill="x", pady=(2, 0))

    # ------------------------------------------------------------------
    # デバイス / ミックス
    # ------------------------------------------------------------------

    def _deferred_startup(self) -> None:
        """ウィンドウ表示後にデバイス取得とミックス開始を行う。"""
        self._refresh_device_lists()
        if self.store.state.mix_enabled:
            self._start_mix()

    def _refresh_device_lists(self) -> None:
        try:
            self._input_devices = list_input_devices()
            self._output_devices = list_output_devices()
        except Exception as exc:
            self._input_var.set("")
            self._output_var.set("")
            messagebox.showerror("デバイス取得失敗", str(exc), parent=self.root)
            return

        in_names = [d.name for d in self._input_devices]
        out_names = [d.name for d in self._output_devices]
        self.input_combo["values"] = in_names
        self.output_combo["values"] = out_names

        saved_in = self.store.state.input_device_name
        saved_out = self.store.state.output_device_name

        if saved_in and saved_in in in_names:
            self._input_var.set(saved_in)
        else:
            default_in = get_default_input_device()
            self._input_var.set(default_in.name if default_in else (in_names[0] if in_names else ""))

        if saved_out and saved_out in out_names:
            self._output_var.set(saved_out)
        else:
            cable = find_device_by_name("cable", kind="output") or find_device_by_name(
                "CABLE", kind="output"
            )
            if cable:
                self._output_var.set(cable.name)
            else:
                default_out = get_default_output_device()
                self._output_var.set(
                    default_out.name if default_out else (out_names[0] if out_names else "")
                )

        self._set_status("デバイス一覧を更新")

    def _resolve_device_index(
        self, name: str, devices: list[DeviceInfo]
    ) -> Optional[int]:
        for d in devices:
            if d.name == name:
                return d.index
        return None

    def _on_devices_changed(self, _event=None) -> None:
        self.store.set_input_device_name(self._input_var.get())
        self.store.set_output_device_name(self._output_var.get())
        self.store.save()
        if self.mixer.is_running() and self.store.state.mix_enabled:
            self._start_mix()

    def _start_mix(self) -> None:
        in_idx = self._resolve_device_index(self._input_var.get(), self._input_devices)
        out_idx = self._resolve_device_index(self._output_var.get(), self._output_devices)
        if in_idx is None or out_idx is None:
            messagebox.showwarning(
                "デバイス未選択",
                "マイク入力とミックス出力を選択してください。\n"
                "Discord等へ乗せるには VB-CABLE 等の仮想ケーブルを\n"
                "出力に選び、通話アプリのマイクをそのケーブルにしてください。",
                parent=self.root,
            )
            return
        try:
            self.mixer.set_mic_volume(self.store.state.mic_volume)
            self.mixer.set_playback_volume(self.store.state.playback_volume)
            self.mixer.set_mic_muted(bool(self._mic_mute_var.get()))
            self.mixer.start(in_idx, out_idx)
            self.store.state.mix_enabled = True
            self._mix_enabled_var.set(True)
            self.store.save()
            self._set_status("ミックス稼働中")
        except AudioMixerError as exc:
            messagebox.showerror("ミックス開始失敗", str(exc), parent=self.root)
            self._set_status("ミックス失敗")

    def _stop_mix(self) -> None:
        self.mixer.stop()
        self._set_status("ミックス停止")

    def _toggle_mix_enabled(self) -> None:
        enabled = bool(self._mix_enabled_var.get())
        self.store.set_mix_enabled(enabled)
        self.store.save()
        if enabled:
            self._start_mix()
        else:
            self._stop_mix()

    def _toggle_mic_mute(self) -> None:
        self.mixer.set_mic_muted(bool(self._mic_mute_var.get()))
        self._set_status("マイクミュート" if self._mic_mute_var.get() else "マイクON")

    def _on_mic_volume(self, _value=None) -> None:
        vol = float(self._mic_vol_var.get()) / 100.0
        self.store.set_mic_volume(vol)
        self.mixer.set_mic_volume(vol)
        if hasattr(self, "_mic_save_after"):
            self.root.after_cancel(self._mic_save_after)
        self._mic_save_after = self.root.after(400, self.store.save)

    def _on_play_volume(self, _value=None) -> None:
        vol = float(self._play_vol_var.get()) / 100.0
        self.store.set_playback_volume(vol)
        self.player.set_volume(vol)
        if hasattr(self, "_play_save_after"):
            self.root.after_cancel(self._play_save_after)
        self._play_save_after = self.root.after(400, self.store.save)

    def _toggle_confirm(self) -> None:
        self.store.set_confirm_before_play(bool(self._confirm_var.get()))
        self.store.save()

    # ------------------------------------------------------------------
    # リスナー
    # ------------------------------------------------------------------

    def _refresh_listener_combo(self) -> None:
        names = list(self.store.state.listeners)
        self.listener_combo["values"] = names
        current = self.store.state.current_listener
        if current in names:
            self._listener_var.set(current)

    def _on_listener_selected(self, _event=None) -> None:
        name = self._listener_var.get()
        self.store.set_current_listener(name)
        self.store.save()
        self._refresh_buttons()
        self._set_status(f"リスナー: {name}")

    def _add_listener(self) -> None:
        name = simpledialog.askstring("リスナー追加", "リスナー名を入力:", parent=self.root)
        if name is None:
            return
        name = name.strip()
        if not name:
            messagebox.showwarning("入力エラー", "名前が空です。", parent=self.root)
            return
        try:
            self.store.add_listener(name)
            self.store.set_current_listener(name)
            self.store.save()
        except ValueError as exc:
            messagebox.showwarning("追加できません", str(exc), parent=self.root)
            return
        self._refresh_listener_combo()
        self._refresh_buttons()
        self._set_status(f"追加: {name}")

    def _remove_listener(self) -> None:
        name = self.store.state.current_listener
        if not messagebox.askokcancel(
            "リスナー削除",
            f"「{name}」を削除しますか？\nスロット設定も消えます。",
            parent=self.root,
        ):
            return
        try:
            self.store.remove_listener(name)
            self.store.save()
        except (ValueError, KeyError) as exc:
            messagebox.showwarning("削除できません", str(exc), parent=self.root)
            return
        self._refresh_listener_combo()
        self._listener_var.set(self.store.state.current_listener)
        self._refresh_buttons()
        self._set_status(f"削除: {name}")

    # ------------------------------------------------------------------
    # ボタン / 再生
    # ------------------------------------------------------------------

    def _refresh_buttons(self) -> None:
        slots = self.store.get_slots()
        for i, (btn, slot) in enumerate(zip(self._slot_buttons, slots)):
            label = slot.display_label(i)
            if slot.is_assigned():
                path_ok = Path(slot.audio_path).exists()
                btn.configure(
                    text=f"▶  {label}",
                    bg="#2a4050" if path_ok else "#503030",
                    fg="#e8ecf2",
                )
            else:
                btn.configure(text=f"○  {label}", bg="#2a3140", fg="#8a93a3")

    def _on_left_click(self, index: int) -> None:
        slots = self.store.get_slots()
        slot = slots[index]
        if not slot.is_assigned():
            messagebox.showinfo(
                "未割当",
                "右クリックから音声ファイルを割り当ててください。",
                parent=self.root,
            )
            return

        path = Path(slot.audio_path)
        if not path.exists():
            messagebox.showerror(
                "ファイルなし",
                f"音声ファイルが見つかりません:\n{slot.audio_path}",
                parent=self.root,
            )
            return

        label = slot.display_label(index)
        if self.store.state.confirm_before_play:
            listener = self.store.state.current_listener
            ok = messagebox.askokcancel(
                "再生確認",
                f"リスナー: {listener}\nスロット {index + 1}: {label}\n\n再生しますか？",
                parent=self.root,
            )
            if not ok:
                self._set_status("キャンセル")
                return

        if self.store.state.mix_enabled and not self.mixer.is_running():
            self._start_mix()
            if not self.mixer.is_running():
                return

        try:
            self.player.play(
                path,
                on_finished=lambda: self.root.after(0, self._on_play_finished),
            )
        except AudioPlayerError as exc:
            messagebox.showerror("再生エラー", str(exc), parent=self.root)
            self._set_status("再生失敗")
            return

        self._set_status(f"再生中: {label}")
        self._highlight_playing(index)

    def _on_play_finished(self) -> None:
        self._refresh_buttons()
        self._set_status("再生終了")

    def _highlight_playing(self, index: int) -> None:
        self._refresh_buttons()
        self._slot_buttons[index].configure(bg="#3a6a4a", fg="#ffffff")

    def _stop_playback(self) -> None:
        self.player.stop()
        self._refresh_buttons()
        self._set_status("再生停止")

    # ------------------------------------------------------------------
    # 右クリック
    # ------------------------------------------------------------------

    def _on_right_click(self, event, index: int) -> str:
        self._context_index = index
        try:
            self._context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._context_menu.grab_release()
        return "break"

    def _menu_assign(self) -> None:
        index = self._context_index
        if index is None:
            return
        path = filedialog.askopenfilename(
            parent=self.root,
            title=f"スロット {index + 1} に割り当てる音声",
            filetypes=AUDIO_FILETYPES,
        )
        if not path:
            return
        self.store.assign_slot(index, path)
        self.store.save()
        self._refresh_buttons()
        self._set_status(f"割当: スロット {index + 1}")

    def _menu_rename(self) -> None:
        index = self._context_index
        if index is None:
            return
        slot = self.store.get_slots()[index]
        new_label = simpledialog.askstring(
            "ラベル変更",
            f"スロット {index + 1} の表示名:",
            initialvalue=slot.display_label(index),
            parent=self.root,
        )
        if new_label is None:
            return
        self.store.set_slot_label(index, new_label)
        self.store.save()
        self._refresh_buttons()
        self._set_status(f"ラベル変更: {new_label}")

    def _menu_clear(self) -> None:
        index = self._context_index
        if index is None:
            return
        slot = self.store.get_slots()[index]
        if not slot.is_assigned():
            self._set_status("既に未割当")
            return
        label = slot.display_label(index)
        if not messagebox.askokcancel(
            "割当削除",
            f"スロット {index + 1}「{label}」の割当を削除しますか？",
            parent=self.root,
        ):
            return
        self.store.clear_slot(index)
        self.store.save()
        self._refresh_buttons()
        self._set_status(f"削除: スロット {index + 1}")

    # ------------------------------------------------------------------
    # 終了
    # ------------------------------------------------------------------

    def _toggle_always_on_top(self) -> None:
        enabled = bool(self._always_on_top_var.get())
        self.store.state.always_on_top = enabled
        self.store.save()
        self._apply_always_on_top()
        self._set_status("最前面: ON" if enabled else "最前面: OFF")

    def _apply_always_on_top(self) -> None:
        """常に最前面表示のON/OFFをウィンドウへ反映。"""
        enabled = bool(self.store.state.always_on_top)
        # Windows では一度 False にしてから True にすると反映が安定する
        self.root.attributes("-topmost", False)
        if enabled:
            self.root.attributes("-topmost", True)
            self.root.lift()
        self._always_on_top_var.set(enabled)

    def _set_status(self, text: str) -> None:
        self._status_var.set(text)

    def _on_close(self) -> None:
        self.player.stop()
        self.mixer.stop()
        self.store.save()
        for win in list(self._help_windows):
            try:
                win.destroy()
            except tk.TclError:
                pass
        self._help_windows.clear()
        self.root.destroy()
