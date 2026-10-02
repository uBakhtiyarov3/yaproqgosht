"""Mini Appsiz — bot ichida inline tugmalar orqali buyurtma berish."""
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

from .. import db
from ..config import config
from ..keyboards import B, ikb, main_kb, webapp_ready, webapp_url
from ..notify import notify_new_order, refresh_staff_messages
from ..orders import OrderError, normalize_phone, place_order, public_settings
from ..roles import get_role
from ..utils import PAYMENT_LABELS, h, money, phone_fmt

router = Router(name="shop")
log = logging.getLogger(__name__)

CO_CANCEL = "❌ Buyurtmani bekor qilish"
CO_SKIP = "➡️ O'tkazib yuborish"


class Checkout(StatesGroup):
    name = State()
    phone = State()
    address = State()
    comment = State()
    payment = State()
    confirm = State()


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


async def _cart_button(user_id: int) -> tuple[str, str] | None:
    items = await db.cart_get(user_id)
    if not items:
        return None
    count = sum(i["qty"] for i in items)
    total = sum(i["qty"] * i["price"] for i in items)
    return f"🛒 Savat ({count} ta · {money(total)})", "sh:cart"


def _min_price(p: dict) -> int:
    return min(v["price"] for v in p["variants"])


# ====================== menyu ======================

async def categories_view(user_id: int, header: str = "") -> tuple[str, InlineKeyboardMarkup]:
    settings = public_settings(await db.get_settings())
    menu = await db.get_menu()
    text = (header + "\n\n" if header else "") + "📋 <b>Menyu</b>\n\nKategoriyani tanlang 👇"
    if not settings["is_open"]:
        text += f"\n\n⏸ Hozir buyurtma qabul qilinmayapti. Ish vaqti: {h(settings['work_hours'])}"
    buttons = [(f"{c['emoji']} {c['name']}", f"sh:cat:{c['id']}") for c in menu]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([await _cart_button(user_id)] if await _cart_button(user_id) else [])
    rows.append([("📦 Buyurtmalarim", "sh:orders")])
    kb = _kb(rows)
    if webapp_ready():
        kb.inline_keyboard.append([InlineKeyboardButton(text="🍔 Mini ilovada ochish",
                                                        web_app=WebAppInfo(url=webapp_url()))])
    return text, kb


async def category_view(user_id: int, cat_id: int, header: str = "") -> tuple[str, InlineKeyboardMarkup]:
    cat = await db.get_category(cat_id)
    products = await db.get_products(cat_id, only_available=True)
    if not cat or not cat["is_active"] or not products:
        return await categories_view(user_id, "Bu kategoriya hozircha bo'sh.")
    text = (header + "\n\n" if header else "") + f"{cat['emoji']} <b>{h(cat['name'])}</b>\n\nMahsulotni tanlang 👇"
    rows = [[(
        f"{p['name']} · {'dan ' if len(p['variants']) > 1 else ''}{money(_min_price(p))}",
        f"sh:p:{p['id']}:0:1",
    )] for p in products]
    rows.append([("⬅️ Kategoriyalar", "sh:cats")] + ([await _cart_button(user_id)] if await _cart_button(user_id) else []))
    return text, _kb(rows)


async def product_view(user_id: int, pid: int, v: int, q: int):
    p = await db.get_product(pid)
    if not p or not p["is_available"]:
        return None
    v = v if 0 <= v < len(p["variants"]) else 0
    q = max(1, min(50, q))
    variant = p["variants"][v]
    lines = [f"<b>{h(p['name'])}</b>"]
    if p["description"]:
        lines.append(h(p["description"]))
    lines.append("")
    for var in p["variants"]:
        lines.append(f"💰 {h(var['name']) + ' — ' if var['name'] else ''}{money(var['price'])}")
    lines.append("")
    chosen = f"{h(variant['name'])} " if variant["name"] else ""
    lines.append(f"Tanlandi: <b>{chosen}× {q} = {money(variant['price'] * q)}</b>")

    rows = []
    if len(p["variants"]) > 1:
        rows.append([((("✅ " if i == v else "") + (var["name"] or "Standart")), f"sh:p:{pid}:{i}:{q}")
                     for i, var in enumerate(p["variants"])])
    rows.append([("➖", f"sh:p:{pid}:{v}:{q - 1}"), (f"{q} ta", "sh:noop"), ("➕", f"sh:p:{pid}:{v}:{q + 1}")])
    rows.append([(f"🛒 Savatga qo'shish · {money(variant['price'] * q)}", f"sh:add:{pid}:{v}:{q}")])
    cart_btn = await _cart_button(user_id)
    rows.append([("⬅️ Ortga", f"sh:cat:{p['category_id']}")] + ([cart_btn] if cart_btn else []))
    return "\n".join(lines), _kb(rows), p["image"]


@router.message(StateFilter(None), F.text == B.BOT_MENU)
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
    _, _, pid, v, q = call.data.split(":")
    if int(q) < 1 or int(q) > 50:
        await call.answer("1 dan 50 tagacha")
        return
    view = await product_view(call.from_user.id, int(pid), int(v), int(q))
    if not view:
        await call.answer("Bu mahsulot hozir mavjud emas", show_alert=True)
        text, kb = await categories_view(call.from_user.id)
        await show(call, text, kb)
        return
    text, kb, image = view
    await show(call, text, kb, image)
    await call.answer()


@router.callback_query(F.data.startswith("sh:add:"))
async def add_cb(call: CallbackQuery) -> None:
    _, _, pid, v, q = call.data.split(":")
    p = await db.get_product(int(pid))
    if not p or not p["is_available"] or int(v) >= len(p["variants"]):
        await call.answer("Bu mahsulot hozir mavjud emas", show_alert=True)
        return
    await db.cart_add(call.from_user.id, int(pid), int(v), int(q))
    vname = p["variants"][int(v)]["name"]
    label = f"{p['name']}{f' ({vname})' if vname else ''} × {q}"
    await call.answer(f"✅ {label} savatga qo'shildi")
    text, kb = await category_view(call.from_user.id, p["category_id"], f"✅ <b>{h(label)}</b> savatga qo'shildi!")
    await show(call, text, kb)


# ====================== savat ======================

async def cart_view(user_id: int, header: str = "") -> tuple[str, InlineKeyboardMarkup]:
    items = await db.cart_get(user_id)
    if not items:
        text = (header + "\n\n" if header else "") + "🛒 Savatingiz bo'sh.\n\nMenyudan mahsulot tanlang 👇"
        return text, _kb([[("📋 Menyuga o'tish", "sh:cats")]])
    settings = public_settings(await db.get_settings())
    subtotal = sum(i["qty"] * i["price"] for i in items)
    fee = settings["delivery_fee"]
    lines = [header, ""] if header else []
    lines.append("🛒 <b>Savat</b>\n")
    for n, i in enumerate(items, 1):
        vn = f" ({h(i['variant_name'])})" if i["variant_name"] else ""
        lines.append(f"{n}. {h(i['name'])}{vn} × {i['qty']} = {money(i['qty'] * i['price'])}")
    lines += [
        "",
        f"Mahsulotlar: {money(subtotal)}",
        f"Yetkazib berish: {money(fee) if fee else 'bepul'}",
        f"<b>Jami: {money(subtotal + fee)}</b>",
    ]
    can_order = settings["is_open"] and subtotal >= settings["min_order"]
    if subtotal < settings["min_order"]:
        lines.append(f"\n⚠️ Minimal buyurtma: {money(settings['min_order'])}. "
                     f"Yana {money(settings['min_order'] - subtotal)} qo'shing.")
    if not settings["is_open"]:
        lines.append(f"\n⏸ Hozir buyurtma qabul qilinmayapti. Ish vaqti: {h(settings['work_hours'])}")

    rows = []
    for n, i in enumerate(items, 1):
        key = f"{i['product_id']}:{i['variant']}"
        rows.append([("➖", f"sh:ci:{key}:-1"), (f"{n}. {i['name'][:18]} × {i['qty']}", "sh:noop"),
                     ("➕", f"sh:ci:{key}:1")])
    rows.append([("🗑 Tozalash", "sh:clr"), ("📋 Menyu", "sh:cats")])
    if can_order:
        rows.append([(f"✅ Buyurtma berish · {money(subtotal + fee)}", "sh:co")])
    return "\n".join(lines), _kb(rows)


@router.message(StateFilter(None), F.text == B.CART)
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
    text, kb = await cart_view(call.from_user.id, "🗑 Savat tozalandi.")
    await show(call, text, kb)
    await call.answer()


# ====================== rasmiylashtirish ======================

def _reply_kb(*rows: list[KeyboardButton]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[r for r in rows if r], resize_keyboard=True, one_time_keyboard=False)


def _short(text: str, n: int = 40) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


async def _back_to_main(message: Message, text: str, user_id: int) -> None:
    await message.answer(text, reply_markup=main_kb(await get_role(user_id)))


@router.callback_query(F.data == "sh:co")
async def checkout_start(call: CallbackQuery, state: FSMContext) -> None:
    items = await db.cart_get(call.from_user.id)
    settings = public_settings(await db.get_settings())
    subtotal = sum(i["qty"] * i["price"] for i in items)
    if not items:
        await call.answer("Savat bo'sh", show_alert=True)
        return
    if not settings["is_open"]:
        await call.answer("Hozir buyurtma qabul qilinmayapti", show_alert=True)
        return
    if subtotal < settings["min_order"]:
        await call.answer(f"Minimal buyurtma: {money(settings['min_order'])}", show_alert=True)
        return
    await call.answer()
    user = await db.get_user(call.from_user.id) or {}
    saved_name = user.get("full_name") or call.from_user.full_name
    await state.set_state(Checkout.name)
    await state.update_data(saved_name=saved_name, saved_phone=user.get("phone") or "",
                            saved_address=user.get("address") or "")
    await call.message.answer(
        "📝 <b>Buyurtmani rasmiylashtirish</b>\n\n1/4. Qabul qiluvchining <b>ismini</b> yozing:",
        reply_markup=_reply_kb([KeyboardButton(text=_short(saved_name))] if saved_name else [],
                               [KeyboardButton(text=CO_CANCEL)]),
    )


@router.message(StateFilter(Checkout), F.text == CO_CANCEL)
async def checkout_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _back_to_main(message, "Rasmiylashtirish bekor qilindi. Savatingiz saqlanib qoldi 🛒", message.from_user.id)


@router.message(Checkout.name, F.text)
async def checkout_name(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    name = message.text.strip()
    if data.get("saved_name") and name == _short(data["saved_name"]):
        name = data["saved_name"]
    if not 2 <= len(name) <= 64:
        await message.answer("Ism 2 dan 64 belgigacha bo'lsin. Qaytadan yozing:")
        return
    await state.update_data(name=name)
    await state.set_state(Checkout.phone)
    saved = data.get("saved_phone")
    await message.answer(
        "2/4. 📞 <b>Telefon raqamingizni</b> yuboring.\n\n"
        "Pastdagi tugmani bosing yoki yozing: <code>+998 90 123 45 67</code>",
        reply_markup=_reply_kb(
            [KeyboardButton(text="📱 Raqamimni yuborish", request_contact=True)],
            [KeyboardButton(text=phone_fmt(saved))] if saved else [],
            [KeyboardButton(text=CO_CANCEL)],
        ),
    )


@router.message(Checkout.phone)
async def checkout_phone(message: Message, state: FSMContext) -> None:
    raw = message.contact.phone_number if message.contact else (message.text or "")
    phone = normalize_phone(raw)
    if not phone:
        await message.answer("❗️ Raqam noto'g'ri. Masalan: <code>+998 90 123 45 67</code> yoki "
                             "«📱 Raqamimni yuborish» tugmasini bosing.")
        return
    await state.update_data(phone=phone)
    await state.set_state(Checkout.address)
    saved = (await state.get_data()).get("saved_address")
    await message.answer(
        "3/4. 📍 <b>Yetkazish manzilini</b> yozing (ko'cha, uy, xonadon, mo'ljal) "
        "yoki joylashuvingizni yuboring:",
        reply_markup=_reply_kb(
            [KeyboardButton(text="📍 Joylashuvni yuborish", request_location=True)],
            [KeyboardButton(text="🏠 " + _short(saved))] if saved else [],
            [KeyboardButton(text=CO_CANCEL)],
        ),
    )


@router.message(Checkout.address)
async def checkout_address(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if message.location:
        loc = message.location
        address = f"📍 Lokatsiya: https://maps.google.com/?q={loc.latitude:.6f},{loc.longitude:.6f}"
        hint = "Joylashuv qabul qilindi ✅\n\n"
    elif message.text:
        address = message.text.strip()
        saved = data.get("saved_address") or ""
        if saved and address == "🏠 " + _short(saved):
            address = saved
        hint = ""
        if not 5 <= len(address) <= 300:
            await message.answer("❗️ Manzilni to'liqroq yozing (kamida 5 belgi):")
            return
    else:
        await message.answer("Manzilni matn ko'rinishida yozing yoki joylashuv yuboring.")
        return
    await state.update_data(address=address)
    await state.set_state(Checkout.comment)
    await message.answer(
        hint + "4/4. 💬 <b>Izoh</b> (ixtiyoriy): uy/xonadon raqami, domofon, mo'ljal va h.k.",
        reply_markup=_reply_kb([KeyboardButton(text=CO_SKIP)], [KeyboardButton(text=CO_CANCEL)]),
    )


@router.message(Checkout.comment, F.text)
async def checkout_comment(message: Message, state: FSMContext) -> None:
    comment = "" if message.text == CO_SKIP else message.text.strip()[:300]
    await state.update_data(comment=comment)
    await state.set_state(Checkout.payment)
    await message.answer("💳 <b>To'lov usulini tanlang:</b>",
                         reply_markup=_reply_kb([KeyboardButton(text=CO_CANCEL)]))
    await message.answer(
        "Hozircha naqd to'lov mavjud. Karta orqali to'lov tez kunda qo'shiladi.",
        reply_markup=ikb([[("💵 Naqd", "sh:pay:cash"), ("💳 Karta · tez kunda", "sh:pay:card")]]),
    )


@router.callback_query(F.data == "sh:pay:card")
async def pay_card(call: CallbackQuery) -> None:
    await call.answer("💳 Karta orqali to'lov tez kunda ishga tushadi! Hozircha naqd to'lovni tanlang.",
                      show_alert=True)


@router.callback_query(F.data == "sh:pay:cash", Checkout.payment)
async def pay_cash(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(payment_method="cash")
    await state.set_state(Checkout.confirm)
    data = await state.get_data()
    items = await db.cart_get(call.from_user.id)
    settings = public_settings(await db.get_settings())
    subtotal = sum(i["qty"] * i["price"] for i in items)
    fee = settings["delivery_fee"]
    lines = ["🧾 <b>Buyurtmani tekshiring</b>\n"]
    for i in items:
        vn = f" ({h(i['variant_name'])})" if i["variant_name"] else ""
        lines.append(f"• {h(i['name'])}{vn} × {i['qty']} = {money(i['qty'] * i['price'])}")
    lines += [
        "",
        f"Mahsulotlar: {money(subtotal)}",
        f"Yetkazib berish: {money(fee) if fee else 'bepul'}",
        f"<b>Jami: {money(subtotal + fee)}</b>",
        f"To'lov: {PAYMENT_LABELS['cash']}",
        "",
        f"👤 {h(data['name'])}",
        f"📞 {phone_fmt(data['phone'])}",
        f"📍 {h(data['address'])}",
    ]
    if data.get("comment"):
        lines.append(f"💬 {h(data['comment'])}")
    await call.message.edit_text(
        "\n".join(lines),
        reply_markup=ikb([[("✅ Tasdiqlash", "sh:ok")], [("✏️ Qaytadan to'ldirish", "sh:co"), ("❌ Bekor qilish", "sh:no")]]),
    )
    await call.answer()


@router.callback_query(F.data == "sh:pay:cash")
async def pay_cash_stale(call: CallbackQuery) -> None:
    await call.answer("Bu forma eskirgan. Savatdan qaytadan rasmiylashtiring.", show_alert=True)


@router.callback_query(F.data == "sh:ok", Checkout.confirm)
async def checkout_confirm(call: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    items = await db.cart_get(call.from_user.id)
    raw = [{"product_id": i["product_id"], "variant": i["variant"], "qty": i["qty"]} for i in items]
    try:
        order_id = await place_order(call.from_user.id, data, raw)
    except OrderError as e:
        await call.answer(e.message, show_alert=True)
        if e.status == 409 or not items:
            await state.clear()
            text, kb = await cart_view(call.from_user.id, "⚠️ " + h(e.message))
            await show(call, text, kb)
        return
    await state.clear()
    await db.cart_clear(call.from_user.id)
    await call.answer("✅ Buyurtma yuborildi!")
    order = await db.get_order(order_id)
    await call.message.edit_text(
        "🎉 <b>Buyurtmangiz qabul qilindi!</b>\n\n"
        f"Buyurtma ID: <code>{order['code']}</code>\n"
        f"Jami: <b>{money(order['total'])}</b>\n\n"
        "Holat o'zgarganda shu yerda xabar beramiz.",
        reply_markup=ikb([[("📦 Buyurtmani kuzatish", f"sh:o:{order['code']}")]]),
    )
    await _back_to_main(call.message, "Rahmat! 😊", call.from_user.id)
    await notify_new_order(bot, order_id, notify_customer=False)


@router.callback_query(F.data == "sh:no")
async def checkout_abort(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    text, kb = await cart_view(call.from_user.id, "Rasmiylashtirish bekor qilindi. Savatingiz saqlanib qoldi.")
    await show(call, text, kb)
    await _back_to_main(call.message, "🏠 Asosiy menyu", call.from_user.id)
    await call.answer()


@router.callback_query(F.data == "sh:ok")
async def checkout_confirm_stale(call: CallbackQuery) -> None:
    await call.answer("Bu forma eskirgan. Savatdan qaytadan rasmiylashtiring.", show_alert=True)


# ====================== buyurtmalarim ======================

SHORT_STATUS = {
    "new": "Kutilmoqda", "accepted": "Qabul qilindi", "cooking": "Tayyorlanmoqda",
    "delivering": "Yetkazilmoqda", "delivered": "Yetkazildi", "cancelled": "Bekor qilindi",
}
STEPS = [("new", "Buyurtma berildi"), ("accepted", "Qabul qilindi"), ("cooking", "Tayyorlanmoqda"),
         ("delivering", "Yetkazilmoqda"), ("delivered", "Yetkazildi")]


async def orders_view(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    orders = await db.get_user_orders(user_id, limit=10)
    if not orders:
        return "Sizda hali buyurtmalar yo'q. Keling, birinchisini beramiz! 🍔", _kb([[("📋 Menyu", "sh:cats")]])
    rows = [[(f"{o['code'][-9:]} · {SHORT_STATUS[o['status']]} · {money(o['total'])}", f"sh:o:{o['code']}")]
            for o in orders]
    rows.append([("📋 Menyu", "sh:cats")])
    return "📦 <b>Buyurtmalarim</b>\n\nBatafsil ko'rish uchun tanlang:", _kb(rows)


async def order_detail_view(order: dict) -> tuple[str, InlineKeyboardMarkup]:
    items = await db.get_order_items(order["id"])
    log_rows = {r["status"]: r["at"] for r in await db.get_order_log(order["id"])}
    lines = [f"🧾 <b>Buyurtma</b> <code>{order['code']}</code>", f"🕒 {order['created_at'][:16]}", ""]
    if order["status"] == "cancelled":
        lines.append("❌ <b>Bekor qilindi</b>")
        if order["cancel_reason"]:
            lines.append(f"Sabab: {h(order['cancel_reason'])}")
    else:
        reached = [s for s, _ in STEPS].index(order["status"])
        for i, (key, label) in enumerate(STEPS):
            if i < reached or (i == reached and order["status"] == "delivered"):
                icon = "✅"
            elif i == reached:
                icon = "🔵"
            else:
                icon = "▫️"
            at = f" — {log_rows[key][11:16]}" if key in log_rows else ""
            lines.append(f"{icon} {'<b>' + label + '</b>' if i == reached else label}{at}")
    lines.append("")
    for it in items:
        vn = f" ({h(it['variant'])})" if it["variant"] else ""
        lines.append(f"• {h(it['name'])}{vn} × {it['qty']} = {money(it['price'] * it['qty'])}")
    lines.append(f"Yetkazib berish: {money(order['delivery_fee']) if order['delivery_fee'] else 'bepul'}")
    lines.append(f"<b>Jami: {money(order['total'])}</b> · {PAYMENT_LABELS.get(order['payment_method'], '')}")
    lines.append(f"\n📍 {h(order['address'])}")

    rows = []
    if order["status"] not in ("delivered", "cancelled"):
        rows.append([("🔄 Yangilash", f"sh:o:{order['code']}")])
    if order["status"] == "new":
        rows.append([("❌ Buyurtmani bekor qilish", f"sh:oc:{order['code']}")])
    if order["status"] in ("delivered", "cancelled"):
        rows.append([("🔁 Qayta buyurtma berish", f"sh:rp:{order['code']}")])
    rows.append([("⬅️ Buyurtmalarim", "sh:orders")])
    return "\n".join(lines), _kb(rows)


@router.message(StateFilter(None), F.text == B.MY_ORDERS)
@router.message(Command("orders"))
async def orders_cmd(message: Message) -> None:
    text, kb = await orders_view(message.from_user.id)
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "sh:orders")
async def orders_cb(call: CallbackQuery) -> None:
    text, kb = await orders_view(call.from_user.id)
    await show(call, text, kb)
    await call.answer()


async def _own_order(call: CallbackQuery) -> dict | None:
    order = await db.get_order_by_code(call.data.split(":", 2)[2])
    if not order or order["user_id"] != call.from_user.id:
        await call.answer("Buyurtma topilmadi", show_alert=True)
        return None
    return order


@router.callback_query(F.data.startswith("sh:o:"))
async def order_cb(call: CallbackQuery) -> None:
    order = await _own_order(call)
    if not order:
        return
    text, kb = await order_detail_view(order)
    await show(call, text, kb)
    await call.answer("🔄 Yangilandi" if call.data.startswith("sh:o:") and order["status"] not in ("delivered", "cancelled") else None)


@router.callback_query(F.data.startswith("sh:oc:"))
async def order_cancel_cb(call: CallbackQuery, bot: Bot) -> None:
    order = await _own_order(call)
    if not order:
        return
    if order["status"] != "new":
        await call.answer("Buyurtma allaqachon qabul qilingan — bekor qilish uchun kafe bilan bog'laning.",
                          show_alert=True)
        return
    await db.set_order_status(order["id"], "cancelled", call.from_user.id, "Mijoz bekor qildi")
    await refresh_staff_messages(bot, order["id"])
    text, kb = await order_detail_view(await db.get_order(order["id"]))
    await show(call, text, kb)
    await call.answer("Buyurtma bekor qilindi")


@router.callback_query(F.data.startswith("sh:rp:"))
async def order_repeat_cb(call: CallbackQuery) -> None:
    order = await _own_order(call)
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
    header = "🔁 Oldingi buyurtma savatga qo'shildi (narxlar joriy menyu bo'yicha)." if added else \
        "Afsuski, bu buyurtmadagi mahsulotlar hozir mavjud emas."
    text, kb = await cart_view(call.from_user.id, header)
    await show(call, text, kb)
    await call.answer()
