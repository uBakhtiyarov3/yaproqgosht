"""Buyurtma qoidalari — Mini App va bot ichidagi savat uchun umumiy.

Narx hisoblash (chegirmalar, promo-kod, yetkazish), ish vaqti va vaqtga buyurtma tekshiruvi shu yerda.
"""
import re
from datetime import datetime, timedelta

from . import db, hours
from .catalog import norm_lang, variant_price
from .i18n import money_l, t
from .utils import TZ, now

ORDER_COOLDOWN_SEC = 20
PHONE_RE = re.compile(r"^\+998\d{9}$")
ORDER_TYPES = ("delivery", "pickup")


class OrderError(Exception):
    """Xato kaliti (i18n) va parametrlari bilan; matn foydalanuvchi tilida olinadi."""

    def __init__(self, key: str, status: int = 400, **params):
        super().__init__(key)
        self.key = key
        self.status = status
        self.params = params

    def text(self, lang: str = "uz") -> str:
        params = {k: (money_l(v, lang) if k in ("min",) else v) for k, v in self.params.items()}
        if self.key == "e_closed":
            nxt = self.params.get("next")
            params["next"] = (" " + t("opens_short", lang, when=nxt)) if nxt else ""
        return t(self.key, lang, **params)

    @property
    def message(self) -> str:
        return self.text("uz")


def normalize_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 9:
        digits = "998" + digits
    phone = "+" + digits
    return phone if PHONE_RE.match(phone) else None


def _when_label(dt: datetime | None) -> str | None:
    if not dt:
        return None
    return dt.strftime("%H:%M") if dt.date() == now().date() else dt.strftime("%d.%m %H:%M")


def public_settings(s: dict) -> dict:
    is_open = hours.is_open_at(s)
    return {
        "is_open": is_open,
        "mode": s.get("mode") or "auto",
        "accepting": (s.get("mode") or "auto") != "closed",
        "next_open": None if is_open else _when_label(hours.next_opening(s)),
        "delivery_fee": int(s.get("delivery_fee") or 0),
        "min_order": int(s.get("min_order") or 0),
        "phone": s.get("phone") or "",
        "work_hours": hours.today_hours(s) or "",
        "schedule": hours.schedule_summary(s),
        "schedule_ru": hours.schedule_summary(s, "ru"),
        "delivery_enabled": s.get("delivery_enabled", "1") == "1",
        "pickup_enabled": s.get("pickup_enabled", "1") == "1",
        "cafe_address": s.get("cafe_address") or "",
    }


async def resolve_items(raw_items) -> list[dict]:
    """[{product_id, variant, qty}] -> narxlari (chegirma bilan) bazadan olingan pozitsiyalar."""
    if not isinstance(raw_items, list) or not raw_items:
        raise OrderError("e_empty_cart")
    if len(raw_items) > 30:
        raise OrderError("e_too_many")
    items = []
    for raw in raw_items:
        try:
            pid, vidx, qty = int(raw["product_id"]), int(raw.get("variant", 0)), int(raw["qty"])
        except (KeyError, TypeError, ValueError):
            raise OrderError("e_cart")
        if not 1 <= qty <= 50:
            raise OrderError("e_qty")
        product = await db.get_product(pid)
        cat = await db.get_category(product["category_id"]) if product else None
        if not product or not product["is_available"] or not cat or not cat["is_active"]:
            raise OrderError("e_unavailable", 409)
        if not 0 <= vidx < len(product["variants"]):
            raise OrderError("e_variant", 409)
        price, _old = variant_price(product, vidx)
        items.append({
            "product_id": pid, "name": product["name"], "variant": product["variants"][vidx]["name"],
            "price": price, "qty": qty,
        })
    return items


# ---------------- promo-kod ----------------

def promo_label(promo: dict, lang: str) -> str:
    if promo["kind"] == "percent":
        return t("promo_percent", lang, value=promo["value"])
    if promo["kind"] == "fixed":
        return t("promo_fixed", lang, value=money_l(promo["value"], lang))
    return t("promo_free_delivery", lang)


def _parse_dt(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)
    except (ValueError, TypeError):
        return None


async def check_promo(code: str, user_id: int, subtotal: int, order_type: str) -> tuple[dict, int, bool]:
    """(promo, chegirma summasi, bepul_yetkazish). Shartlar bajarilmasa OrderError."""
    promo = await db.get_promo_by_code(code)
    if not promo:
        raise OrderError("e_promo_not_found")
    if not promo["is_active"]:
        raise OrderError("e_promo_inactive")
    start, end = _parse_dt(promo["starts_at"]), _parse_dt(promo["ends_at"])
    if start and now() < start:
        raise OrderError("e_promo_not_started")
    if end and now() >= end:
        raise OrderError("e_promo_expired")
    if promo["min_order"] and subtotal < promo["min_order"]:
        raise OrderError("e_promo_min", min=promo["min_order"])
    if promo["usage_limit"] and await db.promo_uses(promo["code"]) >= promo["usage_limit"]:
        raise OrderError("e_promo_limit")
    if promo["per_user_limit"] and await db.promo_uses(promo["code"], user_id) >= promo["per_user_limit"]:
        raise OrderError("e_promo_user_limit")
    if promo["first_order_only"] and await db.user_order_count(user_id) > 0:
        raise OrderError("e_promo_first")

    if promo["kind"] == "free_delivery":
        if order_type != "delivery":
            raise OrderError("e_promo_pickup")
        return promo, 0, True
    if promo["kind"] == "percent":
        discount = subtotal * promo["value"] // 100
        if promo["max_discount"]:
            discount = min(discount, promo["max_discount"])
    else:
        discount = promo["value"]
    return promo, min(discount, subtotal), False


# ---------------- hisob-kitob ----------------

async def quote(user_id: int, raw_items, order_type: str = "delivery", promo_code: str = "",
                lang: str = "uz") -> dict:
    """Savat summasi: mahsulotlar, chegirma, yetkazish, jami. Promo xato bo'lsa OrderError."""
    settings = public_settings(await db.get_settings())
    items = await resolve_items(raw_items)
    subtotal = sum(i["price"] * i["qty"] for i in items)
    fee = settings["delivery_fee"] if order_type == "delivery" else 0
    discount, promo, label = 0, None, ""
    if promo_code:
        promo, discount, free_delivery = await check_promo(promo_code, user_id, subtotal, order_type)
        if free_delivery:
            fee = 0
        label = promo_label(promo, lang)
    return {
        "items": items,
        "subtotal": subtotal,
        "discount": discount,
        "delivery_fee": fee,
        "total": max(0, subtotal - discount) + fee,
        "promo_code": promo["code"] if promo else "",
        "promo_label": label,
        "min_order": settings["min_order"] if order_type == "delivery" else 0,
    }


async def place_order(user_id: int, data: dict, raw_items) -> int:
    """Tekshiradi va buyurtma yaratadi. Xatoda OrderError. order_id qaytaradi."""
    raw_settings = await db.get_settings()
    settings = public_settings(raw_settings)
    lang = norm_lang(data.get("lang"))

    order_type = data.get("order_type") or "delivery"
    if order_type not in ORDER_TYPES or not settings[f"{order_type}_enabled"]:
        raise OrderError("e_type")
    if not settings["accepting"]:
        raise OrderError("e_closed_full")

    scheduled_at = str(data.get("scheduled_at") or "").strip()
    if scheduled_at:
        if not hours.valid_slot(raw_settings, scheduled_at):
            raise OrderError("e_slot")
    elif not settings["is_open"]:
        raise OrderError("e_closed", next=settings["next_open"])

    name = str(data.get("name") or "").strip()
    address = str(data.get("address") or "").strip() if order_type == "delivery" else ""
    comment = str(data.get("comment") or "").strip()[:300]
    phone = normalize_phone(str(data.get("phone") or ""))
    payment = data.get("payment_method")

    if not 2 <= len(name) <= 64:
        raise OrderError("e_name")
    if not phone:
        raise OrderError("e_phone")
    if order_type == "delivery" and not 5 <= len(address) <= 300:
        raise OrderError("e_address")
    if payment == "card":
        raise OrderError("e_card")
    if payment != "cash":
        raise OrderError("e_payment")

    q = await quote(user_id, raw_items, order_type, str(data.get("promo_code") or "").strip(), lang)
    if q["min_order"] and q["subtotal"] < q["min_order"]:
        raise OrderError("e_min_order", min=q["min_order"])

    last = await db.scalar("SELECT MAX(created_at) FROM orders WHERE user_id = ?", user_id)
    if last:
        last_dt = datetime.strptime(last, "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)
        if now() - last_dt < timedelta(seconds=ORDER_COOLDOWN_SEC):
            raise OrderError("e_cooldown", 429)

    order_id = await db.create_order(
        user_id,
        {
            "name": name, "phone": phone, "address": address, "comment": comment, "payment_method": payment,
            "order_type": order_type, "scheduled_at": scheduled_at, "promo_code": q["promo_code"], "lang": lang,
        },
        q["items"],
        q["delivery_fee"],
        q["discount"],
    )
    await db.update_user_profile(user_id, name, phone, address or (await db.get_user(user_id) or {}).get("address") or "")
    return order_id
