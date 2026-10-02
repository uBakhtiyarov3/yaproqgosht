import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo
from aiohttp import web

from app import db
from app.config import config
from app.handlers import setup_routers
from app.keyboards import webapp_ready, webapp_url
from app.webapp import create_app

log = logging.getLogger("yaproq")


async def setup_bot_ui(bot: Bot) -> None:
    await bot.set_my_commands([
        BotCommand(command="start", description="Botni ishga tushirish"),
        BotCommand(command="menu", description="Menyu / buyurtma berish"),
        BotCommand(command="cart", description="Savat"),
        BotCommand(command="orders", description="Buyurtmalarim"),
        BotCommand(command="help", description="Yordam"),
    ])
    if webapp_ready():
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="🍔 Menyu", web_app=WebAppInfo(url=webapp_url()))
        )
    else:
        log.warning("WEBAPP_URL https emas — mini app tugmasi o'rnatilmadi")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not config.bot_token:
        raise SystemExit("BOT_TOKEN topilmadi. .env faylini to'ldiring (.env.example ga qarang).")

    await db.init_db(config.db_path)
    bot = Bot(config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(setup_routers())

    runner = web.AppRunner(create_app(bot))
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", config.port).start()
    log.info("Mini app server: http://0.0.0.0:%s  (WEBAPP_URL=%s)", config.port, config.webapp_url or "-")

    try:
        await setup_bot_ui(bot)
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
        await db.close_db()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
