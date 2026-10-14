# 異常な日常の物語　最適化された男

台本からの音声化プロジェクト（APIキー投入前の準備済み）。

## ファイル

- `manifest.json` … 全行の構造化データ（TTS対象フラグ付き）
- `voice_map.yaml` … 役→ボイス割当
- `LINES.md` … 一覧（確認用）
- `SOURCE.txt` … 元台本パス
- `audio/` … 生成WAVの出力先（git管理外）

## 種別

| kind | 意味 | 既定TTS |
|------|------|---------|
| dialogue | セリフ | する |
| narration | 語り手 | する |
| caption | 場所・テロップ・ポップアップ | する |
| sfx | 効果音ト書き | しない |
| direction | ト書き・演出 | しない |

## キー投入後

```powershell
$env:PYTHONPATH = "src"
py -3 -m gemini_tts synthesize-project projects/異常な日常の物語_最適化された男
```
