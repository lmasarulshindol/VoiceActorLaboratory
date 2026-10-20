# Stream Soundboard

マイク入力に BGM / SE を乗せて、仮想オーディオケーブルへ出力する Windows 向け GUI アプリです。

## 必要なもの

- Python 3.10+
- [VB-Audio Virtual Cable](https://vb-audio.com/Cable/)（推奨）または同様の仮想マイク
- （任意）ffmpeg … MP3 等のデコード用

## セットアップ

```powershell
cd 002_Pythonアプリ/stream-soundboard
py -3 -m pip install -r requirements.txt
py -3 main.py
```

## 使い方（Discord / Zoom 等）

1. VB-CABLE をインストールする
2. アプリで **マイク入力** = 実マイク、**ミックス出力** = `CABLE Input` を選ぶ
3. 「ミックス開始」を押す
4. Discord / Zoom のマイク設定を `CABLE Output` にする
5. 右クリックでスロットに音声を割り当て、左クリックで再生

これで通話相手には「あなたの声 + BGM/SE」が届きます。

## テスト

```powershell
py -3 -m pytest --cov=stream_soundboard --cov-report=term-missing -v
```
