from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import settings
from app.database import crud
from app.data.texts import (
    ADMIN_ADMINS_EMPTY_RU,
    ADMIN_ADMINS_LIST_HEADER_RU,
    ADMIN_DELETE_CONFIRM_RU,
    ADMIN_DELETED_RU,
    ADMIN_PANEL_TEXT_RU,
    ADMIN_REQ_NO_RIGHTS_RU,
    ADMIN_SERVICE_ACTIVE_RU,
    ADMIN_SERVICE_COPIED_RU,
    ADMIN_SERVICE_INACTIVE_RU,
    ADMIN_SERVICE_LIST_HEADER_RU,
    ADMIN_SERVICE_VIEW_RU_BILINGUAL,
)
from app.keyboards.inline import admin_panel_kb, service_action_kb, services_list_kb
from app.utils.callbacks import cb_args
from app.utils.telegram import answer_callback, edit_or_send
from app.utils.text import esc, strip_tags


def services_list_text(services) -> str:
    return ADMIN_SERVICE_LIST_HEADER_RU.format(count=len(services))


def service_view_text(svc) -> str:
    """
    Карточка услуги: оба языка сразу, чтобы переводы были перед глазами.

    Значения экранируются: условия услуги админ набирает HTML-ем, и одна
    незакрытая скобка раньше роняла edit_text, из-за чего карточка либо не
    открывалась, либо показывалась с буквально видимыми тегами шаблона.
    """
    status = ADMIN_SERVICE_ACTIVE_RU if svc["is_active"] else ADMIN_SERVICE_INACTIVE_RU
    return ADMIN_SERVICE_VIEW_RU_BILINGUAL.format(
        emoji=esc(svc["emoji"]), id=esc(svc["id"]),
        title_ua=esc(svc["title_ua"]), title_ru=esc(svc["title_ru"]),
        button_ua=esc(svc["button_label_ua"]), button_ru=esc(svc["button_label_ru"]),
        short_ua=esc(svc["short_desc_ua"]) or "-", short_ru=esc(svc["short_desc_ru"]) or "-",
        terms_ua=esc(svc["terms_ua"]), terms_ru=esc(svc["terms_ru"]),
        status=status,
    )


router = Router()


async def check_admin(user_id: int) -> bool:
    return await crud.is_admin(user_id)


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not message.from_user:  # пост из канала
        return
    if message.chat.id != settings.ADMIN_CHAT_ID and not await check_admin(message.from_user.id):
        await message.answer(ADMIN_REQ_NO_RIGHTS_RU)
        return
    await message.answer(ADMIN_PANEL_TEXT_RU, reply_markup=admin_panel_kb())


@router.callback_query(F.data == "admin:panel")
async def cb_panel(cb: CallbackQuery):
    await edit_or_send(cb, ADMIN_PANEL_TEXT_RU, reply_markup=admin_panel_kb())
    await answer_callback(cb)


# ═══════════════════════════════════════
#  Услуги
# ═══════════════════════════════════════

@router.callback_query(F.data == "admin:services")
async def cb_services(cb: CallbackQuery):
    services = await crud.get_services(active_only=False)
    await edit_or_send(cb, services_list_text(services), reply_markup=services_list_kb(services))
    await answer_callback(cb)


@router.callback_query(F.data.startswith("svc:view:"))
async def view_service(cb: CallbackQuery):
    (sid,) = cb_args(cb.data, "svc:view:")
    svc = await crud.get_service_by_id(sid)
    if not svc:
        await answer_callback(cb, "Не найдено", show_alert=True)
        return
    await edit_or_send(
        cb, service_view_text(svc), reply_markup=service_action_kb(svc["id"], svc["is_active"])
    )
    await answer_callback(cb)


@router.callback_query(F.data.startswith("svc:toggle:"))
async def toggle_service(cb: CallbackQuery):
    (sid,) = cb_args(cb.data, "svc:toggle:")
    await crud.toggle_service(sid)
    svc = await crud.get_service_by_id(sid)
    if not svc:
        await answer_callback(cb, "Не найдено", show_alert=True)
        return
    await edit_or_send(
        cb,
        f"Статус изменен. Теперь: {'🟢' if svc['is_active'] else '🔴'}",
        reply_markup=service_action_kb(svc["id"], svc["is_active"]),
    )
    await answer_callback(cb, "Статус изменен")


@router.callback_query(F.data.startswith("svc:delete:"))
async def delete_service(cb: CallbackQuery):
    (sid,) = cb_args(cb.data, "svc:delete:")
    await edit_or_send(
        cb,
        ADMIN_DELETE_CONFIRM_RU.format(sid=esc(sid)),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"svc:confirm_delete:{sid}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin:services")]
        ]),
    )
    await answer_callback(cb)


@router.callback_query(F.data.startswith("svc:confirm_delete:"))
async def confirm_delete(cb: CallbackQuery):
    (sid,) = cb_args(cb.data, "svc:confirm_delete:")
    await crud.delete_service(sid)
    services = await crud.get_services(active_only=False)
    await edit_or_send(
        cb, ADMIN_DELETED_RU.format(count=len(services)), reply_markup=services_list_kb(services)
    )
    await answer_callback(cb, "Удалено")


@router.callback_query(F.data.startswith("svc:copyua:"))
async def copy_ua_to_ru(cb: CallbackQuery):
    """Копирует украинские тексты в русские — чтобы не перепечатывать."""
    (sid,) = cb_args(cb.data, "svc:copyua:")
    svc = await crud.get_service_by_id(sid)
    if not svc:
        await answer_callback(cb, "Не найдено", show_alert=True)
        return
    await crud.copy_service_language(sid, source="ua")
    # Текст алерта Telegram показывает как есть, без HTML — не экранируем
    await answer_callback(cb, ADMIN_SERVICE_COPIED_RU.format(
        source="UA", target="RU", title=strip_tags(svc["title_ua"])
    ), show_alert=True)


# ═══════════════════════════════════════
#  Админы
# ═══════════════════════════════════════

@router.callback_query(F.data == "admin:admins")
async def list_admins(cb: CallbackQuery):
    admins = await crud.get_admins()
    txt = ADMIN_ADMINS_LIST_HEADER_RU
    for a in admins:
        txt += f"• <code>{a['user_id']}</code> — добавлен {esc(a['added_at'])}\n"
    if not admins:
        txt += ADMIN_ADMINS_EMPTY_RU
    await edit_or_send(cb, txt, reply_markup=admin_panel_kb())
    await answer_callback(cb)


# ═══════════════════════════════════════
#  Статистика
# ═══════════════════════════════════════

@router.callback_query(F.data == "admin:stats")
async def stats_cb(cb: CallbackQuery):
    from app.handlers.admin.stats import get_stats_text
    text = await get_stats_text()
    await edit_or_send(cb, text, reply_markup=admin_panel_kb())
    await answer_callback(cb)
