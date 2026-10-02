"""Admin web panel API (/api/admin/*). Faqat menejerlar uchun.

Kirish: bot bergan bir martalik havola kodi -> sessiya tokeni (X-Admin-Token),
yoki panel Telegram ichida ochilsa — Telegram initData (menejer bo'lsa).
Barcha o'zgarishlar bazaga yoziladi va bot darhol shu ma'lumotlardan foydalanadi.
"""
import asyncio
import csv
import io
import json
import logging
import re
import time
import uuid
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.web_app import safe_parse_webapp_init_data
from aiohttp import web

from . import db, hours
from .backup import make_backup
from .catalog import BADGES, badges_of, discount_active, variant_price
from .config import config
from .i18n import OVERRIDES
from .notify import delete_order, notify_status_change
from .orders import public_settings
from .roles import get_role
from .texts_admin import catalog, validate
from .utils import (
    ACTIVE_STATUSES, PAYMENT_LABELS, TYPE_LABELS, next_status, now, now_str, status_label,
)

log = logging.getLogger(__name__)
SESSION_MINUTES = 14 * 24 * 60
LOGIN_CODE_MINUTES = 15


def err(message: str, status: int = 400) -> web.Response:
    return web.json_response({"ok": False, "error": message}, status=status)


def ok(**data) -> web.Response:
    return web.json_response({"ok": True, **data})


async def _body(request: web.Request) -> dict:
    try:
        data = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise web.HTTPBadRequest(text=json.dumps({"ok": False, "error": "JSON kutilgan"}),
                                 content_type="application/json")
    if not isinstance(data, dict):
        raise web.HTTPBadRequest(text=json.dumps({"ok": False, "error": "JSON obyekt kutilgan"}),
                                 content_type="application/json")
    return data


# ====================== kirish ======================

async def _admin_user(request: web.Request) -> int | None:
    token = request.headers.get("X-Admin-Token", "")
    uid = None
    if token:
        uid = await db.check_admin_token(token, "session")
    elif request.headers.get("X-Telegram-Init-Data"):
        try:
            data = safe_parse_webapp_init_data(config.bot_token, request.headers["X-Telegram-Init-Data"])
            if time.time() - data.auth_date.timestamp() < 24 * 3600:
                uid = data.user.id
        except ValueError:
            uid = None
    elif config.debug and request.headers.get("X-Dev-User", "").isdigit():
        uid = int(request.headers["X-Dev-User"])
    if uid and await get_role(uid) == "manager":
        return uid
    return None


def admin_only(handler):
    async def wrapper(request: web.Request):
        uid = await _admin_user(request)
        if not uid:
            return err("Kirish huquqi yo'q. Botda «🖥 Web panel» tugmasini bosing.", 401)
        request["admin_id"] = uid
        return await handler(request)
    return wrapper


async def make_login_link(user_id: int) -> str:
    code = await db.create_admin_token(user_id, "login", LOGIN_CODE_MINUTES)
    base = config.admin_url or f"{config.webapp_url}/admin"
    return f"{base}/#code={code}"


async def login(request: web.Request) -> web.Response:
    data = await _body(request)
    uid = await db.check_admin_token(str(data.get("code") or ""), "login", consume=True)
    if not uid or await get_role(uid) != "manager":
        return err("Havola eskirgan yoki noto'g'ri. Botdan yangi havola oling.", 401)
    token = await db.create_admin_token(uid, "session", SESSION_MINUTES)
    return ok(token=token, user=await _user_info(uid))


async def logout(request: web.Request) -> web.Response:
    token = request.headers.get("X-Admin-Token", "")
    if token:
        await db.delete_admin_token(token)
    return ok()


async def _user_info(uid: int) -> dict:
    u = await db.get_user(uid) or {}
    return {"id": uid, "name": u.get("full_name") or u.get("first_name") or str(uid), "username": u.get("username")}


@admin_only
async def me(request: web.Request) -> web.Response:
    return ok(user=await _user_info(request["admin_id"]), bot_username=request.app.get("bot_username", ""))


# ====================== dashboard ======================

def _since(period: str) -> str | None:
    n = now()
    days = {"today": 0, "week": 6, "month": 29}.get(period)
    if days is None:
        return None
    return (n - timedelta(days=days)).strftime("%Y-%m-%d 00:00:00")


@admin_only
async def dashboard(request: web.Request) -> web.Response:
    period = request.query.get("period", "today")
    since = _since(period)
    stats = await db.stats(since)
    raw = await db.get_settings()
    return ok(
        period=period,
        stats=stats,
        staff=await db.staff_stats(since),
        daily=await db.daily_revenue(30 if period in ("month", "all") else 7),
        active_orders=len(await db.get_active_orders()),
        status=public_settings(raw),
    )


# ====================== menyu ======================

def _product_json(p: dict) -> dict:
    return {
        "id": p["id"], "category_id": p["category_id"], "name": p["name"], "name_ru": p.get("name_ru") or "",
        "description": p.get("description") or "", "description_ru": p.get("description_ru") or "",
        "image": p.get("image") or "", "variants": p["variants"], "badges": badges_of(p),
        "discount_percent": p.get("discount_percent") or 0, "discount_until": p.get("discount_until") or "",
        "discount_active": discount_active(p), "is_available": bool(p["is_available"]), "sort": p["sort"],
        "prices_now": [variant_price(p, i)[0] for i in range(len(p["variants"]))],
    }


@admin_only
async def menu(request: web.Request) -> web.Response:
    cats = await db.get_categories()
    products = await db.get_products()
    return ok(
        categories=[{**c, "is_active": bool(c["is_active"])} for c in cats],
        products=[_product_json(p) for p in products],
        badges={k: v["uz"] for k, v in BADGES.items()},
    )


def _str(data: dict, key: str, limit: int, required: bool = False) -> str:
    value = str(data.get(key) or "").strip()
    if required and not value:
        raise ValueError(f"«{key}» maydoni majburiy")
    if len(value) > limit:
        raise ValueError(f"«{key}» juda uzun (maks. {limit})")
    return value


@admin_only
async def category_create(request: web.Request) -> web.Response:
    data = await _body(request)
    try:
        name = _str(data, "name", 40, True)
        emoji = _str(data, "emoji", 8)
        name_ru = _str(data, "name_ru", 40)
    except ValueError as e:
        return err(str(e))
    cid = await db.add_category(name, emoji)
    await db.execute("UPDATE categories SET name_ru = ? WHERE id = ?", name_ru, cid)
    return ok(category=await db.get_category(cid))


@admin_only
async def category_update(request: web.Request) -> web.Response:
    cid = int(request.match_info["id"])
    if not await db.get_category(cid):
        return err("Kategoriya topilmadi", 404)
    data = await _body(request)
    try:
        fields = {}
        if "name" in data:
            fields["name"] = _str(data, "name", 40, True)
        if "name_ru" in data:
            fields["name_ru"] = _str(data, "name_ru", 40)
        if "emoji" in data:
            fields["emoji"] = _str(data, "emoji", 8)
        if "is_active" in data:
            fields["is_active"] = 1 if data["is_active"] else 0
    except ValueError as e:
        return err(str(e))
    for k, v in fields.items():
        await db.execute(f"UPDATE categories SET {k} = ? WHERE id = ?", v, cid)
    return ok(category=await db.get_category(cid))


@admin_only
async def category_delete(request: web.Request) -> web.Response:
    cid = int(request.match_info["id"])
    if await db.get_products(cid):
        return err("Kategoriyada mahsulotlar bor. Avval ularni ko'chiring yoki o'chiring (yoki kategoriyani yashiring).")
    await db.execute("DELETE FROM products WHERE category_id = ? AND is_deleted = 1", cid)
    await db.execute("DELETE FROM categories WHERE id = ?", cid)
    return ok()


@admin_only
async def category_order(request: web.Request) -> web.Response:
    ids = (await _body(request)).get("ids") or []
    for pos, cid in enumerate(ids):
        await db.db().execute("UPDATE categories SET sort = ? WHERE id = ?", (pos, int(cid)))
    await db.db().commit()
    return ok()


def _parse_product(data: dict, partial: bool) -> dict:
    fields = {}
    if "name" in data or not partial:
        fields["name"] = _str(data, "name", 60, True)
    for key, limit in (("name_ru", 60), ("description", 500), ("description_ru", 500)):
        if key in data:
            fields[key] = _str(data, key, limit)
    if "category_id" in data or not partial:
        fields["category_id"] = int(data.get("category_id") or 0)
    if "variants" in data or not partial:
        variants = data.get("variants") or []
        if not isinstance(variants, list) or not 1 <= len(variants) <= 6:
            raise ValueError("Narx(lar): 1 dan 6 tagacha o'lcham bo'lishi kerak")
        clean = []
        for v in variants:
            name = str(v.get("name") or "").strip()[:30]
            try:
                price = int(v.get("price"))
            except (TypeError, ValueError):
                raise ValueError("Narx raqam bo'lishi kerak")
            if not 100 <= price <= 10_000_000:
                raise ValueError("Narx 100 dan 10 000 000 so'mgacha bo'lishi kerak")
            clean.append({"name": name, "price": price})
        if len(clean) > 1 and any(not v["name"] for v in clean):
            raise ValueError("Bir nechta o'lcham bo'lsa, har biriga nom bering (masalan O'rta, Katta)")
        fields["variants"] = clean
    if "badges" in data:
        badges = [b for b in (data.get("badges") or []) if b in BADGES]
        fields["badges"] = ",".join(dict.fromkeys(badges))
    if "discount_percent" in data:
        pct = int(data.get("discount_percent") or 0)
        if not 0 <= pct <= 95:
            raise ValueError("Chegirma 0–95% oralig'ida bo'lsin")
        fields["discount_percent"] = pct
    if "discount_until" in data:
        until = str(data.get("discount_until") or "").strip()
        if until:
            try:
                dt = datetime.strptime(until[:10], "%Y-%m-%d")
            except ValueError:
                raise ValueError("Chegirma tugash sanasi noto'g'ri")
            until = dt.strftime("%Y-%m-%d 23:59:59")
        fields["discount_until"] = until
    if "is_available" in data:
        fields["is_available"] = 1 if data["is_available"] else 0
    if "image" in data:
        image = str(data.get("image") or "")
        if image and not re.match(r"^(uploads/[\w.-]+|img/products/[\w.-]+)$", image):
            raise ValueError("Rasm manzili noto'g'ri")
        fields["image"] = image
    return fields


@admin_only
async def product_create(request: web.Request) -> web.Response:
    data = await _body(request)
    try:
        fields = _parse_product(data, partial=False)
    except (ValueError, TypeError) as e:
        return err(str(e))
    if not await db.get_category(fields["category_id"]):
        return err("Kategoriyani tanlang")
    pid = await db.add_product(fields.pop("category_id"), fields.pop("name"), fields.pop("description", ""),
                               fields.pop("image", ""), fields.pop("variants"))
    if fields:
        await db.update_product(pid, **fields)
    return ok(product=_product_json(await db.get_product(pid)))


@admin_only
async def product_update(request: web.Request) -> web.Response:
    pid = int(request.match_info["id"])
    if not await db.get_product(pid):
        return err("Mahsulot topilmadi", 404)
    data = await _body(request)
    try:
        fields = _parse_product(data, partial=True)
    except (ValueError, TypeError) as e:
        return err(str(e))
    if "category_id" in fields and not await db.get_category(fields["category_id"]):
        return err("Kategoriya topilmadi")
    if fields:
        await db.update_product(pid, **fields)
    return ok(product=_product_json(await db.get_product(pid)))


@admin_only
async def product_delete(request: web.Request) -> web.Response:
    pid = int(request.match_info["id"])
    await db.update_product(pid, is_deleted=1)
    return ok()


@admin_only
async def product_order(request: web.Request) -> web.Response:
    ids = (await _body(request)).get("ids") or []
    for pos, pid in enumerate(ids):
        await db.db().execute("UPDATE products SET sort = ? WHERE id = ?", (pos, int(pid)))
    await db.db().commit()
    return ok()


# ====================== rasm yuklash ======================

MAX_UPLOAD = 10 * 1024 * 1024
TARGET = (1200, 900)  # 4:3


def process_image(raw: bytes) -> tuple[bytes, dict]:
    """Rasmni 4:3 nisbatga markazdan kesadi, 1200×900 gacha kichraytiradi, JPG qiladi."""
    from PIL import Image, ImageOps

    img = Image.open(io.BytesIO(raw))
    img = ImageOps.exif_transpose(img)
    ow, oh = img.size
    warnings = []
    if img.mode not in ("RGB", "L"):
        bg = Image.new("RGB", img.size, (12, 30, 20))  # shaffof fon -> brend to'q yashil
        bg.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[-1])
        img = bg
    img = img.convert("RGB")
    ratio = ow / oh
    if abs(ratio - 4 / 3) > 0.04:
        warnings.append(f"Rasm nisbati {ow}×{oh} — 4:3 ga markazdan kesildi. Mahsulot markazda bo'lsin.")
        img = ImageOps.fit(img, (max(4, min(ow, int(oh * 4 / 3))), max(3, min(oh, int(ow * 3 / 4)))),
                           method=Image.LANCZOS)
    if img.width > TARGET[0]:
        img = img.resize(TARGET, Image.LANCZOS)
    if ow < 800 or oh < 600:
        warnings.append(f"Rasm kichik ({ow}×{oh}). Sifatli ko'rinishi uchun kamida 1200×900 tavsiya qilinadi.")
    out = io.BytesIO()
    img.save(out, "JPEG", quality=86, optimize=True, progressive=True)
    return out.getvalue(), {"width": img.width, "height": img.height, "original": [ow, oh], "warnings": warnings}


@admin_only
async def upload(request: web.Request) -> web.Response:
    reader = await request.multipart()
    field = await reader.next()
    while field is not None and field.name != "file":
        field = await reader.next()
    if field is None:
        return err("Fayl topilmadi")
    raw = await field.read(decode=False)
    if len(raw) > MAX_UPLOAD:
        return err("Fayl juda katta (maks. 10 MB)")
    try:
        data, info = await asyncio.to_thread(process_image, raw)
    except Exception:
        return err("Rasmni o'qib bo'lmadi. JPG, PNG yoki WebP yuklang.")
    config.uploads_dir.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex[:16]}.jpg"
    (config.uploads_dir / name).write_bytes(data)
    return ok(path=f"uploads/{name}", size=len(data), **info)


# ====================== matnlar ======================

@admin_only
async def texts(request: web.Request) -> web.Response:
    return ok(texts=catalog(dict(OVERRIDES)))


@admin_only
async def text_save(request: web.Request) -> web.Response:
    data = await _body(request)
    key, lang = str(data.get("key") or ""), str(data.get("lang") or "")
    value = str(data.get("value") or "")
    if lang not in ("uz", "ru"):
        return err("Til noto'g'ri")
    if value.strip():
        problems = validate(key, lang, value)
        if problems:
            return err("; ".join(problems))
        await db.set_text(key, lang, value)
    else:
        await db.set_text(key, lang, None)  # asl matnga qaytarish
    return ok()


# ====================== sozlamalar ======================

SETTINGS_KEYS = ("mode", "schedule", "delivery_fee", "min_order", "phone", "cafe_address", "delivery_enabled",
                 "pickup_enabled", "prep_time", "slot_step")


async def _settings_payload() -> web.Response:
    raw = await db.get_settings()
    return ok(settings={
        "mode": raw.get("mode") or "auto",
        "schedule": hours.load_schedule(raw),
        "delivery_fee": int(raw.get("delivery_fee") or 0),
        "min_order": int(raw.get("min_order") or 0),
        "phone": raw.get("phone") or "",
        "cafe_address": raw.get("cafe_address") or "",
        "delivery_enabled": raw.get("delivery_enabled", "1") == "1",
        "pickup_enabled": raw.get("pickup_enabled", "1") == "1",
        "prep_time": int(raw.get("prep_time") or 40),
        "slot_step": int(raw.get("slot_step") or 30),
    }, status=public_settings(raw))


@admin_only
async def settings_get(request: web.Request) -> web.Response:
    return await _settings_payload()


@admin_only
async def settings_save(request: web.Request) -> web.Response:
    data = await _body(request)
    updates: dict[str, str] = {}
    try:
        if "mode" in data:
            if data["mode"] not in ("auto", "open", "closed"):
                raise ValueError("Rejim noto'g'ri")
            updates["mode"] = data["mode"]
        if "schedule" in data:
            sch = data["schedule"] or {}
            clean = {}
            for d in hours.DAYS:
                v = sch.get(d)
                if not v:
                    clean[d] = None
                    continue
                o, c = hours.parse_hhmm(str(v[0])), hours.parse_hhmm(str(v[1]))
                if not o or not c or o == c:
                    raise ValueError(f"{d}: vaqt noto'g'ri")
                clean[d] = [f"{o[0]:02d}:{o[1]:02d}", f"{c[0] % 24:02d}:{c[1]:02d}"]
            updates["schedule"] = json.dumps(clean)
        for key, lo, hi in (("delivery_fee", 0, 1_000_000), ("min_order", 0, 10_000_000),
                            ("prep_time", 10, 600), ("slot_step", 10, 120)):
            if key in data:
                v = int(data[key])
                if not lo <= v <= hi:
                    raise ValueError(f"{key}: {lo}–{hi} oralig'ida bo'lsin")
                updates[key] = str(v)
        for key, limit in (("phone", 40), ("cafe_address", 200)):
            if key in data:
                updates[key] = _str(data, key, limit)
        for key in ("delivery_enabled", "pickup_enabled"):
            if key in data:
                updates[key] = "1" if data[key] else "0"
    except (ValueError, TypeError) as e:
        return err(str(e))
    current = await db.get_settings()
    merged = {**current, **updates}
    if merged.get("delivery_enabled", "1") != "1" and merged.get("pickup_enabled", "1") != "1":
        return err("Yetkazib berish yoki olib ketishdan kamida bittasi yoqilgan bo'lishi kerak")
    for k, v in updates.items():
        await db.set_setting(k, v)
    return await _settings_payload()


# ====================== promo-kodlar ======================

def _parse_promo(data: dict, partial: bool) -> dict:
    fields = {}
    if "code" in data or not partial:
        code = str(data.get("code") or "").strip().upper()
        if not re.match(r"^[A-Z0-9_-]{3,20}$", code):
            raise ValueError("Kod: lotin harflari, raqamlar, «-» va «_» (3–20 belgi)")
        fields["code"] = code
    if "kind" in data or not partial:
        if data.get("kind") not in ("percent", "fixed", "free_delivery"):
            raise ValueError("Chegirma turini tanlang")
        fields["kind"] = data["kind"]
    for key in ("value", "min_order", "max_discount", "usage_limit", "per_user_limit"):
        if key in data:
            v = int(data.get(key) or 0)
            if v < 0:
                raise ValueError(f"{key} manfiy bo'lmasin")
            fields[key] = v
    for key in ("first_order_only", "is_active"):
        if key in data:
            fields[key] = 1 if data[key] else 0
    for key in ("starts_at", "ends_at"):
        if key in data:
            v = str(data.get(key) or "").strip().replace("T", " ")
            if v:
                try:
                    dt = datetime.strptime(v[:16], "%Y-%m-%d %H:%M") if len(v) > 10 else \
                        datetime.strptime(v, "%Y-%m-%d").replace(hour=23 if key == "ends_at" else 0,
                                                                  minute=59 if key == "ends_at" else 0)
                except ValueError:
                    raise ValueError("Sana noto'g'ri")
                v = dt.strftime("%Y-%m-%d %H:%M:00")
            fields[key] = v
    return fields


@admin_only
async def promos(request: web.Request) -> web.Response:
    return ok(promos=await db.get_promos())


@admin_only
async def promo_create(request: web.Request) -> web.Response:
    data = await _body(request)
    try:
        fields = _parse_promo(data, partial=False)
    except (ValueError, TypeError) as e:
        return err(str(e))
    if fields["kind"] != "free_delivery" and not fields.get("value"):
        return err("Chegirma qiymatini kiriting")
    if fields["kind"] == "percent" and fields.get("value", 0) > 100:
        return err("Foiz 1–100 oralig'ida bo'lsin")
    if await db.get_promo_by_code(fields["code"]):
        return err("Bunday kod allaqachon bor")
    fields.setdefault("per_user_limit", 1)
    pid = await db.add_promo(**fields)
    return ok(promo=await db.get_promo(pid))


@admin_only
async def promo_update(request: web.Request) -> web.Response:
    pid = int(request.match_info["id"])
    promo = await db.get_promo(pid)
    if not promo:
        return err("Topilmadi", 404)
    data = await _body(request)
    try:
        fields = _parse_promo(data, partial=True)
    except (ValueError, TypeError) as e:
        return err(str(e))
    if "code" in fields and fields["code"] != promo["code"] and await db.get_promo_by_code(fields["code"]):
        return err("Bunday kod allaqachon bor")
    kind = fields.get("kind", promo["kind"])
    if kind == "percent" and fields.get("value", promo["value"]) > 100:
        return err("Foiz 1–100 oralig'ida bo'lsin")
    await db.update_promo(pid, **fields)
    return ok(promo=await db.get_promo(pid))


@admin_only
async def promo_delete(request: web.Request) -> web.Response:
    await db.delete_promo(int(request.match_info["id"]))
    return ok()


# ====================== buyurtmalar ======================

def _order_row(o: dict) -> dict:
    return {
        **o,
        "status_label": status_label(o["status"], o["order_type"]),
        "type_label": TYPE_LABELS.get(o["order_type"], ""),
        "payment_label": PAYMENT_LABELS.get(o["payment_method"], ""),
        "next": next_status(o["status"], o["order_type"]),
    }


@admin_only
async def orders(request: web.Request) -> web.Response:
    kind = request.query.get("status", "active")
    q = request.query.get("q", "").strip()
    sql = db.ORDER_SELECT + " WHERE 1=1"
    args: list = []
    if kind == "active":
        sql += f" AND o.status IN ({','.join('?' * len(ACTIVE_STATUSES))})"
        args += list(ACTIVE_STATUSES)
    elif kind in ("delivered", "cancelled", "new"):
        sql += " AND o.status = ?"
        args.append(kind)
    if q:
        sql += " AND (o.code LIKE ? OR o.phone LIKE ? OR o.customer_name LIKE ?)"
        like = f"%{q.upper() if q.upper().startswith('YG') else q}%"
        args += [like, f"%{re.sub(r'[^0-9]', '', q) or q}%", f"%{q}%"]
    rows = await db.fetchall(sql + " ORDER BY o.id DESC LIMIT 200", *args)
    return ok(orders=[_order_row(o) for o in rows])


@admin_only
async def order_detail(request: web.Request) -> web.Response:
    order = await db.get_order(int(request.match_info["id"]))
    if not order:
        return err("Topilmadi", 404)
    return ok(order=_order_row(order), items=await db.get_order_items(order["id"]),
              log=await db.get_order_log(order["id"]), review=await db.get_review(order["id"]))


@admin_only
async def order_status(request: web.Request) -> web.Response:
    order = await db.get_order(int(request.match_info["id"]))
    if not order:
        return err("Topilmadi", 404)
    data = await _body(request)
    new = data.get("status")
    if new == "cancelled":
        if order["status"] not in ACTIVE_STATUSES:
            return err("Bu buyurtmani bekor qilib bo'lmaydi")
        await db.set_order_status(order["id"], "cancelled", request["admin_id"],
                                  str(data.get("reason") or "Kafe tomonidan bekor qilindi")[:200])
    else:
        step = next_status(order["status"], order["order_type"])
        if not step or step[0] != new:
            return err("Holat allaqachon o'zgargan. Sahifani yangilang.", 409)
        await db.set_order_status(order["id"], new, request["admin_id"])
    bot: Bot | None = request.app.get("bot")
    if bot:
        asyncio.create_task(notify_status_change(bot, order["id"]))
    return ok(order=_order_row(await db.get_order(order["id"])))


@admin_only
async def order_delete(request: web.Request) -> web.Response:
    order = await db.get_order(int(request.match_info["id"]))
    if not order:
        return err("Topilmadi", 404)
    await delete_order(request.app.get("bot"), order)
    log.info("Buyurtma %s o'chirildi (menejer %s)", order["code"], request["admin_id"])
    return ok()


# ====================== baholar, mijozlar, xodimlar ======================

@admin_only
async def reviews(request: web.Request) -> web.Response:
    low = request.query.get("low") == "1"
    since = (now() - timedelta(days=29)).strftime("%Y-%m-%d 00:00:00")
    return ok(reviews=await db.get_reviews(100, 3 if low else None),
              total=await db.review_stats(), month=await db.review_stats(since))


@admin_only
async def customers(request: web.Request) -> web.Response:
    q = request.query.get("q", "").strip().lstrip("@")
    sql = ("SELECT u.id, u.first_name, u.username, u.full_name, u.phone, u.address, u.lang, u.role, u.is_blocked,"
           " u.created_at, COUNT(o.id) AS orders, COALESCE(SUM(CASE WHEN o.status='delivered' THEN o.total END), 0)"
           " AS spent FROM users u LEFT JOIN orders o ON o.user_id = u.id")
    args: list = []
    if q:
        sql += " WHERE CAST(u.id AS TEXT) = ? OR lower(u.username) = lower(?) OR u.phone LIKE ? OR u.full_name LIKE ?" \
               " OR u.first_name LIKE ?"
        args = [q, q, f"%{re.sub(r'[^0-9]', '', q) or q}%", f"%{q}%", f"%{q}%"]
    rows = await db.fetchall(sql + " GROUP BY u.id ORDER BY spent DESC, u.id DESC LIMIT 100", *args)
    total = await db.scalar("SELECT COUNT(*) FROM users")
    return ok(customers=rows, total=total)


@admin_only
async def staff(request: web.Request) -> web.Response:
    rows = await db.get_staff()
    return ok(staff=rows, admins=sorted(config.admin_ids))


@admin_only
async def staff_add(request: web.Request) -> web.Response:
    data = await _body(request)
    role = data.get("role")
    if role not in ("staff", "manager"):
        return err("Rolni tanlang")
    query = str(data.get("query") or "").strip()
    user = await db.find_user(query)
    if not user and query.isdigit():
        await db.upsert_user(int(query), "", None, None)
        user = await db.get_user(int(query))
    if not user:
        return err("Foydalanuvchi topilmadi. U avval botga /start bosishi kerak yoki Telegram ID kiriting.")
    await db.set_role(user["id"], role)
    bot: Bot | None = request.app.get("bot")
    if bot:
        try:
            await bot.send_message(user["id"], f"🎉 Sizga <b>Yaproq go'sht</b> botida "
                                   f"{'👷 Xodim' if role == 'staff' else '👑 Menejer'} huquqi berildi! /start bosing.")
        except Exception:
            pass
    return ok()


@admin_only
async def staff_remove(request: web.Request) -> web.Response:
    uid = int(request.match_info["id"])
    if uid == request["admin_id"]:
        return err("O'zingizni olib tashlay olmaysiz")
    await db.set_role(uid, "user")
    return ok()


# ====================== rassilka ======================

BROADCAST: dict = {"running": False, "sent": 0, "failed": 0, "total": 0, "finished_at": None}


def _bc_markup(buttons: list, order_btn: bool) -> InlineKeyboardMarkup | None:
    rows = []
    for b in buttons or []:
        text, url = str(b.get("text") or "").strip()[:40], str(b.get("url") or "").strip()
        if text and re.match(r"^(https?|tg)://\S+$", url):
            rows.append([InlineKeyboardButton(text=text, url=url)])
    if order_btn:
        rows.append([InlineKeyboardButton(text="📋 Buyurtma berish", callback_data="sh:cats")])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


async def _bc_send(bot: Bot, chat_id: int, text: str, photo, markup) -> str | None:
    """Bitta xabar. Rasm bo'lsa file_id qaytaradi (keyingilariga qayta yuklamaslik uchun)."""
    if photo is not None:
        msg = await bot.send_photo(chat_id, photo, caption=text or None, reply_markup=markup)
        return msg.photo[-1].file_id
    await bot.send_message(chat_id, text, reply_markup=markup)
    return None


@admin_only
async def broadcast(request: web.Request) -> web.Response:
    bot: Bot | None = request.app.get("bot")
    if not bot:
        return err("Bot ulanmagan")
    if BROADCAST["running"]:
        return err("Rassilka hali davom etmoqda")
    reader = await request.multipart()
    form, photo_bytes = {}, None
    while (part := await reader.next()) is not None:
        if part.name == "photo" and part.filename:
            photo_bytes = await part.read(decode=False)
        else:
            form[part.name] = (await part.read(decode=True)).decode()
    text = form.get("text", "").strip()
    if not text and not photo_bytes:
        return err("Matn yoki rasm kerak")
    problems = []
    if text:
        from .texts_admin import _Checker

        checker = _Checker()
        checker.feed(text)
        checker.close()
        problems = checker.errors + ([f"Yopilmagan teg: <{checker.stack[-1]}>"] if checker.stack else [])
    if len(text) > (1024 if photo_bytes else 4000):
        problems.append("Matn juda uzun" + (" (rasm bilan — 1024 belgigacha)" if photo_bytes else ""))
    if problems:
        return err("; ".join(problems))
    markup = _bc_markup(json.loads(form.get("buttons") or "[]"), form.get("order_btn") == "1")
    photo = BufferedInputFile(photo_bytes, "post.jpg") if photo_bytes else None

    if form.get("test") == "1":
        try:
            await _bc_send(bot, request["admin_id"], text, photo, markup)
        except TelegramBadRequest as e:
            return err(f"Telegram xatosi: {e.message}")
        return ok(test=True)

    user_ids = await db.all_user_ids()
    BROADCAST.update(running=True, sent=0, failed=0, total=len(user_ids), finished_at=None)

    async def run():
        file = photo
        try:
            for uid in user_ids:
                for attempt in range(2):
                    try:
                        fid = await _bc_send(bot, uid, text, file, markup)
                        if fid:
                            file = fid
                        BROADCAST["sent"] += 1
                    except TelegramRetryAfter as e:
                        if attempt == 0:
                            await asyncio.sleep(e.retry_after + 1)
                            continue
                        BROADCAST["failed"] += 1
                    except TelegramForbiddenError:
                        await db.set_blocked(uid, True)
                        BROADCAST["failed"] += 1
                    except Exception as e:  # noqa: BLE001
                        log.warning("Broadcast %s: %s", uid, e)
                        BROADCAST["failed"] += 1
                    break
                await asyncio.sleep(0.05)
        finally:
            BROADCAST.update(running=False, finished_at=now_str())

    asyncio.create_task(run())
    return ok(total=len(user_ids))


@admin_only
async def broadcast_status(request: web.Request) -> web.Response:
    return ok(**BROADCAST, users=len(await db.all_user_ids()))


# ====================== hisobot va zaxira ======================

@admin_only
async def export_csv(request: web.Request) -> web.Response:
    period = request.query.get("period", "month")
    rows = await db.all_orders_for_export(_since(period))
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Buyurtma ID", "Sana", "Turi", "Vaqtga", "Holat", "Mijoz", "Telefon", "Manzil", "Mahsulotlar",
                "Summa", "Promo-kod", "Chegirma", "Yetkazish", "Jami", "To'lov", "Xodim", "Izoh"])
    for o in rows:
        w.writerow([
            o["code"], o["created_at"], TYPE_LABELS.get(o["order_type"], "").split(" ", 1)[-1], o["scheduled_at"],
            status_label(o["status"], o["order_type"]).split(" ", 1)[-1], o["customer_name"], o["phone"],
            o["address"], o["items"], o["subtotal"], o["promo_code"], o["discount"], o["delivery_fee"], o["total"],
            PAYMENT_LABELS.get(o["payment_method"], ""), o["staff_name"] or "", o["comment"] or "",
        ])
    name = f"buyurtmalar_{period}_{now().strftime('%Y%m%d_%H%M')}.csv"
    return web.Response(body=("﻿" + buf.getvalue()).encode(), content_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})


@admin_only
async def backup(request: web.Request) -> web.Response:
    data, name = await make_backup()
    return web.Response(body=data, content_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ====================== marshrutlar ======================

def setup(app: web.Application) -> None:
    r = app.router
    r.add_post("/api/admin/login", login)
    r.add_post("/api/admin/logout", logout)
    r.add_get("/api/admin/me", me)
    r.add_get("/api/admin/dashboard", dashboard)
    r.add_get("/api/admin/menu", menu)
    r.add_post("/api/admin/categories", category_create)
    r.add_post("/api/admin/categories/order", category_order)
    r.add_patch("/api/admin/categories/{id:\\d+}", category_update)
    r.add_delete("/api/admin/categories/{id:\\d+}", category_delete)
    r.add_post("/api/admin/products", product_create)
    r.add_post("/api/admin/products/order", product_order)
    r.add_patch("/api/admin/products/{id:\\d+}", product_update)
    r.add_delete("/api/admin/products/{id:\\d+}", product_delete)
    r.add_post("/api/admin/upload", upload)
    r.add_get("/api/admin/texts", texts)
    r.add_put("/api/admin/texts", text_save)
    r.add_get("/api/admin/settings", settings_get)
    r.add_put("/api/admin/settings", settings_save)
    r.add_get("/api/admin/promos", promos)
    r.add_post("/api/admin/promos", promo_create)
    r.add_patch("/api/admin/promos/{id:\\d+}", promo_update)
    r.add_delete("/api/admin/promos/{id:\\d+}", promo_delete)
    r.add_get("/api/admin/orders", orders)
    r.add_get("/api/admin/orders/{id:\\d+}", order_detail)
    r.add_post("/api/admin/orders/{id:\\d+}/status", order_status)
    r.add_delete("/api/admin/orders/{id:\\d+}", order_delete)
    r.add_get("/api/admin/reviews", reviews)
    r.add_get("/api/admin/customers", customers)
    r.add_get("/api/admin/staff", staff)
    r.add_post("/api/admin/staff", staff_add)
    r.add_delete("/api/admin/staff/{id:\\d+}", staff_remove)
    r.add_post("/api/admin/broadcast", broadcast)
    r.add_get("/api/admin/broadcast", broadcast_status)
    r.add_get("/api/admin/export.csv", export_csv)
    r.add_get("/api/admin/backup", backup)

