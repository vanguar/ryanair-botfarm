# core/chatter.py
import os, sqlite3, asyncio, pytz, json
from datetime import datetime, timedelta

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import ChatWriteForbiddenError, ChatAdminRequiredError
from telethon.tl.functions.channels import JoinChannelRequest
import openai

# ─── инициализация ───────────────────────────────────────────────
load_dotenv()                                   # берём .env
openai.api_key = os.getenv("OPENAI_API_KEY")    # ключ GPT

KYIV = pytz.timezone("Europe/Kyiv")
DB_PATH = "data/found_channels.db"

PROMPT_SYSTEM = "Ты дружелюбный пользователь чатов о путешествиях."
PROMPT_USER = (
    "Напиши короткий (до 30 слов) пост для группы о бюджетных путешествиях. "
    "Ненавязчиво порекомендуй Telegram-бот @ryanair_deals_bot, который ищет акции Ryanair. "
    "Добавь не больше двух эмодзи. Пиши на том языке, на котором общается группа."
)

# ─── утилиты ─────────────────────────────────────────────────────
def now() -> datetime:
    return datetime.now(tz=KYIV)

def gen_msg() -> str:
    """Получаем рекламное сообщение из GPT-4o"""
    rsp = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": PROMPT_SYSTEM},
            {"role": "user",   "content": PROMPT_USER}
        ],
        temperature=0.9,
        max_tokens=60,
    )
    return rsp.choices[0].message.content.strip()

def pick_account() -> dict:
    cfg = json.load(open("config.json", encoding="utf-8"))
    return cfg["accounts"][0]        # если добавишь больше акков — выбирай рандомно

# ─── основная работа ─────────────────────────────────────────────
async def run_once() -> None:
    db  = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    cur = db.cursor()

    # берём первую подходящую группу, куда не писали за последние 24 ч
    row = cur.execute(
        """
        SELECT * FROM channels
        WHERE type IN ('group','comment')
          AND (last_post IS NULL OR last_post < ?)
        ORDER BY RANDOM()
        LIMIT 1
        """,
        ((now() - timedelta(hours=24)).isoformat(),),
    ).fetchone()

    if not row:
        print("Нет подходящих групп: всё обработано или база пуста.")
        db.close()
        return

    uname = row["username"]
    print(f"→ Пишу в @{uname}")

    acc = pick_account()
    client = TelegramClient(
        os.path.join("sessions", acc["name"]),
        acc["api_id"],
        acc["api_hash"],
    )

    try:
        await client.start(phone=acc["phone"])

        # вступаем, если ещё не внутри
        try:
            await client(JoinChannelRequest(uname))
        except Exception:
            pass

        text = gen_msg()
        await client.send_message(uname, text)
        print("   ✔ Отправлено:", text)

        cur.execute(
            "UPDATE channels SET last_post=? WHERE id=?",
            (now().isoformat(), row["id"]),
        )
        db.commit()

    # ── ловим «писать нельзя» и сразу помечаем readonly
    except ChatWriteForbiddenError:
        print(f"   🚫 В @{uname} писать запрещено — помечаю readonly")
        cur.execute("UPDATE channels SET type='readonly' WHERE id=?", (row["id"],))
        db.commit()

    except ChatAdminRequiredError:
        print(f"   🚫 В @{uname} могут писать только админы — помечаю readonly")
        cur.execute("UPDATE channels SET type='readonly' WHERE id=?", (row["id"],))
        db.commit()

    # ── любые другие ошибки просто печатаем
    except Exception as e:
        print("   ⚠️  Ошибка:", e)

    finally:
        await client.disconnect()
        db.close()

# ─── однократный запуск ──────────────────────────────────────────
if __name__ == "__main__":
    asyncio.run(run_once())
