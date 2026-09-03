"""
Локализация V3.0 — Двуязычная система (UA/RU)
t(key, lang) — универсальный доступ к текстам
"""


# ═══════════════════════════════════════════════════
#  ХЕЛПЕР: получение текста по ключу и языку
# ═══════════════════════════════════════════════════

def t(key: str, lang: str = "ua") -> str:
    """Получить текст: t('welcome', 'ua') или t('welcome', 'ru')"""
    entry = TEXTS.get(key)
    if not entry:
        return f"[{key}]"
    return entry.get(lang, entry.get("ua", f"[{key}]"))


# ═══════════════════════════════════════════════════
#  ВСЕ ТЕКСТЫ: UA + RU
# ═══════════════════════════════════════════════════

TEXTS = {

    # ── Выбор языка ──
    "choose_lang": {
        "ua": "🌐 Оберіть мову / Выберите язык:",
        "ru": "🌐 Оберіть мову / Выберите язык:",
    },

    # ── Приветствие ──
    "welcome": {
        "ua": """🛡️ <b>Вітаємо у конфіденційному сервісі</b>

Ми — надійна опора вашої <b>безпеки та анонімності</b>.
Даний сервіс повністю <b>конфіденційний</b>.

{source_line}

🔒 Жодні ваші дані не зберігаються після обробки заявки.
🔒 Всі діалоги видаляються автоматично.
🔒 Ми працюємо виключно через захищені канали.

Оберіть послугу, яка вас цікавить, за допомогою кнопок нижче 👇""",
        "ru": """🛡️ <b>Добро пожаловать в конфиденциальный сервис</b>

Мы — надёжная опора вашей <b>безопасности и анонимности</b>.
Данный сервис полностью <b>конфиденциален</b>.

{source_line}

🔒 Никакие ваши данные не сохраняются после обработки заявки.
🔒 Все диалоги удаляются автоматически.
🔒 Мы работаем исключительно через защищённые каналы.

Выберите интересующую услугу с помощью кнопок ниже 👇""",
    },

    "source_direct": {
        "ua": "🔗 <b>Джерело:</b> Прямий перехід",
        "ru": "🔗 <b>Источник:</b> Прямой переход",
    },
    "source_channel": {
        "ua": "🔗 <b>Джерело:</b> Канал <b>{source}</b>",
        "ru": "🔗 <b>Источник:</b> Канал <b>{source}</b>",
    },

    # ── Услуги ──
    "service_header": {
        "ua": "<b>{emoji} {title}</b>\n<i>{short_desc}</i>\n\n",
        "ru": "<b>{emoji} {title}</b>\n<i>{short_desc}</i>\n\n",
    },
    "terms_footer": {
        "ua": "\n\nНатисніть <b>✅ Погоджуюсь</b>, щоб продовжити.",
        "ru": "\n\nНажмите <b>✅ Согласен</b>, чтобы продолжить.",
    },

    # ── Анкета ──
    "questionnaire_start": {
        "ua": """✅ <b>Дякуємо, що прийняли умови.</b>

Для оформлення заявки потрібно заповнити коротку анкету.
<i>Команда /cancel для скасування</i>""",
        "ru": """✅ <b>Спасибо, что приняли условия.</b>

Для оформления заявки нужно заполнить короткую анкету.
<i>Команда /cancel для отмены</i>""",
    },
    "ask_name": {
        "ua": "<b>Крок 1/3 — Звертання</b>\n\nЯк до вас можна звертатися?",
        "ru": "<b>Шаг 1/3 — Обращение</b>\n\nКак к вам можно обращаться?",
    },
    "ask_age": {
        "ua": "<b>Крок 2/3 — Вік</b>\n\nВкажіть ваш вік (числом 16-99)",
        "ru": "<b>Шаг 2/3 — Возраст</b>\n\nУкажите ваш возраст (числом 16-99)",
    },
    "ask_recipient": {
        "ua": "<b>Крок 3/3 — Кому потрібна послуга</b>\n\nПослуга потрібна вам чи іншій людині?\nНапишіть: <b>Мені</b> / <b>Рідному</b> / <b>Другу</b>",
        "ru": "<b>Шаг 3/3 — Кому требуется услуга</b>\n\nУслуга требуется вам или другому человеку?\nНапишите: <b>Мне</b> / <b>Родному</b> / <b>Другу</b>",
    },
    "invalid_recipient": {
        "ua": "⚠️ Напишіть одним словом: <b>Мені</b>, <b>Рідному</b> або <b>Другу</b>\n<i>Можна просто натиснути кнопку нижче 👇</i>",
        "ru": "⚠️ Напишите одним словом: <b>Мне</b>, <b>Родному</b> или <b>Другу</b>\n<i>Можно просто нажать кнопку ниже 👇</i>",
    },
    "invalid_age": {
        "ua": "⚠️ Вік має бути числом від 16 до 99",
        "ru": "⚠️ Возраст должен быть числом от 16 до 99",
    },
    "invalid_name": {
        "ua": "⚠️ Вкажіть, будь ласка, ім'я — мінімум 2 символи",
        "ru": "⚠️ Укажите, пожалуйста, имя — минимум 2 символа",
    },
    "final_message": {
        "ua": """<b>✅ Дякуємо! Заявку прийнято.</b>

Вона буде розглянута найближчим часом, з вами зв'яжеться адміністрація прямо тут, у цьому чаті.

🔒 <i>Залишайтеся на зв'язку.</i>""",
        "ru": """<b>✅ Спасибо! Заявка принята.</b>

Она будет рассмотрена в ближайшее время, администрация свяжется с вами прямо здесь, в этом чате.

🔒 <i>Оставайтесь на связи.</i>""",
    },
    "cancel_message": {
        "ua": "❌ Анкету скасовано. Оберіть послугу знову.",
        "ru": "❌ Анкета отменена. Выберите услугу снова.",
    },

    # ── Услуга выключена админом ──
    "service_inactive": {
        "ua": "⚠️ Ця послуга зараз недоступна.\n\nОберіть, будь ласка, іншу з меню нижче 👇",
        "ru": "⚠️ Эта услуга сейчас недоступна.\n\nПожалуйста, выберите другую из меню ниже 👇",
    },

    # ── Антифлуд ──
    "flood_warning": {
        "ua": "⚠️ Надто багато повідомлень поспіль.\n"
              "Зачекайте, будь ласка, кілька секунд — і напишіть ще раз, "
              "щоб адміністрація точно отримала ваше повідомлення.",
        "ru": "⚠️ Слишком много сообщений подряд.\n"
              "Подождите, пожалуйста, несколько секунд — и напишите ещё раз, "
              "чтобы администрация точно получила ваше сообщение.",
    },

    # ── Заявка не ушла в админ-чат (бот не смог отправить) ──
    "ticket_send_error": {
        "ua": "⚠️ Сталася технічна помилка — заявка не дійшла до адміністрації.\n"
              "Будь ласка, спробуйте ще раз за хвилину.",
        "ru": "⚠️ Произошла техническая ошибка — заявка не дошла до администрации.\n"
              "Пожалуйста, попробуйте ещё раз через минуту.",
    },

    # ── Условия услуги содержат битый HTML ──
    "service_terms_broken": {
        "ua": "⚠️ Не вдалося показати умови послуги коректно. Напишіть нам — надішлемо вручну.",
        "ru": "⚠️ Не удалось корректно показать условия услуги. Напишите нам — отправим вручную.",
    },

    # ── Кнопки ──
    "btn_agree": {
        "ua": "✅ Погоджуюсь",
        "ru": "✅ Согласен",
    },
    "btn_cancel": {
        "ua": "❌ Скасувати",
        "ru": "❌ Отменить",
    },

    # ── Кому требуется услуга (шаг 3/3) ──
    "btn_for_me": {
        "ua": "👤 Мені",
        "ru": "👤 Мне",
    },
    "btn_for_relative": {
        "ua": "👨‍👩‍👦 Рідному",
        "ru": "👨‍👩‍👦 Родному",
    },
    "btn_for_friend": {
        "ua": "🤝 Другу",
        "ru": "🤝 Другу",
    },
    "btn_pay_cryptobot": {
        "ua": "💳 Оплатити через CryptoBot",
        "ru": "💳 Оплатить через CryptoBot",
    },
    "btn_check_payment": {
        "ua": "🔄 Перевірити оплату",
        "ru": "🔄 Проверить оплату",
    },

    # ── Ответ админа юзеру ──
    "admin_media_reply": {
        "ua": "📷 Медіа від адміністрації",
        "ru": "📷 Медиа от администрации",
    },
    "admin_reply_to_user": {
        "ua": """💬 <b>Відповідь від адміністрації:</b>

{admin_text}

<i>💡 Ви можете відповісти адміністрації — просто натисніть "Відповісти" (Reply) на це повідомлення.</i>""",
        "ru": """💬 <b>Ответ от администрации:</b>

{admin_text}

<i>💡 Вы можете ответить администрации — просто нажмите "Ответить" (Reply) на это сообщение.</i>""",
    },

    # ── Оплата (юзеру) ──
    "invoice_created_user": {
        "ua": """✅ <b>Вашу заявку підтверджено!</b>

💎 Послуга: <b>{service_title}</b>
💰 Договірна ціна: <b>{amount} {asset}</b>

Це <b>безстроковий рахунок</b> (без обмеження за часом) — ви можете оплатити коли зручно.

👇 Натисніть кнопку нижче для оплати через @CryptoBot:

<i>Після оплати натисніть "Перевірити оплату"</i>""",
        "ru": """✅ <b>Ваша заявка подтверждена!</b>

💎 Услуга: <b>{service_title}</b>
💰 Договорная цена: <b>{amount} {asset}</b>

Это <b>бессрочный счёт</b> (без ограничения по времени) — вы можете оплатить когда удобно.

👇 Нажмите кнопку ниже для оплаты через @CryptoBot:

<i>После оплаты нажмите "Проверить оплату"</i>""",
    },
    "invoice_paid_user": {
        "ua": """🎉 <b>Оплату підтверджено!</b>

Дякуємо, платіж на {amount} {asset} отримано.
Адміністрація зв'яжеться з вами найближчим часом для надання послуги.

🔒 <i>Зберігайте чек в @CryptoBot</i>""",
        "ru": """🎉 <b>Оплата подтверждена!</b>

Спасибо, платёж на {amount} {asset} получен.
Администрация свяжется с вами в ближайшее время для предоставления услуги.

🔒 <i>Сохраняйте чек в @CryptoBot</i>""",
    },
    "invoice_not_paid": {
        "ua": "⏳ Оплата ще не надійшла. Спробуйте через хвилину.",
        "ru": "⏳ Оплата ещё не поступила. Попробуйте через минуту.",
    },
    "invoice_paid_check": {
        "ua": "✅ Оплачено!",
        "ru": "✅ Оплачено!",
    },
    "invoice_not_found": {
        "ua": "Рахунок не знайдено",
        "ru": "Счёт не найден",
    },

    # ── Отклонение (юзеру) ──
    "declined_user": {
        "ua": """❌ <b>Вашу заявку відхилено.</b>

Причина від адміністрації:
<i>{reason}</i>

Ви можете обрати іншу послугу або звернутися пізніше.""",
        "ru": """❌ <b>Ваша заявка отклонена.</b>

Причина от администрации:
<i>{reason}</i>

Вы можете выбрать другую услугу или обратиться позже.""",
    },

    # ── Бан (юзеру) ──
    "banned_user": {
        "ua": "⛔ <b>Ви були заблоковані адміністрацією.</b>\n\nДоступ до сервісу обмежено.",
        "ru": "⛔ <b>Вы были заблокированы администрацией.</b>\n\nДоступ к сервису ограничен.",
    },
    "unbanned_user": {
        "ua": "✅ <b>Вас розблоковано!</b>\n\nВи знову можете користуватися сервісом.",
        "ru": "✅ <b>Вы разблокированы!</b>\n\nВы снова можете пользоваться сервисом.",
    },

    # ── Смена языка ──
    "lang_changed": {
        "ua": "🇺🇦 Мову змінено на українську.",
        "ru": "🇷🇺 Язык изменён на русский.",
    },
}


# ═══════════════════════════════════════════════════
#  ADMIN TEXTS (всегда русский, без локализации)
# ═══════════════════════════════════════════════════

ADMIN_TEMPLATE_RU = """
🔔 <b>НОВАЯ ЗАЯВКА — {date}</b>
━━━━━━━━━━━━━━━
👤 <b>Обращение:</b> {name}
🎂 <b>Возраст:</b> {age}
👥 <b>Кому требуется:</b> {recipient}
💎 <b>Услуга:</b> {service_title} (<code>{service_id}</code>)
🔗 <b>Источник:</b> {source}
🌐 <b>Язык:</b> {lang}
━━━━━━━━━━━━━━━
🆔 <b>Юзер:</b> {user_mention} | <code>{user_id}</code>
💬 <b>Username:</b> {username}

<i>↩️ Чтобы ответить — сделай REPLY на это сообщение.</i>
<i>✅ Чтобы выставить договорной счет — нажми "Подтвердить" ниже.</i>
"""

USER_CONTINUATION_TEMPLATE_RU = """
💬 <b>Продолжение диалога — {name}</b>
🆔 <code>{user_id}</code> | {username}
💎 Услуга: {service_title}

📨 Сообщение:
<i>{text}</i>

<i>↩️ Отвечай REPLY на это сообщение.</i>
"""

# Короткая подпись к медиа от пользователя: подпись Telegram ограничена 1024
# символами, поэтому длинный текст досылается отдельным сообщением (см. user_chat).
USER_MEDIA_CAPTION_RU = """📷 <b>Медиа от клиента — {name}</b>
🆔 <code>{user_id}</code> | {username}
💎 Услуга: {service_title}

<i>↩️ Отвечай REPLY на это сообщение.</i>"""

# Аналогично для ответа админа пользователю (фото/документ с длинной подписью):
# текст берётся из TEXTS["admin_media_reply"] по языку пользователя.

ADMIN_PANEL_TEXT_RU = "🛡️ <b>Админ-панель</b>\n\nВыбери раздел:"

ADMIN_STATS_TEXT_RU = """
📊 <b>Статистика</b>
━━━━━━━━━━━━━━
👥 Всего пользователей: <b>{total}</b>
🆕 Сегодня: <b>{today}</b>
💬 Открытых диалогов: <b>{open_t}</b>
💰 Оплаченных заявок: <b>{paid_t}</b>
🏆 Топ-услуга: <b>{top_text}</b>
━━━━━━━━━━━━━━
Отправь /users чтобы увидеть список последних 20 пользователей
"""

ADMIN_NO_USERS_RU = "Пользователей пока нет"
ADMIN_USERS_HEADER_RU = "👤 <b>Последние 20 пользователей</b>\n\n"

ADMIN_NEW_ADMIN_RU = "👮 Новый админ: {name} (<code>{uid}</code>) — права выданы автоматически."
ADMIN_REMOVE_ADMIN_RU = "🚪 Админ {name} удален из чата, права сняты."
ADMIN_ADMINS_LIST_HEADER_RU = "👥 <b>Администраторы</b> (динамически из админ-чата):\n\n"
ADMIN_ADMINS_EMPTY_RU = "Пока никого. Добавь людей в админ-чат."

ADMIN_SERVICE_LIST_HEADER_RU = "🛠 <b>Управление услугами</b>\nВсего: {count}"
ADMIN_SERVICE_VIEW_RU = "{emoji} <b>{title}</b>\n\nID: <code>{id}</code>\nКнопка: {button_label}\nОписание: {short_desc}\n\nУсловия:\n{terms}\n\nСтатус: {status}"
ADMIN_SERVICE_ACTIVE_RU = "🟢 Активна"
ADMIN_SERVICE_INACTIVE_RU = "🔴 Выключена"

ADMIN_DELETE_CONFIRM_RU = "❓ Удалить услугу <code>{sid}</code>?\nЭто безвозвратно."
ADMIN_DELETED_RU = "🗑 Услуга удалена.\nВсего: {count}"

ADMIN_SEND_ERROR_NO_TEXT_RU = "⚠️ Отправь текст, фото или документ."
ADMIN_SENT_OK_RU = "✅ Отправлено пользователю <code>{uid}</code>"
ADMIN_SEND_FAIL_RU = "❌ Не удалось отправить пользователю. Возможно, он заблокировал бота.\n{e}"

# ── Мастер добавления услуги (10 шагов: UA + RU) ──
ADMIN_SERVICE_ADD_START_RU = (
    "🆕 <b>Добавление услуги — шаг 1/10</b>\n\n"
    "Введи <b>ID услуги</b> латиницей без пробелов:\n"
    "<i>Например: confidential_docs</i>"
)
ADMIN_SERVICE_ADD_EMOJI_RU = "2/10 — Введи <b>эмодзи</b> для услуги:"
ADMIN_SERVICE_ADD_TITLE_UA_RU = "3/10 — Название услуги <b>🇺🇦 UA</b>:"
ADMIN_SERVICE_ADD_TITLE_RU_RU = (
    "4/10 — Название услуги <b>🇷🇺 RU</b>:\n"
    "<i>или отправь <code>=</code> чтобы скопировать украинский вариант</i>"
)
ADMIN_SERVICE_ADD_SHORT_UA_RU = "5/10 — Краткое описание <b>🇺🇦 UA</b> (1 строка):"
ADMIN_SERVICE_ADD_SHORT_RU_RU = (
    "6/10 — Краткое описание <b>🇷🇺 RU</b> (1 строка):\n"
    "<i>или <code>=</code> чтобы скопировать UA</i>"
)
ADMIN_SERVICE_ADD_TERMS_UA_RU = "7/10 — <b>Условия покупки 🇺🇦 UA</b> (HTML):"
ADMIN_SERVICE_ADD_TERMS_RU_RU = (
    "8/10 — <b>Условия покупки 🇷🇺 RU</b> (HTML):\n"
    "<i>или <code>=</code> чтобы скопировать UA</i>"
)
ADMIN_SERVICE_ADD_BUTTON_UA_RU = "9/10 — Текст кнопки <b>🇺🇦 UA</b>:\n<i>Например: {example}</i>"
ADMIN_SERVICE_ADD_BUTTON_RU_RU = (
    "10/10 — Текст кнопки <b>🇷🇺 RU</b>:\n"
    "<i>Например: {example_ru} · или <code>=</code> чтобы скопировать UA</i>"
)
ADMIN_SERVICE_ADD_ID_SHORT_RU = "❌ ID слишком короткий (минимум 3 символа)"
ADMIN_SERVICE_ADD_ID_INVALID_RU = (
    "❌ В ID допустимы только латинские буквы, цифры и «_» (3–32 символа).\n"
    "Пробелы, точки и двоеточия сломают кнопки админ-панели.\n"
    "<i>Например: confidential_docs</i>"
)
ADMIN_SERVICE_ADD_ID_EXISTS_RU = "❌ Такой ID уже существует"
ADMIN_SERVICE_ADD_BUTTON_EXISTS_RU = "❌ Такая кнопка уже используется другой услугой. Придумай другой текст."
ADMIN_SERVICE_ADD_BUTTON_LONG_RU = (
    "❌ Текст кнопки длиннее 64 символов — Telegram такую кнопку не примет. Сократи."
)
ADMIN_SERVICE_ADD_EMPTY_RU = "❌ Текст не может быть пустым. Попробуй ещё раз."
ADMIN_SERVICE_CREATED_RU = (
    "✅ Услуга <b>{title}</b> создана на двух языках!\n\n"
    "🇺🇦 {title_ua} — кнопка «{button_ua}»\n"
    "🇷🇺 {title_ru} — кнопка «{button_ru}»"
)
ADMIN_SERVICE_UPDATED_RU = "✅ Поле <b>{field}</b> ({lang}) обновлено для «{title}»"
ADMIN_SERVICE_COPIED_RU = "✅ Перевод скопирован: {source} → {target} для услуги «{title}»"

# ── Точечная правка услуги ──
ADMIN_SERVICE_EDIT_CHOOSE_LANG_RU = "✏️ <b>Редактирование:</b> {title}\n\nВыбери язык, который правим:"
ADMIN_SERVICE_EDIT_CHOOSE_FIELD_RU = "✏️ <b>{title}</b> · язык <b>{lang}</b>\n\nЧто меняем?"
ADMIN_SERVICE_EDIT_ASK_RU = (
    "✏️ Введи новое значение для поля <b>{field}</b> ({lang}):\n\n"
    "Сейчас:\n<code>{current}</code>\n\n"
    "<i>Или /cancel для отмены</i>"
)
ADMIN_SERVICE_EDIT_STATE_LOST_RU = "❌ Данные правки потеряны. Открой карточку услуги заново через /admin."

ADMIN_SERVICE_VIEW_RU_BILINGUAL = """{emoji} <b>{title_ua}</b> / <b>{title_ru}</b>

ID: <code>{id}</code>
Кнопка UA: {button_ua}
Кнопка RU: {button_ru}
Описание UA: {short_ua}
Описание RU: {short_ru}

Условия UA:
{terms_ua}

Условия RU:
{terms_ru}

Статус: {status}"""

ADMIN_REQ_NO_RIGHTS_RU = "⛔ Нет прав администратора"

ADMIN_CONFIRM_BTN_RU = "✅ Подтвердить заявку"
ADMIN_DECLINE_BTN_RU = "❌ Отклонить"

ADMIN_ASK_PRICE_RU = """
✅ Подтверждение заявки для <code>{user_id}</code>

Теперь введите <b>договорную цену</b> в формате:
<code>100 USDT</code> или <code>0.05 BTC</code> или <code>50 TON</code>
"""

ADMIN_PRICE_INVALID_RU = "⚠️ Неверный формат. Пример: <code>100 USDT</code>"

ADMIN_INVOICE_CREATING_RU = "⏳ Создаю бесконечный счет в CryptoBot на {amount} {asset}..."

ADMIN_INVOICE_CREATED_RU = """
✅ <b>Бесконечный счет создан!</b>

👤 Пользователь: {user_display}
💎 Услуга: {service_title}
💰 Сумма: <b>{amount} {asset}</b>
🔗 Ссылка: {bot_url}

Crypto Invoice ID: <code>{crypto_id}</code>
"""

ADMIN_INVOICE_ERROR_RU = "❌ Ошибка CryptoBot: {e}"
ADMIN_DECLINE_ASK_REASON_RU = "Напиши причину отклонения (отправится пользователю):"

ADMIN_INVOICE_PAID_RU = """
💰 <b>СЧЁТ ОПЛАЧЕН</b>
━━━━━━━━━━━━━━━
👤 Пользователь: <code>{user_id}</code> | {username}
💎 Услуга: <b>{service_title}</b>
💰 Сумма: <b>{amount} {asset}</b>
🧾 Invoice: <code>{crypto_id}</code>
"""

ADMIN_INVOICE_MISMATCH_RU = (
    "⚠️ <b>Внимание:</b> сумма оплаты не совпадает с выставленной!\n"
    "Выставляли: <b>{expected_amount} {expected_asset}</b>\n"
    "Оплачено: <b>{paid_amount} {paid_asset}</b>"
)

ADMIN_ADMINS_SYNCED_RU = "👮 Админы синхронизированы с группой: +{added}, -{removed}, всего {total}."
ADMIN_BROADCASTS_RESTORED_RU = "📢 Восстановлено активных рассылок: {count}"

ADMIN_TEMPLATE = ADMIN_TEMPLATE_RU
USER_CONTINUATION_TEMPLATE = USER_CONTINUATION_TEMPLATE_RU
ADMIN_PANEL_TEXT = ADMIN_PANEL_TEXT_RU


# ═══════════════════════════════════════════════════
#  СТАРЫЕ КОНСТАНТЫ (для обратной совместимости)
# ═══════════════════════════════════════════════════

WELCOME_TEXT_UA = TEXTS["welcome"]["ua"]
WELCOME_TEXT_RU_TEXT = TEXTS["welcome"]["ru"]
QUESTIONNAIRE_START_UA = TEXTS["questionnaire_start"]["ua"]
ASK_NAME_UA = TEXTS["ask_name"]["ua"]
ASK_AGE_UA = TEXTS["ask_age"]["ua"]
ASK_RECIPIENT_UA = TEXTS["ask_recipient"]["ua"]
INVALID_AGE_UA = TEXTS["invalid_age"]["ua"]
FINAL_USER_MESSAGE_UA = TEXTS["final_message"]["ua"]
CANCEL_MESSAGE_UA = TEXTS["cancel_message"]["ua"]
BTN_AGREE_UA = TEXTS["btn_agree"]["ua"]
BTN_CANCEL_UA = TEXTS["btn_cancel"]["ua"]
ADMIN_REPLY_TO_USER_UA = TEXTS["admin_reply_to_user"]["ua"]
INVOICE_CREATED_USER_UA = TEXTS["invoice_created_user"]["ua"]
INVOICE_PAID_USER_UA = TEXTS["invoice_paid_user"]["ua"]
INVOICE_NOT_PAID_UA = TEXTS["invoice_not_paid"]["ua"]
ADMIN_DECLINED_USER_UA = TEXTS["declined_user"]["ua"]

WELCOME_TEXT = WELCOME_TEXT_UA
QUESTIONNAIRE_START = QUESTIONNAIRE_START_UA
ASK_NAME = ASK_NAME_UA
ASK_AGE = ASK_AGE_UA
ASK_RECIPIENT = ASK_RECIPIENT_UA
INVALID_AGE = INVALID_AGE_UA
FINAL_USER_MESSAGE = FINAL_USER_MESSAGE_UA
CANCEL_MESSAGE = CANCEL_MESSAGE_UA
BTN_AGREE = BTN_AGREE_UA
BTN_CANCEL = BTN_CANCEL_UA
ADMIN_REPLY_TO_USER = ADMIN_REPLY_TO_USER_UA

SERVICE_CHOSEN_HEADER_UA = TEXTS["service_header"]["ua"]
TERMS_FOOTER_UA = TEXTS["terms_footer"]["ua"]
SERVICE_CHOSEN_HEADER = SERVICE_CHOSEN_HEADER_UA
TERMS_FOOTER = TERMS_FOOTER_UA

SOURCE_LINE_DIRECT_UA = TEXTS["source_direct"]["ua"]
SOURCE_LINE_CHANNEL_UA = TEXTS["source_channel"]["ua"]
SOURCE_LINE_DIRECT = SOURCE_LINE_DIRECT_UA
SOURCE_LINE_CHANNEL = SOURCE_LINE_CHANNEL_UA
