# Discord Bot（声優×AI研究所）

Cursor や自宅PCから Discord サーバー「声優×AI研究所」へ接続するための設定・手順まとめです。

| 項目 | 値 |
| --- | --- |
| サーバー | 声優×AI研究所 |
| Guild ID | `1502168994529017886` |
| BOT専用チャンネル | `#bot連携` |
| Channel ID | `1533950961435803800` |
| カテゴリ | 優真×Bot |

---

## 重要：トークンの扱い

- 実トークンは **`.env` にだけ**置く（このファイルは Git 管理外）
- リポジトリにコミットされるのは `.env.example`（プレースホルダ）のみ
- トークンが漏れたら [Developer Portal](https://discord.com/developers/applications) → Bot → **Reset Token** ですぐ無効化する

### 自宅PCへの持ち運び方

1. このPCの `discord-bot/.env` を USB / 暗号化メモ / パスワードマネージャ等でコピー
2. 自宅PCで同じパス（または任意の作業フォルダ）に `.env` を置く
3. 下の「Cursor MCP」または「Pythonスクリプト」の手順を自宅でも実行

`.env` が無い場合は:

```powershell
Copy-Item .env.example .env
# .env を開いて DISCORD_BOT_TOKEN を実トークンに書き換える
```

---

## 前提（Bot側の設定）

1. [Discord Developer Portal](https://discord.com/developers/applications) でアプリを開く
2. **Bot** タブでトークンを取得（OAuth2 の Client Secret ではない）
3. 必要なら Privileged Gateway Intents を ON  
   - メッセージ本文を Gateway で読む場合: **MESSAGE CONTENT INTENT**
4. OAuth2 → URL Generator で `bot` を選び、少なくとも以下を付与してサーバーへ招待  
   - View Channels / Send Messages / Read Message History / Embed Links
5. サーバー内に Bot がオンライン表示されることを確認

---

## 方法A: Cursor から使う（MCP）

Cursor は公式 Discord プラグインが無いので、**MCP** で繋ぎます。

### 1. 設定ファイル

Windows ならユーザー設定:

`%USERPROFILE%\.cursor\mcp.json`

このフォルダの `mcp.example.json` を参考に、`DISCORD_TOKEN` を実トークンへ置換する。

```json
{
  "mcpServers": {
    "discord": {
      "command": "cmd",
      "args": ["/c", "npx", "-y", "@pasympa/discord-mcp"],
      "env": {
        "DISCORD_TOKEN": "（Botトークン）",
        "DISCORD_MESSAGE_CONTENT": "false",
        "DISCORD_GUILD_MEMBERS": "false"
      }
    }
  }
}
```

- Intent を Portal で ON にしていない場合、`DISCORD_MESSAGE_CONTENT` / `DISCORD_GUILD_MEMBERS` を `false` にしておく（`Used disallowed intents` 回避）
- Node.js（`npx`）が必要

### 2. 反映

Cursor → **Settings → MCP** で `discord` を Reload（または Cursor 再起動）。緑になれば OK。

### 3. チャットでの使い方例

- 「`#bot連携` にテストメッセージ送って」
- 「サーバーのチャンネル一覧を教えて」
- 「直近の会話を要約して `#bot連携` に投稿して」

### MCPの制限（重要）

`discord_read_messages` は **1回あたり最大100件**で、ページ送り（`before`）引数がありません。  
1か月分など長期間の履歴は、下の **方法B（Python）** を使ってください。

---

## 方法B: Pythonスクリプト（ページ送り対応）

### セットアップ

PowerShell:

```powershell
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

cd "（この discord-bot フォルダ）"
py -3 -m pip install -r requirements.txt
```

### テスト送信

```powershell
py -3 scripts/send_test.py
```

`#bot連携` に1通投稿します。

### 履歴取得（1か月・全テキストチャンネル）

```powershell
py -3 scripts/fetch_history.py --days 30
```

- Discord API の 100件制限を `before` でページ送りして突破します
- 結果は `work/history_YYYYMMDD.json` に保存（Git 管理外）

特定チャンネルだけ:

```powershell
py -3 scripts/fetch_history.py --days 30 --channel-id 1502173544895873237
```

---

## よくあるエラー

| 症状 | 原因と対処 |
| --- | --- |
| `invalid token` | Client Secret を貼っている／トークン失効。Bot タブの Token を再発行 |
| `Used disallowed intents` | Portal で Intent OFF なのに MCP が要求している。`mcp.json` で Intent を `false` に |
| メッセージが送れない | Bot に Send Messages が無い／チャンネル権限で拒否 |
| QRログインできない | メール＋パスワードでログインすればよい（トークン取得にはQR不要） |

---

## ディレクトリ構成

```
discord-bot/
├── README.md           … この手順書
├── .env                … 実トークン（Git外・自宅へコピー）
├── .env.example        … テンプレート（コミット可）
├── mcp.example.json    … Cursor MCP 設定例
├── requirements.txt
├── scripts/
│   ├── send_test.py
│   └── fetch_history.py
└── work/               … 取得JSONなど（Git外）
```

---

## 更新メモ

- 2026-08-05: Cursor MCP 接続確認、`#bot連携` へのテスト送信・月次サマリー投稿を実施
