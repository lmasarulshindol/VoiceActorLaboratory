"""#bot連携 へテストメッセージを1通送る。"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import discord
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

TOKEN = os.getenv("DISCORD_BOT_TOKEN", "").strip()
CHANNEL_ID = int(os.getenv("DISCORD_BOT_CHANNEL_ID", "0") or "0")


async def main() -> int:
    if not TOKEN or TOKEN.startswith("YOUR_"):
        print(".env の DISCORD_BOT_TOKEN を設定してください", file=sys.stderr)
        return 1
    if not CHANNEL_ID:
        print(".env の DISCORD_BOT_CHANNEL_ID を設定してください", file=sys.stderr)
        return 1

    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready() -> None:
        channel = client.get_channel(CHANNEL_ID)
        if channel is None:
            channel = await client.fetch_channel(CHANNEL_ID)
        await channel.send("自宅PC/スクリプトからのテスト送信です (･ω･)b")
        print(f"送信完了: #{getattr(channel, 'name', CHANNEL_ID)}")
        await client.close()

    await client.start(TOKEN)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
