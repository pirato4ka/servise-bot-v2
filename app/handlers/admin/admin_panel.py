from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from app.config import settings
from app.database import crud
from app.keyboards.inline import admin_panel_kb, services_list_kb, service_action_kb
from app.data.texts import (
    ADMIN_PANEL_TEXT_RU, ADMIN_SERVICE_LIST_HEADER_RU,
    ADMIN_SERVICE_VIEW_RU, ADMIN_SERVICE_ACTIVE_RU, ADMIN_SERVICE_INACTIVE_RU,
    ADMIN_DELETE_CONFIRM_RU, ADMIN_DELETED_RU,
    ADMIN_ADMINS_LIST_HEADER_RU, ADMIN_ADMINS_EMPTY_RU,
    ADMIN_REQ_NO_RIGHTS_RU
)

router = Router()


async def check_admin(user_id: int) -> bool:
    return await crud.is_admin(user_id)


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.chat.id != settings.ADMIN_CHAT_ID:
        if not await check_admin(message.from_user.id):
            await message.answer(ADMIN_REQ_NO_RIGHTS_RU)
            return
    await message.answer(ADMIN_PANEL_TEXT_RU, reply_markup=admin_panel_kb())


@router.callback_query(F.data == "admin:panel")
async def cb_panel(cb: CallbackQuery):
    await cb.message.edit_text(ADMIN_PANEL_TEXT_RU, reply_markup=admin_panel_kb())
    await cb.answer()


# ═══════════════════════════════════════
#  Услуги
# ═══════════════════════════════════════

@router.callback_query(F.data == "admin:services")
async def cb_services(cb: CallbackQuery):
    services = await crud.get_services(active_only=False)
    await cb.message.edit_text(
        ADMIN_SERVICE_LIST_HEADER_RU.format(count=len(services)),
        reply_markup=services_list_kb(services),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("svc:view:"))
async def view_service(cb: CallbackQuery):
    sid = cb.data.split(":")[2]
    svc = await crud.get_service_by_id(sid)
    if not svc:
        await cb.answer("Не найдено", show_alert=True)
        return
    status = ADMIN_SERVICE_ACTIVE_RU if svc['is_active'] else ADMIN_SERVICE_INACTIVE_RU
    text = ADMIN_SERVICE_VIEW_RU.format(
        emoji=svc['emoji'], title=svc['title'], id=svc['id'],
        button_label=svc['button_label'], short_desc=svc['short_desc'] or "-",
        terms=svc['terms'], status=status
    )
    try:
        await cb.message.edit_text(text, reply_markup=service_action_kb(svc["id"], svc["is_active"]))
    except Exception:
        import html as html_lib
        await cb.message.edit_text(
            html_lib.escape(text), reply_markup=service_action_kb(svc["id"], svc["is_active"])
        )
    await cb.answer()


@router.callback_query(F.data.startswith("svc:toggle:"))
async def toggle_service(cb: CallbackQuery):
    sid = cb.data.split(":")[2]
    await crud.toggle_service(sid)
    svc = await crud.get_service_by_id(sid)
    await cb.message.edit_text(
        f"Статус изменен. Теперь: {'🟢' if svc['is_active'] else '🔴'}",
        reply_markup=service_action_kb(svc["id"], svc["is_active"]),
    )
    await cb.answer("Статус изменен")


@router.callback_query(F.data.startswith("svc:delete:"))
async def delete_service(cb: CallbackQuery):
    sid = cb.data.split(":")[2]
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    await cb.message.edit_text(ADMIN_DELETE_CONFIRM_RU.format(sid=sid), reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"svc:confirm_delete:{sid}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin:services")]
    ]))
    await cb.answer()


@router.callback_query(F.data.startswith("svc:confirm_delete:"))
async def confirm_delete(cb: CallbackQuery):
    sid = cb.data.split(":")[2]
    await crud.delete_service(sid)
    services = await crud.get_services(active_only=False)
    await cb.message.edit_text(
        ADMIN_DELETED_RU.format(count=len(services)), reply_markup=services_list_kb(services)
    )
    await cb.answer("Удалено")


# ═══════════════════════════════════════
#  Админы
# ═══════════════════════════════════════

@router.callback_query(F.data == "admin:admins")
async def list_admins(cb: CallbackQuery):
    admins = await crud.get_admins()
    txt = ADMIN_ADMINS_LIST_HEADER_RU
    for a in admins:
        txt += f"• <code>{a['user_id']}</code> — добавлен {a['added_at']}\n"
    if not admins:
        txt += ADMIN_ADMINS_EMPTY_RU
    await cb.message.edit_text(txt, reply_markup=admin_panel_kb())
    await cb.answer()


# ═══════════════════════════════════════
#  Статистика
# ═══════════════════════════════════════

@router.callback_query(F.data == "admin:stats")
async def stats_cb(cb: CallbackQuery):
    from app.handlers.admin.stats import get_stats_text
    text = await get_stats_text()
    await cb.message.edit_text(text, reply_markup=admin_panel_kb())
    await cb.answer()
