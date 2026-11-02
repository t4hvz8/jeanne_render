# создать pip freeze > requirements.txt
# установить pip install -r requirements.txt
import asyncio
import logging
import os
import libsql
import sqlite3

from pathlib import Path

from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from pathlib import Path




# --- Корневая папка = папка, где лежит этот скрипт ---
BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)


# --- Структура папок проекта ---
REQUIRED_DIRS = [
    BASE_DIR / "data" / "bd",
    BASE_DIR / "data" / "var",
    BASE_DIR / "data" / "var" / "history",
    BASE_DIR / "data" / "var" / "post",
    BASE_DIR / "data" / "var" / "scr" / "avatars",
    BASE_DIR / "data" / "files",
]


def ensure_directories() -> None:
    """Создаёт все необходимые папки, если их нет."""
    for directory in REQUIRED_DIRS:
        if not directory.exists():
            directory.mkdir(parents=True, exist_ok=True)
            logging.info("Создана папка: %s", directory)
        elif not directory.is_dir():
            raise NotADirectoryError(f"Путь существует, но это не папка: {directory}")
    logging.info("Структура папок проверена. Корень: %s", BASE_DIR)


# Опционально: перейти в неё, чтобы относительные пути в коде/библиотеках работали от неё
os.chdir(BASE_DIR)

# Загружаем .env именно из корневой папки бота (не из cwd!)


# --- Конфигурация ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ROLE_URL = os.getenv("ROLE_URL")
ROLE_TOKEN = os.getenv("ROLE_TOKEN")

#  настройки вебхука
BASE_WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL", "https://render-2-v6lm.onrender.com")
WEBHOOK_PATH = "/webhook"
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "my-secret-token")
WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = int(os.getenv("PORT", 10000))

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Пример: пути к файлам теперь строим от BASE_DIR
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)  # создаём папку data рядом со скриптом, если её нет
# Пример использования:
# db_path = DATA_DIR / "bot.db"
# log_path = BASE_DIR / "bot.log"


# --- Роутер и хендлеры ---
router = Router()




@router.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    await message.answer(
        f"Привет, {message.from_user.full_name}!\n"
        f"Твой user_id: <code>{message.from_user.id}</code>\n"
        f"Бот работает через polling.\n"
        f"Корневая папка: <code>{BASE_DIR}</code>"
    )

@router.message(Command("myid"))
async def myid_handler(message: Message) -> None:
    await message.answer(f"Твой user_id: <code>{message.from_user.id}</code>")
    idtg = message.from_user.id
    name = message.chat.first_name
    con = libsql.connect(
        database=os.environ["ROLE_URL"],
        auth_token=os.environ["ROLE_TOKEN"],
    )
    con.execute(
            "INSERT INTO admins (idtg, name) VALUES (?, ?)",
            (idtg, name),
        )
    con.commit()
    print (f"отдал на запись {idtg} {name}")
    con.close()

@router.message(F.text)
async def echo_handler(message: Message) -> None:
    await message.answer(f"Вы написали: {message.text}")


# --- Ежедневная задача ---
async def send_daily_message(bot: Bot) -> None:
    try:
        await bot.send_message(ADMIN_ID, "🔔 Ежедневное сообщение: 14:00 UTC. Всё работает.")
        logging.info("Daily message sent to %s", ADMIN_ID)
    except Exception as e:
        logging.exception("Failed to send daily message: %s", e)


# --- Запуск (polling) ---
scheduler: AsyncIOScheduler | None = None

async def on_startup(bot: Bot) -> None:
    global scheduler

    #  установка вебхука
    await bot.set_webhook(
        f"{BASE_WEBHOOK_URL}{WEBHOOK_PATH}",
        secret_token=WEBHOOK_SECRET,
        drop_pending_updates=True,
    )

    # Удаляем ранее установленный вебхук, иначе polling не заработает
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Webhook deleted, switching to polling")

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        send_daily_message,
        CronTrigger(hour=14, minute=00, timezone="UTC"),
        args=[bot],
        id="daily_message",
        replace_existing=True,
    )
    scheduler.start()
    logging.info("Scheduler started. Next run: %s", scheduler.get_job("daily_message").next_run_time)

async def on_shutdown(bot: Bot) -> None:
    global scheduler
    if scheduler:
        scheduler.shutdown(wait=False)
        logging.info("Scheduler stopped")


def setup_logging() -> None:
    """Логи пишем рядом со скриптом, а не в cwd."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(BASE_DIR / "data/files/bot.log", encoding="utf-8"),
        ],
    )


def role_db():
    """Возвращает соединение с удалённой базой данных Turso."""
    # Используем локальное имя файла (например, :memory:), но sync_url указывает на удалённую базу данных
    # Это режим Embedded Replica, чтение происходит локально, запись синхронизируется в облако
    conn = libsql.connect(
        "role.db",  # локальный файл-заглушка, на Render временный, но данные в безопасности в облаке
        sync_url=ROLE_URL,
        auth_token=ROLE_TOKEN,
    )
    return con


def main():
    logging.basicConfig(level=logging.INFO)

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    dp.startup.register(on_startup)

    app = web.Application()
    handler = SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=WEBHOOK_SECRET)
    handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    app.router.add_get("/", lambda r: web.Response(text="OK"))

    web.run_app(app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))


if __name__ == "__main__":
    asyncio.run(main())