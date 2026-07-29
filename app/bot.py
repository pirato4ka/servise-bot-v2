import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession

from app.config import settings
from app.database.db import init_db
from app.handlers import start, services, questionnaire, user_chat
from app.handlers.admin import (
    admin_panel, services_crud, reply_handler, stats, membership,
    confirm_payment, payment_check, debug_all, broadcast
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


async def main():
    await init_db()

    proxy_url = settings.PROXY_URL
    if proxy_url:
        logging.info(f"Использую прокси для Telegram: {proxy_url}")
        session = AiohttpSession(proxy=proxy_url)
    else:
        session = AiohttpSession()

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session
    )
    dp = Dispatcher()

    # Админские - порядок важен
    dp.include_router(confirm_payment.router)
    dp.include_router(broadcast.router)
    dp.include_router(reply_handler.router)
    dp.include_router(membership.router)
    dp.include_router(payment_check.router)
    dp.include_router(admin_panel.router)
    dp.include_router(services_crud.router)
    dp.include_router(stats.router)

    # Пользовательские
    dp.include_router(start.router)
    dp.include_router(questionnaire.router)
    dp.include_router(services.router)
    dp.include_router(user_chat.router)

    # DEBUG последним
    dp.include_router(debug_all.router)

    await bot.delete_webhook(drop_pending_updates=True)
    me = await bot.get_me()
    logging.info(f"Bot started @{me.username} id={me.id} proxy={'ON' if proxy_url else 'OFF'} ADMIN_CHAT={settings.ADMIN_CHAT_ID}")

    # Загружаем активные рассылки из БД

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
