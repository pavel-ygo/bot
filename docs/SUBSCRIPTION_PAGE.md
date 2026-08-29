# 🎨 Красивая страница подписок (Remnawave Subscription Page)

Официальная веб-страница, которую открывает пользователь по ссылке подписки:
логотип, кнопки «Скачать Hiddify/Happ/v2rayNG», автоматическое добавление конфига,
счётчик трафика. Вместо «сырой» ссылки `/api/sub/...` клиент получает красивую страницу.

После настройки бот **автоматически** начнёт выдавать ссылки вида
`https://sub.ваш-домен/<shortUuid>` — достаточно указать `SUB_PAGE_DOMAIN` в `.env`.

## Шаг 0 — Поддомен

Нужен отдельный адрес для страницы подписок, панель и страница не могут жить на одном домене.

Вариант для DuckDNS: добавьте в панели DuckDNS ещё одно имя (например `quacktunnel-sub`)
либо попробуйте `sub.quack-tunnel.duckdns.org` — DuckDNS обычно резолвит поддомены
на тот же IP. Если не заработало — заведите отдельное имя и используйте его.

Проверьте, что имя резолвится:

```bash
dig +short sub.quack-tunnel.duckdns.org   # должен вернуть IP вашего сервера
```

## Шаг 1 — Контейнер страницы подписок

```bash
mkdir -p /opt/remnawave/subscription && cd /opt/remnawave/subscription
nano docker-compose.yml
```

Содержимое:

```yaml
services:
  remnawave-subscription-page:
    image: remnawave/subscription-page:latest
    container_name: remnawave-subscription-page
    restart: unless-stopped
    networks:
      - remnawave-network
    environment:
      - APP_PORT=3010
      - REMNAWAVE_PANEL_URL=http://remnawave:3000
      - REMNAWAVE_API_TOKEN=ТОКЕН_ПАНЕЛИ   # тот же, что у бота

networks:
  remnawave-network:
    external: true
```

Запуск:

```bash
docker compose up -d && docker compose logs --tail 20
```

## Шаг 2 — Caddy: маршрут для поддомена

Откройте Caddyfile (обычно `/opt/remnawave/caddy/Caddyfile`) и добавьте блок:

```caddyfile
sub.quack-tunnel.duckdns.org {
    encode
    reverse_proxy remnawave-subscription-page:3010
}
```

Примените конфиг:

```bash
docker exec caddy caddy reload --config /etc/caddy/Caddyfile
# либо: cd /opt/remnawave && docker compose restart caddy
```

## Шаг 3 — Скажите боту про новый домен

```bash
cd /opt/vpn-bot
nano .env
# добавьте/раскомментируйте строку:
# SUB_PAGE_DOMAIN=https://sub.quack-tunnel.duckdns.org
docker compose up -d --force-recreate
```

## Шаг 4 — Проверка

1. В браузере откройте `https://sub.quack-tunnel.duckdns.org` — должна открыться
   заглушка/страница сервиса
2. В боте: «💳 Моя подписка» — ссылка теперь вида
   `https://sub.quack-tunnel.duckdns.org/<shortUuid>`, и она открывает красивую
   страницу с кнопками приложений

## Настройка внешнего вида (опционально)

Логотип, название, цвета — через переменные контейнера
(см. официальную документацию: https://remna.st/docs/subscription-page/setup)
и файлы сервиса в панели (Config Profiles → Subscription Settings).

## Если что-то не работает

| Симптом | Причина |
|---|---|
| `ERR_NAME_NOT_RESOLVED` | Поддомен не зарегистрирован в DuckDNS — создайте отдельное имя |
| 502 от Caddy | Контейнер не поднялся: `docker logs remnawave-subscription-page` |
| Страница открывается, но ссылки в боте старые | Не забыли `SUB_PAGE_DOMAIN` + `up -d --force-recreate`? |
| «Invalid token» в логах контейнера | Неверный `REMNAWAVE_API_TOKEN` |
