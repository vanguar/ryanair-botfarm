"""
Берёт пачку ключевиков из keywords.txt, ищет каналы,
добавляет их в БД и сразу помечает тип: group / comment /
readonly / channel / dead
"""

import asyncio, os, sqlite3, json, pathlib
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.functions.channels import GetFullChannelRequest

ROOT      = pathlib.Path(__file__).resolve().parent.parent      # /app
DB        = ROOT / "data" / "found_channels.db"
KWFILE    = ROOT / "keywords.txt"
SESS_DIR  = ROOT / "sessions"                                   # /app/sessions
SESS_DIR.mkdir(parents=True, exist_ok=True)

BATCH = 10    # сколько ключей за прогон
LIMIT = 100   # сколько чатов на ключ


def load_account() -> dict:
    cfg = json.load(open(ROOT / "config.json", encoding="utf-8"))
    return cfg["accounts"][0]


def next_keywords() -> list[str]:
    if not KWFILE.exists():
        return []
    lines = KWFILE.read_text(encoding="utf-8").splitlines()
    fresh, rest = lines[:BATCH], lines[BATCH:]
    KWFILE.write_text("\n".join(rest), encoding="utf-8")
    return [l.strip() for l in fresh if l.strip()]


async def fetch() -> None:
    acc = load_account()
    kws = next_keywords()
    if not kws:
        print("⚠️  keywords.txt пуст — нечего искать")
        return

    # ──────── создаём Telegram-клиент ────────
    if acc.get("session"):
        client = TelegramClient(
            StringSession(acc["session"]),
            acc["api_id"], acc["api_hash"]
        )
        await client.connect()
        if not await client.is_user_authorized():
            raise RuntimeError(
                "❌ StringSession не авторизован. Сгенерируйте новую строку и "
                "обновите config.json."
            )
    else:
        client = TelegramClient(
            SESS_DIR / acc["name"],
            acc["api_id"], acc["api_hash"]
        )
        await client.start(phone=acc["phone"])
    # ─────────────────────────────────────────
    DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB)
    cur = db.cursor()

    added_total = 0
    try:
        for kw in kws:
            print(f"🔍 keyword: {kw!r}")
            res = await client(SearchRequest(q=kw, limit=LIMIT))
            for chat in res.chats:
                uname = chat.username
                if not uname:
                    continue
                cur.execute(
                    "INSERT OR IGNORE INTO channels(username) VALUES(?)",
                    (uname.lower(),)
                )
            db.commit()
            added_total += cur.rowcount
            print(f"   + {cur.rowcount} new channels")

    finally:
        db.close()
        await client.disconnect()

    print(f"✅ fetch_new завершён — добавлено {added_total} записей")


if __name__ == "__main__":
    asyncio.run(fetch())
