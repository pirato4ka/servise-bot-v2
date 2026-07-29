from aiogram import Router, F
from aiogram.types import Message, ChatMemberUpdated
from aiogram.filters import ChatMemberUpdatedFilter, IS_NOT_MEMBER, IS_MEMBER

from app.config import settings
from app.database import crud
from app.data.texts import ADMIN_NEW_ADMIN_RU, ADMIN_REMOVE_ADMIN_RU

router = Router()

@router.message(F.chat.id == settings.ADMIN_CHAT_ID, F.new_chat_members)
async def new_members_in_admin_chat(message: Message):
    for user in message.new_chat_members:
        if user.is_bot:
            continue
        await crud.add_admin(user.id, added_by=message.from_user.id)
        await message.answer(ADMIN_NEW_ADMIN_RU.format(name=user.full_name, uid=user.id))

@router.message(F.chat.id == settings.ADMIN_CHAT_ID, F.left_chat_member)
async def left_member(message: Message):
    user = message.left_chat_member
    if user:
        await crud.remove_admin(user.id)
        await message.answer(ADMIN_REMOVE_ADMIN_RU.format(name=user.full_name))

@router.chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER), F.chat.id == settings.ADMIN_CHAT_ID)
async def member_joined(event: ChatMemberUpdated):
    if event.new_chat_member.user.is_bot:
        return
    await crud.add_admin(event.new_chat_member.user.id, added_by=event.from_user.id if event.from_user else None)

@router.chat_member(ChatMemberUpdatedFilter(IS_MEMBER >> IS_NOT_MEMBER), F.chat.id == settings.ADMIN_CHAT_ID)
async def member_left(event: ChatMemberUpdated):
    await crud.remove_admin(event.old_chat_member.user.id)

# Авто-регистрация — только для обычных сообщений, НЕ для реплаев на тикеты
@router.message(F.chat.id == settings.ADMIN_CHAT_ID, ~F.reply_to_message)
async def auto_register_admin_on_message(message: Message):
    if not message.from_user.is_bot:
        if not await crud.is_admin(message.from_user.id):
            await crud.add_admin(message.from_user.id)
