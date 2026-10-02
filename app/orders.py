"""Buyurtma yaratish qoidalari — Mini App va bot ichidagi savat uchun umumiy."""
import re
from datetime import datetime, timedelta

from . import db
from .utils import TZ, money, now

ORDER_COOLDOWN_SEC = 20
PHONE_RE = re.compile(r"^\+998\d{9}$")


class OrderError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def normalize_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 9:
        digits = "998" + digits
    phone = "+" + digits
    return phone if PHONE_RE.match(phone) else None


def public_settings(s: dict) -> dict:
    return {
        "is_open": s.get("is_open") == "1",
        "delivery_fee": int(s.get("delivery_fee") or 0),
        "min_order": int(s.get("min_order") or 0),
        "phone": s.get("phone") or "",
        "work_hours": s.get("work_hours") or "",
    }


async def resolve_items(raw_items) -> list[dict]:
    """[{product_id, variant, qty}] -> narxlari bazadan olingan pozitsiyalar."""
    if not isinstance(raw_items, list) or not raw_items:
        raise OrderError("Savat bo'sh")
    if len(raw_items) > 30:
        raise OrderError("Savatda juda ko'p mahsulot")
    items = []
    for raw in raw_items:
        try:
            pid, vidx, qty = int(raw["product_id"]), int(raw.get("variant", 0)), int(raw["qty"])
        except (KeyError, TypeError, ValueError):
            raise OrderError("Savatda xato bor")
        if not 1 <= qty <= 50:
            raise OrderError("Mahsulot soni 1 dan 50 gacha bo'lishi kerak")
        product = await db.get_product(pid)
        cat = await db.get_category(product["category_id"]) if product else None
        if not product or not product["is_available"] or not cat or not cat["is_active"]:
            raise OrderError("Savatdagi ba'zi mahsulotlar endi mavjud emas. Savatni yangilang.", 409)
        if not 0 <= vidx < len(product["variants"]):
            raise OrderError("Mahsulot o'lchami topilmadi. Savatni yangilang.", 409)
        variant = product["variants"][vidx]
        items.append({
            "product_id": pid, "name": product["name"], "variant": variant["name"],
            "price": int(variant["price"]), "qty": qty,
        })
    return items


async def place_order(user_id: int, data: dict, raw_items) -> int:
    """Tekshiradi va buyurtma yaratadi. Xatoda OrderError ko'taradi. order_id qaytaradi."""
    settings = public_settings(await db.get_settings())
    if not settings["is_open"]:
        raise OrderError("Hozir buyurtma qabul qilinmayapti. Ish vaqti: " + settings["work_hours"])

    name = str(data.get("name") or "").strip()
    address = str(data.get("address") or "").strip()
    comment = str(data.get("comment") or "").strip()[:300]
    phone = normalize_phone(str(data.get("phone") or ""))
    payment = data.get("payment_method")

    if not 2 <= len(name) <= 64:
        raise OrderError("Qabul qiluvchi ismini kiriting")
    if not phone:
        raise OrderError("Telefon raqam noto'g'ri. Format: +998 90 123 45 67")
    if not 5 <= len(address) <= 300:
        raise OrderError("Manzilni to'liqroq kiriting")
    if payment == "card":
        raise OrderError("Karta orqali to'lov tez kunda ishga tushadi. Hozircha naqd to'lovni tanlang.")
    if payment != "cash":
        raise OrderError("To'lov usulini tanlang")

    items = await resolve_items(raw_items)
    subtotal = sum(i["price"] * i["qty"] for i in items)
    if subtotal < settings["min_order"]:
        raise OrderError(f"Minimal buyurtma summasi: {money(settings['min_order'])}")

    last = await db.scalar("SELECT MAX(created_at) FROM orders WHERE user_id = ?", user_id)
    if last:
        last_dt = datetime.strptime(last, "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)
        if now() - last_dt < timedelta(seconds=ORDER_COOLDOWN_SEC):
            raise OrderError("Iltimos, biroz kuting va qayta urinib ko'ring", 429)

    order_id = await db.create_order(
        user_id,
        {"name": name, "phone": phone, "address": address, "comment": comment, "payment_method": payment},
        items,
        settings["delivery_fee"],
    )
    await db.update_user_profile(user_id, name, phone, address)
    return order_id
