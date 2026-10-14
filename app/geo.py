"""Kafe joylashuvi: Google Maps havolasidan koordinatalarni aniqlash (olib ketish uchun lokatsiya)."""
import logging
import re
import time

import aiohttp

from . import db

log = logging.getLogger(__name__)

# !3d41.29!4d69.20 (aniq joy), @41.29,69.20 (xarita markazi), q=41.29,69.20 / ll=... (so'rov)
_PATTERNS = (
    re.compile(r"!3d(-?\d{1,2}\.\d+)!4d(-?\d{1,3}\.\d+)"),
    re.compile(r"[?&](?:q|ll|query|destination|center)=(-?\d{1,2}\.\d+)(?:,|%2C)\s*(-?\d{1,3}\.\d+)"),
    re.compile(r"@(-?\d{1,2}\.\d+),(-?\d{1,3}\.\d+)"),
)
_last_fail = 0.0


def parse_coords(text: str) -> tuple[float, float] | None:
    for pattern in _PATTERNS:
        m = pattern.search(text or "")
        if m:
            lat, lng = float(m.group(1)), float(m.group(2))
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                return lat, lng
    return None


async def resolve_map_url(url: str) -> tuple[float, float] | None:
    """Qisqa havolani (maps.app.goo.gl) ochib, yakuniy manzil yoki sahifadan koordinatani topadi."""
    if coords := parse_coords(url):
        return coords
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        headers = {"User-Agent": "Mozilla/5.0 (compatible; YaproqBot/1.0)"}
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as s:
            async with s.get(url, allow_redirects=True, max_redirects=6) as r:
                if coords := parse_coords(str(r.url)):
                    return coords
                for prev in r.history:
                    if coords := parse_coords(prev.headers.get("Location", "")):
                        return coords
                body = (await r.content.read(400_000)).decode("utf-8", "ignore")
                return parse_coords(body)
    except Exception as e:  # noqa: BLE001
        log.warning("Xarita havolasini ochib bo'lmadi: %s", e)
    return None


async def cafe_location(force: bool = False) -> tuple[float, float] | None:
    """Sozlamalardagi koordinata; bo'lmasa havoladan aniqlab, saqlab qo'yadi."""
    global _last_fail
    s = await db.get_settings()
    try:
        if s.get("cafe_lat") and s.get("cafe_lng"):
            return float(s["cafe_lat"]), float(s["cafe_lng"])
    except ValueError:
        pass
    url = (s.get("cafe_map_url") or "").strip()
    if not url or (not force and time.time() - _last_fail < 600):
        return None
    coords = await resolve_map_url(url)
    if coords:
        await db.set_setting("cafe_lat", f"{coords[0]:.6f}")
        await db.set_setting("cafe_lng", f"{coords[1]:.6f}")
    else:
        _last_fail = time.time()
    return coords
