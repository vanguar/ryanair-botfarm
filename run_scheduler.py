from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz, asyncio, core.chatter as chatter

KYIV = pytz.timezone("Europe/Kyiv")

async def job():
    await chatter.run_once()

def main():
    sched = AsyncIOScheduler(timezone=KYIV)
    sched.add_job(job, "cron", minute="*/30", hour="9-23")
    sched.start()
    print("Запущено. Постим каждые 30 мин с 09:00 до 24:00 (Киев).")
    asyncio.get_event_loop().run_forever()

if __name__ == "__main__":
    main()
