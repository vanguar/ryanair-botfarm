"""
Коммент-бот: перебирает каналы, пишет короткий совет, метит невидимым
WATERMARK (U+2060#x9f). В одном проходе идёт по каналам, пока не отправит
успешно или не исчерпает базу. Аккаунт берётся случайно из config.json.
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
from pathlib import Path
from telethon.sessions import StringSession

# ── базовая настройка ──────────────────────────────────────────
load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")
KYIV           = pytz.timezone("Europe/Kyiv")
WATERMARK      = "\u2060#x9f"
DB_PATH        = "data/found_channels.db"
ROOT = Path(__file__).resolve().parent.parent          # /app
SESS_DIR = os.getenv("SESS_DIR", str(ROOT / "sessions"))
Path(SESS_DIR).mkdir(parents=True, exist_ok=True)


# включить RPC-трейсы Telethon, если TG_DEBUG=1
if os.getenv("TG_DEBUG", "").lower() in {"1", "true", "yes"}:
    logging.getLogger("telethon").setLevel(logging.DEBUG)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%d.%m.%Y %H:%M:%S",
)
log = logging.getLogger(__name__)

PROMPT_SYSTEM = (
    "Ты дружелюбный путешественник, обожаешь дешёвые перелёты и делишься советами."
)
PROMPT_USER = (
    "Напиши до 30 слов о бюджетных авиаперелётах. Упомяни бот @ryanair_deals_bot, "
    "≤2 эмодзи, язык тот же, что в чате."
)

# ── утилиты ────────────────────────────────────────────────────
def now() -> datetime:
    return datetime.now(tz=KYIV)


def gen_msg() -> str:
    """Получить короткий комментарий от ChatGPT."""
    rsp = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": PROMPT_SYSTEM},
            {"role": "user",   "content": PROMPT_USER},
        ],
        temperature=0.9,
        max_tokens=60,
    )
    return rsp.choices[0].message.content.strip()


def load_cfg() -> dict:
    with open("config.json", encoding="utf-8") as f:
        return json.load(f)


# ── основная корутина ─────────────────────────────────────────
async def run_once() -> bool:
    """Перебирает каналы, пока не запостит комментарий (или не исчерпает базу)."""
    cfg = load_cfg()
    cd_min, cd_max = cfg.get("cooldown_range", [24, 24])

    account = random.choice(cfg["accounts"])
    log.info("🤖 Работаю под аккаунтом: %s", account.get("name", account["phone"]))

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    cur = db.cursor()

    if account.get("session"):
        client = TelegramClient(
            StringSession(account["session"]),
            account["api_id"],
            account["api_hash"],
        )
    else:
        client = TelegramClient(
            os.path.join(SESS_DIR, account["name"]),
            account["api_id"],
            account["api_hash"],
        )


    await client.start(phone=account["phone"])

    try:
        while True:
            # берём случайный канал без кулдауна
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
                log.warning("Каналов без кулдауна не осталось.")
                return False

            uname = row["username"]
            log.info("Пробую писать в @%s …", uname)

            # попытка подписаться (если ещё нет)
            try:
                await client(JoinChannelRequest(uname))
            except Exception:
                pass  # не критично

            try:
                text = gen_msg()
                to_send = f"{text} {WATERMARK}"
                msg = await client.send_message(uname, to_send)
                log.info("✔ Отправлено (msg_id=%s): %s", msg.id, text)

                # ставим кулдаун и выходим
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
                cur.execute(
                    "UPDATE channels SET type='readonly' WHERE id=?", (row["id"],)
                )
                db.commit()
                # продолжаем цикл — берём следующий канал

            except Exception as e:
                log.error("⚠️  Ошибка в @%s: %s", uname, e)
                return False

    finally:
        await client.disconnect()
        db.close()


# ── ручной запуск ────────────────────────────────────────────
if __name__ == "__main__":
    asyncio.run(run_once())
