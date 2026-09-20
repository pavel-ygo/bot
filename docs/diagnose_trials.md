# 🔬 Диагностика триал-юзеров: почему не активируют

Команда показывает для каждого триал-юзера панели: когда создан, до когда доступ,
**открывал ли он подписку** (`subLastOpenedAt`), **был ли трафик** (`usedTrafficBytes`).

Выполнить на сервере:

```bash
cd /opt/vpn-bot
docker compose exec vpn-bot python -c "
import asyncio
from bot.config import load_config
from bot.remnawave import RemnawaveClient
from bot.utils import fmt_date, parse_iso

async def go():
    rc = RemnawaveClient(load_config())
    rows = []
    async for u in rc.iter_users():
        tag = str(u.get('tag') or '')
        if 'trial' not in tag and not u.get('description','').startswith('Пробный'):
            # триалы могли быть до внедрения тегов — смотрим и по описанию
            if 'Пробный' not in str(u.get('description') or ''):
                continue
        created = parse_iso(u.get('createdAt'))
        expire = parse_iso(u.get('expireAt'))
        opened = u.get('subLastOpenedAt')
        used = u.get('usedTrafficBytes')
        if used is None:
            used = (u.get('userTraffic') or {}).get('usedTrafficBytes') or 0
        rows.append((
            u.get('username'), u.get('telegramId'),
            fmt_date(created, __import__('zoneinfo').ZoneInfo('Europe/Moscow')) if created else '—',
            fmt_date(expire, __import__('zoneinfo').ZoneInfo('Europe/Moscow')) if expire else '—',
            'ДА' if opened else 'НЕТ',
            used,
            u.get('status'),
        ))
    print(f'{\"ЛОГИН\":<22}{\"TG\":<12}{\"СОЗДАН\":<18}{\"ДО\":<18}{\"ОТКРЫЛ\":<7}{\"ТРАФИК\":>12}  {\"СТАТУС\"}')
    for r in sorted(rows, key=lambda x: str(x[2]), reverse=True):
        print(f'{str(r[0]):<22}{str(r[1]):<12}{str(r[2]):<18}{str(r[3]):<18}{str(r[4]):<7}{r[5]:>12}  {r[6]}')
    await rc.aclose()

asyncio.run(go())
"
```

## Как читать результат

| Открыл | Трафик | Диагноз |
|---|---|---|
| НЕТ | 0 | Не дошёл до приложения → инструкция/мотивация (гайд + nudge) |
| ДА | 0 | Открыл конфиг, но не подключил → проблема на шаге подключения (приложение/протокол) |
| ДА | >0 | Всё работает! Не вернулся/не купил → дело в цене/продлении |
