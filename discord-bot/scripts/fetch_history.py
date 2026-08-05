"""テキストチャンネル履歴をページ送りで取得する（API 100件制限を回避）。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import discord
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

TOKEN = os.getenv("DISCORD_BOT_TOKEN", "").strip()
GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", "0") or "0")
JST = timezone(timedelta(hours=9))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Discord履歴をページ送りで取得")
    p.add_argument("--days", type=int, default=30, help="何日前まで遡るか（既定30）")
    p.add_argument("--channel-id", type=int, default=0, help="指定時はそのチャンネルのみ")
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="出力JSONパス（省略時 work/history_YYYYMMDD.json）",
    )
    return p.parse_args()


async def fetch_channel_since(
    channel: discord.abc.Messageable,
    since: datetime,
) -> list[dict]:
    rows: list[dict] = []
    async for message in channel.history(limit=None, after=since, oldest_first=True):
        rows.append(
            {
                "id": str(message.id),
                "channel_id": str(message.channel.id),
                "channel_name": getattr(message.channel, "name", ""),
                "author": str(message.author),
                "author_id": str(message.author.id),
                "content": message.content,
                "timestamp": message.created_at.astimezone(timezone.utc).isoformat(),
                "attachments": len(message.attachments),
                "pinned": message.pinned,
            }
        )
    return rows


async def main() -> int:
    args = parse_args()
    if not TOKEN or TOKEN.startswith("YOUR_"):
        print(".env の DISCORD_BOT_TOKEN を設定してください", file=sys.stderr)
        return 1
    if not GUILD_ID and not args.channel_id:
        print("GUILD_ID か --channel-id が必要です", file=sys.stderr)
        return 1

    since = datetime.now(timezone.utc) - timedelta(days=args.days)
    out = args.out or (ROOT / "work" / f"history_{datetime.now(JST):%Y%m%d}.json")
    out.parent.mkdir(parents=True, exist_ok=True)

    intents = discord.Intents.default()
    # Portal で MESSAGE CONTENT INTENT が OFF でもログインできるよう既定は False
    intents.message_content = False
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready() -> None:
        all_rows: list[dict] = []
        try:
            if args.channel_id:
                channel = client.get_channel(args.channel_id)
                if channel is None:
                    channel = await client.fetch_channel(args.channel_id)
                channels = [channel]
            else:
                guild = client.get_guild(GUILD_ID)
                if guild is None:
                    print(f"Guild {GUILD_ID} が見つかりません（Bot未招待の可能性）", file=sys.stderr)
                    await client.close()
                    return
                me = guild.me
                channels = []
                for c in guild.text_channels:
                    if me is None or c.permissions_for(me).read_message_history:
                        channels.append(c)

            for channel in channels:
                name = getattr(channel, "name", str(getattr(channel, "id", "?")))
                print(f"取得中: #{name}")
                try:
                    rows = await fetch_channel_since(channel, since)
                except discord.Forbidden:
                    print(f"  権限なしのためスキップ: #{name}")
                    continue
                print(f"  {len(rows)} 件")
                all_rows.extend(rows)
        finally:
            payload = {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "since": since.isoformat(),
                "days": args.days,
                "message_count": len(all_rows),
                "messages": all_rows,
            }
            out.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"保存: {out}（合計 {len(all_rows)} 件）")
            await client.close()

    try:
        await client.start(TOKEN)
    except discord.LoginFailure as e:
        print(f"ログイン失敗: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
