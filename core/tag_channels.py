import sqlite3, asyncio
from telethon import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest

DB = "data/found_channels.db"
PHONE = input("Номер (+380…): ").strip()
API_ID = int(input("API ID: ").strip())
API_HASH = input("API HASH: ").strip()

async def tag():
    conn = sqlite3.connect(DB)
    cur  = conn.cursor()
    cur.execute("ALTER TABLE channels ADD COLUMN type TEXT")  # игнорит, если колонка есть

    client = TelegramClient(f"sessions/{PHONE}", API_ID, API_HASH)
    await client.start(phone=PHONE)

    rows = cur.execute("SELECT id,username FROM channels WHERE type IS NULL").fetchall()
    print("Всего на проверку:", len(rows))

    for cid, uname in rows:
        try:
            full = await client(GetFullChannelRequest(uname))
            ch   = full.full_chat
            tg_type = "group" if getattr(ch, "megagroup", False) else "channel"
            # если у канала включены комментарии — Telethon даст отдельный peer, это пишет как 'comment'
            if tg_type == "channel" and ch.linked_chat_id:
                tg_type = "comment"
            cur.execute("UPDATE channels SET type=? WHERE id=?", (tg_type, cid))
            conn.commit()
            print(f"@{uname:25} → {tg_type}")
        except Exception as e:
            cur.execute("UPDATE channels SET type='dead' WHERE id=?", (cid,))
            conn.commit()
            print(f"@{uname:25} → dead ({e})")

    await client.disconnect()
    conn.close()

asyncio.run(tag())
