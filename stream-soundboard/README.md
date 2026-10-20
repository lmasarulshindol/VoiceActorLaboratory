# Stream Soundboard

マイク入力に BGM / SE を乗せて、仮想オーディオケーブルへ出力する Windows 向け GUI アプリです。

## 必要なもの

- Python 3.10+（ソース実行時）
- [VB-Audio Virtual Cable](https://vb-audio.com/Cable/)（推奨）または同様の仮想マイク
- （任意）ffmpeg … MP3 等のデコード用

## セットアップ（ソース）

```powershell
cd 001_声優・音声/VoiceActorLaboratory/stream-soundboard
py -3 -m pip install -r requirements.txt
py -3 main.py
```

## 配布 exe（高速起動 = onedir）

```powershell
.\build_exe.ps1
```

起動は次のファイルをダブルクリック:

`dist/StreamSoundboard/StreamSoundboard.exe`

※ フォルダごと配布してください（単体 exe ではなく、同梱 DLL が必要です）。

## 使い方（Discord / Zoom 等）

1. VB-CABLE をインストールする
2. アプリで **マイク入力** = 実マイク、**ミックス出力** = `CABLE Input` を選ぶ
3. 「ミックス出力」を ON にする
4. Discord / Zoom のマイク設定を `CABLE Output` にする
5. 右クリックでスロットに音声を割り当て、左クリックで再生

これで通話相手には「あなたの声 + BGM/SE」が届きます。

## テスト

```powershell
py -3 -m pytest --cov=stream_soundboard --cov-report=term-missing -v
```
