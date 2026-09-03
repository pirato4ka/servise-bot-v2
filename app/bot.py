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
from app.services.invoice_watcher import invoice_watcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)


def build_session() -> AiohttpSession:
    """Сессия с опциональным прокси (http/https/socks — socks требует aiohttp_socks)."""
    proxy_url = settings.PROXY_URL
    if proxy_url:
        logging.info(f"Использую прокси для Telegram: {proxy_url}")
        return AiohttpSession(proxy=proxy_url)
    return AiohttpSession()


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()

    # Админские — порядок важен.
    # membership ставим ПОСЛЕДНИМ: его обработчик «любое сообщение в админ-чате»
    # иначе перехватывал бы ввод мастера добавления услуг и прочие диалоги.
    dp.include_router(confirm_payment.router)
    dp.include_router(broadcast.router)
    dp.include_router(reply_handler.router)
    dp.include_router(payment_check.router)
    dp.include_router(admin_panel.router)
    dp.include_router(services_crud.router)
    dp.include_router(stats.router)
    dp.include_router(membership.router)

    # Пользовательские
    dp.include_router(start.router)
    dp.include_router(questionnaire.router)
    dp.include_router(services.router)
    dp.include_router(user_chat.router)

    # Отладочный роутер — только по запросу, иначе он перехватывает чужие колбеки
    if settings.DEBUG_ALL:
        logging.warning("DEBUG_ALL включён: все входящие апдейты логируются")
        dp.include_router(debug_all.router)

    return dp


async def main():
    await init_db()

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=build_session(),
    )
    dp = build_dispatcher()

    await bot.delete_webhook(drop_pending_updates=True)
    me = await bot.get_me()
    logging.info(
        f"Bot started @{me.username} id={me.id} "
        f"proxy={'ON' if settings.PROXY_URL else 'OFF'} ADMIN_CHAT={settings.ADMIN_CHAT_ID}"
    )

    # Кто уже есть в группе — остаётся админом после перезапуска
    try:
        added, removed = await membership.sync_chat_admins(bot)
        logging.info(f"Админы синхронизированы: +{added} / -{removed}")
    except Exception as e:
        logging.warning(f"Не удалось синхронизировать админов: {e}")

    # Восстанавливаем активные рассылки (раньше функция existed, но не вызывалась)
    try:
        restored = await broadcast.load_active_broadcasts(bot)
        if restored:
            logging.info(f"Восстановлено рассылок: {restored}")
    except Exception as e:
        logging.error(f"Ошибка восстановления рассылок: {e}")

    watcher_task = asyncio.create_task(invoice_watcher(bot))

    try:
        await dp.start_polling(bot)
    finally:
        logging.info("Остановка бота...")
        watcher_task.cancel()
        try:
            await watcher_task
        except (asyncio.CancelledError, Exception):
            pass
        await broadcast.stop_all_broadcasts()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
