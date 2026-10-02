"""Mahsulot narxi (chegirma bilan), belgilar va tarjima — bot va Mini App uchun umumiy."""
from datetime import datetime

from .utils import TZ, now

BADGES = {
    "hit": {"uz": "🔥 Hit", "ru": "🔥 Хит"},
    "new": {"uz": "🆕 Yangi", "ru": "🆕 Новинка"},
    "top": {"uz": "⭐ Top", "ru": "⭐ Топ"},
    "spicy": {"uz": "🌶 Achchiq", "ru": "🌶 Острое"},
}

VARIANT_RU = {
    "o'rta": "Средний", "katta": "Большой", "kichik": "Маленький", "standart": "Стандарт",
    "oddiy": "Обычный", "dabl": "Двойной",
}


def norm_lang(lang: str | None) -> str:
    return "ru" if (lang or "").lower().startswith("ru") else "uz"


def badges_of(p: dict) -> list[str]:
    return [b for b in (p.get("badges") or "").split(",") if b in BADGES]


def discount_active(p: dict) -> int:
    """Faol chegirma foizi (0 — chegirma yo'q yoki muddati tugagan)."""
    pct = int(p.get("discount_percent") or 0)
    if pct <= 0:
        return 0
    until = p.get("discount_until") or ""
    if until:
        try:
            if datetime.strptime(until, "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ) <= now():
                return 0
        except ValueError:
            return 0
    return min(pct, 95)


def apply_percent(price: int, pct: int) -> int:
    """Chegirmali narx, 100 so'mgacha yaxlitlangan."""
    return int(round(price * (100 - pct) / 100 / 100)) * 100


def variant_price(p: dict, vidx: int) -> tuple[int, int | None]:
    """(joriy narx, eski narx yoki None)."""
    base = int(p["variants"][vidx]["price"])
    pct = discount_active(p)
    if not pct:
        return base, None
    return apply_percent(base, pct), base


def product_name(p: dict, lang: str) -> str:
    return (p.get("name_ru") or p["name"]) if lang == "ru" else p["name"]


def product_desc(p: dict, lang: str) -> str:
    return (p.get("description_ru") or p.get("description") or "") if lang == "ru" else (p.get("description") or "")


def category_name(c: dict, lang: str) -> str:
    return (c.get("name_ru") or c["name"]) if lang == "ru" else c["name"]


def variant_name(name: str, lang: str) -> str:
    if lang == "ru" and name:
        return VARIANT_RU.get(name.strip().lower(), name)
    return name


def badge_labels(p: dict, lang: str) -> list[str]:
    labels = [BADGES[b][lang] for b in badges_of(p)]
    pct = discount_active(p)
    if pct:
        labels.insert(0, f"-{pct}%")
    return labels


def product_public(p: dict, lang: str) -> dict:
    """Mini App API uchun mahsulot."""
    variants = []
    for i, v in enumerate(p["variants"]):
        price, old = variant_price(p, i)
        variants.append({"name": variant_name(v["name"], lang), "price": price, "old_price": old})
    return {
        "id": p["id"],
        "name": product_name(p, lang),
        "description": product_desc(p, lang),
        "image": p["image"],
        "variants": variants,
        "badges": badges_of(p),
        "discount": discount_active(p),
        # qidiruv uchun ikkala tildagi nom
        "search": f"{p['name']} {p.get('name_ru') or ''}".lower(),
    }
