# run_scheduler.py

import asyncio
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import core.chatter as chatter

# Устанавливаем часовой пояс для корректной работы расписания
KYIV = pytz.timezone("Europe/Kyiv")

async def job():
    """
    Асинхронная задача-обертка для выполнения.
    Такая обертка полезна, если в будущем вы захотите добавить
    дополнительную логику до или после основного вызова (например, логирование).
    """
    await chatter.run_once()

async def main():
    """
    Основная асинхронная функция для настройки и запуска планировщика.
    """
    # Создаем экземпляр планировщика с указанием часового пояса
    sched = AsyncIOScheduler(timezone=KYIV)

    # Добавляем задачу в расписание: запускать каждые 30 минут (в :00 и :30)
    # в период с 9:00 до 23:59 по киевскому времени.
    sched.add_job(job, "cron", minute="*/30", hour="9-23") #

    # Запускаем планировщик. Ошибки не будет, так как цикл asyncio уже работает.
    sched.start()
    print("✅ Планировщик запущен. Постинг каждые 30 минут с 09:00 до 23:59 (Киев).")

    # Используем asyncio.Event().wait() для "вечного" ожидания.
    # Это элегантный способ не давать скрипту завершиться.
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        print("Планировщик остановлен.")

if __name__ == "__main__":
    # asyncio.run() создает и запускает цикл событий, выполняя нашу main() функцию.
    # Это современный и правильный способ запуска asyncio-приложений.
    asyncio.run(main())