"""Генерация QR-кодов для ссылок на подписку."""
from __future__ import annotations

import io

import qrcode
from aiogram.types import BufferedInputFile

_cache: dict[str, bytes] = {}


def qr_file(url: str, *, filename: str = "subscription.png") -> BufferedInputFile:
    png = _cache.get(url)
    if png is None:
        img = qrcode.make(url, box_size=10, border=2)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png = buf.getvalue()
        _cache[url] = png
        if len(_cache) > 200:  # защита от разрастания
            _cache.pop(next(iter(_cache)))
    return BufferedInputFile(png, filename=filename)
