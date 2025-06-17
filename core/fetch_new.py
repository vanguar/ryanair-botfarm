"""
Берёт пачку ключевиков из keywords.txt, ищет каналы,
добавляет их в БД и сразу помечает тип: group / comment /
readonly / channel / dead
"""

import asyncio, os, sqlite3, json, pathlib
from telethon import TelegramClient
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.functions.channels import GetFullChannelRequest

ROOT   = pathlib.Path(__file__).resolve().parent.parent
DB     = ROOT / "data" / "found_channels.db"
KWFILE = ROOT / "keywords.txt"

SESS_DIR = ROOT / "sessions"
SESS_DIR.mkdir(parents=True, exist_ok=True)

BATCH  = 10   # сколько ключей за прогон
LIMIT  = 100  # сколько чатов на ключ

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

async def fetch():
    kws = next_keywords()
    if not kws:
        print("🔔 keywords.txt пуст — нечего собирать.")
        return

    acc = load_account()
    client = TelegramClient(SESS_DIR / acc["name"],
                            acc["api_id"], acc["api_hash"])
    await client.start(phone=acc["phone"])

    conn = sqlite3.connect(DB)
    cur  = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS channels(
        id INTEGER PRIMARY KEY,
        username TEXT UNIQUE,
        title TEXT,
        lang TEXT,
        type TEXT,
        last_post TEXT)""")

    for kw in kws:
        print("🔍", kw)
        try:
            res = await client(SearchRequest(q=kw, limit=LIMIT))
        except Exception as e:
            print("   ⚠", e)
            continue

        for chat in res.chats:
            if not getattr(chat, "username", None):
                continue
            uname = chat.username.lower()
            title = chat.title or ""
            try:
                cur.execute("INSERT OR IGNORE INTO channels(username,title,lang)"
                            " VALUES(?,?,?)", (uname, title, "unknown"))
            except Exception:
                pass

    # ── помечаем типы сразу ───────────────────────────────────
    rows = cur.execute("SELECT id,username FROM channels WHERE type IS NULL").fetchall()
    print("Проверяем тип для", len(rows), "чатов")

    for cid, uname in rows:
        try:
            full = await client(GetFullChannelRequest(uname))
            ch   = full.full_chat
            tg_type = "group" if getattr(ch, "megagroup", False) else "channel"
            if tg_type == "channel" and ch.linked_chat_id:
                tg_type = "comment"

            # «readonly» — у группы/комментариев, если запрет на send_messages
            rights = getattr(ch, "default_banned_rights", None)
            if rights and rights.send_messages:
                tg_type = "readonly"

        except Exception:
            tg_type = "dead"

        cur.execute("UPDATE channels SET type=? WHERE id=?", (tg_type, cid))

    conn.commit()
    conn.close()
    await client.disconnect()
    print("✅ fetch_new завершён, база пополнена.")

if __name__ == "__main__":
    asyncio.run(fetch())
