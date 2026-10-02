"""Mini app uchun HTTP server: statik fayllar + JSON API."""
import asyncio
import json
import logging
import re
import time
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.utils.web_app import safe_parse_webapp_init_data
from aiohttp import web

from . import db
from .config import config
from .notify import notify_new_order, refresh_staff_messages
from .utils import ACTIVE_STATUSES, STATUS_LABELS, STATUSES, TZ, now

log = logging.getLogger(__name__)

INIT_DATA_TTL = 24 * 3600
ORDER_COOLDOWN_SEC = 20
PHONE_RE = re.compile(r"^\+998\d{9}$")


def api_error(message: str, status: int = 400) -> web.Response:
    return web.json_response({"ok": False, "error": message}, status=status)


# ---------------- auth ----------------

@web.middleware
async def auth_middleware(request: web.Request, handler):
    if not request.path.startswith("/api/"):
        return await handler(request)
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    tg_user = None
    if init_data:
        try:
            data = safe_parse_webapp_init_data(config.bot_token, init_data)
            if time.time() - data.auth_date.timestamp() > INIT_DATA_TTL:
                return api_error("Sessiya eskirgan. Mini ilovani qayta oching.", 401)
            tg_user = data.user
        except ValueError:
            return api_error("Telegram ma'lumotlari tasdiqlanmadi", 401)
    elif config.debug and request.headers.get("X-Dev-User", "").isdigit():
        # Faqat DEBUG=1 da: brauzerda test qilish uchun
        uid = int(request.headers["X-Dev-User"])
        user, _ = await db.upsert_user(uid, "Test", None, None)
        request["user"] = user
        return await handler(request)
    if not tg_user:
        return api_error("Mini ilovani Telegram ichida oching", 401)
    # Mini app ochilganda ham akkaunt avtomatik yaratiladi
    user, _ = await db.upsert_user(tg_user.id, tg_user.first_name, tg_user.last_name, tg_user.username)
    request["user"] = user
    return await handler(request)


# ---------------- helpers ----------------

def normalize_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 9:
        digits = "998" + digits
    phone = "+" + digits
    return phone if PHONE_RE.match(phone) else None


async def order_json(order: dict) -> dict:
    items = await db.get_order_items(order["id"])
    log_rows = await db.get_order_log(order["id"])
    return {
        "id": order["id"],
        "code": order["code"],
        "status": order["status"],
        "status_label": STATUS_LABELS.get(order["status"]),
        "created_at": order["created_at"],
        "customer_name": order["customer_name"],
        "phone": order["phone"],
        "address": order["address"],
        "comment": order["comment"],
        "payment_method": order["payment_method"],
        "subtotal": order["subtotal"],
        "delivery_fee": order["delivery_fee"],
        "total": order["total"],
        "cancel_reason": order["cancel_reason"],
        "items": [
            {"name": i["name"], "variant": i["variant"], "price": i["price"], "qty": i["qty"]}
            for i in items
        ],
        "timeline": {r["status"]: r["at"] for r in log_rows},
    }


def public_settings(s: dict) -> dict:
    return {
        "is_open": s.get("is_open") == "1",
        "delivery_fee": int(s.get("delivery_fee") or 0),
        "min_order": int(s.get("min_order") or 0),
        "phone": s.get("phone") or "",
        "work_hours": s.get("work_hours") or "",
    }


# ---------------- API ----------------

async def api_menu(request: web.Request) -> web.Response:
    return web.json_response({
        "ok": True,
        "categories": await db.get_menu(),
        "settings": public_settings(await db.get_settings()),
    })


async def api_me(request: web.Request) -> web.Response:
    u = request["user"]
    return web.json_response({
        "ok": True,
        "user": {
            "id": u["id"],
            "first_name": u["first_name"],
            "full_name": u["full_name"] or "",
            "phone": u["phone"] or "",
            "address": u["address"] or "",
        },
    })


async def api_create_order(request: web.Request) -> web.Response:
    user = request["user"]
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return api_error("Noto'g'ri so'rov")
    if not isinstance(body, dict):
        return api_error("Noto'g'ri so'rov")

    settings = public_settings(await db.get_settings())
    if not settings["is_open"]:
        return api_error("Hozir buyurtma qabul qilinmayapti. Ish vaqti: " + settings["work_hours"])

    name = str(body.get("name") or "").strip()
    address = str(body.get("address") or "").strip()
    comment = str(body.get("comment") or "").strip()[:300]
    phone = normalize_phone(str(body.get("phone") or ""))
    payment = body.get("payment_method")

    if not 2 <= len(name) <= 64:
        return api_error("Qabul qiluvchi ismini kiriting")
    if not phone:
        return api_error("Telefon raqam noto'g'ri. Format: +998 90 123 45 67")
    if not 5 <= len(address) <= 300:
        return api_error("Manzilni to'liqroq kiriting")
    if payment == "card":
        return api_error("Karta orqali to'lov tez kunda ishga tushadi. Hozircha naqd to'lovni tanlang.")
    if payment != "cash":
        return api_error("To'lov usulini tanlang")

    raw_items = body.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        return api_error("Savat bo'sh")
    if len(raw_items) > 30:
        return api_error("Savatda juda ko'p mahsulot")

    items = []
    for raw in raw_items:
        try:
            pid, vidx, qty = int(raw["product_id"]), int(raw.get("variant", 0)), int(raw["qty"])
        except (KeyError, TypeError, ValueError):
            return api_error("Savatda xato bor")
        if not 1 <= qty <= 50:
            return api_error("Mahsulot soni 1 dan 50 gacha bo'lishi kerak")
        product = await db.get_product(pid)
        cat = await db.get_category(product["category_id"]) if product else None
        if not product or not product["is_available"] or not cat or not cat["is_active"]:
            return api_error("Savatdagi ba'zi mahsulotlar endi mavjud emas. Savatni yangilang.", 409)
        if not 0 <= vidx < len(product["variants"]):
            return api_error("Mahsulot o'lchami topilmadi. Savatni yangilang.", 409)
        variant = product["variants"][vidx]
        items.append({
            "product_id": pid, "name": product["name"], "variant": variant["name"],
            "price": int(variant["price"]), "qty": qty,
        })

    subtotal = sum(i["price"] * i["qty"] for i in items)
    if subtotal < settings["min_order"]:
        return api_error(f"Minimal buyurtma summasi: {settings['min_order']:,} so'm".replace(",", " "))

    last = await db.scalar("SELECT MAX(created_at) FROM orders WHERE user_id = ?", user["id"])
    if last:
        last_dt = datetime.strptime(last, "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)
        if now() - last_dt < timedelta(seconds=ORDER_COOLDOWN_SEC):
            return api_error("Iltimos, biroz kuting va qayta urinib ko'ring", 429)

    order_id = await db.create_order(
        user["id"],
        {"name": name, "phone": phone, "address": address, "comment": comment, "payment_method": payment},
        items,
        settings["delivery_fee"],
    )
    await db.update_user_profile(user["id"], name, phone, address)

    bot: Bot | None = request.app.get("bot")
    if bot:
        asyncio.create_task(notify_new_order(bot, order_id))

    return web.json_response({"ok": True, "order": await order_json(await db.get_order(order_id))})


async def api_orders(request: web.Request) -> web.Response:
    orders = await db.get_user_orders(request["user"]["id"], limit=30)
    return web.json_response({"ok": True, "orders": [await order_json(o) for o in orders]})


async def api_order(request: web.Request) -> web.Response:
    order = await db.get_order_by_code(request.match_info["code"])
    if not order or order["user_id"] != request["user"]["id"]:
        return api_error("Buyurtma topilmadi", 404)
    return web.json_response({"ok": True, "order": await order_json(order)})


async def api_cancel_order(request: web.Request) -> web.Response:
    """Mijoz faqat hali qabul qilinmagan (yangi) buyurtmani bekor qila oladi."""
    order = await db.get_order_by_code(request.match_info["code"])
    if not order or order["user_id"] != request["user"]["id"]:
        return api_error("Buyurtma topilmadi", 404)
    if order["status"] != "new":
        return api_error("Buyurtma allaqachon qabul qilingan — bekor qilish uchun kafe bilan bog'laning")
    await db.set_order_status(order["id"], "cancelled", request["user"]["id"], "Mijoz bekor qildi")
    bot: Bot | None = request.app.get("bot")
    if bot:
        asyncio.create_task(refresh_staff_messages(bot, order["id"]))
    return web.json_response({"ok": True, "order": await order_json(await db.get_order(order["id"]))})


# ---------------- static ----------------

async def index(request: web.Request) -> web.Response:
    html = (config.webapp_dir / "index.html").read_text(encoding="utf-8")
    html = html.replace("{{v}}", request.app["version"])
    return web.Response(text=html, content_type="text/html", headers={"Cache-Control": "no-cache"})


def static_file(name: str):
    async def handler(request: web.Request) -> web.FileResponse:
        return web.FileResponse(config.webapp_dir / name, headers={"Cache-Control": "no-cache"})
    return handler


async def health(request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "statuses": STATUSES, "active": list(ACTIVE_STATUSES)})


def create_app(bot: Bot | None) -> web.Application:
    app = web.Application(middlewares=[auth_middleware], client_max_size=1024 * 64)
    app["bot"] = bot
    app["version"] = str(int(time.time()))
    config.uploads_dir.mkdir(parents=True, exist_ok=True)
    app.router.add_get("/", index)
    app.router.add_get("/app.js", static_file("app.js"))
    app.router.add_get("/style.css", static_file("style.css"))
    app.router.add_get("/health", health)
    app.router.add_static("/img", config.webapp_dir / "img")
    app.router.add_static("/uploads", config.uploads_dir)
    app.router.add_get("/api/menu", api_menu)
    app.router.add_get("/api/me", api_me)
    app.router.add_get("/api/orders", api_orders)
    app.router.add_post("/api/orders", api_create_order)
    app.router.add_get("/api/orders/{code}", api_order)
    app.router.add_post("/api/orders/{code}/cancel", api_cancel_order)
    return app
