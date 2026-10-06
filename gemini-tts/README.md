# Gemini TTS（VoiceActorLaboratory）

Google Gemini API の Text-to-Speech を使う CLI / ライブラリです。

## セットアップ

```powershell
cd "001_声優・音声/VoiceActorLaboratory/gemini-tts"
py -3 -m pip install -r requirements.txt
copy .env.example .env
```

`.env` に [Google AI Studio](https://aistudio.google.com/apikey) の APIキーを書いてください。

```
GEMINI_API_KEY=実際のキー
```

## 使い方

ボイス一覧:

```powershell
py -3 -m gemini_tts list-voices
```

テキストから WAV 生成:

```powershell
$env:PYTHONPATH = "src"
py -3 -m gemini_tts synthesize "こんにちは。藤優真です。" -o output/hello.wav --voice Kore
```

ファイルから生成 + スタイル指定:

```powershell
$env:PYTHONPATH = "src"
py -3 -m gemini_tts synthesize -f scripts/sample.txt --style "落ち着いたナレーション調で" --voice Aoede
```

標準入力から生成（テキスト引数に `-`）:

```powershell
Get-Content scripts/sample.txt -Raw | py -3 -m gemini_tts synthesize - --voice Kore -o output/from_stdin.wav
```

マルチスピーカー（最大2名想定）:

```powershell
$env:PYTHONPATH = "src"
py -3 -m gemini_tts synthesize -f scripts/dialogue.txt --speaker Alice:Kore --speaker Bob:Puck
```

## 設定

| 優先度 | 源 |
|--------|----|
| 高 | CLI オプション（`--voice` 等） |
| 中 | 環境変数 / `.env` |
| 低 | `config.yaml`（`config.example.yaml` をコピー） |

主な環境変数:

- `GEMINI_API_KEY` … APIキー（必須）
- `GEMINI_TTS_MODEL` … 既定 `gemini-3.8-flash-tts`
- `GEMINI_TTS_VOICE` … 既定 `Kore`

代替モデル例: `gemini-3.8-flash-lite-tts` / `gemini-3.1-flash-tts-preview`

## Git 管理方針

| 対象 | git |
|------|-----|
| ソース・設定例・テスト・README | 管理する |
| `.env`（APIキー） | **管理しない** |
| `output/*.wav` など生成音声 | **管理しない** |

`output/.gitkeep` だけ残し、生成物は ignore しています。親リポジトリの `.gitignore` も `.env` / 音声拡張子を除外済みです。

## 台本からプロジェクト化（API不要）

```powershell
$env:PYTHONPATH = "src"
py -3 -m gemini_tts parse-script "..\台本\異常な日常の物語 最適化された男.md" -o "projects/異常な日常の物語_最適化された男"
py -3 -m gemini_tts synthesize-project "projects/異常な日常の物語_最適化された男" --dry-run
```

キー投入後に本番生成:

```powershell
py -3 -m gemini_tts synthesize-project "projects/異常な日常の物語_最適化された男"
```

`--kinds dialogue,narration` のように Caption を外すこともできます。

```powershell
$env:PYTHONPATH = "src"
py -3 -m pytest --cov=gemini_tts --cov-report=term-missing
```

## 構成

```
gemini-tts/
  .env.example
  config.example.yaml
  requirements.txt
  src/gemini_tts/
    audio.py      # WAV 正規化・保存
    client.py     # Gemini TTS API
    cli.py        # コマンドライン
    config.py     # .env / YAML
    voices.py     # プリビルト30ボイス
  output/         # 生成先（git外）
  tests/
```

## 参考

- [Text-to-speech generation](https://ai.google.dev/gemini-api/docs/speech-generation)
- [Gemini 3.8 Flash TTS](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash-tts)
