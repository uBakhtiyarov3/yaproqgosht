import asyncio
import csv
import io
import re
import uuid
from datetime import timedelta

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    KeyboardButtonRequestUsers,
    Message,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from .. import db, hours
from ..backup import send_backup
from ..catalog import BADGES, badges_of, discount_active
from ..config import config
from ..i18n import t
from ..keyboards import B, cancel_kb, ikb, main_kb, manager_kb
from ..notify import broadcast, send_post
from ..orders import public_settings
from ..roles import IsManager, lang_of
from ..utils import PAYMENT_LABELS, STATUS_LABELS, TYPE_LABELS, fmt_dt, h, money, now, status_label

router = Router(name="admin")
router.message.filter(IsManager)
router.callback_query.filter(IsManager)


class AddProduct(StatesGroup):
    name = State()
    description = State()
    prices = State()
    photo = State()


class EditProduct(StatesGroup):
    value = State()


class AddCategory(StatesGroup):
    name = State()


class RenameCategory(StatesGroup):
    name = State()


class Broadcast(StatesGroup):
    message = State()
    preview = State()
    buttons = State()


class AddStaff(StatesGroup):
    user = State()


class EditSetting(StatesGroup):
    value = State()


class FindUser(StatesGroup):
    query = State()


# ====================== umumiy ======================

@router.message(F.text == B.CANCEL)
async def cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Bekor qilindi.", reply_markup=manager_kb())


@router.message(StateFilter(None), F.text == B.MANAGER)
@router.message(Command("admin"))
async def panel(message: Message, state: FSMContext) -> None:
    await state.clear()
    s = await db.stats(now().strftime("%Y-%m-%d 00:00:00"))
    active = len(await db.get_active_orders())
    await message.answer(
        "👑 <b>Menejer paneli</b>\n\n"
        f"Holat: {await _status_line()}\n\n"
        "<b>Bugun:</b>\n"
        f"📦 Buyurtmalar: <b>{s['total_orders']}</b> (faol: {active})\n"
        f"💰 Tushum: <b>{money(s['revenue'])}</b>\n"
        f"🙋 Yangi mijozlar: <b>{s['new_users']}</b>\n"
        f"👥 Jami foydalanuvchilar: <b>{s['users_total']}</b>",
        reply_markup=manager_kb(),
    )


async def _status_line() -> str:
    raw = await db.get_settings()
    s = public_settings(raw)
    mode = {"auto": "🕒 Jadval bo'yicha", "open": "🟢 Doim ochiq", "closed": "🔴 To'xtatilgan"}[s["mode"]]
    now_state = "🟢 hozir ochiq" if s["is_open"] else "🔴 hozir yopiq"
    if s["mode"] == "auto" and not s["is_open"] and s["next_open"]:
        now_state += f" (ochiladi: {s['next_open']})"
    return f"{mode} — {now_state}" if s["mode"] == "auto" else mode


# ====================== statistika ======================

PERIODS = {"today": "Bugun", "week": "7 kun", "month": "30 kun", "all": "Barcha vaqt"}


def _since(period: str) -> str | None:
    n = now()
    if period == "today":
        return n.strftime("%Y-%m-%d 00:00:00")
    if period == "week":
        return (n - timedelta(days=6)).strftime("%Y-%m-%d 00:00:00")
    if period == "month":
        return (n - timedelta(days=29)).strftime("%Y-%m-%d 00:00:00")
    return None


def _period_kb(prefix: str, current: str | None = None):
    return ikb([[((f"• {v} •" if k == current else v), f"{prefix}:{k}") for k, v in PERIODS.items()]])


async def _stats_text(period: str) -> str:
    since = _since(period)
    s = await db.stats(since)
    bs = s["by_status"]
    lines = [
        f"📊 <b>Statistika — {PERIODS[period]}</b>\n",
        f"💰 Tushum (yetkazilgan): <b>{money(s['revenue'])}</b>",
        f"🧾 O'rtacha chek: <b>{money(s['avg_check'])}</b>",
        f"⏳ Jarayondagi summa: {money(s['pending_sum'])}",
        "",
        f"📦 Jami buyurtmalar: <b>{s['total_orders']}</b>",
    ]
    for st in ("new", "accepted", "cooking", "delivering", "delivered", "cancelled"):
        if bs.get(st):
            lines.append(f"   {STATUS_LABELS[st]}: {bs[st]}")
    bt = s["by_type"]
    if bt:
        lines.append(f"   🛵 Yetkazish: {bt.get('delivery', 0)} · 🏃 Olib ketish: {bt.get('pickup', 0)}")
    if s["promo_sum"]:
        lines.append(f"🎁 Promo-kod chegirmalari: {money(s['promo_sum'])}")
    r = s["rating"]
    if r["count"]:
        lines.append(f"⭐ O'rtacha baho: <b>{r['avg']}</b> / 5 ({r['count']} ta baho)")
    lines += [
        "",
        f"🙋 Buyurtma bergan mijozlar: {s['customers']}",
        f"🆕 Yangi foydalanuvchilar: {s['new_users']}",
        f"👥 Jami foydalanuvchilar: {s['users_total']}",
    ]
    if s["top"]:
        lines.append("\n🏆 <b>Top mahsulotlar:</b>")
        for i, row in enumerate(s["top"], 1):
            lines.append(f"{i}. {h(row['name'])} — {row['qty']} ta ({money(row['amount'])})")
    staff = await db.staff_stats(since)
    if staff:
        lines.append("\n👷 <b>Xodimlar (yetkazilgan):</b>")
        for st in staff:
            lines.append(f"• {h(st['name'])} — {st['c']} ta ({money(st['amount'])})")
    if period in ("week", "month"):
        days = await db.daily_revenue(7 if period == "week" else 30)
        if days:
            lines.append("\n📅 <b>Kunlar bo'yicha:</b>")
            for d in days[:10]:
                lines.append(f"{d['day']}: {d['orders']} ta — {money(d['amount'])}")
    return "\n".join(lines)


@router.message(StateFilter(None), F.text == B.STATS)
async def stats(message: Message) -> None:
    await message.answer(await _stats_text("today"), reply_markup=_period_kb("st", "today"))


@router.callback_query(F.data.startswith("st:"))
async def stats_period(call: CallbackQuery) -> None:
    period = call.data.split(":")[1]
    await call.message.edit_text(await _stats_text(period), reply_markup=_period_kb("st", period))
    await call.answer()


# ====================== buyurtmalar ======================

@router.message(StateFilter(None), F.text == B.ORDERS)
async def orders(message: Message) -> None:
    await _orders_list(message, "active")


async def _orders_list(message: Message, kind: str, edit: bool = False) -> None:
    if kind == "active":
        rows = await db.get_active_orders()
        title = "🔄 Faol buyurtmalar"
    elif kind == "done":
        rows = await db.get_orders_by_status(("delivered",), limit=20)
        title = "🎉 Oxirgi yetkazilganlar"
    else:
        rows = await db.get_orders_by_status(("cancelled",), limit=20)
        title = "❌ Oxirgi bekor qilinganlar"
    buttons = [
        [(f"{'🏃' if o['order_type'] == 'pickup' else '🛵'}{'⏰' if o['scheduled_at'] else ''} {o['code']} · "
          f"{status_label(o['status'], o['order_type']).split(' ', 1)[1]} · {money(o['total'])}", f"ov:{o['id']}")]
        for o in rows[:30]
    ]
    buttons.append([("🔄 Faol", "ol:active"), ("🎉 Yetkazilgan", "ol:done"), ("❌ Bekor", "ol:cancel")])
    text = f"<b>{title}</b> ({len(rows)})\n\nBatafsil ko'rish uchun buyurtmani tanlang.\n" \
           "ID bo'yicha qidirish: /order YG-482917"
    if not rows:
        text = f"<b>{title}</b>\n\nHozircha bo'sh."
    if edit:
        await message.edit_text(text, reply_markup=ikb(buttons))
    else:
        await message.answer(text, reply_markup=ikb(buttons))


@router.callback_query(F.data.startswith("ol:"))
async def orders_kind(call: CallbackQuery) -> None:
    await _orders_list(call.message, call.data.split(":")[1], edit=True)
    await call.answer()


# ====================== hisobot (CSV) ======================

@router.message(StateFilter(None), F.text == B.EXPORT)
async def export(message: Message) -> None:
    await message.answer("📥 Qaysi davr uchun hisobot kerak?", reply_markup=_period_kb("ex"))


@router.callback_query(F.data.startswith("ex:"))
async def export_period(call: CallbackQuery) -> None:
    period = call.data.split(":")[1]
    rows = await db.all_orders_for_export(_since(period))
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Buyurtma ID", "Sana", "Turi", "Vaqtga", "Holat", "Mijoz", "Telefon", "Manzil", "Mahsulotlar",
                "Summa", "Promo-kod", "Chegirma", "Yetkazish", "Jami", "To'lov", "Xodim", "Izoh"])
    for o in rows:
        w.writerow([
            o["code"], o["created_at"], TYPE_LABELS.get(o["order_type"], "").split(" ", 1)[1], o["scheduled_at"],
            status_label(o["status"], o["order_type"]).split(" ", 1)[1], o["customer_name"],
            o["phone"], o["address"], o["items"], o["subtotal"], o["promo_code"], o["discount"],
            o["delivery_fee"], o["total"],
            PAYMENT_LABELS.get(o["payment_method"], ""), o["staff_name"] or "", o["comment"] or "",
        ])
    data = ("\ufeff" + buf.getvalue()).encode("utf-8")  # BOM — Excel to'g'ri ochishi uchun
    fname = f"buyurtmalar_{period}_{now().strftime('%Y%m%d_%H%M')}.csv"
    await call.message.answer_document(
        BufferedInputFile(data, filename=fname),
        caption=f"📥 {PERIODS[period]}: {len(rows)} ta buyurtma",
    )
    await call.answer()


# ====================== web panel ======================

@router.message(StateFilter(None), F.text == B.WEB_PANEL)
async def web_panel(message: Message) -> None:
    from ..admin_api import LOGIN_CODE_MINUTES, make_login_link

    link = await make_login_link(message.from_user.id)
    rows = []
    if link.startswith("https://"):
        rows.append([InlineKeyboardButton(text="🌐 Brauzerda ochish", url=link)])
        rows.append([InlineKeyboardButton(text="📱 Telegram ichida ochish",
                                          web_app=WebAppInfo(url=link.split("#", 1)[0]))])
    await message.answer(
        "🖥 <b>Admin web panel</b>\n\n"
        "Panelda botning hamma narsasini boshqarasiz: menyu, kategoriyalar, rasmlar, narxlar, chegirmalar, "
        "barcha xabar matnlari, ish vaqti, sozlamalar, promo-kodlar, buyurtmalar, rassilka va hisobotlar.\n"
        "Saqlash tugmasi bosilishi bilan bot darhol yangilanadi.\n\n"
        f"🔐 Havola bir martalik va {LOGIN_CODE_MINUTES} daqiqa amal qiladi. Uni hech kimga bermang!"
        + ("" if rows else f"\n\n<code>{h(link)}</code>"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if rows else None,
        disable_web_page_preview=True,
    )


# ====================== zaxira nusxa ======================

@router.message(StateFilter(None), F.text == B.BACKUP)
async def backup(message: Message, bot: Bot) -> None:
    await message.answer("⏳ Zaxira nusxa tayyorlanmoqda...")
    await send_backup(bot, [message.chat.id])
    await message.answer("ℹ️ Har kuni soat 04:00 da zaxira nusxa bosh menejerga avtomatik yuboriladi.")


# ====================== mijozlar ======================

@router.message(StateFilter(None), F.text == B.USERS)
async def users(message: Message, state: FSMContext) -> None:
    total = await db.scalar("SELECT COUNT(*) FROM users")
    blocked = await db.scalar("SELECT COUNT(*) FROM users WHERE is_blocked = 1")
    with_orders = await db.scalar("SELECT COUNT(DISTINCT user_id) FROM orders")
    top = await db.fetchall(
        "SELECT u.id, COALESCE(u.full_name, u.first_name) name, u.phone, COUNT(o.id) c, SUM(o.total) s"
        " FROM orders o JOIN users u ON u.id = o.user_id WHERE o.status = 'delivered'"
        " GROUP BY u.id ORDER BY s DESC LIMIT 10"
    )
    lines = [
        "🙋 <b>Mijozlar</b>\n",
        f"Jami: <b>{total}</b>",
        f"Buyurtma berganlar: <b>{with_orders}</b>",
        f"Botni bloklaganlar: {blocked}",
    ]
    if top:
        lines.append("\n🏆 <b>Eng faol mijozlar:</b>")
        for i, u in enumerate(top, 1):
            lines.append(f"{i}. {h(u['name'])} ({h(u['phone'] or '-')}) — {u['c']} ta, {money(u['s'])}")
    await message.answer("\n".join(lines), reply_markup=ikb([[("🔍 Mijozni qidirish", "ufind")]]))


@router.callback_query(F.data == "ufind")
async def user_find_start(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(FindUser.query)
    await call.message.answer("Mijoz ID si, @username yoki telefon raqamini yuboring:", reply_markup=cancel_kb())
    await call.answer()


@router.message(FindUser.query, F.text)
async def user_find(message: Message, state: FSMContext) -> None:
    q = message.text.strip()
    user = await db.find_user(q)
    if not user:
        digits = re.sub(r"\D", "", q)
        if digits:
            user = await db.fetchone("SELECT * FROM users WHERE phone LIKE ?", f"%{digits[-9:]}")
    if not user:
        await message.answer("Topilmadi. Qaytadan yuboring yoki bekor qiling.")
        return
    await state.clear()
    st = await db.fetchone(
        "SELECT COUNT(*) c, COALESCE(SUM(total), 0) s FROM orders WHERE user_id = ? AND status = 'delivered'",
        user["id"],
    )
    last = await db.get_user_orders(user["id"], limit=5)
    lines = [
        f"👤 <b>{h(user['full_name'] or user['first_name'])}</b>",
        f"ID: <code>{user['id']}</code>",
        f"Username: @{h(user['username'])}" if user["username"] else "Username: -",
        f"Telefon: {h(user['phone'] or '-')}",
        f"Manzil: {h(user['address'] or '-')}",
        f"Rol: {user['role']}",
        f"Ro'yxatdan o'tgan: {user['created_at'][:16]}",
        f"Yetkazilgan buyurtmalar: {st['c']} ta, {money(st['s'])}",
    ]
    if last:
        lines.append("\nOxirgi buyurtmalar:")
        lines += [f"{o['code']} — {money(o['total'])} — {status_label(o['status'], o['order_type'])}" for o in last]
    await message.answer("\n".join(lines), reply_markup=manager_kb())


# ====================== rassilka ======================

_album_buffer: dict[tuple[int, str], list[int]] = {}
URL_RE = re.compile(r"^(.+?)\s*[-|–—]\s*((?:https?://|tg://)\S+)$")


def _broadcast_markup(data: dict) -> InlineKeyboardMarkup | None:
    rows = [[InlineKeyboardButton(text=t, url=u)] for t, u in data.get("buttons", [])]
    if data.get("order_btn"):
        rows.append([InlineKeyboardButton(text="📋 Buyurtma berish", callback_data="sh:cats")])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def _url_buttons(markup: InlineKeyboardMarkup | None) -> list[list[str]]:
    """Kanal postidagi URL tugmalarni saqlab qolish uchun."""
    if not markup:
        return []
    return [[b.text, b.url] for row in markup.inline_keyboard for b in row if b.url]


@router.message(StateFilter(None), F.text == B.BROADCAST)
async def broadcast_start(message: Message, state: FSMContext) -> None:
    count = len(await db.all_user_ids())
    await state.set_state(Broadcast.message)
    await message.answer(
        f"📢 <b>Barchaga xabar yuborish</b> ({count} ta foydalanuvchi)\n\n"
        "Postni shu yerga yuboring — u qanday bo'lsa, foydalanuvchilarga xuddi shunday boradi:\n"
        "• matn, rasm yoki video (izohi bilan)\n"
        "• 🖼 albom — bir nechta rasm/video birga\n"
        "• ↪️ kanaldagi <b>tayyor rasmli postni forward qiling</b> (tugmalari ham saqlanadi)\n\n"
        "Keyin xohlasangiz havola tugma yoki «Buyurtma berish» tugmasini qo'shasiz.",
        reply_markup=cancel_kb(),
    )


@router.message(Broadcast.message)
async def broadcast_receive(message: Message, state: FSMContext, bot: Bot) -> None:
    if message.media_group_id:
        key = (message.chat.id, message.media_group_id)
        first = key not in _album_buffer
        _album_buffer.setdefault(key, []).append(message.message_id)
        if not first:
            return
        await asyncio.sleep(1.5)  # albomning qolgan qismlari kelishini kutamiz
        ids = sorted(_album_buffer.pop(key, []))
    else:
        ids = [message.message_id]
    forwarded = bool(message.forward_origin)
    await state.update_data(
        chat_id=message.chat.id, message_ids=ids, mode="copy", order_btn=False,
        buttons=_url_buttons(message.reply_markup), forwarded=forwarded,
    )
    await state.set_state(Broadcast.preview)
    await _broadcast_preview(message, state, bot)


async def _broadcast_preview(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    album = len(data["message_ids"]) > 1
    markup = _broadcast_markup(data)
    await message.answer("👇 <b>Foydalanuvchilar ko'radigan ko'rinish:</b>", reply_markup=cancel_kb())
    await send_post(bot, message.chat.id, data["chat_id"], data["message_ids"], data["mode"], markup)

    count = len(await db.all_user_ids())
    notes = [f"👥 Qabul qiluvchilar: <b>{count}</b>",
             f"Turi: {'🖼 albom (' + str(len(data['message_ids'])) + ' ta)' if album else '📄 bitta post'}",
             f"Rejim: {'↪️ Forward (manba ko`rinadi)' if data['mode'] == 'forward' else '📋 Nusxa (bot nomidan)'}"]
    can_buttons = data["mode"] == "copy" and not album
    if not can_buttons:
        notes.append("ℹ️ Albom va forward rejimida qo'shimcha tugmalar biriktirilmaydi.")
    rows = [[(f"✅ Yuborish ({count} ta)", "bc:send")]]
    if can_buttons:
        rows.append([("🔗 Havola tugma qo'shish", "bc:link"),
                     (("✅ " if data.get("order_btn") else "➕ ") + "«Buyurtma berish» tugmasi", "bc:order")])
        if data.get("buttons"):
            rows.append([("🗑 Havola tugmalarni o'chirish", "bc:clear")])
    rows.append([("📋 Nusxa rejimi" if data["mode"] == "forward" else "↪️ Forward rejimi", "bc:mode")])
    rows.append([("🚫 Bekor qilish", "bc:no")])
    await message.answer("\n".join(notes), reply_markup=ikb(rows))


@router.callback_query(F.data.in_({"bc:order", "bc:mode", "bc:clear"}), Broadcast.preview)
async def broadcast_toggle(call: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    if call.data == "bc:order":
        await state.update_data(order_btn=not data.get("order_btn"))
    elif call.data == "bc:mode":
        await state.update_data(mode="copy" if data["mode"] == "forward" else "forward")
    else:
        await state.update_data(buttons=[])
    await call.message.delete()
    await call.answer()
    await _broadcast_preview(call.message, state, bot)


@router.callback_query(F.data == "bc:link", Broadcast.preview)
async def broadcast_link_start(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Broadcast.buttons)
    await call.message.answer(
        "🔗 Tugmalarni yuboring — har bir qatorda bitta:\n"
        "<code>Matn - https://havola</code>\n\n"
        "Masalan:\n<code>Instagram - https://instagram.com/yaproqgosht\n"
        "Kanalimiz - https://t.me/yaproqgosht</code>",
        reply_markup=cancel_kb(),
    )
    await call.answer()


@router.message(Broadcast.buttons, F.text)
async def broadcast_link_save(message: Message, state: FSMContext, bot: Bot) -> None:
    buttons = []
    for line in message.text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        m = URL_RE.match(line)
        if not m:
            await message.answer(f"❗️ Format noto'g'ri: <code>{h(line)}</code>\nTo'g'ri: <code>Matn - https://havola</code>")
            return
        buttons.append([m.group(1)[:40], m.group(2)])
    data = await state.get_data()
    await state.update_data(buttons=(data.get("buttons") or []) + buttons)
    await state.set_state(Broadcast.preview)
    await _broadcast_preview(message, state, bot)


@router.callback_query(F.data.in_({"bc:send", "bc:no"}), Broadcast.preview)
async def broadcast_confirm(call: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    await state.clear()
    if call.data == "bc:no":
        await call.message.edit_text("Rassilka bekor qilindi.")
        await call.message.answer("Menejer paneli", reply_markup=manager_kb())
        await call.answer()
        return
    await call.message.edit_text("⏳ Yuborilmoqda...")
    await call.message.answer("Rassilka fonda ketmoqda, tugagach xabar beraman.", reply_markup=manager_kb())
    await call.answer()
    markup = _broadcast_markup(data)

    async def run():
        async def progress(i, total):
            try:
                await call.message.edit_text(f"⏳ Yuborilmoqda... {i}/{total}")
            except Exception:
                pass
        ok, fail = await broadcast(bot, data["chat_id"], data["message_ids"], data["mode"], markup, progress)
        await call.message.edit_text(f"✅ Rassilka tugadi!\n\nYuborildi: {ok}\nYetib bormadi: {fail}")

    asyncio.create_task(run())


@router.callback_query(F.data.startswith("bc:"))
async def broadcast_stale(call: CallbackQuery) -> None:
    await call.answer("Bu rassilka eskirgan. «📢 Xabar yuborish» ni qaytadan bosing.", show_alert=True)


# ====================== xodimlar ======================

ROLE_NAMES = {"staff": "👷 Xodim", "manager": "👑 Menejer"}


async def _staff_view() -> tuple[str, list]:
    staff = await db.get_staff()
    lines = ["👥 <b>Xodimlar</b>\n"]
    lines += [f"👑 Bosh menejer: <code>{a}</code>" for a in sorted(config.admin_ids)]
    buttons = []
    for u in staff:
        name = h(u["full_name"] or u["first_name"] or u["id"])
        lines.append(f"{ROLE_NAMES[u['role']]}: {name} (<code>{u['id']}</code>)")
        buttons.append([(f"🗑 {u['first_name'] or u['id']} ni olib tashlash", f"srm:{u['id']}")])
    if not staff:
        lines.append("\nHali xodim qo'shilmagan.")
    lines.append("\nYangi buyurtma barcha xodim va menejerlarga yuboriladi.")
    buttons.append([("➕ Xodim qo'shish", "sadd:staff"), ("➕ Menejer qo'shish", "sadd:manager")])
    return "\n".join(lines), buttons


@router.message(StateFilter(None), F.text == B.STAFF_LIST)
async def staff_list(message: Message) -> None:
    text, buttons = await _staff_view()
    await message.answer(text, reply_markup=ikb(buttons))


@router.callback_query(F.data.startswith("sadd:"))
async def staff_add_start(call: CallbackQuery, state: FSMContext) -> None:
    role = call.data.split(":")[1]
    await state.set_state(AddStaff.user)
    await state.update_data(role=role)
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Kontaktlardan tanlash",
                            request_users=KeyboardButtonRequestUsers(request_id=1, user_is_bot=False))],
            [KeyboardButton(text=B.CANCEL)],
        ],
        resize_keyboard=True,
    )
    await call.message.answer(
        f"{ROLE_NAMES[role]} qo'shish.\n\n"
        "Pastdagi tugma orqali kontaktlardan tanlang yoki uning Telegram <b>ID</b> raqamini / "
        "<b>@username</b> ini yuboring (username uchun u avval botga /start bosgan bo'lishi kerak).",
        reply_markup=kb,
    )
    await call.answer()


@router.message(AddStaff.user)
async def staff_add(message: Message, state: FSMContext, bot: Bot) -> None:
    role = (await state.get_data())["role"]
    user = None
    if message.users_shared:
        uid = message.users_shared.user_ids[0]
        user = await db.get_user(uid)
        if not user:
            await db.upsert_user(uid, "", None, None)
            user = await db.get_user(uid)
    elif message.text:
        user = await db.find_user(message.text)
        if not user and message.text.strip().isdigit():
            await db.upsert_user(int(message.text.strip()), "", None, None)
            user = await db.get_user(int(message.text.strip()))
    if not user:
        await message.answer("❗️ Foydalanuvchi topilmadi. U avval botga /start bosishi kerak yoki ID yuboring.")
        return
    await db.set_role(user["id"], role)
    await state.clear()
    await message.answer(f"✅ {ROLE_NAMES[role]} qo'shildi: <code>{user['id']}</code>", reply_markup=manager_kb())
    try:
        await bot.send_message(
            user["id"],
            f"🎉 Sizga <b>Yaproq go'sht</b> botida {ROLE_NAMES[role]} huquqi berildi!\n"
            "Endi yangi buyurtmalar haqida xabar olasiz. /start bosing.",
            reply_markup=main_kb(role),
        )
    except Exception:
        await message.answer("ℹ️ Unga xabar yuborib bo'lmadi — u botga /start bosishi kerak.")


@router.callback_query(F.data.startswith("srm:"))
async def staff_remove(call: CallbackQuery, bot: Bot) -> None:
    uid = int(call.data.split(":")[1])
    await db.set_role(uid, "user")
    text, buttons = await _staff_view()
    await call.message.edit_text(text, reply_markup=ikb(buttons))
    await call.answer("Olib tashlandi")
    try:
        await bot.send_message(uid, "Sizning xodim huquqingiz olib tashlandi.", reply_markup=main_kb("user"))
    except Exception:
        pass


# ====================== sozlamalar ======================

SETTING_PROMPTS = {
    "delivery_fee": "🚚 Yetkazib berish narxini yuboring (so'mda, 0 — bepul):",
    "min_order": "🧾 Yetkazib berish uchun minimal buyurtma summasini yuboring (so'mda, 0 — cheklovsiz):",
    "phone": "📞 Kafe telefon raqamini yuboring:",
    "cafe_address": "📍 Kafe manzilini yuboring (olib ketish uchun mijozlarga ko'rsatiladi):",
    "prep_time": "⏱ Vaqtga buyurtma uchun minimal tayyorlash vaqtini yuboring (daqiqada, masalan 40):",
    "slot_step": "⏲ Vaqt tanlash qadamini yuboring (daqiqada: 15, 20, 30 yoki 60):",
}
NUMERIC_SETTINGS = {"delivery_fee", "min_order", "prep_time", "slot_step"}
MODES = ["auto", "open", "closed"]
MODE_LABELS = {"auto": "🕒 Jadval bo'yicha (avtomatik)", "open": "🟢 Doim ochiq", "closed": "🔴 To'xtatilgan"}


async def _settings_view() -> tuple[str, list]:
    s = await db.get_settings()
    yes = lambda key: s.get(key, "1") == "1"  # noqa: E731
    fee, min_order = int(s["delivery_fee"] or 0), int(s["min_order"] or 0)
    text = (
        "⚙️ <b>Sozlamalar</b>\n\n"
        f"Holat: {await _status_line()}\n"
        f"🗓 Ish jadvali: {h(hours.schedule_summary(s))}\n\n"
        f"🛵 Yetkazib berish: {'✅ yoqilgan' if yes('delivery_enabled') else '❌ o`chirilgan'}\n"
        f"   Narxi: {money(fee) if fee else 'bepul'} · Minimal: {money(min_order) if min_order else 'cheklovsiz'}\n"
        f"🏃 Olib ketish: {'✅ yoqilgan' if yes('pickup_enabled') else '❌ o`chirilgan'}\n"
        f"📍 Kafe manzili: {h(s.get('cafe_address') or '-')}\n"
        f"📞 Telefon: {h(s.get('phone') or '-')}\n"
        f"⏱ Vaqtga buyurtma: kamida {s.get('prep_time')} daqiqa oldin, har {s.get('slot_step')} daqiqada\n"
        "💳 Karta orqali to'lov: tez kunda"
    )
    buttons = [
        [("Rejim: " + MODE_LABELS[s.get("mode") or "auto"] + " 🔁", "set:mode")],
        [("🗓 Ish jadvalini sozlash", "sch:view")],
        [(("✅" if yes("delivery_enabled") else "❌") + " Yetkazib berish", "set:tgl:delivery_enabled"),
         (("✅" if yes("pickup_enabled") else "❌") + " Olib ketish", "set:tgl:pickup_enabled")],
        [("🚚 Yetkazish narxi", "set:delivery_fee"), ("🧾 Minimal summa", "set:min_order")],
        [("📍 Kafe manzili", "set:cafe_address"), ("📞 Telefon", "set:phone")],
        [("⏱ Tayyorlash vaqti", "set:prep_time"), ("⏲ Vaqt qadami", "set:slot_step")],
    ]
    return text, buttons


async def _refresh_settings(call: CallbackQuery) -> None:
    text, buttons = await _settings_view()
    await call.message.edit_text(text, reply_markup=ikb(buttons))


@router.message(StateFilter(None), F.text == B.SETTINGS)
async def settings(message: Message) -> None:
    text, buttons = await _settings_view()
    await message.answer(text, reply_markup=ikb(buttons))


@router.callback_query(F.data == "set:mode")
async def settings_mode(call: CallbackQuery) -> None:
    cur = await db.get_setting("mode") or "auto"
    new = MODES[(MODES.index(cur) + 1) % len(MODES)] if cur in MODES else "auto"
    await db.set_setting("mode", new)
    await _refresh_settings(call)
    await call.answer(MODE_LABELS[new])


@router.callback_query(F.data.startswith("set:tgl:"))
async def settings_toggle(call: CallbackQuery) -> None:
    key = call.data.split(":")[2]
    s = await db.get_settings()
    new = "0" if s.get(key, "1") == "1" else "1"
    other = "pickup_enabled" if key == "delivery_enabled" else "delivery_enabled"
    if new == "0" and s.get(other, "1") != "1":
        await call.answer("Kamida bittasi (yetkazish yoki olib ketish) yoqilgan bo'lishi kerak", show_alert=True)
        return
    await db.set_setting(key, new)
    await _refresh_settings(call)
    await call.answer("Saqlandi")


@router.callback_query(F.data.startswith("set:"))
async def settings_edit(call: CallbackQuery, state: FSMContext) -> None:
    key = call.data.split(":")[1]
    if key not in SETTING_PROMPTS:
        await call.answer()
        return
    await state.set_state(EditSetting.value)
    await state.update_data(key=key)
    await call.message.answer(SETTING_PROMPTS[key], reply_markup=cancel_kb())
    await call.answer()


@router.message(EditSetting.value, F.text)
async def settings_save(message: Message, state: FSMContext) -> None:
    key = (await state.get_data())["key"]
    value = message.text.strip()
    if key in NUMERIC_SETTINGS:
        digits = re.sub(r"\D", "", value)
        if not digits:
            await message.answer("Faqat raqam yuboring, masalan: 10000")
            return
        value = str(int(digits))
        if key == "slot_step" and not 10 <= int(value) <= 120:
            await message.answer("Qadam 10 dan 120 daqiqagacha bo'lsin")
            return
        if key == "prep_time" and not 10 <= int(value) <= 600:
            await message.answer("Tayyorlash vaqti 10 dan 600 daqiqagacha bo'lsin")
            return
    await db.set_setting(key, value[:200])
    await state.clear()
    await message.answer("✅ Saqlandi", reply_markup=manager_kb())
    text, buttons = await _settings_view()
    await message.answer(text, reply_markup=ikb(buttons))


# ====================== menyu boshqaruvi ======================

def parse_prices(text: str) -> list[dict] | None:
    """'15000' yoki har qatorda 'O'rta 15000' / 'Katta - 20 000' formatini o'qiydi."""
    variants = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(.*?)[\s:\-–—=]*(\d[\d\s]*)\s*(so'm|сум|sum)?$", line, re.IGNORECASE)
        if not m:
            return None
        price = int(re.sub(r"\s", "", m.group(2)))
        if price <= 0 or price > 10_000_000:
            return None
        variants.append({"name": m.group(1).strip(), "price": price})
    if not variants:
        return None
    if len(variants) > 1 and any(not v["name"] for v in variants):
        return None
    return variants


def variants_text(variants: list[dict]) -> str:
    return " / ".join(f"{v['name']} {money(v['price'])}".strip() for v in variants)


async def _menu_view() -> tuple[str, list]:
    cats = await db.get_categories()
    buttons = []
    for c in cats:
        count = len(await db.get_products(c["id"]))
        hidden = "" if c["is_active"] else " 🙈"
        buttons.append([(f"{c['emoji']} {c['name']} ({count}){hidden}", f"cat:{c['id']}")])
    buttons.append([("➕ Kategoriya qo'shish", "cadd")])
    return "🍔 <b>Menyuni boshqarish</b>\n\nKategoriyani tanlang:", buttons


@router.message(StateFilter(None), F.text == B.MENU_EDIT)
async def menu_edit(message: Message) -> None:
    text, buttons = await _menu_view()
    await message.answer(text, reply_markup=ikb(buttons))


@router.callback_query(F.data == "menu")
async def menu_back(call: CallbackQuery) -> None:
    text, buttons = await _menu_view()
    await _edit_or_send(call, text, buttons)


async def _edit_or_send(call: CallbackQuery, text: str, buttons: list) -> None:
    """Rasmli xabarni matnga aylantirib bo'lmaydi — o'chirib yangisini yuboramiz."""
    if call.message.photo:
        await call.message.delete()
        await call.message.answer(text, reply_markup=ikb(buttons))
    else:
        await call.message.edit_text(text, reply_markup=ikb(buttons))
    await call.answer()


async def _category_view(cat_id: int) -> tuple[str, list]:
    cat = await db.get_category(cat_id)
    products = await db.get_products(cat_id)
    buttons = [
        [(f"{'' if p['is_available'] else '🚫 '}{p['name']} — {money(p['variants'][0]['price'])}", f"pr:{p['id']}")]
        for p in products
    ]
    buttons.append([("➕ Mahsulot qo'shish", f"padd:{cat_id}")])
    buttons.append([("🇷🇺 Ruscha nom" + (f": {cat['name_ru']}" if cat.get("name_ru") else ""), f"cru:{cat_id}")])
    buttons.append([
        ("✏️ Nomi / emoji", f"cren:{cat_id}"),
        ("🙈 Yashirish" if cat["is_active"] else "👁 Ko'rsatish", f"ctg:{cat_id}"),
    ])
    buttons.append([("⬆️ Yuqoriga", f"cmv:{cat_id}:-1"), ("⬇️ Pastga", f"cmv:{cat_id}:1")])
    buttons.append([("🗑 Kategoriyani o'chirish", f"cdl:{cat_id}"), ("⬅️ Ortga", "menu")])
    status = "" if cat["is_active"] else "\n🙈 Bu kategoriya mijozlarga ko'rinmaydi."
    text = f"{cat['emoji']} <b>{h(cat['name'])}</b> — {len(products)} ta mahsulot{status}\n\n" \
           "🚫 — sotuvda yo'q (mijozlarga ko'rinmaydi)"
    return text, buttons


@router.callback_query(F.data.startswith("cat:"))
async def category(call: CallbackQuery) -> None:
    text, buttons = await _category_view(int(call.data.split(":")[1]))
    await _edit_or_send(call, text, buttons)


@router.callback_query(F.data.startswith("ctg:"))
async def category_toggle(call: CallbackQuery) -> None:
    cat_id = int(call.data.split(":")[1])
    await db.execute("UPDATE categories SET is_active = 1 - is_active WHERE id = ?", cat_id)
    text, buttons = await _category_view(cat_id)
    await _edit_or_send(call, text, buttons)


@router.callback_query(F.data.startswith("cmv:"))
async def category_move(call: CallbackQuery) -> None:
    """Kategoriyani tartibda bir pog'ona yuqoriga/pastga suradi (mini appdagi tartib ham o'zgaradi)."""
    _, cat_id, delta = call.data.split(":")
    cat_id, delta = int(cat_id), int(delta)
    cats = await db.get_categories()
    ids = [c["id"] for c in cats]
    i = ids.index(cat_id)
    j = i + delta
    if not 0 <= j < len(ids):
        await call.answer("Bu chekka pozitsiya")
        return
    ids[i], ids[j] = ids[j], ids[i]
    for pos, cid in enumerate(ids):
        await db.db().execute("UPDATE categories SET sort = ? WHERE id = ?", (pos, cid))
    await db.db().commit()
    text, buttons = await _category_view(cat_id)
    await _edit_or_send(call, text + f"\n\n📍 Tartibdagi o'rni: {j + 1}/{len(ids)}", buttons)


@router.callback_query(F.data.startswith("cdl:"))
async def category_delete_ask(call: CallbackQuery) -> None:
    cat_id = int(call.data.split(":")[1])
    if await db.get_products(cat_id):
        await call.answer(
            "Kategoriyada mahsulotlar bor. Avval ularni boshqa kategoriyaga ko'chiring yoki o'chiring "
            "(yoki kategoriyani shunchaki yashiring).", show_alert=True,
        )
        return
    await call.message.edit_reply_markup(
        reply_markup=ikb([[("✅ Ha, o'chirish", f"cdy:{cat_id}"), ("🚫 Yo'q", f"cat:{cat_id}")]])
    )
    await call.answer("Rostdan o'chirasizmi?")


@router.callback_query(F.data.startswith("cdy:"))
async def category_delete(call: CallbackQuery) -> None:
    cat_id = int(call.data.split(":")[1])
    if await db.get_products(cat_id):
        await call.answer("Kategoriyada mahsulotlar bor", show_alert=True)
        return
    # buyurtma tarixi mahsulot nomini o'zida saqlaydi, shuning uchun o'chirilgan mahsulot qatorlari kerak emas
    await db.execute("DELETE FROM products WHERE category_id = ? AND is_deleted = 1", cat_id)
    await db.execute("DELETE FROM categories WHERE id = ?", cat_id)
    await call.answer("Kategoriya o'chirildi")
    text, buttons = await _menu_view()
    await _edit_or_send(call, text, buttons)


@router.callback_query(F.data == "cadd")
async def category_add_start(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddCategory.name)
    await call.message.answer("Yangi kategoriya nomini yuboring (boshida emoji bo'lishi mumkin, masalan: ☕ Ichimliklar):",
                              reply_markup=cancel_kb())
    await call.answer()


def _split_emoji(text: str) -> tuple[str, str]:
    text = text.strip()
    first, _, rest = text.partition(" ")
    if rest and not any(ch.isalnum() for ch in first):
        return first, rest.strip()
    return "", text


@router.message(AddCategory.name, F.text)
async def category_add(message: Message, state: FSMContext) -> None:
    emoji, name = _split_emoji(message.text)
    cat_id = await db.add_category(name[:40], emoji)
    await state.clear()
    await message.answer("✅ Kategoriya qo'shildi", reply_markup=manager_kb())
    text, buttons = await _category_view(cat_id)
    await message.answer(text, reply_markup=ikb(buttons))


class CategoryRu(StatesGroup):
    name = State()


@router.callback_query(F.data.startswith("cru:"))
async def category_ru_start(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CategoryRu.name)
    await state.update_data(cat_id=int(call.data.split(":")[1]))
    await call.message.answer("🇷🇺 Kategoriyaning ruscha nomini yuboring (o'chirish uchun «-»):",
                              reply_markup=cancel_kb())
    await call.answer()


@router.message(CategoryRu.name, F.text)
async def category_ru_save(message: Message, state: FSMContext) -> None:
    cat_id = (await state.get_data())["cat_id"]
    value = "" if message.text.strip() == "-" else message.text.strip()[:40]
    await db.execute("UPDATE categories SET name_ru = ? WHERE id = ?", value, cat_id)
    await state.clear()
    await message.answer("✅ Saqlandi", reply_markup=manager_kb())
    text, buttons = await _category_view(cat_id)
    await message.answer(text, reply_markup=ikb(buttons))


@router.callback_query(F.data.startswith("cren:"))
async def category_rename_start(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(RenameCategory.name)
    await state.update_data(cat_id=int(call.data.split(":")[1]))
    await call.message.answer("Kategoriyaning yangi nomini yuboring (emoji bilan):", reply_markup=cancel_kb())
    await call.answer()


@router.message(RenameCategory.name, F.text)
async def category_rename(message: Message, state: FSMContext) -> None:
    cat_id = (await state.get_data())["cat_id"]
    emoji, name = _split_emoji(message.text)
    await db.execute("UPDATE categories SET name = ?, emoji = ? WHERE id = ?", name[:40], emoji, cat_id)
    await state.clear()
    await message.answer("✅ Saqlandi", reply_markup=manager_kb())
    text, buttons = await _category_view(cat_id)
    await message.answer(text, reply_markup=ikb(buttons))


# ---------- mahsulot kartasi ----------

def _product_caption(p: dict, cat: dict | None) -> str:
    badges = ", ".join(BADGES[b]["uz"] for b in badges_of(p)) or "-"
    pct = discount_active(p)
    if pct:
        until = f" ({fmt_dt(p['discount_until'])} gacha)" if p.get("discount_until") else " (muddatsiz)"
        discount = f"-{pct}%{until}"
    elif p.get("discount_percent"):
        discount = "muddati tugagan"
    else:
        discount = "-"
    return (
        f"<b>{h(p['name'])}</b>\n"
        f"{h(p['description'])}\n\n"
        f"🇷🇺 {h(p.get('name_ru') or '— (ruscha nom yo`q)')}\n"
        f"<i>{h(p.get('description_ru') or '')}</i>\n\n"
        f"💰 {h(variants_text(p['variants']))}\n"
        f"💸 Chegirma: {discount}\n"
        f"🏷 Belgilar: {badges}\n"
        f"📂 {h(cat['name']) if cat else '-'}\n"
        f"Holat: {'✅ Sotuvda' if p['is_available'] else '🚫 Sotuvda yo`q'}"
    )


def _product_buttons(p: dict) -> list:
    pid = p["id"]
    return [
        [("✏️ Nomi", f"pe:{pid}:name"), ("📝 Tavsif", f"pe:{pid}:description")],
        [("🇷🇺 Ruscha nom", f"pe:{pid}:name_ru"), ("🇷🇺 Ruscha tavsif", f"pe:{pid}:description_ru")],
        [("💰 Narx", f"pe:{pid}:variants"), ("💸 Chegirma", f"pe:{pid}:discount")],
        [("🏷 Belgilar (Hit/Yangi/Top)", f"pbg:{pid}"), ("🖼 Rasm", f"pe:{pid}:image")],
        [("🚫 Sotuvdan olish" if p["is_available"] else "✅ Sotuvga qo'yish", f"ptg:{pid}"),
         ("📂 Kategoriya", f"pcat:{pid}")],
        [("🗑 O'chirish", f"pdl:{pid}"), ("⬅️ Ortga", f"cat:{p['category_id']}")],
    ]


async def _refresh_product_card(call: CallbackQuery, pid: int) -> None:
    p = await db.get_product(pid)
    caption = _product_caption(p, await db.get_category(p["category_id"]))
    if call.message.photo:
        await call.message.edit_caption(caption=caption, reply_markup=ikb(_product_buttons(p)))
    else:
        await call.message.edit_text(caption, reply_markup=ikb(_product_buttons(p)))


@router.callback_query(F.data.startswith("pbg:"))
async def product_badges(call: CallbackQuery) -> None:
    pid = int(call.data.split(":")[1])
    p = await db.get_product(pid)
    current = badges_of(p)
    rows = [[(("✅ " if b in current else "▫️ ") + BADGES[b]["uz"], f"pbt:{pid}:{b}")] for b in BADGES]
    rows.append([("✔️ Tayyor", f"pbd:{pid}")])
    await call.message.edit_reply_markup(reply_markup=ikb(rows))
    await call.answer("Belgilarni yoqing yoki o'chiring")


@router.callback_query(F.data.startswith("pbt:"))
async def product_badge_toggle(call: CallbackQuery) -> None:
    _, pid, badge = call.data.split(":")
    p = await db.get_product(int(pid))
    current = badges_of(p)
    current = [b for b in current if b != badge] if badge in current else current + [badge]
    await db.update_product(int(pid), badges=",".join(current))
    await product_badges(call)


@router.callback_query(F.data.startswith("pbd:"))
async def product_badges_done(call: CallbackQuery) -> None:
    await _refresh_product_card(call, int(call.data.split(":")[1]))
    await call.answer("Saqlandi")


def _image_input(image: str):
    """Mahsulot rasmi lokal faylda saqlanadi (webapp/img/... yoki data/uploads/...)."""
    if not image:
        return None
    if image.startswith("uploads/"):
        path = config.uploads_dir / image.removeprefix("uploads/")
    else:
        path = config.webapp_dir / image
    return FSInputFile(path) if path.exists() else None


async def send_product_card(message: Message, product_id: int) -> None:
    p = await db.get_product(product_id)
    cat = await db.get_category(p["category_id"])
    caption = _product_caption(p, cat)
    kb = ikb(_product_buttons(p))
    photo = _image_input(p["image"])
    if photo:
        await message.answer_photo(photo, caption=caption, reply_markup=kb)
    else:
        await message.answer(caption + "\n\n🖼 Rasm yo'q", reply_markup=kb)


@router.callback_query(F.data.startswith("pr:"))
async def product(call: CallbackQuery) -> None:
    await call.message.delete()
    await send_product_card(call.message, int(call.data.split(":")[1]))
    await call.answer()


@router.callback_query(F.data.startswith("ptg:"))
async def product_toggle(call: CallbackQuery) -> None:
    pid = int(call.data.split(":")[1])
    p = await db.get_product(pid)
    await db.update_product(pid, is_available=0 if p["is_available"] else 1)
    await _refresh_product_card(call, pid)
    await call.answer("Saqlandi")


@router.callback_query(F.data.startswith("pcat:"))
async def product_category_choose(call: CallbackQuery) -> None:
    pid = int(call.data.split(":")[1])
    p = await db.get_product(pid)
    rows = [
        [(("✅ " if c["id"] == p["category_id"] else "") + f"{c['emoji']} {c['name']}", f"pmv:{pid}:{c['id']}")]
        for c in await db.get_categories()
    ]
    rows.append([("⬅️ Ortga", f"pr:{pid}")])
    await call.message.edit_reply_markup(reply_markup=ikb(rows))
    await call.answer("Yangi kategoriyani tanlang")


@router.callback_query(F.data.startswith("pmv:"))
async def product_category_move(call: CallbackQuery) -> None:
    _, pid, cat_id = call.data.split(":")
    await db.update_product(int(pid), category_id=int(cat_id))
    await call.answer("Ko'chirildi")
    await call.message.delete()
    await send_product_card(call.message, int(pid))


@router.callback_query(F.data.startswith("pdl:"))
async def product_delete_ask(call: CallbackQuery) -> None:
    pid = int(call.data.split(":")[1])
    await call.message.edit_reply_markup(
        reply_markup=ikb([[("✅ Ha, o'chirish", f"pdy:{pid}"), ("🚫 Yo'q", f"pr:{pid}")]])
    )
    await call.answer("Rostdan o'chirasizmi?")


@router.callback_query(F.data.startswith("pdy:"))
async def product_delete(call: CallbackQuery) -> None:
    pid = int(call.data.split(":")[1])
    p = await db.get_product(pid)
    await db.update_product(pid, is_deleted=1)
    await call.answer("O'chirildi")
    text, buttons = await _category_view(p["category_id"])
    await _edit_or_send(call, text, buttons)


EDIT_PROMPTS = {
    "name": "Yangi nomni yuboring:",
    "description": "Yangi tavsifni yuboring (tarkibi, og'irligi va h.k.):",
    "variants": "Yangi narxni yuboring.\n\nBitta narx: <code>25000</code>\n"
                "O'lchamlar bilan (har biri yangi qatorda):\n<code>O'rta 15000\nKatta 20000</code>",
    "image": "Yangi rasmni yuboring (rasm sifatida, fayl emas).\n\n"
             "📐 Ideal: 4:3 nisbat (masalan 1200×900), JPG, mahsulot markazda, bir xil fon.",
    "name_ru": "🇷🇺 Mahsulotning ruscha nomini yuboring (o'chirish uchun «-»):",
    "description_ru": "🇷🇺 Ruscha tavsifni yuboring (o'chirish uchun «-»):",
    "discount": "💸 Chegirma foizini yuboring.\n\n"
                "<code>20</code> — 20% muddatsiz\n"
                "<code>20 7</code> — 20%, 7 kun davomida\n"
                "<code>15 31.12.2026</code> — 15%, shu sanagacha\n"
                "<code>0</code> — chegirmani olib tashlash\n\n"
                "Mijozlarga eski narx chizilgan, yangisi ajratib ko'rsatiladi.",
}


def parse_discount(text: str) -> tuple[int, str] | None:
    """'20' | '20 7' (kun) | '20 31.12.2026' -> (foiz, tugash 'YYYY-MM-DD HH:MM:SS' yoki '')."""
    parts = text.replace("%", " ").split()
    if not parts or not parts[0].isdigit():
        return None
    pct = int(parts[0])
    if not 0 <= pct <= 95:
        return None
    if pct == 0 or len(parts) == 1:
        return pct, ""
    arg = parts[1]
    if arg.isdigit():
        until = now() + timedelta(days=int(arg))
        return pct, until.strftime("%Y-%m-%d 23:59:59")
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", arg)
    if not m:
        return None
    d, mo, y = map(int, m.groups())
    try:
        from datetime import date
        date(y, mo, d)
    except ValueError:
        return None
    return pct, f"{y:04d}-{mo:02d}-{d:02d} 23:59:59"


@router.callback_query(F.data.startswith("pe:"))
async def product_edit_start(call: CallbackQuery, state: FSMContext) -> None:
    _, pid, field = call.data.split(":")
    await state.set_state(EditProduct.value)
    await state.update_data(pid=int(pid), field=field)
    await call.message.answer(EDIT_PROMPTS[field], reply_markup=cancel_kb())
    await call.answer()


async def save_photo(bot: Bot, message: Message) -> str:
    config.uploads_dir.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex[:16]}.jpg"
    await bot.download(message.photo[-1], destination=config.uploads_dir / name)
    return f"uploads/{name}"


@router.message(EditProduct.value)
async def product_edit_save(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    field, pid = data["field"], data["pid"]
    if field == "image":
        if not message.photo:
            await message.answer("Iltimos, rasm yuboring.")
            return
        value = await save_photo(bot, message)
    elif not message.text:
        await message.answer("Iltimos, matn yuboring.")
        return
    elif field == "variants":
        value = parse_prices(message.text)
        if not value:
            await message.answer("❗️ Narx formati noto'g'ri. Masalan: <code>25000</code> yoki "
                                 "<code>O'rta 15000</code> (har bir o'lcham yangi qatorda).")
            return
    elif field == "discount":
        parsed = parse_discount(message.text)
        if not parsed:
            await message.answer("❗️ Format noto'g'ri. Masalan: <code>20</code>, <code>20 7</code> yoki "
                                 "<code>15 31.12.2026</code>")
            return
        await db.update_product(pid, discount_percent=parsed[0], discount_until=parsed[1])
        await state.clear()
        await message.answer("✅ Saqlandi", reply_markup=manager_kb())
        await send_product_card(message, pid)
        return
    else:
        value = message.text.strip()
        if field in ("name_ru", "description_ru") and value == "-":
            value = ""
        value = value[:500 if field.startswith("description") else 60]
    await db.update_product(pid, **{field: value})
    await state.clear()
    await message.answer("✅ Saqlandi", reply_markup=manager_kb())
    await send_product_card(message, pid)


# ---------- yangi mahsulot ----------

@router.callback_query(F.data.startswith("padd:"))
async def product_add_start(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddProduct.name)
    await state.update_data(cat_id=int(call.data.split(":")[1]))
    await call.message.answer("➕ <b>Yangi mahsulot</b>\n\n1/4. Mahsulot nomini yuboring:", reply_markup=cancel_kb())
    await call.answer()


@router.message(AddProduct.name, F.text)
async def product_add_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip()[:60])
    await state.set_state(AddProduct.description)
    await message.answer("2/4. Mahsulot haqida ma'lumot (tarkibi, og'irligi). O'tkazib yuborish uchun «-» yuboring:")


@router.message(AddProduct.description, F.text)
async def product_add_desc(message: Message, state: FSMContext) -> None:
    desc = "" if message.text.strip() == "-" else message.text.strip()[:500]
    await state.update_data(description=desc)
    await state.set_state(AddProduct.prices)
    await message.answer("3/4. " + EDIT_PROMPTS["variants"])


@router.message(AddProduct.prices, F.text)
async def product_add_prices(message: Message, state: FSMContext) -> None:
    variants = parse_prices(message.text)
    if not variants:
        await message.answer("❗️ Narx formati noto'g'ri. Qaytadan yuboring.")
        return
    await state.update_data(variants=variants)
    await state.set_state(AddProduct.photo)
    await message.answer("4/4. Mahsulot rasmini yuboring (yoki rasmsiz qo'shish uchun «-»):")


@router.message(AddProduct.photo)
async def product_add_photo(message: Message, state: FSMContext, bot: Bot) -> None:
    if message.photo:
        image = await save_photo(bot, message)
    elif message.text and message.text.strip() == "-":
        image = ""
    else:
        await message.answer("Rasm yuboring yoki «-»")
        return
    data = await state.get_data()
    pid = await db.add_product(data["cat_id"], data["name"], data["description"], image, data["variants"])
    await state.clear()
    await message.answer("✅ Mahsulot qo'shildi va menyuda ko'rinadi!", reply_markup=manager_kb())
    await send_product_card(message, pid)


# ====================== mijoz xabarlariga javob ======================

@router.message(StateFilter(None), F.reply_to_message, F.reply_to_message.text.regexp(r"#u(\d+)", mode="search"))
async def reply_to_customer(message: Message, bot: Bot) -> None:
    uid = int(re.search(r"#u(\d+)", message.reply_to_message.text).group(1))
    try:
        await bot.send_message(uid, t("reply_from_cafe", await lang_of(uid)))
        await bot.copy_message(uid, message.chat.id, message.message_id)
        await message.reply("✅ Javob yuborildi")
    except Exception:
        await message.reply("❗️ Yuborib bo'lmadi (mijoz botni bloklagan bo'lishi mumkin)")
