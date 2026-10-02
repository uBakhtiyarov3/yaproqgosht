"""Mini Appsiz — bot ichida inline tugmalar orqali buyurtma berish (o'zbek/rus)."""
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from .. import db, hours
from ..catalog import (
    BADGES, badge_labels, badges_of, category_name, discount_active, product_desc, product_name,
    variant_name, variant_price,
)
from ..config import config
from ..i18n import both, money_l, stars, status_text, t
from ..keyboards import ikb, main_kb, webapp_ready, webapp_url
from ..notify import notify_new_order, notify_review, refresh_staff_messages
from ..orders import OrderError, normalize_phone, place_order, public_settings, quote
from ..roles import get_role, lang_of
from ..utils import h, phone_fmt

router = Router(name="shop")
log = logging.getLogger(__name__)


class Checkout(StatesGroup):
    name = State()
    phone = State()
    address = State()
    time = State()
    comment = State()
    promo = State()
    payment = State()
    confirm = State()


class ReviewComment(StatesGroup):
    text = State()


# ====================== ko'rsatish yordamchilari ======================

_photo_cache: dict[str, str] = {}  # rasm yo'li -> Telegram file_id (qayta yuklamaslik uchun)


def _photo_input(image: str):
    if not image:
        return None
    if image in _photo_cache:
        return _photo_cache[image]
    if image.startswith("uploads/"):
        path = config.uploads_dir / image.removeprefix("uploads/")
    else:
        path = config.webapp_dir / image
    return FSInputFile(path) if path.exists() else None


def _remember_photo(image: str, msg: Message | bool) -> None:
    if image and isinstance(msg, Message) and msg.photo:
        _photo_cache[image] = msg.photo[-1].file_id


async def show(event: Message | CallbackQuery, text: str, kb: InlineKeyboardMarkup | None,
               image: str = "") -> None:
    """Callbackda mavjud xabarni tahrirlaydi (rasm <-> matn almashinuvi bilan), aks holda yangisini yuboradi."""
    photo = _photo_input(image)
    if isinstance(event, Message):
        if photo:
            _remember_photo(image, await event.answer_photo(photo, caption=text, reply_markup=kb))
        else:
            await event.answer(text, reply_markup=kb)
        return

    msg = event.message
    try:
        if photo and msg.photo:
            res = await msg.edit_media(InputMediaPhoto(media=photo, caption=text), reply_markup=kb)
            _remember_photo(image, res)
        elif not photo and not msg.photo:
            await msg.edit_text(text, reply_markup=kb)
        else:
            await msg.delete()
            if photo:
                _remember_photo(image, await msg.answer_photo(photo, caption=text, reply_markup=kb))
            else:
                await msg.answer(text, reply_markup=kb)
    except TelegramBadRequest as e:
        if "not modified" not in str(e):
            log.warning("show() fallback: %s", e)
            if photo:
                _remember_photo(image, await msg.answer_photo(photo, caption=text, reply_markup=kb))
            else:
                await msg.answer(text, reply_markup=kb)


def _kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return ikb([r for r in rows if r])


def _price_html(price: int, old: int | None, lang: str) -> str:
    if old:
        return f"<s>{money_l(old, lang)}</s> → <b>{money_l(price, lang)}</b>"
    return money_l(price, lang)


async def _cart_button(user_id: int, lang: str) -> tuple[str, str] | None:
    items = await db.cart_get(user_id)
    if not items:
        return None
    count = sum(i["qty"] for i in items)
    total = sum(i["qty"] * i["price"] for i in items)
    return t("cart_btn", lang, count=count, sum=money_l(total, lang)), "sh:cart"


def _badge_prefix(p: dict) -> str:
    icons = "".join(BADGES[b]["uz"].split()[0] for b in badges_of(p))
    return f"{icons} " if icons else ""


# ====================== menyu ======================

async def categories_view(user_id: int, header: str = "") -> tuple[str, InlineKeyboardMarkup]:
    lang = await lang_of(user_id)
    settings = public_settings(await db.get_settings())
    menu = await db.get_menu(lang)
    text = (header + "\n\n" if header else "") + t("menu_title", lang)
    if not settings["is_open"]:
        text += "\n\n" + t("closed_now", lang)
        if settings["next_open"]:
            text += " " + t("opens_at", lang, when=settings["next_open"])
    buttons = [(f"{c['emoji']} {c['name']}", f"sh:cat:{c['id']}") for c in menu]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    cart_btn = await _cart_button(user_id, lang)
    rows.append([cart_btn] if cart_btn else [])
    rows.append([(t("orders_btn", lang), "sh:orders")])
    kb = _kb(rows)
    if webapp_ready():
        kb.inline_keyboard.append([InlineKeyboardButton(text=t("mini_inline", lang),
                                                        web_app=WebAppInfo(url=webapp_url()))])
    return text, kb


async def category_view(user_id: int, cat_id: int, header: str = "") -> tuple[str, InlineKeyboardMarkup]:
    lang = await lang_of(user_id)
    cat = await db.get_category(cat_id)
    products = await db.get_products(cat_id, only_available=True)
    if not cat or not cat["is_active"] or not products:
        return await categories_view(user_id, t("cat_empty", lang))
    text = (header + "\n\n" if header else "") + f"{cat['emoji']} <b>{h(category_name(cat, lang))}</b>\n\n" \
        + t("choose_product", lang)
    rows = []
    for p in products:
        price = min(variant_price(p, i)[0] for i in range(len(p["variants"])))
        prefix = t("from", lang) if len(p["variants"]) > 1 else ""
        pct = discount_active(p)
        label = f"{_badge_prefix(p)}{product_name(p, lang)} · {prefix}{money_l(price, lang)}"
        if pct:
            label += f" (-{pct}%)"
        rows.append([(label, f"sh:p:{p['id']}:0:1")])
    cart_btn = await _cart_button(user_id, lang)
    rows.append([(t("back_cats", lang), "sh:cats")] + ([cart_btn] if cart_btn else []))
    return text, _kb(rows)


async def product_view(user_id: int, pid: int, v: int, q: int):
    lang = await lang_of(user_id)
    p = await db.get_product(pid)
    if not p or not p["is_available"]:
        return None
    v = v if 0 <= v < len(p["variants"]) else 0
    q = max(1, min(50, q))
    lines = []
    labels = badge_labels(p, lang)
    if labels:
        lines.append(" · ".join(labels))
    lines.append(f"<b>{h(product_name(p, lang))}</b>")
    desc = product_desc(p, lang)
    if desc:
        lines.append(h(desc))
    lines.append("")
    for i, var in enumerate(p["variants"]):
        price, old = variant_price(p, i)
        name = variant_name(var["name"], lang)
        lines.append(f"💰 {h(name) + ' — ' if name else ''}{_price_html(price, old, lang)}")
    price, _old = variant_price(p, v)
    vname = variant_name(p["variants"][v]["name"], lang)
    lines.append("")
    lines.append(f"{t('chosen', lang)}: <b>{h(vname) + ' ' if vname else ''}× {q} = {money_l(price * q, lang)}</b>")

    rows = []
    if len(p["variants"]) > 1:
        rows.append([((("✅ " if i == v else "") + (variant_name(var["name"], lang) or "Standart")),
                      f"sh:p:{pid}:{i}:{q}") for i, var in enumerate(p["variants"])])
    rows.append([("➖", f"sh:p:{pid}:{v}:{q - 1}"), (t("pcs", lang, n=q), "sh:noop"), ("➕", f"sh:p:{pid}:{v}:{q + 1}")])
    rows.append([(t("add_btn", lang, sum=money_l(price * q, lang)), f"sh:add:{pid}:{v}:{q}")])
    cart_btn = await _cart_button(user_id, lang)
    rows.append([(t("back", lang), f"sh:cat:{p['category_id']}")] + ([cart_btn] if cart_btn else []))
    return "\n".join(lines), _kb(rows), p["image"]


@router.message(StateFilter(None), F.text.in_(both("b_menu_mini")))
async def open_mini_app(message: Message) -> None:
    lang = await lang_of(message.from_user.id)
    if not webapp_ready():
        text, kb = await categories_view(message.from_user.id)
        await message.answer(text, reply_markup=kb)
        return
    await message.answer(
        t("open_mini_text", lang),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=t("open_mini_btn", lang), web_app=WebAppInfo(url=webapp_url()))
        ]]),
    )


@router.message(StateFilter(None), F.text.in_(both("b_menu")))
@router.message(Command("menu"))
async def menu_cmd(message: Message, state: FSMContext) -> None:
    await state.clear()
    text, kb = await categories_view(message.from_user.id)
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "sh:noop")
async def noop(call: CallbackQuery) -> None:
    await call.answer()


@router.callback_query(F.data == "sh:cats")
async def cats_cb(call: CallbackQuery) -> None:
    text, kb = await categories_view(call.from_user.id)
    await show(call, text, kb)
    await call.answer()


@router.callback_query(F.data.startswith("sh:cat:"))
async def cat_cb(call: CallbackQuery) -> None:
    text, kb = await category_view(call.from_user.id, int(call.data.split(":")[2]))
    await show(call, text, kb)
    await call.answer()


@router.callback_query(F.data.startswith("sh:p:"))
async def product_cb(call: CallbackQuery) -> None:
    lang = await lang_of(call.from_user.id)
    _, _, pid, v, q = call.data.split(":")
    if int(q) < 1 or int(q) > 50:
        await call.answer(t("qty_limit", lang))
        return
    view = await product_view(call.from_user.id, int(pid), int(v), int(q))
    if not view:
        await call.answer(t("unavailable", lang), show_alert=True)
        text, kb = await categories_view(call.from_user.id)
        await show(call, text, kb)
        return
    text, kb, image = view
    await show(call, text, kb, image)
    await call.answer()


@router.callback_query(F.data.startswith("sh:add:"))
async def add_cb(call: CallbackQuery) -> None:
    lang = await lang_of(call.from_user.id)
    _, _, pid, v, q = call.data.split(":")
    p = await db.get_product(int(pid))
    if not p or not p["is_available"] or int(v) >= len(p["variants"]):
        await call.answer(t("unavailable", lang), show_alert=True)
        return
    await db.cart_add(call.from_user.id, int(pid), int(v), int(q))
    vname = variant_name(p["variants"][int(v)]["name"], lang)
    label = f"{product_name(p, lang)}{f' ({vname})' if vname else ''} × {q}"
    await call.answer(t("added_toast", lang))
    text, kb = await category_view(call.from_user.id, p["category_id"], t("added", lang, item=h(label)))
    await show(call, text, kb)


# ====================== savat ======================

async def cart_view(user_id: int, header: str = "") -> tuple[str, InlineKeyboardMarkup]:
    lang = await lang_of(user_id)
    items = await db.cart_get(user_id)
    if not items:
        text = (header + "\n\n" if header else "") + t("cart_empty", lang)
        return text, _kb([[(t("to_menu", lang), "sh:cats")]])
    settings = public_settings(await db.get_settings())
    subtotal = sum(i["qty"] * i["price"] for i in items)
    lines = [header, ""] if header else []
    lines.append(t("cart_title", lang) + "\n")
    for n, i in enumerate(items, 1):
        vn = variant_name(i["variant_name"], lang)
        vn = f" ({h(vn)})" if vn else ""
        price = _price_html(i["qty"] * i["price"], i["qty"] * i["old_price"] if i["old_price"] else None, lang)
        lines.append(f"{n}. {h(product_name(i['product'], lang))}{vn} × {i['qty']} = {price}")
    lines += ["", f"<b>{t('items_sum', lang)}: {money_l(subtotal, lang)}</b>"]
    if settings["delivery_enabled"]:
        fee = settings["delivery_fee"]
        lines.append(f"{t('delivery', lang)}: {money_l(fee, lang) if fee else t('free', lang)}")
        if settings["min_order"] and subtotal < settings["min_order"]:
            lines.append(t("min_order_warn", lang, min=money_l(settings["min_order"], lang)))
    if not settings["is_open"]:
        line = t("closed_now", lang)
        if settings["next_open"]:
            line += " " + t("opens_at", lang, when=settings["next_open"])
        lines.append("\n" + line)

    rows = []
    for n, i in enumerate(items, 1):
        key = f"{i['product_id']}:{i['variant']}"
        rows.append([("➖", f"sh:ci:{key}:-1"),
                     (f"{n}. {product_name(i['product'], lang)[:18]} × {i['qty']}", "sh:noop"),
                     ("➕", f"sh:ci:{key}:1")])
    rows.append([(t("clear", lang), "sh:clr"), (t("menu_btn", lang), "sh:cats")])
    if settings["accepting"]:
        rows.append([(t("checkout_btn", lang, sum=money_l(subtotal, lang)), "sh:co")])
    return "\n".join(lines), _kb(rows)


@router.message(StateFilter(None), F.text.in_(both("b_cart")))
@router.message(Command("cart"))
async def cart_cmd(message: Message, state: FSMContext) -> None:
    await state.clear()
    text, kb = await cart_view(message.from_user.id)
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "sh:cart")
async def cart_cb(call: CallbackQuery) -> None:
    text, kb = await cart_view(call.from_user.id)
    await show(call, text, kb)
    await call.answer()


@router.callback_query(F.data.startswith("sh:ci:"))
async def cart_item_cb(call: CallbackQuery) -> None:
    _, _, pid, v, delta = call.data.split(":")
    await db.cart_change(call.from_user.id, int(pid), int(v), int(delta))
    text, kb = await cart_view(call.from_user.id)
    await show(call, text, kb)
    await call.answer()


@router.callback_query(F.data == "sh:clr")
async def cart_clear_cb(call: CallbackQuery) -> None:
    await db.cart_clear(call.from_user.id)
    text, kb = await cart_view(call.from_user.id, t("cart_cleared", await lang_of(call.from_user.id)))
    await show(call, text, kb)
    await call.answer()


# ====================== rasmiylashtirish ======================

def _reply_kb(*rows: list[KeyboardButton]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[r for r in rows if r], resize_keyboard=True)


def _short(text: str, n: int = 40) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def _cancel_row(lang: str) -> list[KeyboardButton]:
    return [KeyboardButton(text=t("co_cancel", lang))]


async def _back_to_main(message: Message, text: str, user_id: int) -> None:
    lang = await lang_of(user_id)
    await message.answer(text, reply_markup=main_kb(await get_role(user_id), lang))


async def _ask_name(message: Message, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    saved = data.get("saved_name")
    await state.set_state(Checkout.name)
    await message.answer(
        t("ask_name", lang),
        reply_markup=_reply_kb([KeyboardButton(text=_short(saved))] if saved else [], _cancel_row(lang)),
    )


@router.callback_query(F.data == "sh:co")
async def checkout_start(call: CallbackQuery, state: FSMContext) -> None:
    lang = await lang_of(call.from_user.id)
    items = await db.cart_get(call.from_user.id)
    raw = await db.get_settings()
    settings = public_settings(raw)
    if not items:
        await call.answer(t("e_empty_cart", lang), show_alert=True)
        return
    if not settings["accepting"]:
        await call.answer(t("e_closed_full", lang), show_alert=True)
        return
    if not settings["is_open"] and not hours.slots(raw):
        await call.answer(t("no_slots", lang), show_alert=True)
        return
    await call.answer()
    u = call.from_user
    user, _ = await db.upsert_user(u.id, u.first_name, u.last_name, u.username)
    await state.clear()
    await state.update_data(
        saved_name=user.get("full_name") or call.from_user.full_name,
        saved_phone=user.get("phone") or "", saved_address=user.get("address") or "",
    )
    await call.message.answer(t("co_title", lang))
    types = [x for x in ("delivery", "pickup") if settings[f"{x}_enabled"]]
    if len(types) == 2:
        await call.message.answer(t("ask_type", lang), reply_markup=ikb([[
            (t("type_delivery", lang), "sh:ot:delivery"), (t("type_pickup", lang), "sh:ot:pickup"),
        ]]))
        return
    await state.update_data(order_type=types[0] if types else "delivery")
    await _ask_name(call.message, state, lang)


@router.callback_query(F.data.startswith("sh:ot:"))
async def checkout_type(call: CallbackQuery, state: FSMContext) -> None:
    lang = await lang_of(call.from_user.id)
    otype = call.data.split(":")[2]
    settings = public_settings(await db.get_settings())
    if otype == "delivery" and settings["min_order"]:
        subtotal = sum(i["qty"] * i["price"] for i in await db.cart_get(call.from_user.id))
        if subtotal < settings["min_order"]:
            await call.answer(t("e_min_order", lang, min=money_l(settings["min_order"], lang)), show_alert=True)
            return
    await state.update_data(order_type=otype)
    await call.message.edit_text(t("type_delivery" if otype == "delivery" else "type_pickup", lang) + " ✅")
    await call.answer()
    await _ask_name(call.message, state, lang)


@router.message(StateFilter(Checkout), F.text.in_(both("co_cancel")))
async def checkout_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _back_to_main(message, t("co_cancelled", await lang_of(message.from_user.id)), message.from_user.id)


@router.message(Checkout.name, F.text)
async def checkout_name(message: Message, state: FSMContext) -> None:
    lang = await lang_of(message.from_user.id)
    data = await state.get_data()
    name = message.text.strip()
    if data.get("saved_name") and name == _short(data["saved_name"]):
        name = data["saved_name"]
    if not 2 <= len(name) <= 64:
        await message.answer(t("bad_name", lang))
        return
    await state.update_data(name=name)
    await state.set_state(Checkout.phone)
    saved = data.get("saved_phone")
    await message.answer(
        t("ask_phone", lang),
        reply_markup=_reply_kb(
            [KeyboardButton(text=t("send_phone_btn", lang), request_contact=True)],
            [KeyboardButton(text=phone_fmt(saved))] if saved else [],
            _cancel_row(lang),
        ),
    )


@router.message(Checkout.phone)
async def checkout_phone(message: Message, state: FSMContext) -> None:
    lang = await lang_of(message.from_user.id)
    raw = message.contact.phone_number if message.contact else (message.text or "")
    phone = normalize_phone(raw)
    if not phone:
        await message.answer(t("bad_phone", lang))
        return
    await state.update_data(phone=phone)
    data = await state.get_data()
    if data.get("order_type") == "pickup":
        await _ask_time(message, state, lang)
        return
    await state.set_state(Checkout.address)
    saved = data.get("saved_address")
    await message.answer(
        t("ask_address", lang),
        reply_markup=_reply_kb(
            [KeyboardButton(text=t("send_location_btn", lang), request_location=True)],
            [KeyboardButton(text="🏠 " + _short(saved))] if saved else [],
            _cancel_row(lang),
        ),
    )


@router.message(Checkout.address)
async def checkout_address(message: Message, state: FSMContext) -> None:
    lang = await lang_of(message.from_user.id)
    data = await state.get_data()
    if message.location:
        loc = message.location
        address = f"{t('location_label', lang)}: https://maps.google.com/?q={loc.latitude:.6f},{loc.longitude:.6f}"
        await message.answer(t("location_ok", lang))
    elif message.text:
        address = message.text.strip()
        saved = data.get("saved_address") or ""
        if saved and address == "🏠 " + _short(saved):
            address = saved
        if not 5 <= len(address) <= 300:
            await message.answer(t("bad_address", lang))
            return
    else:
        await message.answer(t("bad_address", lang))
        return
    await state.update_data(address=address)
    await _ask_time(message, state, lang)


# ---------- vaqt ----------

def _time_kb(raw_settings: dict, lang: str) -> InlineKeyboardMarkup | None:
    rows = []
    if hours.is_open_at(raw_settings):
        rows.append([(t("asap", lang), "sh:tm:asap")])
    days = hours.slots(raw_settings)
    if days:
        rows.append([(t(d["day"], lang), f"sh:td:{i}") for i, d in enumerate(days)])
    return ikb(rows) if rows else None


async def _ask_time(message: Message, state: FSMContext, lang: str) -> None:
    await state.set_state(Checkout.time)
    kb = _time_kb(await db.get_settings(), lang)
    if not kb:
        await state.clear()
        await _back_to_main(message, t("no_slots", lang), message.from_user.id)
        return
    await message.answer(t("ask_time", lang), reply_markup=_reply_kb(_cancel_row(lang)))
    await message.answer("👇", reply_markup=kb)


@router.callback_query(F.data.startswith("sh:td:"), Checkout.time)
async def time_day(call: CallbackQuery) -> None:
    lang = await lang_of(call.from_user.id)
    days = hours.slots(await db.get_settings())
    idx = int(call.data.split(":")[2])
    if idx >= len(days):
        await call.answer(t("e_slot", lang), show_alert=True)
        return
    day = days[idx]
    buttons = [(tm["label"], "sh:tt:" + tm["value"].replace("-", "").replace(" ", "").replace(":", ""))
               for tm in day["times"]]
    rows = [buttons[i:i + 4] for i in range(0, len(buttons), 4)]
    rows.append([(t("back", lang), "sh:tb")])
    await call.message.edit_text(t("pick_time", lang, day=t(day["day"], lang).split(" ", 1)[1]), reply_markup=ikb(rows))
    await call.answer()


@router.callback_query(F.data == "sh:tb", Checkout.time)
async def time_back(call: CallbackQuery) -> None:
    lang = await lang_of(call.from_user.id)
    kb = _time_kb(await db.get_settings(), lang)
    await call.message.edit_text("👇", reply_markup=kb)
    await call.answer()


async def _after_time(call: CallbackQuery, state: FSMContext, scheduled: str, label: str) -> None:
    lang = await lang_of(call.from_user.id)
    await state.update_data(scheduled_at=scheduled)
    await call.message.edit_text(label + " ✅")
    await call.answer()
    await state.set_state(Checkout.comment)
    await call.message.answer(
        t("ask_comment", lang),
        reply_markup=_reply_kb([KeyboardButton(text=t("co_skip", lang))], _cancel_row(lang)),
    )


@router.callback_query(F.data == "sh:tm:asap", Checkout.time)
async def time_asap(call: CallbackQuery, state: FSMContext) -> None:
    lang = await lang_of(call.from_user.id)
    if not hours.is_open_at(await db.get_settings()):
        await call.answer(t("e_closed", lang, next=""), show_alert=True)
        return
    await _after_time(call, state, "", t("when_asap", lang))


@router.callback_query(F.data.startswith("sh:tt:"), Checkout.time)
async def time_pick(call: CallbackQuery, state: FSMContext) -> None:
    lang = await lang_of(call.from_user.id)
    raw = call.data.split(":")[2]  # 202610021900
    value = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]} {raw[8:10]}:{raw[10:12]}"
    if not hours.valid_slot(await db.get_settings(), value):
        await call.answer(t("e_slot", lang), show_alert=True)
        return
    await _after_time(call, state, value, t("when_at", lang, when=_when_text(value, lang)))


def _when_text(value: str, lang: str) -> str:
    from datetime import datetime, timedelta

    from ..utils import now

    try:
        dt = datetime.strptime(value[:16], "%Y-%m-%d %H:%M")
    except ValueError:
        return value
    if dt.date() == now().date():
        day = t("today", lang).split(" ", 1)[1]
    elif dt.date() == (now() + timedelta(days=1)).date():
        day = t("tomorrow", lang).split(" ", 1)[1]
    else:
        day = dt.strftime("%d.%m")
    return f"{day.lower()} {dt.strftime('%H:%M')}"


@router.callback_query(F.data.startswith(("sh:td:", "sh:tt:", "sh:tm:", "sh:tb")))
async def time_stale(call: CallbackQuery) -> None:
    await call.answer(t("form_stale", await lang_of(call.from_user.id)), show_alert=True)


# ---------- izoh, promo, to'lov ----------

@router.message(Checkout.comment, F.text)
async def checkout_comment(message: Message, state: FSMContext) -> None:
    lang = await lang_of(message.from_user.id)
    comment = "" if message.text in both("co_skip") else message.text.strip()[:300]
    await state.update_data(comment=comment)
    await state.set_state(Checkout.promo)
    await message.answer(
        t("ask_promo", lang),
        reply_markup=_reply_kb([KeyboardButton(text=t("co_skip", lang))], _cancel_row(lang)),
    )


@router.message(Checkout.promo, F.text)
async def checkout_promo(message: Message, state: FSMContext) -> None:
    lang = await lang_of(message.from_user.id)
    code = "" if message.text in both("co_skip") else message.text.strip().upper()[:32]
    if code:
        data = await state.get_data()
        try:
            q = await quote(message.from_user.id, await _raw_cart(message.from_user.id),
                            data.get("order_type", "delivery"), code, lang)
        except OrderError as e:
            await message.answer("❗️ " + e.text(lang) + "\n\n" + t("ask_promo", lang))
            return
        await state.update_data(promo_code=q["promo_code"])
        await message.answer(t("promo_ok", lang, code=h(q["promo_code"]), label=h(q["promo_label"])))
    await state.set_state(Checkout.payment)
    await message.answer(t("ask_payment", lang), reply_markup=_reply_kb(_cancel_row(lang)))
    await message.answer(
        t("payment_hint", lang),
        reply_markup=ikb([[(t("pay_cash", lang), "sh:pay:cash"), (t("pay_card", lang), "sh:pay:card")]]),
    )


async def _raw_cart(user_id: int) -> list[dict]:
    return [{"product_id": i["product_id"], "variant": i["variant"], "qty": i["qty"]}
            for i in await db.cart_get(user_id)]


@router.callback_query(F.data == "sh:pay:card")
async def pay_card(call: CallbackQuery) -> None:
    await call.answer(t("pay_card_alert", await lang_of(call.from_user.id)), show_alert=True)


@router.callback_query(F.data == "sh:pay:cash", Checkout.payment)
async def pay_cash(call: CallbackQuery, state: FSMContext) -> None:
    lang = await lang_of(call.from_user.id)
    await state.update_data(payment_method="cash")
    await state.set_state(Checkout.confirm)
    data = await state.get_data()
    try:
        q = await quote(call.from_user.id, await _raw_cart(call.from_user.id),
                        data.get("order_type", "delivery"), data.get("promo_code", ""), lang)
    except OrderError as e:
        await call.answer(e.text(lang), show_alert=True)
        await state.clear()
        text, kb = await cart_view(call.from_user.id, "⚠️ " + h(e.text(lang)))
        await show(call, text, kb)
        return
    items = await db.cart_get(call.from_user.id)
    otype = data.get("order_type", "delivery")
    lines = [t("check_title", lang) + "\n"]
    for i in items:
        vn = variant_name(i["variant_name"], lang)
        vn = f" ({h(vn)})" if vn else ""
        lines.append(f"• {h(product_name(i['product'], lang))}{vn} × {i['qty']} = {money_l(i['qty'] * i['price'], lang)}")
    lines += ["", f"{t('items_sum', lang)}: {money_l(q['subtotal'], lang)}"]
    if q["promo_code"]:
        disc = f"−{money_l(q['discount'], lang)}" if q["discount"] else h(q["promo_label"])
        lines.append(f"🎁 {t('discount', lang)} ({h(q['promo_code'])}): {disc}")
    if otype == "delivery":
        lines.append(f"{t('delivery', lang)}: {money_l(q['delivery_fee'], lang) if q['delivery_fee'] else t('free', lang)}")
    lines += [
        f"<b>{t('total', lang)}: {money_l(q['total'], lang)}</b>",
        f"{t('payment', lang)}: {t('pay_cash', lang)}",
        "",
        t("type_delivery" if otype == "delivery" else "type_pickup", lang),
        t("when_at", lang, when=_when_text(data["scheduled_at"], lang)) if data.get("scheduled_at")
        else t("when_asap", lang),
        f"👤 {h(data['name'])}",
        f"📞 {phone_fmt(data['phone'])}",
    ]
    if otype == "delivery":
        lines.append(f"📍 {h(data['address'])}")
    else:
        cafe = await db.get_setting("cafe_address")
        lines.append(t("pickup_from", lang, address=h(cafe or t("pickup_cafe", lang))))
    if data.get("comment"):
        lines.append(f"💬 {h(data['comment'])}")
    await call.message.edit_text(
        "\n".join(lines),
        reply_markup=ikb([[(t("confirm_btn", lang), "sh:ok")],
                          [(t("refill_btn", lang), "sh:co"), (t("cancel_btn", lang), "sh:no")]]),
    )
    await call.answer()


@router.callback_query(F.data == "sh:pay:cash")
async def pay_cash_stale(call: CallbackQuery) -> None:
    await call.answer(t("form_stale", await lang_of(call.from_user.id)), show_alert=True)


@router.callback_query(F.data == "sh:ok", Checkout.confirm)
async def checkout_confirm(call: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    lang = await lang_of(call.from_user.id)
    data = await state.get_data()
    raw = await _raw_cart(call.from_user.id)
    try:
        order_id = await place_order(call.from_user.id, {**data, "lang": lang}, raw)
    except OrderError as e:
        await call.answer(e.text(lang), show_alert=True)
        if e.status == 409 or not raw or e.key.startswith(("e_promo", "e_slot", "e_closed", "e_min")):
            await state.clear()
            text, kb = await cart_view(call.from_user.id, "⚠️ " + h(e.text(lang)))
            await show(call, text, kb)
        return
    await state.clear()
    await db.cart_clear(call.from_user.id)
    await call.answer(t("order_sent_toast", lang))
    order = await db.get_order(order_id)
    await call.message.edit_text(
        t("order_placed", lang, code=order["code"], total=money_l(order["total"], lang)),
        reply_markup=ikb([[(t("track_btn", lang), f"sh:o:{order['code']}")]]),
    )
    await _back_to_main(call.message, t("thanks", lang), call.from_user.id)
    await notify_new_order(bot, order_id, notify_customer=False)


@router.callback_query(F.data == "sh:no")
async def checkout_abort(call: CallbackQuery, state: FSMContext) -> None:
    lang = await lang_of(call.from_user.id)
    await state.clear()
    text, kb = await cart_view(call.from_user.id, t("co_cancelled", lang))
    await show(call, text, kb)
    await _back_to_main(call.message, t("main_menu", lang), call.from_user.id)
    await call.answer()


@router.callback_query(F.data == "sh:ok")
async def checkout_confirm_stale(call: CallbackQuery) -> None:
    await call.answer(t("form_stale", await lang_of(call.from_user.id)), show_alert=True)


# ====================== buyurtmalarim ======================

STEPS = ["new", "accepted", "cooking", "delivering", "delivered"]


async def orders_view(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    lang = await lang_of(user_id)
    orders = await db.get_user_orders(user_id, limit=10)
    if not orders:
        return t("no_orders", lang), _kb([[(t("menu_btn", lang), "sh:cats")]])
    rows = []
    for o in orders:
        st = status_text(o["status"], o["order_type"], lang).split(" ", 1)[1]
        rows.append([(f"{o['code']} · {st} · {money_l(o['total'], lang)}", f"sh:o:{o['code']}")])
    rows.append([(t("menu_btn", lang), "sh:cats")])
    return t("orders_title", lang), _kb(rows)


async def _item_name(it: dict, lang: str) -> str:
    if lang == "ru" and it.get("product_id"):
        p = await db.fetchone("SELECT name, name_ru FROM products WHERE id = ?", it["product_id"])
        if p and p["name_ru"]:
            return p["name_ru"]
    return it["name"]


async def order_detail_view(order: dict, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    items = await db.get_order_items(order["id"])
    log_rows = {r["status"]: r["at"] for r in await db.get_order_log(order["id"])}
    otype = order.get("order_type") or "delivery"
    lines = [t("order_title", lang, code=order["code"]), f"🕒 {order['created_at'][:16]}",
             t("type_delivery" if otype == "delivery" else "type_pickup", lang)]
    if order.get("scheduled_at"):
        lines.append(t("when_at", lang, when=_when_text(order["scheduled_at"], lang)))
    lines.append("")
    if order["status"] == "cancelled":
        lines.append(f"<b>{t('s_cancelled', lang)}</b>")
        if order["cancel_reason"]:
            lines.append(t("reason", lang, reason=h(order["cancel_reason"])))
    else:
        reached = STEPS.index(order["status"])
        for i, key in enumerate(STEPS):
            label = t("step_new", lang) if key == "new" else status_text(key, otype, lang).split(" ", 1)[1]
            if i < reached or (i == reached and key == "delivered"):
                icon = "✅"
            elif i == reached:
                icon = "🔵"
            else:
                icon = "▫️"
            at = f" — {log_rows[key][11:16]}" if key in log_rows else ""
            lines.append(f"{icon} {'<b>' + label + '</b>' if i == reached else label}{at}")
    lines.append("")
    for it in items:
        vn = variant_name(it["variant"], lang)
        vn = f" ({h(vn)})" if vn else ""
        lines.append(f"• {h(await _item_name(it, lang))}{vn} × {it['qty']} = {money_l(it['price'] * it['qty'], lang)}")
    if order.get("discount"):
        lines.append(f"🎁 {t('discount', lang)} ({h(order['promo_code'])}): −{money_l(order['discount'], lang)}")
    if otype == "delivery":
        fee = order["delivery_fee"]
        lines.append(f"{t('delivery', lang)}: {money_l(fee, lang) if fee else t('free', lang)}")
        lines.append(f"<b>{t('total', lang)}: {money_l(order['total'], lang)}</b>")
        lines.append(f"\n📍 {h(order['address'])}")
    else:
        lines.append(f"<b>{t('total', lang)}: {money_l(order['total'], lang)}</b>")
        cafe = await db.get_setting("cafe_address")
        lines.append("\n" + t("pickup_from", lang, address=h(cafe or t("pickup_cafe", lang))))
    if order.get("comment"):
        lines.append(f"💬 {h(order['comment'])}")

    review = await db.get_review(order["id"])
    if review:
        lines.append("\n" + t("your_rating", lang, stars=stars(review["rating"])))

    rows = []
    if order["status"] not in ("delivered", "cancelled"):
        rows.append([(t("refresh", lang), f"sh:o:{order['code']}")])
    if order["status"] == "new":
        rows.append([(t("cancel_order_btn", lang), f"sh:oc:{order['code']}")])
    if order["status"] == "delivered" and not review:
        rows.append([(f"{n}⭐", f"rv:{order['id']}:{n}") for n in range(1, 6)])
    if order["status"] in ("delivered", "cancelled"):
        rows.append([(t("repeat_btn", lang), f"sh:rp:{order['code']}")])
    rows.append([(t("back_orders", lang), "sh:orders")])
    return "\n".join(lines), _kb(rows)


@router.message(StateFilter(None), F.text.in_(both("b_orders")))
@router.message(Command("orders"))
async def orders_cmd(message: Message) -> None:
    text, kb = await orders_view(message.from_user.id)
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "sh:orders")
async def orders_cb(call: CallbackQuery) -> None:
    text, kb = await orders_view(call.from_user.id)
    await show(call, text, kb)
    await call.answer()


async def _own_order(call: CallbackQuery, lang: str) -> dict | None:
    order = await db.get_order_by_code(call.data.split(":", 2)[2])
    if not order or order["user_id"] != call.from_user.id:
        await call.answer(t("order_not_found", lang), show_alert=True)
        return None
    return order


@router.callback_query(F.data.startswith("sh:o:"))
async def order_cb(call: CallbackQuery) -> None:
    lang = await lang_of(call.from_user.id)
    order = await _own_order(call, lang)
    if not order:
        return
    text, kb = await order_detail_view(order, lang)
    await show(call, text, kb)
    await call.answer(t("refreshed", lang) if order["status"] not in ("delivered", "cancelled") else None)


@router.callback_query(F.data.startswith("sh:oc:"))
async def order_cancel_cb(call: CallbackQuery, bot: Bot) -> None:
    lang = await lang_of(call.from_user.id)
    order = await _own_order(call, lang)
    if not order:
        return
    if order["status"] != "new":
        await call.answer(t("cancel_not_allowed", lang), show_alert=True)
        return
    await db.set_order_status(order["id"], "cancelled", call.from_user.id, "Mijoz bekor qildi")
    await refresh_staff_messages(bot, order["id"])
    text, kb = await order_detail_view(await db.get_order(order["id"]), lang)
    await show(call, text, kb)
    await call.answer(t("order_cancelled_toast", lang))


@router.callback_query(F.data.startswith("sh:rp:"))
async def order_repeat_cb(call: CallbackQuery) -> None:
    lang = await lang_of(call.from_user.id)
    order = await _own_order(call, lang)
    if not order:
        return
    added = 0
    for it in await db.get_order_items(order["id"]):
        p = await db.get_product(it["product_id"]) if it["product_id"] else None
        if not p or not p["is_available"]:
            continue
        idx = next((i for i, v in enumerate(p["variants"]) if v["name"] == it["variant"]), 0)
        await db.cart_add(call.from_user.id, p["id"], idx, it["qty"])
        added += 1
    text, kb = await cart_view(call.from_user.id, t("repeat_added" if added else "repeat_none", lang))
    await show(call, text, kb)
    await call.answer()


# ====================== baholash ======================

@router.callback_query(F.data.startswith("rv:"))
async def rate_cb(call: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    lang = await lang_of(call.from_user.id)
    _, order_id, rating = call.data.split(":")
    order = await db.get_order(int(order_id))
    if not order or order["user_id"] != call.from_user.id:
        await call.answer(t("order_not_found", lang), show_alert=True)
        return
    if order["status"] != "delivered":
        await call.answer(t("rate_not_ready", lang), show_alert=True)
        return
    rating = max(1, min(5, int(rating)))
    if not await db.add_review(order["id"], call.from_user.id, rating):
        await call.answer(t("already_rated", lang), show_alert=True)
        return
    await call.answer("⭐" * rating)
    await state.set_state(ReviewComment.text)
    await state.update_data(review_order=order["id"])
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
    await call.message.answer(
        t("rate_thanks", lang, stars=stars(rating)),
        reply_markup=ikb([[(t("co_skip", lang), f"rvs:{order['id']}")]]),
    )


async def _finish_review(message: Message, state: FSMContext, bot: Bot, order_id: int, user_id: int) -> None:
    await state.clear()
    await message.answer(t("review_saved", await lang_of(user_id)))
    await notify_review(bot, order_id)


@router.message(ReviewComment.text, F.text)
async def review_comment(message: Message, state: FSMContext, bot: Bot) -> None:
    order_id = (await state.get_data()).get("review_order")
    if order_id:
        await db.set_review_comment(order_id, message.text.strip())
    await _finish_review(message, state, bot, order_id, message.from_user.id)


@router.callback_query(F.data.startswith("rvs:"))
async def review_skip(call: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await call.answer()
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
    await _finish_review(call.message, state, bot, int(call.data.split(":")[1]), call.from_user.id)
