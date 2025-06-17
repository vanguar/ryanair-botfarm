"""
Бот-«ферма»: находит релевантные каналы, пишет комментарии и помечает их
невидимым водяным знаком, чтобы затем легко искать.
"""

import os, json, sqlite3, asyncio, random, logging
from datetime import datetime, timedelta
from pathlib import Path

import pytz
from dotenv import load_dotenv
import openai
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import ChatWriteForbiddenError, ChatAdminRequiredError
from telethon.tl.functions.channels import JoinChannelRequest

# ──────────── константы ─────────────
load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")
KYIV           = pytz.timezone("Europe/Kyiv")

ROOT      = Path(__file__).resolve().parent.parent      # /app
SESS_DIR  = Path(os.getenv("SESS_DIR", ROOT / "sessions"))
SESS_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH   = ROOT / "data" / "found_channels.db"
WATERMARK = "\u2060#x9f"   # невидимый тег

PROMPT_SYSTEM = (
    "Ты дружелюбный путешественник, обожаешь дешёвые перелёты и делишься "
    "полезными советами в чатах."
)
PROMPT_USER = (
    "Напиши до 30 слов о бюджетных авиаперелётах. Упомяни, что искать акции "
    "помогает бот @ryanair_deals_bot. Не больше двух эмодзи. Язык тот же, что "
    "используется в чате."
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%d.%m.%Y %H:%M:%S",
)
log = logging.getLogger(__name__)


# ──────────── утилиты ─────────────
def now() -> datetime:
    return datetime.now(tz=KYIV)


def gen_msg() -> str:
    resp = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": PROMPT_SYSTEM},
            {"role": "user", "content": PROMPT_USER},
        ],
        temperature=0.9,
        max_tokens=60,
    )
    return resp.choices[0].message.content.strip()


def load_cfg() -> dict:
    with open(ROOT / "config.json", encoding="utf-8") as f:
        return json.load(f)


# ────────────── основная корутина ──────────────
async def run_once() -> bool:
    """Пробуем писать, пока не будет успеха. После первого удачного поста — пауза."""
    cfg = load_cfg()
    cd_min, cd_max = cfg.get("cooldown_range", [24, 24])

    account = random.choice(cfg["accounts"])
    log.info("🤖 Работаю под аккаунтом: %s", account.get("name", account["phone"]))

    # ───── создание клиента ─────
    if account.get("session"):
        client = TelegramClient(
            StringSession(account["session"]),
            account["api_id"], account["api_hash"]
        )
        await client.connect()
        if not await client.is_user_authorized():
            raise RuntimeError("❌ StringSession не авторизован — обнови config.json.")
    else:
        client = TelegramClient(
            SESS_DIR / f"{account['name']}.session",
            account["api_id"], account["api_hash"]
        )
        await client.start(phone=account["phone"])

    # ───── БД и таблица ─────
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    cur = db.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS channels (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        username     TEXT UNIQUE COLLATE NOCASE,
        type         TEXT DEFAULT 'group',
        next_allowed TEXT
    );
    """)
    db.commit()

    # ───── цикл «пока не получится» ─────
    while True:
        row = cur.execute("""
            SELECT * FROM channels
            WHERE type IN ('group','comment')
              AND (next_allowed IS NULL OR next_allowed < datetime('now'))
            ORDER BY RANDOM()
            LIMIT 1
        """).fetchone()

        if not row:
            log.warning("Нет подходящих групп: база пуста или все на кулдауне.")
            await client.disconnect()
            db.close()
            return False

        uname = row["username"]
        log.info("Пробую писать в @%s …", uname)

        try:
            try:
                await client(JoinChannelRequest(uname))   # вдруг нужно вступить
            except Exception:
                pass

            text = gen_msg()
            await client.send_message(uname, f"{text} {WATERMARK}")
            log.info("✔ Отправлено: %s", text)

            # ставим кулдаун и завершаем цикл
            pause_h = random.randint(cd_min, cd_max)
            next_ts = (now() + timedelta(hours=pause_h)).isoformat()
            cur.execute("UPDATE channels SET next_allowed=? WHERE id=?",
                        (next_ts, row["id"]))
            db.commit()

            await client.disconnect()
            db.close()
            return True

        except (ChatWriteForbiddenError, ChatAdminRequiredError):
            # нельзя писать здесь — помечаем readonly и пробуем следующую
            log.warning("🚫 В @%s писать нельзя — помечаю readonly", uname)
            cur.execute("UPDATE channels SET type='readonly' WHERE id=?", (row["id"],))
            db.commit()
            # цикл продолжается → берём другой канал

        except Exception as e:
            log.error("⚠️ Ошибка при отправке в @%s: %s", uname, e)
            # не метим readonly, попробуем в другой раз
            await asyncio.sleep(2)  # маленькая пауза, чтобы не крутиться мгновенно


# ────────────── standalone запуск ──────────────
if __name__ == "__main__":
    asyncio.run(run_once())
