"""Бизнес-логика: выдача/продление подписок, напоминания, общие объекты рантайма."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from . import texts
from .config import Config, Tariff
from .db import Database
from .keyboards import main_menu
from .texts import SYS_PAYMENT
from .payments import CryptoBotProvider, YooKassaProvider
from .remnawave import RemnaError, RemnawaveClient
from .utils import fmt_bytes, fmt_date, human_days_left, parse_iso, random_suffix, to_iso, utcnow

log = logging.getLogger(__name__)


@dataclass
class Runtime:
    cfg: Config
    db: Database
    remna: RemnawaveClient
    bot_username: str = ""
    cryptobot: CryptoBotProvider | None = None
    yookassa: YooKassaProvider | None = None
    _squad_uuid: str | None = None
    extra: dict = field(default_factory=dict)

    async def unavailable_reasons(self, tariff: Tariff) -> list[str]:
        """Почему способы оплаты недоступны (для подсказки администратору)."""
        from . import texts

        reasons: list[str] = []
        card_set = bool(await self.db.get_setting("card_number", ""))
        card_on = await self.db.get_setting("pay_card", "1") == "1"
        if not card_set:
            reasons.append(texts.PAY_NO_CARD)
        elif not card_on:
            reasons.append(texts.PAY_CARD_OFF)
        if not tariff.price_rub:
            reasons.append(texts.PAY_NO_PRICE)
        if not (bool(tariff.price_stars) and self.cfg.stars_enabled):
            reasons.append(texts.PAY_STARS_OFF)
        if not (self.cryptobot and tariff.price_usdt):
            reasons.append(texts.PAY_CRYPTO_OFF)
        if not (self.yookassa and tariff.price_rub):
            reasons.append(texts.PAY_YK_OFF)
        return reasons

    async def reload_tariffs(self) -> None:
        """Тарифы из БД (админка) с приоритетом над TARIFFS из .env."""
        from .config import _parse_tariffs

        raw = await self.db.get_setting("tariffs_json")
        if raw:
            try:
                self.cfg.tariffs = _parse_tariffs(raw)
            except Exception as e:  # noqa: BLE001
                log.error("tariffs_json invalid, keeping current: %s", e)

    async def serialize_tariffs(self) -> str:
        """Текущие тарифы -> JSON для хранения в БД."""
        import json as _json

        payload = {}
        for tid, t in self.cfg.tariffs.items():
            payload[tid] = {
                "title": t.title, "days": t.days,
                "price_rub": t.price_rub, "price_stars": t.price_stars,
                "price_usdt": t.price_usdt,
                "description": t.description, "visible": t.visible,
            }
        return _json.dumps(payload, ensure_ascii=False)

    async def payment_recipients(self) -> list[int]:
        """Кому пересылать чеки: админы + операторы, без дублей."""
        operators = await self.payment_operators()
        rec = list(self.cfg.admin_ids)
        for op in operators:
            if op not in rec:
                rec.append(op)
        return rec

    async def payment_operators(self) -> list[int]:
        raw = await self.db.get_setting("pay_operators", "") or ""
        out: list[int] = []
        for part in raw.split(","):
            part = part.strip()
            if part.isdigit():
                tg = int(part)
                if tg not in out:
                    out.append(tg)
        return out

    async def is_payment_operator(self, tg_id: int) -> bool:
        if tg_id in self.cfg.admin_ids:
            return True
        return tg_id in await self.payment_operators()

    async def available_providers(self, tariff: Tariff) -> dict[str, bool]:
        """Способы оплаты: сконфигурированы И включены в админке.

        По умолчанию включены: перевод на карту (если заданы реквизиты) и ЮKassa.
        Stars и криптовалюта выключены — включаются в /admin → 💳 Способы оплаты.
        """
        card_ready = bool(tariff.price_rub) and bool(
            await self.db.get_setting("card_number", "")
        )
        return {
            "card": card_ready and await self.db.get_setting("pay_card", "1") == "1",
            "yookassa": bool(self.yookassa and tariff.price_rub)
            and await self.db.get_setting("pay_yookassa", "0") == "1",
            "stars": bool(tariff.price_stars)
            and self.cfg.stars_enabled
            and await self.db.get_setting("pay_stars", "0") == "1",
            "cryptobot": bool(self.cryptobot and tariff.price_usdt)
            and await self.db.get_setting("pay_cryptobot", "0") == "1",
        }

    async def squad_uuid(self) -> str:
        """UUID Internal Squad из конфига; иначе — первый доступный (с предупреждением)."""
        if self._squad_uuid:
            return self._squad_uuid
        if self.cfg.squad_uuid:
            self._squad_uuid = self.cfg.squad_uuid
            return self._squad_uuid
        squads = await self.remna.list_internal_squads()
        if not squads:
            raise RemnaError(
                "В Remnawave нет ни одного Internal Squad. "
                "Создайте его в панели (Управление → Internal Squads) и добавьте хосты."
            )
        first = squads[0]
        self._squad_uuid = first.get("uuid")
        log.warning(texts.SQUAD_HINT.format(name=first.get("name")))
        return self._squad_uuid


# ──────────────────────────── карточка в панели ────────────────────────────


def _segment_of(tariff: Tariff) -> tuple[str, str]:
    """(тег, пометка в описании) по типу тарифа."""
    tid = tariff.id
    if tid == "trial":
        return "trial", "Пробный период"
    if tid == "gift":
        return "gift", "Выдано админом"
    if tid == "refbonus":
        return "refbonus", "Реф. бонус"
    if tid.startswith("promo_"):
        code = tid.removeprefix("promo_").upper()
        return "promo", f"Промокод {code}"
    return "paid", "Оплата"


async def panel_card_fields(rt: Runtime, tg_id: int | None, tariff: Tariff) -> dict:
    """Собирает email/tag/description для карточки пользователя в панели."""
    from .utils import utcnow

    segment, note = _segment_of(tariff)
    tag = f"tgbot|{segment}"
    bot_user = await rt.db.get_bot_user(tg_id) if tg_id else None
    tg_username = (bot_user or {}).get("username")
    email = f"@{tg_username}" if tg_username else (f"id{tg_id}" if tg_id else "")

    source = "напрямую"
    if bot_user:
        if bot_user.get("source"):
            source = bot_user["source"]
        elif bot_user.get("referred_by"):
            source = f"реферал {bot_user['referred_by']}"

    if tg_id:
        cnt, rub = await rt.db.paid_summary(tg_id)
    else:
        cnt, rub = 0, 0.0
    date = utcnow().astimezone(rt.cfg.tz).strftime("%d.%m.%Y")
    if note == "Оплата":
        desc = f"Источник: {source} | Покупок: {cnt} ({rub:g} ₽) | {note} {date}"
    else:
        desc = f"Источник: {source} | {note} +{tariff.days} дн. | {date}"
    return {"email": email, "tag": tag, "description": desc[:500]}



# ──────────────────────────── выдача подписки ────────────────────────────


async def deliver_subscription(
    rt: Runtime, tg_id: int | None, tariff: Tariff, *, existing: dict | None = None
) -> tuple[str, str | None]:
    """Находит или создаёт пользователя Remnawave и продлевает подписку на tariff.days.

    existing — заранее найденный пользователь Remnawave (продлеваем его).
    Возвращает (текст_результата, ссылка_на_подписку | None).
    """
    now = utcnow()
    squad = await rt.squad_uuid()

    user = existing
    if user is None and tg_id is not None:
        user = await rt.remna.get_user_by_telegram_id(tg_id)
    if user:
        current_expire = parse_iso(user.get("expireAt")) or now
        new_expire = max(now, current_expire) + timedelta(days=tariff.days)
        await rt.remna.set_expire(user["uuid"], new_expire)
        try:
            await rt.remna.enable_user(user["uuid"])
        except RemnaError as e:
            log.warning("enable_user failed: %s", e)
        if rt.cfg.reset_traffic_on_renew:
            try:
                await rt.remna.reset_traffic(user["uuid"])
            except RemnaError as e:
                log.warning("reset_traffic failed: %s", e)
        # обновляем карточку в панели (email/tag/description)
        if tg_id is not None:
            try:
                card = await panel_card_fields(rt, tg_id, tariff)
                updates: dict = {"tag": card["tag"], "description": card["description"]}
                if card["email"]:
                    updates["email"] = card["email"]
                await rt.remna.update_user(user["uuid"], **updates)
            except RemnaError as e:
                log.warning("panel card update failed: %s", e)
        fresh = await rt.remna.get_user(user["uuid"])
        url = _safe_url(rt, fresh)
        return texts.SUB_EXTENDED.format(expire=fmt_date(new_expire, rt.cfg.tz), url=url), url

    # ── создаём нового пользователя Remnawave ──
    if tg_id is None:
        raise RemnaError("Некорректный Telegram ID пользователя")
    base_name = f"tg{tg_id}"
    created: dict | None = None
    last_error: Exception | None = None
    card = await panel_card_fields(rt, tg_id, tariff)
    for attempt in range(3):
        username = base_name if attempt == 0 else f"{base_name}_{random_suffix()}"
        base_payload = {
            "username": username,
            "expire_at": to_iso(now + timedelta(days=tariff.days)),
            "squad_uuids": [squad],
            "telegram_id": tg_id,
        }
        full_payload = {
            **base_payload,
            "email": card["email"] or None,
            "description": card["description"],
            "tag": card["tag"],
        }
        try:
            created = await rt.remna.create_user(**full_payload)
            break
        except RemnaError as e:
            last_error = e
            if e.status == 409:  # имя занято — пробуем с суффиксом
                continue
            if e.status == 400:
                # панель не приняла доп. поля (email/description/tag) —
                # пробуем без email, затем минимальный payload
                try:
                    created = await rt.remna.create_user(
                        **{**base_payload, "description": card["description"],
                           "tag": card["tag"]}
                    )
                    break
                except RemnaError as e2:
                    last_error = e2
                    if e2.status == 400:
                        try:
                            created = await rt.remna.create_user(**base_payload)
                            break
                        except RemnaError as e3:
                            last_error = e3
                            if e3.status == 409:
                                continue
                            raise
                    if e2.status == 409:
                        continue
                    raise
            raise
    if created is None:
        raise last_error or RemnaError("Не удалось создать пользователя")

    expire = parse_iso(created.get("expireAt"))
    url = _safe_url(rt, created)
    return texts.SUB_NEW.format(expire=fmt_date(expire, rt.cfg.tz), url=url), url


def _safe_url(rt: Runtime, rw_user: dict) -> str | None:
    try:
        return rt.remna.build_sub_url(rw_user)
    except RemnaError as e:
        log.error("sub url: %s", e)
        return None


async def complete_payment(
    rt: Runtime, bot: Bot, tg_id: int, payment: dict, *, success_prefix: str = ""
) -> bool:
    """Оплата подтверждена — выдаём подписку. Возвращает True при успехе."""
    tariff = rt.cfg.tariffs.get(payment["tariff_id"])
    if tariff is None:
        await rt.db.mark_error(payment["id"], "tariff vanished")
        return False

    try:
        result_text, sub_url = await deliver_subscription(rt, tg_id, tariff)
    except Exception as e:
        log.exception("delivery failed for payment #%s", payment["id"])
        await rt.db.mark_error(payment["id"], f"{e.__class__.__name__}: {e}")
        try:
            await bot.send_message(tg_id, texts.ERROR_DELIVERY)
        except Exception:
            pass
        for admin_id in rt.cfg.admin_ids:
            try:
                await bot.send_message(
                    admin_id,
                    texts.ADMIN_NOTIFY_ERROR.format(
                        tg_id=tg_id, payment_id=payment["id"],
                        provider=payment["provider"], error=str(e)[:400],
                    ),
                )
            except Exception:
                pass
        return False

    await rt.db.mark_delivered(payment["id"])
    text = (success_prefix + "\n\n" if success_prefix else "") + texts.SUCCESS_TITLE + result_text
    kb = subscription_kb(sub_url)
    try:
        await bot.send_message(tg_id, text, reply_markup=kb, disable_web_page_preview=True)
    except Exception as e:
        log.warning("Не удалось отправить сообщение %s: %s", tg_id, e)

    await _notify_payment(rt, bot, tg_id, payment)
    await _credit_referral(rt, bot, tg_id, payment)
    return True


async def _notify_payment(rt: Runtime, bot: Bot, tg_id: int, payment: dict) -> None:
    """Короткое уведомление админам о состоявшейся оплате."""
    tariff = rt.cfg.tariffs.get(payment["tariff_id"])
    bot_user = await rt.db.get_bot_user(tg_id) or {}
    name = bot_user.get("first_name") or bot_user.get("username") or str(tg_id)
    provider_names = {
        "stars": "Stars", "cryptobot": "CryptoBot", "yookassa": "ЮKassa",
    }
    cur_sym = {"RUB": "₽", "XTR": "⭐", "USDT": " USDT"}
    amount = f"{payment['amount']}{cur_sym.get(payment['currency'], payment['currency'])}"
    notif = texts.NOTIF_PAYMENT.format(
        title=tariff.title if tariff else payment["tariff_id"],
        days=tariff.days if tariff else "?",
        amount=amount,
        provider=provider_names.get(payment["provider"], payment["provider"]),
        uid=tg_id, name=name,
        source=payment.get("source") or "—",
    )
    for admin_id in rt.cfg.admin_ids:
        try:
            await bot.send_message(admin_id, notif)
        except Exception:
            pass
    await sys_log(rt, bot, SYS_PAYMENT.format(
        title=tariff.title if tariff else payment["tariff_id"],
        days=tariff.days if tariff else "?",
        amount=amount,
        provider=provider_names.get(payment["provider"], payment["provider"]),
        uid=tg_id, name=name,
        source=payment.get("source") or "—",
    ))


async def _credit_referral(rt: Runtime, bot: Bot, tg_id: int, payment: dict) -> None:
    """Если это первая оплата приглашённого пользователя — бонус рефереру."""
    bonus_days = rt.cfg.ref_bonus_days
    if bonus_days <= 0:
        return
    bot_user = await rt.db.get_bot_user(tg_id)
    if not bot_user or not bot_user.get("referred_by"):
        return
    # бонус только за ПЕРВУЮ оплату приглашённого
    if await rt.db.delivered_paid_count(tg_id) != 1:
        return
    try:
        referrer = int(bot_user["referred_by"])
    except (TypeError, ValueError):
        return
    if referrer == tg_id:
        return

    tariff = Tariff(id="refbonus", title="Бонус за приглашённого друга",
                    days=bonus_days, description="")
    try:
        result_text, url = await deliver_subscription(rt, referrer, tariff)
    except Exception as e:
        log.warning("referral bonus delivery failed for %s: %s", referrer, e)
        return
    await rt.db.add_payment(
        referrer, "refbonus", "refbonus", str(bonus_days), "days",
        status="delivered", note=f"referral {tg_id} paid",
    )
    try:
        await bot.send_message(
            referrer,
            f"🎉 Ваш друг оплатил подписку — вам <b>+{bonus_days} дн.</b> в подарок!\n\n"
            + result_text,
            reply_markup=subscription_kb(url),
            disable_web_page_preview=True,
        )
    except Exception:
        pass
    for admin_id in rt.cfg.admin_ids:
        try:
            await bot.send_message(
                admin_id,
                f"👥 Реферал оплатил: <code>{tg_id}</code> → бонус "
                f"+{bonus_days} дн. для <code>{referrer}</code>",
            )
        except Exception:
            pass
    await sys_log(rt, bot, texts.SYS_REFBONUS.format(
        uid=tg_id, referrer=referrer, days=bonus_days,
    ))


def subscription_kb(sub_url: str | None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if sub_url:
        rows.append([InlineKeyboardButton(text="🔗 Подключить", url=sub_url)])
        rows.append([InlineKeyboardButton(text="📱 QR-код", callback_data="menu:qr")])
    rows.append([InlineKeyboardButton(text="💳 Моя подписка", callback_data="menu:sub")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ──────────────────────────── напоминания ────────────────────────────


async def check_reminders(rt: Runtime, bot: Bot) -> tuple[int, int]:
    """Обход пользователей Remnawave: предупреждение за 3 дня, за 1 день и об истечении."""
    sent = 0
    errors = 0
    async for rw_user in rt.remna.iter_users():
        tg_raw = rw_user.get("telegramId")
        if not tg_raw:
            continue
        try:
            tg_id = int(tg_raw)
        except (TypeError, ValueError):
            continue
        expire = parse_iso(rw_user.get("expireAt"))
        if expire is None or str(rw_user.get("status", "")).upper() != "ACTIVE":
            continue

        delta_days = (expire - utcnow()).total_seconds() / 86400
        if delta_days > 3:
            await rt.db.set_reminder(tg_id, "")  # продление/новая подписка — сброс цикла
            continue

        if delta_days > 1:
            code, when = "d3", "через 2–3 дня"
        elif delta_days > 0:
            code, when = "d1", "уже завтра"
        else:
            code, when = "expired", None

        last = await rt.db.get_reminder(tg_id)
        if last == code:
            continue

        text = (
            texts.REMINDER_EXPIRED if code == "expired" else texts.REMINDER_SOON.format(when=when)
        )
        try:
            await bot.send_message(tg_id, text, reply_markup=main_menu())
            await rt.db.set_reminder(tg_id, code)
            sent += 1
        except Exception:
            errors += 1
    return sent, errors


# ──────────────────────────── пробный период ────────────────────────────


async def trial_config(rt: Runtime) -> dict:
    """Настройки пробного периода: из БД (админка) с фолбэком на .env."""
    db = rt.db
    channel = await db.get_setting("trial_channel", rt.cfg.trial_channel or "")
    url = await db.get_setting("trial_channel_url", rt.cfg.trial_channel_url or "")
    try:
        days = int(await db.get_setting("trial_days", str(rt.cfg.trial_days)) or 1)
    except ValueError:
        days = rt.cfg.trial_days
    enabled = (await db.get_setting("trial_enabled", "1")) == "1"
    return {
        "enabled": enabled,
        "channel": channel.strip() or None,
        "url": url.strip() or None,
        "days": max(1, days),
    }


async def is_channel_member(bot: Bot, channel: str, user_id: int) -> bool | None:
    """True/False — статус подписки; None — не удалось проверить (нет прав и т.п.)."""
    chat_id: int | str = channel
    if channel.lstrip("-").isdigit():
        chat_id = int(channel)
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except Exception:
        return None
    return member.status in ("member", "administrator", "creator")


# ──────────────────────────── карточка подписки ────────────────────────────


def subscription_card(rt: Runtime, rw_user: dict) -> str:
    expire = parse_iso(rw_user.get("expireAt"))
    used = rw_user.get("usedTrafficBytes")
    if used is None:
        ut = rw_user.get("userTraffic") or rw_user.get("user_traffic") or {}
        used = ut.get("usedTrafficBytes")
    limit = rw_user.get("trafficLimitBytes")

    traffic_line = ""
    if used is not None:
        limit_line = texts.SUB_STATUS_LIMIT.format(limit=fmt_bytes(limit)) if limit else ""
        traffic_line = texts.SUB_STATUS_TRAFFIC.format(used=fmt_bytes(used), limit_line=limit_line)

    status = str(rw_user.get("status", "")).upper()
    status_line = texts.SUB_STATUS_DISABLED if status == "DISABLED" else texts.SUB_STATUS_ACTIVE

    text = texts.SUB_STATUS.format(
        username=rw_user.get("username", "—"),
        expire=fmt_date(expire, rt.cfg.tz),
        traffic_line=traffic_line,
        status_line=status_line,
    )
    days_left = human_days_left(expire)
    if days_left is not None and days_left <= 3 and status != "DISABLED":
        text += texts.SUB_EXPIRES_SOON
    return text


async def card_settings(rt: Runtime) -> dict:
    """Реквизиты для ручной оплаты (хранятся в БД, задаются в админке)."""
    return {
        "number": (await rt.db.get_setting("card_number", "") or "").strip(),
        "bank": (await rt.db.get_setting("card_bank", "") or "").strip(),
        "holder": (await rt.db.get_setting("card_holder", "") or "").strip(),
        "sbp": (await rt.db.get_setting("card_sbp", "") or "").strip(),
    }


# ──────────────────────── системный канал ────────────────────────


async def sys_channel(rt: Runtime) -> str | None:
    """ID/username канала системных событий или None."""
    value = (await rt.db.get_setting("sys_channel", "") or "").strip()
    return value or None


async def sys_log(rt: Runtime, bot: Bot, text: str) -> None:
    """Публикует событие в системный канал (если задан). Молча глотает ошибки,
    чтобы журнал никогда не ломал основной сценарий."""
    channel = await sys_channel(rt)
    if not channel:
        return
    try:
        await bot.send_message(channel, text, disable_web_page_preview=True)
    except Exception as e:
        log.warning("sys_log to %s failed: %s", channel, e)


async def sys_new_user(rt: Runtime, bot: Bot, tg_id: int, name: str,
                       source: str | None, referred_by: str | None) -> None:
    """Публикует событие о новом пользователе в системный канал."""
    src = source or (f"реферал {referred_by}" if referred_by else "напрямую")
    await sys_log(rt, bot, texts.SYS_NEW_USER.format(name=name, uid=tg_id, source=src))
