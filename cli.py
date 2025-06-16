import os, sqlite3, time, asyncio
from langdetect import detect
from telethon import TelegramClient
from telethon.tl.functions.contacts import SearchRequest

os.makedirs("sessions", exist_ok=True)
LOG_PATH = "logs/log.txt"

def log(msg):
    ts = time.strftime("[%Y-%m-%d %H:%M:%S]")
    print(f"{ts} {msg}")
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"{ts} {msg}\n")

def main():
    kw_raw = input("🔎 Ключевые слова (через запятую): ")
    keywords = [k.strip() for k in kw_raw.split(",") if k.strip()]
    #  lang_raw = input("🌍 Языки (через запятую, пусто = без фильтра): ")
    #  lang_filter = [l.strip().lower() for l in lang_raw.split(",") if l.strip()]

    phone    = input("📱 Номер Telegram (+380...): ").strip()
    api_id   = int(input("🧩 API ID: ").strip())
    api_hash = input("🔐 API HASH: ").strip()

    conn = sqlite3.connect("data/found_channels.db")
    cur  = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS channels (
                     id INTEGER PRIMARY KEY,
                     username TEXT UNIQUE,
                     title TEXT,
                     lang TEXT)""")
    conn.commit()

    client = TelegramClient(f"sessions/{phone}", api_id, api_hash)

    async def runner():
        await client.start(phone=phone)
        log("✅ Авторизован")

        for kw in keywords:
            log(f"🔍 Поиск «{kw}»")
            try:
                res = await client(SearchRequest(q=kw, limit=100))
            except Exception as e:
                log(f"⚠️ Search error: {e}")
                continue

            for chat in res.chats:
                if not getattr(chat, "username", None):
                    continue
                uname = chat.username.lower()
                title = chat.title or ""

                #  # язык-фильтр (если нужен)
                #  try:
                #      msgs = await client.get_messages(uname, limit=3)
                #      text = " ".join(m.text for m in msgs if m.text)
                #      lang = detect(text) if text else "unknown"
                #  except Exception:
                #      lang = "unknown"
                #  if lang_filter and lang not in lang_filter:
                #      continue
                lang = "unknown"  # собираем всё, язык можно вычислить потом

                try:
                    cur.execute("INSERT OR IGNORE INTO channels(username,title,lang) VALUES(?,?,?)",
                                (uname, title, lang))
                    conn.commit()
                    log(f"   ➕ @{uname} добавлен")
                except Exception as e:
                    log(f"   ⚠️ DB error @{uname}: {e}")

        await client.disconnect()
        conn.close()
        log("🛑 Готово")

    asyncio.run(runner())

if __name__ == "__main__":
    main()
