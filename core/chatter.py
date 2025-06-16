# core/chatter.py
import os, json, sqlite3, asyncio, pytz, random
from datetime import datetime, timedelta
from dotenv import load_dotenv

from telethon import TelegramClient
from telethon.errors import ChatWriteForbiddenError, ChatAdminRequiredError
from telethon.tl.functions.channels import JoinChannelRequest
import openai

# ─── инициализация ───────────────────────────────────────────────
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

KYIV     = pytz.timezone("Europe/Kyiv")
DB_PATH  = "data/found_channels.db"
SESS_DIR = os.getenv("SESS_DIR", "sessions")   # <— здесь берётся /data/sessions

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

def load_cfg():
    return json.load(open("config.json", encoding="utf-8"))

# ─── основная работа ─────────────────────────────────────────────
async def run_once() -> bool:
    cfg      = load_cfg()
    cd_min, cd_max = cfg.get("cooldown_range", [24, 24])
    acc      = cfg["accounts"][0]

    db  = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    cur = db.cursor()

    # группа пригодна, если next_allowed либо NULL, либо уже прошло
    row = cur.execute(
        """
        SELECT * FROM channels
        WHERE type IN ('group','comment')
          AND (next_allowed IS NULL OR next_allowed < datetime('now'))
        ORDER BY RANDOM()
        LIMIT 1
        """
    ).fetchone()

    if not row:
        print("Нет подходящих групп: всё обработано или база пуста.")
        db.close()
        return False

    uname = row["username"]
    print(f"→ Пишу в @{uname}")

    client = TelegramClient(
        os.path.join(SESS_DIR, acc["name"]),
        acc["api_id"],
        acc["api_hash"],
    )

    try:
        await client.start(phone=acc["phone"])
        try:
            await client(JoinChannelRequest(uname))
        except Exception:
            pass

        text = gen_msg()
        await client.send_message(uname, text)
        print("   ✔ Отправлено:", text)

        pause_h   = random.randint(cd_min, cd_max)
        next_time = (now() + timedelta(hours=pause_h)).isoformat()

        cur.execute(
            "UPDATE channels SET next_allowed=? WHERE id=?",
            (next_time, row["id"]),
        )
        db.commit()
        return True

    except (ChatWriteForbiddenError, ChatAdminRequiredError):
        print(f"   🚫 В @{uname} писать нельзя — помечаю readonly")
        cur.execute("UPDATE channels SET type='readonly' WHERE id=?", (row["id"],))
        db.commit()
        return False

    except Exception as e:
        print("   ⚠️  Ошибка:", e)
        return False

    finally:
        await client.disconnect()
        db.close()

# ─── однократный запуск ──────────────────────────────────────────
if __name__ == "__main__":
    asyncio.run(run_once())
