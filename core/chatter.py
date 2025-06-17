# core/chatter.py
"""
Бот-«ферма»: находит релевантные каналы, пишет комментарии и помечает их
невидимым водяным знаком, чтобы затем легко искать.

▪︎ Водяной знак добавляется ТОЛЬКО к отправляемому сообщению.
▪︎ В лог (stdout) выводится чистый текст без знака, чтобы логи были
  читаемыми и без «мусорных» символов.
▪︎ Аккаунт теперь выбирается случайно из списка в config.json — достаточно
  добавить новые профили в конфиг, код менять не нужно.
"""

import os
import json
import sqlite3
import asyncio
import random
import logging
from datetime import datetime, timedelta

import pytz
from dotenv import load_dotenv
import openai
from telethon import TelegramClient
from telethon.errors import ChatWriteForbiddenError, ChatAdminRequiredError
from telethon.tl.functions.channels import JoinChannelRequest

# ────────────────────────── настройка и константы ─────────────────────────────
load_dotenv()

openai.api_key  = os.getenv("OPENAI_API_KEY")
KYIV            = pytz.timezone("Europe/Kyiv")
WATERMARK       = "\u2060#x9f"                            # невидимый тег
DB_PATH         = "data/found_channels.db"
SESS_DIR        = os.getenv("SESS_DIR", "sessions")

PROMPT_SYSTEM = (
    "Ты дружелюбный путешественник, обожаешь дешёвые перелёты и делишься "
    "полезными советами в чатах."
)
PROMPT_USER = (
    "Напиши до 30 слов о бюджетных авиаперелётах. Упомяни, что искать акции "
    "помогает бот @ryanair_deals_bot. Не больше двух эмодзи. Язык тот же, что "
    "используется в чате."
)

# ──────────────────────────── логирование ────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%d.%m.%Y %H:%M:%S",
)
log = logging.getLogger(__name__)

# ──────────────────────────── утилиты ────────────────────────────────────────
def now() -> datetime:
    return datetime.now(tz=KYIV)


def gen_msg() -> str:
    """Получить готовый короткий комментарий от ChatGPT."""
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
    with open("config.json", encoding="utf-8") as f:
        return json.load(f)


# ──────────────────────────── основная корутина ──────────────────────────────
async def run_once() -> bool:
    """Один проход: выбрать канал, отправить комментарий, обновить БД."""
    cfg = load_cfg()
    cd_min, cd_max = cfg.get("cooldown_range", [24, 24])

    # 🔹 выбираем случайный аккаунт вместо фиксированного
    account = random.choice(cfg["accounts"])
    log.info("🤖 Работаю под аккаунтом: %s", account.get("name", account["phone"]))

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    cur = db.cursor()

    # Берём случайный подходящий канал
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
        log.warning("Нет подходящих групп: база пуста или все на кулдауне.")
        db.close()
        return False

    uname = row["username"]
    log.info("Пробую писать в @%s …", uname)

    client = TelegramClient(
        os.path.join(SESS_DIR, account["name"]),
        account["api_id"],
        account["api_hash"],
    )

    try:
        await client.start(phone=account["phone"])

        # на всякий случай попробуем вступить
        try:
            await client(JoinChannelRequest(uname))
        except Exception:
            pass

        # генерируем сообщение
        text_clean = gen_msg()
        msg_send   = f"{text_clean} {WATERMARK}"       # сюда вклеиваем знак

        await client.send_message(uname, msg_send)
        log.info("✔ Отправлено: %s", text_clean)

        # обновляем кулдаун
        pause_h = random.randint(cd_min, cd_max)
        next_ts = (now() + timedelta(hours=pause_h)).isoformat()

        cur.execute(
            "UPDATE channels SET next_allowed=? WHERE id=?",
            (next_ts, row["id"]),
        )
        db.commit()
        return True

    except (ChatWriteForbiddenError, ChatAdminRequiredError):
        log.warning("🚫 В @%s писать нельзя — помечаю readonly", uname)
        cur.execute("UPDATE channels SET type='readonly' WHERE id=?", (row["id"],))
        db.commit()
        return False

    except Exception as e:
        log.error("⚠️  Ошибка при отправке в @%s: %s", uname, e)
        return False

    finally:
        await client.disconnect()
        db.close()


# ──────────────────────────── standalone запуск ──────────────────────────────
if __name__ == "__main__":
    asyncio.run(run_once())
