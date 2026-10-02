"""Mini app uchun HTTP server: statik fayllar + JSON API."""
import asyncio
import json
import logging
import time

from aiogram import Bot
from aiogram.utils.web_app import safe_parse_webapp_init_data
from aiohttp import web

from . import db, hours
from .catalog import norm_lang, variant_name
from .config import config
from .i18n import status_text, t, web_texts
from .notify import notify_new_order, notify_review, refresh_staff_messages
from .orders import OrderError, place_order, public_settings, quote
from .utils import ACTIVE_STATUSES, STATUSES

log = logging.getLogger(__name__)

INIT_DATA_TTL = 24 * 3600


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
    if not user.get("lang"):
        await db.set_lang(tg_user.id, norm_lang(tg_user.language_code))
        user = await db.get_user(tg_user.id)
    request["user"] = user
    return await handler(request)


# ---------------- helpers ----------------

def user_lang(request: web.Request) -> str:
    return norm_lang(request["user"].get("lang"))


def order_error(e: OrderError, request: web.Request) -> web.Response:
    return api_error(e.text(user_lang(request)), e.status)


async def order_json(order: dict, lang: str = "uz") -> dict:
    items = await db.get_order_items(order["id"])
    log_rows = await db.get_order_log(order["id"])
    review = await db.get_review(order["id"])
    names = {}
    if lang == "ru":
        for i in items:
            if i["product_id"] and i["product_id"] not in names:
                p = await db.fetchone("SELECT name_ru FROM products WHERE id = ?", i["product_id"])
                names[i["product_id"]] = (p or {}).get("name_ru") or ""
    otype = order.get("order_type") or "delivery"
    return {
        "id": order["id"],
        "code": order["code"],
        "status": order["status"],
        "status_label": status_text(order["status"], otype, lang),
        "order_type": otype,
        "scheduled_at": order.get("scheduled_at") or "",
        "promo_code": order.get("promo_code") or "",
        "discount": order.get("discount") or 0,
        "review": {"rating": review["rating"], "comment": review["comment"]} if review else None,
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
            {"name": names.get(i["product_id"]) or i["name"], "variant": variant_name(i["variant"], lang),
             "price": i["price"], "qty": i["qty"]}
            for i in items
        ],
        "timeline": {r["status"]: r["at"] for r in log_rows},
    }


# ---------------- API ----------------

async def api_menu(request: web.Request) -> web.Response:
    lang = user_lang(request)
    raw = await db.get_settings()
    return web.json_response({
        "ok": True,
        "lang": lang,
        "texts": web_texts(lang),
        "categories": await db.get_menu(lang),
        "settings": public_settings(raw),
        "slots": hours.slots(raw),
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
            "lang": user_lang(request),
        },
    })


async def _json_body(request: web.Request) -> dict | None:
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return body if isinstance(body, dict) else None


async def api_set_lang(request: web.Request) -> web.Response:
    body = await _json_body(request) or {}
    lang = norm_lang(body.get("lang"))
    await db.set_lang(request["user"]["id"], lang)
    return web.json_response({"ok": True, "lang": lang})


async def api_quote(request: web.Request) -> web.Response:
    """Savat summasini hisoblaydi va promo-kodni tekshiradi (rasmiylashtirishda jonli ko'rsatish uchun)."""
    body = await _json_body(request)
    if body is None:
        return api_error("Bad request")
    lang = user_lang(request)
    otype = body.get("order_type") if body.get("order_type") in ("delivery", "pickup") else "delivery"
    try:
        q = await quote(request["user"]["id"], body.get("items"), otype,
                        str(body.get("promo_code") or "").strip()[:32], lang)
    except OrderError as e:
        return order_error(e, request)
    q.pop("items")
    return web.json_response({"ok": True, "quote": q})


async def api_create_order(request: web.Request) -> web.Response:
    user = request["user"]
    body = await _json_body(request)
    if body is None:
        return api_error("Noto'g'ri so'rov")
    lang = user_lang(request)
    try:
        order_id = await place_order(user["id"], {**body, "lang": lang}, body.get("items"))
    except OrderError as e:
        return order_error(e, request)

    bot: Bot | None = request.app.get("bot")
    if bot:
        asyncio.create_task(notify_new_order(bot, order_id))

    return web.json_response({"ok": True, "order": await order_json(await db.get_order(order_id), lang)})


async def api_review(request: web.Request) -> web.Response:
    lang = user_lang(request)
    order = await db.get_order_by_code(request.match_info["code"])
    if not order or order["user_id"] != request["user"]["id"]:
        return api_error(t("order_not_found", lang), 404)
    if order["status"] != "delivered":
        return api_error(t("rate_not_ready", lang))
    body = await _json_body(request) or {}
    try:
        rating = int(body.get("rating"))
    except (TypeError, ValueError):
        rating = 0
    if not 1 <= rating <= 5:
        return api_error("1–5")
    if not await db.add_review(order["id"], order["user_id"], rating, str(body.get("comment") or "").strip()[:500]):
        return api_error(t("already_rated", lang))
    bot: Bot | None = request.app.get("bot")
    if bot:
        asyncio.create_task(notify_review(bot, order["id"]))
    return web.json_response({"ok": True, "order": await order_json(order, lang)})


async def api_orders(request: web.Request) -> web.Response:
    orders = await db.get_user_orders(request["user"]["id"], limit=30)
    lang = user_lang(request)
    return web.json_response({"ok": True, "orders": [await order_json(o, lang) for o in orders]})


async def api_order(request: web.Request) -> web.Response:
    order = await db.get_order_by_code(request.match_info["code"])
    if not order or order["user_id"] != request["user"]["id"]:
        return api_error(t("order_not_found", user_lang(request)), 404)
    return web.json_response({"ok": True, "order": await order_json(order, user_lang(request))})


async def api_cancel_order(request: web.Request) -> web.Response:
    """Mijoz faqat hali qabul qilinmagan (yangi) buyurtmani bekor qila oladi."""
    lang = user_lang(request)
    order = await db.get_order_by_code(request.match_info["code"])
    if not order or order["user_id"] != request["user"]["id"]:
        return api_error(t("order_not_found", lang), 404)
    if order["status"] != "new":
        return api_error(t("cancel_not_allowed", lang))
    await db.set_order_status(order["id"], "cancelled", request["user"]["id"], "Mijoz bekor qildi")
    bot: Bot | None = request.app.get("bot")
    if bot:
        asyncio.create_task(refresh_staff_messages(bot, order["id"]))
    return web.json_response({"ok": True, "order": await order_json(await db.get_order(order["id"]), lang)})


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
    app.router.add_get("/config.js", static_file("config.js"))
    app.router.add_get("/health", health)
    app.router.add_static("/img", config.webapp_dir / "img")
    app.router.add_static("/uploads", config.uploads_dir)
    app.router.add_get("/api/menu", api_menu)
    app.router.add_get("/api/me", api_me)
    app.router.add_post("/api/me/lang", api_set_lang)
    app.router.add_post("/api/quote", api_quote)
    app.router.add_get("/api/orders", api_orders)
    app.router.add_post("/api/orders", api_create_order)
    app.router.add_get("/api/orders/{code}", api_order)
    app.router.add_post("/api/orders/{code}/cancel", api_cancel_order)
    app.router.add_post("/api/orders/{code}/review", api_review)
    return app
