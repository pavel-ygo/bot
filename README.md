# 🛒 Telegram-бот для продажи VPN-подписок (Remnawave)

Готовый магазин подписок в Telegram, интегрированный с панелью [Remnawave](https://remna.st).
Пользователь платит — бот сам создаёт/продлевает ему аккаунт в Remnawave и выдаёт ссылку на подписку + QR-код.

## ✨ Возможности

**Для покупателей:**
- 🛍 Покупка подписки в пару кликов, доступ выдаётся **автоматически** сразу после оплаты
- 💳 Оплата **Telegram Stars**, **криптовалютой (CryptoBot, USDT)** и **картой (ЮKassa)** — настраивается
- 💳 «Моя подписка»: срок действия, трафик, ссылка, QR-код
- 📖 Инструкция по подключению (iOS/Android/Windows/macOS/TV)
- ⏳ Напоминания об окончании подписки (за 3 дня, за 1 день и в день истечения)
- 🔄 Повторная покупка **продлевает** текущую подписку (плюс остаток дней), опционально сбрасывает трафик

**Для администратора (`/admin`):**
- 📊 Статистика: продажи по способам оплаты, за 7/30 дней, пользователи бота и панели
- 📡 Состояние нод Remnawave (онлайн/оффлайн)
- 🔧 Проверка панели (токен, squads, платёжки) прямо из бота
- 📢 Массовая рассылка всем пользователям бота
- 🎁 Выдача/продление подписки вручную (по TG ID или логину Remnawave)
- 🚫 Отключение и ✅ включение пользователей
- ⚠️ Уведомления об ошибках выдачи

## 🚀 Быстрый старт

### 1. Подготовьте Remnawave
1. В панели: **Настройки → API Tokens** → создайте токен.
2. **Управление → Internal Squads** → убедитесь, что есть squad с вашими хостами → скопируйте его **UUID**.
3. (Опционально) Проверьте, что ссылка на подписку открывается из панели — бот отдаёт пользователю ту же ссылку.

### 2. Создайте бота
1. Напишите [@BotFather](https://t.me/BotFather) → `/newbot` → получите **токен**.
2. Узнайте свой Telegram ID (например, [@userinfobot](https://t.me/userinfobot)) — он понадобится для админки.

### 3. Настройте и запустите

```bash
git clone <repo> vpn-bot && cd vpn-bot
cp .env.example .env
nano .env        # заполните BOT_TOKEN, ADMIN_IDS, REMNAWAVE_*, платёжки
```

Минимальный `.env`:

```env
BOT_TOKEN=123456:AAF...
ADMIN_IDS=123456789
REMNAWAVE_PANEL_URL=https://panel.example.com
REMNAWAVE_API_TOKEN=eyJhbGciOi...
REMNAWAVE_SQUAD_UUID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

Проверьте окружение (панель, токены, ноды, squads):

```bash
python3 -m bot.doctor
```

Запуск:

- **Через Docker (рекомендуется):**
  ```bash
  docker compose up -d --build
  docker compose logs -f
  ```
- **Либо напрямую:**
  ```bash
  pip install -r requirements.txt
  python3 -m bot
  ```

## 🖥 Деплой на хост с Remnawave

Самый удобный вариант: бот ходит в панель **напрямую по внутренней docker-сети**
(`http://remnawave:3000`) — быстрее, не зависит от DNS/TLS публичного домена и работает
даже если порт панели закрыт файрволом. Наружу бот ничего не публикует (портов в compose нет) —
только исходящие соединения к Telegram и платёжным системам.

### Шаг 1. Скопируйте код на сервер

```bash
# если PR ещё не смержен — клонируйте ветку:
git clone -b arena/01a0440c-bot https://github.com/pavel-ygo/bot.git /opt/vpn-bot
# после мержа:
git clone https://github.com/pavel-ygo/bot.git /opt/vpn-bot
cd /opt/vpn-bot
```

### Шаг 2. Узнайте имя docker-сети и контейнера панели

```bash
docker network ls | grep -i remna        # обычно: remnawave_network
docker ps --format '{{.Names}}' | grep -i remna   # обычно: remnawave
```

В стандартной установке Remnawave это `remnawave_network` и `remnawave` — они уже
подставлены по умолчанию, ничего менять не нужно.

### Шаг 3. Настройте .env

```bash
cp .env.example .env
nano .env
```

Ключевые строки для совместного хоста:

```env
REMNAWAVE_PANEL_URL=http://remnawave:3000     # контейнер панели напрямую
REMNAWAVE_API_TOKEN=...                       # панель → Настройки → API Tokens
REMNAWAVE_SQUAD_UUID=...                      # панель → Internal Squads
# в конце файла раскомментируйте две строки:
COMPOSE_FILE=docker-compose.yml:docker-compose.remna.yml
REMNAWAVE_DOCKER_NETWORK=remnawave_network
```

> Если сеть панели называется иначе — впишите её в `REMNAWAVE_DOCKER_NETWORK`.

### Шаг 4. Проверьте и запустите

```bash
docker compose run --rm vpn-bot python -m bot.doctor   # связь с панелью, ноды, squads
docker compose up -d --build
docker compose logs -f                                  # смотреть логи
```

`doctor` покажет ноды (обе ваши должны быть `online`), найденные Internal Squads
и подскажет, если `REMNAWAVE_SQUAD_UUID` не совпадает с панелью.

### Обновление бота

```bash
cd /opt/vpn-bot && git pull && docker compose up -d --build
```

### Альтернатива

Не хотите трогать docker-сеть панели — просто оставьте
`REMNAWAVE_PANEL_URL=https://panel.example.com` (публичный адрес) и запускайте
обычный `docker compose up -d --build` без файла `docker-compose.remna.yml`.
Работает так же, трафик пойдёт через Caddy.

## 💰 Приём платежей

| Способ | Что нужно | Где взять |
|---|---|---|
| ⭐ Telegram Stars | ничего (включён, если у тарифа есть `price_stars`) | встроено в Telegram |
| 🪙 CryptoBot (USDT) | `CRYPTOBOT_TOKEN` | [@CryptoBot](https://t.me/CryptoBot) → Crypto Pay → Create App → API Token |
| 💳 ЮKassa (карты) | `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET` | [yookassa.ru](https://yookassa.ru) → Настройки → Магазин → Секретный ключ |

Включайте только нужные способы: неиспользуемые реквизиты просто оставьте пустыми.
Счёт ждёт оплаты 24 часа, потом автоматически отменяется. Оплата проверяется двумя путями:
фоновым опросом каждые 20 секунд и кнопкой «Проверить оплату» в боте.

## 🧾 Тарифы

Тарифы задаются JSON-ом в `.env` (переменная `TARIFFS`). Пример с несколькими тарифами:

```json
{
  "m1":   {"title": "1 месяц",  "days": 30,  "price_rub": 199, "price_stars": 150, "price_usdt": 1.99,  "description": "Все локации"},
  "m3":   {"title": "3 месяца", "days": 90,  "price_rub": 499, "price_stars": 400, "price_usdt": 4.99,  "description": "Выгода 17%"},
  "m12":  {"title": "12 месяцев","days": 365,"price_rub": 1499,"price_stars": 1400,"price_usdt": 14.99, "description": "Выгода 38%"}
}
```

- Не нужен какой-то способ оплаты — поставьте `null` вместо цены.
- Telegram Stars: 1 ⭐ ≈ минимальная цена 1 звезда; ЮKassa — рубли; CryptoBot — USDT.

## ⚙️ Все переменные окружения

| Переменная | Описание |
|---|---|
| `BOT_TOKEN` | токен бота от @BotFather |
| `ADMIN_IDS` | Telegram ID админов через запятую |
| `REMNAWAVE_PANEL_URL` | URL панели, напр. `https://panel.example.com` |
| `REMNAWAVE_API_TOKEN` | API-токен из панели |
| `REMNAWAVE_API_PREFIX` | префикс API, по умолчанию `/api` |
| `REMNAWAVE_SQUAD_UUID` | Internal Squad для покупателей (если пусто — берётся первый) |
| `SUB_PAGE_DOMAIN` | домен страницы подписок, напр. `https://sub.example.com` (если пусто — ссылка берётся из API) |
| `RESET_TRAFFIC_ON_RENEW` | сбрасывать трафик при продлении (`true`/`false`) |
| `CRYPTOBOT_TOKEN` / `CRYPTOBOT_TESTNET` | токен Crypto Pay и переключатель тестнета |
| `YOOKASSA_SHOP_ID` / `YOOKASSA_SECRET` | реквизиты ЮKassa |
| `TARIFFS` | JSON с тарифами |
| `DB_PATH` | файл SQLite, по умолчанию `data/bot.db` |
| `TZ` | часовой пояс для дат, по умолчанию `Europe/Moscow` |
| `SUPPORT_URL` | ссылка на поддержку (кнопка в меню) |

## 🧩 Как это работает

```
Пользователь            Бот                        Remnawave            Платёжка
     │  /start           │                             │                  │
     │  Купить ─────────►│                             │                  │
     │  Оплата ──────────┼─── счёт/инвойс ────────────┼─────────────────►│
     │                   │◄── подтверждение оплаты ────┼──────────────────┤
     │                   ├─── создать/продлить юзера ─►│                  │
     │◄── ссылка + QR ───┤◄── subscriptionUrl ─────────┤                  │
```

- Пользователь бота связывается с пользователем Remnawave по `telegramId` — повторная
  покупка всегда продлевает существующий аккаунт и включает его заново.
- Все операции идемпотентны: двойное подтверждение оплаты не выдаст две подписки.
- Напоминания и продления не ломают счётчик уведомлений (хранится в SQLite).

## 📁 Структура

```
bot/
├── main.py          # запуск, регистрация роутеров
├── config.py        # .env → конфиг + валидация
├── remnawave.py     # клиент REST API Remnawave
├── db.py            # SQLite (пользователи, платежи, статистика)
├── payments.py      # CryptoBot + ЮKassa (Stars — нативно в aiogram)
├── services.py      # выдача/продление подписок, напоминания
├── handlers/
│   ├── user.py      # меню, моя подписка, помощь, QR
│   ├── buy.py       # покупка и все платёжные хэндлеры
│   └── admin.py     # админ-раздел
├── jobs.py          # фоновые задачи (опрос платежей, напоминания)
└── doctor.py        # самопроверка окружения
```

## ❓ FAQ

**Бот пишет «Панель недоступна».** — Проверьте `REMNAWAVE_PANEL_URL` (доступен ли он с
сервера, где запущен бот) и не истёк ли `REMNAWAVE_API_TOKEN`.

**Пользователь оплатил, но подписка не пришла.** — Смотрите `/admin → 📊 Статистика` и
логи: при ошибке выдачи админам приходит уведомление, платёж помечается `error` и
пользователю обещают разбор. После исправления выдайте подписку вручную
(`/admin → 🎁 Выдать подписку`).

**Как поменять тексты бота?** — Все строки в `bot/texts.py`.

**Где хранятся данные?** — SQLite-файл `data/bot.db` (пользователи бота, платежи).
Сами подписки живут в Remnawave, бот их только создаёт/продлевает.
