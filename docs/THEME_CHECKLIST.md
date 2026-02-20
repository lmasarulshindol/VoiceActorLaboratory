# テーマカラー確認チェックリスト

QSS で一元管理しているウィジェット一覧。新規ダイアログ・ウィンドウを追加するときは、この一覧に**該当するウィジェット種別が .qss に既にあるか**を確認し、無ければ `src/ui/themes/theme_light.qss` と `theme_dark.qss` にセレクタを追加すること。

## .qss に含めるセレクタ一覧

| 対象 | セレクタ例 | 用途 |
|------|------------|------|
| 基底 | `QWidget`, `QMainWindow` | ウィンドウ背景・文字色 |
| メッセージボックス | `QMessageBox` | 確認・警告・情報ダイアログ（削除確認含む） |
| メッセージボックス内ボタン | `QMessageBox QPushButton` | Yes/No 等のボタン色 |
| ダイアログ | `QDialog` | 設定・エクスポート等 |
| ダイアログボタン | `QDialogButtonBox QPushButton` | OK/キャンセル |
| メニュー | `QMenu`, `QMenu::item`, `QMenu::item:selected` | 右クリックメニュー |
| コンボボックス | `QComboBox`, `QComboBox::drop-down`, `QComboBox QAbstractItemView` | 録音・再生・速度・波形 |
| リスト | `QListWidget`, `QListWidget::item:selected` | テイク一覧 |
| 台本エリア | `QPlainTextEdit` | 台本 |
| ラベル | `QLabel#heading`, `#body`, `#caption` | 見出し・本文・キャプション |
| カード | `QFrame#welcomeCard` | はじめにカード |
| ボタン | `QPushButton#accentButton`, `#recentProjectButton` | アクセント・最近開いた |
| 録音/再生ボタン | `#recordToggleBtn`, `#recordStopBtn`, `#playPauseBtn`, `#playStopBtn` | 録音・停止・再生・停止 |
| サイドバー | `QWidget#sidebar` | 左サイドバー背景・枠 |
| グループ | `QGroupBox`, `QRadioButton`, `QCheckBox` | 設定・エクスポートダイアログ内 |
| ステータスバー | `QStatusBar` | ステータスバー文字色 |
| ショートカット/録音ラベル | `QLabel#shortcutLabel`, `#recordingLabel` | ステータスバー右・録音時間 |

## 確認手順

1. **QMessageBox**: 削除確認・終了確認・各種警告・情報を表示し、ダーク/ライト両方で背景・文字・ボタンがテーマに沿っているか確認する。
2. **QDialog**: 設定ダイアログ・エクスポートダイアログを開き、同様に確認する。
3. **QMenu**: テイク一覧で右クリックし、メニューの見た目を確認する。
4. **QInputDialog**: メモ編集等で表示される入力ダイアログは、OS/ネイティブの場合は要確認。効かない場合は自前 QDialog への差し替えを検討する。
5. **QFileDialog**: ファイル/フォルダ選択はシステムダイアログのため、テーマが効かない場合がある。必要に応じてチェックリストに「要確認」として記載する。

## ファイル配置

- ライト: `src/ui/themes/theme_light.qss`
- ダーク: `src/ui/themes/theme_dark.qss`
- ローダー: `src/ui/theme_loader.py`（プレースホルダ `{{NAME}}` を `theme_colors` の値で置換して `QApplication.setStyleSheet` に渡す）

新規ウィジェットを追加したら、上表に 1 行追加し、両 .qss にセレクタを追加することでテーマ修正漏れを防ぐ。
