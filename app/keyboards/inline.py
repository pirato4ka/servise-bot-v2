from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_lang_keyboard():
    """Клавиатура выбора языка"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇺🇦 Українська", callback_data="lang:ua"),
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
        ]
    ])


def get_agree_keyboard(service_id: str):
    from app.data.texts import TEXTS
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=TEXTS["btn_agree"]["ua"], callback_data=f"agree:{service_id}")]
    ])


def get_agree_keyboard_localized(service_id: str, lang: str = "ua"):
    from app.data.texts import t
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_agree", lang), callback_data=f"agree:{service_id}")]
    ])


def admin_panel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats"), InlineKeyboardButton(text="🛠 Услуги", callback_data="admin:services")],
        [InlineKeyboardButton(text="👥 Админы", callback_data="admin:admins"), InlineKeyboardButton(text="📢 Рассылка", callback_data="admin:broadcast")],
    ])


def services_list_kb(services):
    kb = []
    for s in services:
        title_ru = s.get("title_ru") or s.get("title") or s.get("title_ua") or s["id"]
        title_ua = s.get("title_ua") or title_ru
        label = f"{'🟢' if s['is_active'] else '🔴'} {title_ua} / {title_ru}" if title_ua != title_ru \
            else f"{'🟢' if s['is_active'] else '🔴'} {title_ru}"
        kb.append([InlineKeyboardButton(text=label, callback_data=f"svc:view:{s['id']}")])
    kb.append([InlineKeyboardButton(text="➕ Добавить услугу", callback_data="svc:add")])
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:panel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def service_action_kb(service_id: str, is_active: int):
    """Карточка услуги: правка по языкам + копирование UA -> RU."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"svc:edit:{service_id}")],
        [InlineKeyboardButton(text="🇺🇦→🇷🇺 Скопировать UA в RU", callback_data=f"svc:copyua:{service_id}")],
        [InlineKeyboardButton(text="❌ Удалить" if is_active else "🗑 Удалить", callback_data=f"svc:delete:{service_id}")],
        [InlineKeyboardButton(text="🔴 Выключить" if is_active else "🟢 Включить", callback_data=f"svc:toggle:{service_id}")],
        [InlineKeyboardButton(text="⬅️ К списку", callback_data="admin:services")]
    ])


def service_edit_lang_kb(service_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇦 Українська", callback_data=f"svc:editlang:{service_id}:ua"),
         InlineKeyboardButton(text="🇷🇺 Русский", callback_data=f"svc:editlang:{service_id}:ru")],
        [InlineKeyboardButton(text="🎨 Эмодзи", callback_data=f"svc:editfield:{service_id}:ua:emoji")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"svc:view:{service_id}")]
    ])


SERVICE_FIELD_BUTTONS = (
    ("title", "📝 Название"),
    ("short_desc", "💬 Краткое описание"),
    ("terms", "📄 Условия"),
    ("button_label", "🔘 Текст кнопки"),
)


def service_edit_field_kb(service_id: str, lang: str):
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"svc:editfield:{service_id}:{lang}:{field}")]
        for field, label in SERVICE_FIELD_BUTTONS
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"svc:edit:{service_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_ticket_kb(admin_message_id: int):
    from app.data.texts import ADMIN_CONFIRM_BTN_RU, ADMIN_DECLINE_BTN_RU
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=ADMIN_CONFIRM_BTN_RU, callback_data=f"ticket:confirm:{admin_message_id}"),
            InlineKeyboardButton(text=ADMIN_DECLINE_BTN_RU, callback_data=f"ticket:decline:{admin_message_id}")
        ]
    ])


def user_invoice_kb(bot_invoice_url: str, crypto_invoice_id: int, lang: str = "ua"):
    from app.data.texts import t
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("btn_pay_cryptobot", lang), url=bot_invoice_url)],
        [InlineKeyboardButton(text=t("btn_check_payment", lang), callback_data=f"checkpay:{crypto_invoice_id}")]
    ])


def admin_check_invoice_kb(crypto_invoice_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"admin_check:{crypto_invoice_id}")]
    ])
