"""
Запускается один раз, забирает порцию ключевиков,
добавляет каналы в БД, тут же проставляет типы.
"""
import asyncio, os, sqlite3, time, json, pathlib
from telethon import TelegramClient
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.functions.channels import GetFullChannelRequest

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB   = ROOT / "data" / "found_channels.db"
KW_FILE = ROOT / "keywords.txt"
BATCH   = 10        # сколько ключей за один запуск
LIMIT   = 100       # сколько чатов на ключ

def load_account():
    cfg = json.load(open(ROOT / "config.json", encoding="utf-8"))
    acc = cfg["accounts"][0]
    return acc

def next_keywords():
    """берём первые BATCH строк из keywords.txt и помечаем их как использованные"""
    if not KW_FILE.exists():
        return []
    lines = KW_FILE.read_text(encoding="utf-8").splitlines()
    fresh, rest = lines[:BATCH], lines[BATCH:]
    KW_FILE.write_text("\n".join(rest), encoding="utf-8")
    return [l.strip() for l in fresh if l.strip()]

async def fetch():
    kws = next_keywords()
    if not kws:
        print("🔔 нет новых ключей – keywords.txt пуст.")
        return

    acc = load_account()
    client = TelegramClient(
        ROOT / "sessions" / acc["name"],
        acc["api_id"],
        acc["api_hash"]
    )
    await client.start(phone=acc["phone"])

    conn = sqlite3.connect(DB)
    cur  = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS channels(
         id INTEGER PRIMARY KEY,
         username TEXT UNIQUE,
         title TEXT,
         lang TEXT,
         type TEXT,
         last_post TEXT
    )""")

    for kw in kws:
        print("🔍", kw)
        try:
            res = await client(SearchRequest(q=kw, limit=LIMIT))
        except Exception as e:
            print("   ⚠️", e)
            continue

        for chat in res.chats:
            if not getattr(chat, "username", None):
                continue
            uname = chat.username.lower()
            title = chat.title or ""
            try:
                cur.execute("INSERT OR IGNORE INTO channels(username,title,lang) VALUES(?,?,?)",
                            (uname, title, "unknown"))
                conn.commit()
            except Exception:
                pass

    # помечаем типы
    rows = cur.execute("SELECT id,username FROM channels WHERE type IS NULL").fetchall()
    print("Проверяем тип для", len(rows), "чатов")
    for cid, uname in rows:
        try:
            full = await client(GetFullChannelRequest(uname))
            ch   = full.full_chat
            tg_type = "group" if getattr(ch, "megagroup", False) else "channel"
            if tg_type == "channel" and ch.linked_chat_id:
                tg_type = "comment"
        except Exception:
            tg_type = "dead"
        cur.execute("UPDATE channels SET type=? WHERE id=?", (tg_type, cid))
    conn.commit()
    conn.close()
    await client.disconnect()
    print("✅ fetch_new завершён")

if __name__ == "__main__":
    asyncio.run(fetch())
