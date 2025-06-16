import os, sqlite3, random, asyncio, pytz, openai
from datetime import datetime, timedelta
from telethon import TelegramClient
from telethon.tl.functions.channels import JoinChannelRequest
from dotenv import load_dotenv
load_dotenv()                     # ← подхватывает .env в корне проекта
openai.api_key = os.getenv("OPENAI_API_KEY")
import json


KYIV = pytz.timezone("Europe/Kyiv")

PROMPT_SYSTEM = "Ты дружелюбный пользователь чатов о путешествиях."
PROMPT_USER   = (
    "Напиши короткий (до 30 слов) пост для группы о бюджетных путешествиях. "
    "Ненавязчиво порекомендуй Telegram-бот @ryanair_deals_bot, который ищет акции Ryanair. "
    "Добавь не больше двух эмодзи. Пиши на том же языке, на котором общается группа."
)

def now():
    return datetime.now(tz=KYIV)

def gen_msg():
    r = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": PROMPT_SYSTEM},
            {"role": "user",    "content": PROMPT_USER}
        ],
        max_tokens=60,
        temperature=0.9
    )
    return r.choices[0].message.content.strip()

async def run_once():
    db = sqlite3.connect("data/found_channels.db")
    db.row_factory = sqlite3.Row
    cur = db.cursor()

    row = cur.execute("""
        SELECT * FROM channels
        WHERE type IN ('group','comment')
          AND (last_post IS NULL OR last_post < ?)
        ORDER BY RANDOM()
        LIMIT 1
    """, ((now() - timedelta(hours=24)).isoformat(),)).fetchone()

    if not row:
        print("Нет новых групп для постинга.")
        db.close()
        return

    uname = row["username"]
    print(f"→ Пишу в @{uname}")

    cfg = json.load(open("config.json", encoding="utf-8"))
    acc = cfg["accounts"][0]

    client = TelegramClient(f"sessions/{acc['name']}",
                            acc["api_id"], acc["api_hash"])

    try:
        await client.start(phone=acc["phone"])
        try:
            await client(JoinChannelRequest(uname))
        except:
            pass
        text = gen_msg()
        await client.send_message(uname, text)
        print("   ✔", text)
        cur.execute("UPDATE channels SET last_post=? WHERE id=?",
                    (now().isoformat(), row["id"]))
        db.commit()
    except Exception as e:
        print("   ⚠ Ошибка:", e)
    finally:
        await client.disconnect()
        db.close()

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_once())
