import asyncio
import pytz
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from core.chatter import run_once

KYIV = pytz.timezone("Europe/Kyiv")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%d.%m.%Y %H:%M:%S",
)

async def main() -> None:
    """Старт APScheduler и бесконечное ожидание (для Railway)."""
    sched = AsyncIOScheduler(timezone=KYIV)
    # каждые 30 минут с 09:00 до 23:30 по Киеву
    sched.add_job(run_once, "cron", minute="*/30", hour="9-23")
    sched.start()
    logging.info("✅ Планировщик запущен (09:00-23:30, шаг 30 мин).")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
