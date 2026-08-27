"""Все тексты бота (RU)."""

START = (
    "👋 <b>Привет, {name}!</b>\n\n"
    "Это бот для покупки и управления <b>VPN-подпиской</b>.\n\n"
    "⚡️ Быстрое и стабильное подключение\n"
    "🌍 Серверы в нескольких странах\n"
    "📱 Работает на iPhone, Android, Windows, macOS и TV\n\n"
    "Выберите действие в меню ниже 👇"
)

MENU_BUY = "🔑 <b>Купить подписку</b>"

NO_SUBSCRIPTION = (
    "😕 <b>У вас ещё нет подписки.</b>\n\n"
    "Нажмите «🔑 Купить подписку» — доступ откроется автоматически сразу после оплаты."
)

SUB_STATUS = (
    "💳 <b>Ваша подписка</b>\n\n"
    "🆔 Логин: <code>{username}</code>\n"
    "📅 Действует до: <b>{expire}</b>\n"
    "{traffic_line}"
    "{status_line}"
)

SUB_STATUS_TRAFFIC = "📊 Трафик: <b>{used}</b>{limit_line}\n"
SUB_STATUS_LIMIT = " из {limit}"
SUB_STATUS_ACTIVE = "\n✅ Статус: активна"
SUB_STATUS_DISABLED = "\n⛔️ Статус: отключена"

SUB_EXPIRES_SOON = (
    "\n⚠️ <b>Подписка скоро закончится</b> — продлите, чтобы не терять доступ."
)

TARIFF_CARD = (
    "🔑 <b>{title}</b>\n"
    "⏳ Срок: <b>{days} дн.</b>\n"
    "{description}\n"
    "💰 Цена: <b>{price}</b>\n\n"
    "Выберите способ оплаты 👇"
)

PAY_STARS_HINT = "Нажмите кнопку ниже и подтвердите оплату звёздами ⭐"
PAY_LINK_HINT = (
    "Нажмите кнопку ниже — откроется страница оплаты.\n"
    "После оплаты вернитесь в бот и нажмите «Проверить оплату»."
)

PAYMENT_CREATED = (
    "🧾 <b>Счёт создан</b>\n\n"
    "Тариф: <b>{title}</b> ({days} дн.)\n"
    "Сумма: <b>{amount}</b>\n\n{hint}"
)

PAYMENT_CANCELED = "❌ Счёт отменён."
PAYMENT_NOT_FOUND = "Счёт не найден или уже обработан."
PAYMENT_STILL_PENDING = "⏳ Оплата пока не поступила. Если вы уже оплатили — подождите пару минут и нажмите кнопку снова."
PAYMENT_EXPIRED = "Время оплаты счёта истекло. Создайте новый счёт."

SUCCESS_STARS = "⭐ Оплата звёздами получена!"

SUCCESS_TITLE = "🎉 <b>Оплата получена!</b>\n\n"

SUB_NEW = (
    "✅ <b>Подписка активирована</b>\n"
    "📅 Действует до: <b>{expire}</b>\n\n"
    "🔗 Ваша ссылка на подписку:\n<code>{url}</code>\n\n"
    "📱 Нажмите кнопку «Подключить» — ссылка откроется в приложении и всё настроится автоматически."
)

SUB_EXTENDED = (
    "✅ <b>Подписка продлена</b>\n"
    "📅 Новый срок действия: <b>{expire}</b>\n\n"
    "🔗 Ссылка на подписку:\n<code>{url}</code>"
)

ERROR_DELIVERY = (
    "😔 Произошла ошибка при выдаче подписки. Оплата зафиксирована, "
    "мы уже уведомлены и всё исправим — ожидайте сообщения."
)

QR_CAPTION = "📱 Отсканируйте QR-код в приложении (кнопка «+» → «Импорт из QR»)"

HELP = (
    "📖 <b>Как подключиться</b>\n\n"
    "<b>1.</b> Оплатите подписку в боте.\n"
    "<b>2.</b> Установите приложение для вашей платформы:\n\n"
    "📱 <b>iPhone / iPad:</b> Happ, Streisand, V2Box, Shadowrocket\n"
    "🤖 <b>Android:</b> Happ, v2rayNG, Husi\n"
    "💻 <b>Windows:</b> Happ, Nekoray, Furious\n"
    "🍎 <b>macOS:</b> Happ, V2Box, Furious\n"
    "📺 <b>Android TV:</b> Happ TV\n\n"
    "<b>3.</b> В боте нажмите «💳 Моя подписка» → «🔗 Подключить».\n"
    "Ссылка откроется в приложении, и все серверы добавятся автоматически.\n\n"
    "💡 Альтернатива: скопируйте ссылку и добавьте её в приложении через «Импорт из буфера» "
    "или отсканируйте QR-код (кнопка «QR-код» в разделе «Моя подписка»).\n\n"
    "❗️ Если подключение перестало работать — просто обновите подписку в приложении "
    "(свайп вниз / кнопка обновления)."
)

REMINDER_SOON = (
    "⏳ <b>Напоминаем:</b> ваша VPN-подписка истекает {when}.\n"
    "Продлите сейчас, чтобы доступ не прерывался 👇"
)
REMINDER_EXPIRED = (
    "⛔️ <b>Ваша подписка истекла.</b>\n"
    "Продлите её, чтобы снова пользоваться VPN 👇"
)

PAYMENTS_NOTHING = (
    "Счётов пока нет. Методы оплаты, которые можно включить:\n"
    "• <b>Telegram Stars</b> — задаётся price_stars в TARIFFS\n"
    "• <b>CryptoBot</b> — нужен CRYPTOBOT_TOKEN и price_usdt\n"
    "• <b>ЮKassa</b> — нужны YOOKASSA_SHOP_ID/YOOKASSA_SECRET и price_rub"
)

# ── админка ────────────────────────────────────────────────────────────

ADMIN_MENU = "🛠 <b>Админ-панель</b>\nВыберите раздел:"

ADMIN_STATS = (
    "📊 <b>Статистика</b>\n\n"
    "👥 Пользователей бота: <b>{bot_users}</b>\n\n"
    "💰 <b>Продажи</b>\n{sales}\n"
    "├ За 7 дней: <b>{week}</b>\n"
    "├ За 30 дней: <b>{month}</b>\n"
    "└ Выдано вручную: <b>{gifts}</b>\n\n"
    "🌐 <b>Remnawave</b>\n"
    "├ Всего пользователей: <b>{rw_total}</b>\n"
    "└ Активных: <b>{rw_active}</b>"
)

ADMIN_STATS_EMPTY = "продаж пока нет 🙈"

ADMIN_NODES = "📡 <b>Состояние нод</b>\n\n{nodes}\n\nВсего: {total}, онлайн: {online}"
ADMIN_NODES_ONLINE = "🟢 {name}"
ADMIN_NODES_OFFLINE = "🔴 {name}"
ADMIN_NODES_EMPTY = "Ноды не найдены."

ADMIN_GRANT_ASK_TARGET = (
    "🎁 <b>Выдача подписки</b>\n\n"
    "Пришлите Telegram ID пользователя (число) или логин пользователя в Remnawave."
)
ADMIN_GRANT_ASK_DAYS = "Сколько дней выдать? Пришлите число (например 30)."
ADMIN_GRANT_DONE = "✅ Готово!\n\n{details}"

ADMIN_BAN_ASK = (
    "🚫 Пришлите Telegram ID или логин пользователя Remnawave, "
    "которого нужно <b>отключить</b>."
)
ADMIN_UNBAN_ASK = (
    "✅ Пришлите Telegram ID или логин пользователя Remnawave, "
    "которого нужно <b>включить</b>."
)
ADMIN_DONE = "✅ Готово."
ADMIN_USER_NOT_FOUND = "❌ Пользователь не найден ни по Telegram ID, ни по логину."
ADMIN_ASK_NUMBER = "Пришлите, пожалуйста, просто число."
ADMIN_BROADCAST_ASK = (
    "📢 <b>Рассылка</b>\n\n"
    "Пришлите любое сообщение (текст, фото, видео) — оно будет отправлено всем "
    "пользователям бота.\n\nДля отмены: /cancel"
)
ADMIN_BROADCAST_PREVIEW = "Сообщение будет отправлено <b>{count}</b> пользователям.\n\nПредпросмотр:"
ADMIN_BROADCAST_DONE = (
    "📢 Рассылка завершена.\n\n"
    "✅ Доставлено: {ok}\n"
    "⛔️ Заблокировали бота: {fail}"
)
ADMIN_BROADCAST_CANCELED = "Рассылка отменена."

ADMIN_CHECK = (
    "🔧 <b>Проверка панели Remnawave</b>\n\n"
    "{checks}"
)

CHECK_OK = "✅ {label}: {value}"
CHECK_FAIL = "❌ {label}: {error}"

ADMIN_NOTIFY_ERROR = (
    "⚠️ <b>Ошибка выдачи подписки</b>\n\n"
    "Пользователь: <a href=\"tg://user?id={tg_id}\">{tg_id}</a>\n"
    "Счёт #{payment_id} ({provider})\n"
    "Ошибка: <code>{error}</code>"
)

SQUAD_HINT = (
    "⚠️ REMNAWAVE_SQUAD_UUID не задан в .env — бот использует squad «{name}».\n"
    "Проверьте, что он содержит нужные хосты, или пропишите UUID явно."
)
