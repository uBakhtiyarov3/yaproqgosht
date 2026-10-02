"""Menejer paneli: ish jadvali, promo-kodlar va baholar."""
import json
import re
import secrets
from datetime import date, timedelta

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from .. import db, hours
from ..keyboards import B, cancel_kb, ikb, manager_kb
from ..roles import IsManager
from ..utils import fmt_dt, h, money, now

router = Router(name="admin_extra")
router.message.filter(IsManager)
router.callback_query.filter(IsManager)


# ====================== ish jadvali ======================

class EditSchedule(StatesGroup):
    value = State()


TIME_RANGE_RE = re.compile(r"^(\d{1,2}[:.]\d{2})\s*[-–—]\s*(\d{1,2}[:.]\d{2})$")
DAY_OFF = {"dam", "yopiq", "-", "выходной", "off"}


async def _schedule_view() -> tuple[str, list]:
    s = await db.get_settings()
    lines = ["🗓 <b>Ish jadvali</b>\n", *hours.schedule_lines(s), ""]
    lines.append("Jadval «🕒 Jadval bo'yicha» rejimida ishlaydi: ish vaqtidan tashqarida mijozlar "
                 "faqat vaqtga buyurtma bera oladi.")
    schedule = hours.load_schedule(s)
    rows = []
    for i, d in enumerate(hours.DAYS):
        val = f"{schedule[d][0]}–{schedule[d][1]}" if schedule.get(d) else "dam olish"
        rows.append([(f"{hours.DAY_NAMES['uz'][i]}: {val}", f"sch:d:{d}")])
    rows.append([("📋 Barcha kunlarga bir xil", "sch:d:all")])
    return "\n".join(lines), rows


@router.callback_query(F.data == "sch:view")
async def schedule_view(call: CallbackQuery) -> None:
    text, rows = await _schedule_view()
    await call.message.edit_text(text, reply_markup=ikb(rows))
    await call.answer()


@router.callback_query(F.data.startswith("sch:d:"))
async def schedule_edit(call: CallbackQuery, state: FSMContext) -> None:
    day = call.data.split(":")[2]
    name = "barcha kunlar" if day == "all" else hours.DAY_NAMES["uz"][hours.DAYS.index(day)]
    await state.set_state(EditSchedule.value)
    await state.update_data(day=day)
    await call.message.answer(
        f"🕒 <b>{name.capitalize()}</b> uchun ish vaqtini yuboring:\n\n"
        "<code>10:00-23:00</code> — oddiy kun\n"
        "<code>18:00-02:00</code> — tungacha (keyingi kun 02:00 gacha)\n"
        "<code>dam</code> — dam olish kuni",
        reply_markup=cancel_kb(),
    )
    await call.answer()


@router.message(EditSchedule.value, F.text)
async def schedule_save(message: Message, state: FSMContext) -> None:
    day = (await state.get_data())["day"]
    text = message.text.strip().lower()
    if text in DAY_OFF:
        value = None
    else:
        m = TIME_RANGE_RE.match(text)
        o = hours.parse_hhmm(m.group(1)) if m else None
        c = hours.parse_hhmm(m.group(2)) if m else None
        if not o or not c or o == c:
            await message.answer("❗️ Format noto'g'ri. Masalan: <code>10:00-23:00</code> yoki <code>dam</code>")
            return
        value = [f"{o[0]:02d}:{o[1]:02d}", f"{c[0] % 24:02d}:{c[1]:02d}"]
    schedule = hours.load_schedule(await db.get_settings())
    for d in (hours.DAYS if day == "all" else [day]):
        schedule[d] = value
    await db.set_setting("schedule", json.dumps(schedule))
    await state.clear()
    await message.answer("✅ Jadval saqlandi", reply_markup=manager_kb())
    view, rows = await _schedule_view()
    await message.answer(view, reply_markup=ikb(rows))


# ====================== promo-kodlar ======================

class PromoNew(StatesGroup):
    code = State()
    value = State()


class PromoEdit(StatesGroup):
    value = State()


KIND_LABELS = {"percent": "💯 Foiz chegirma", "fixed": "💵 Aniq summa", "free_delivery": "🚚 Bepul yetkazish"}
CODE_RE = re.compile(r"^[A-Z0-9_-]{3,20}$")


def _promo_short(p: dict) -> str:
    if p["kind"] == "percent":
        return f"-{p['value']}%"
    if p["kind"] == "fixed":
        return f"-{money(p['value'])}"
    return "bepul yetkazish"


def _promo_status(p: dict) -> str:
    n = now().strftime("%Y-%m-%d %H:%M:%S")
    if not p["is_active"]:
        return "⏸ o'chirilgan"
    if p["starts_at"] and n < p["starts_at"]:
        return "⏳ hali boshlanmagan"
    if p["ends_at"] and n >= p["ends_at"]:
        return "⌛️ muddati tugagan"
    if p["usage_limit"] and p.get("used", 0) >= p["usage_limit"]:
        return "🔚 limit tugagan"
    return "✅ faol"


async def _promos_view() -> tuple[str, list]:
    promos = await db.get_promos()
    lines = ["🎁 <b>Promo-kodlar</b>\n"]
    if not promos:
        lines.append("Hali promo-kod yo'q. Birinchisini yarating 👇")
    lines.append("Mijoz kodni buyurtma berishda kiritadi (botda ham, mini ilovada ham).")
    rows = [[(f"{_promo_status(p).split()[0]} {p['code']} · {_promo_short(p)} · {p['used']}"
              f"{'/' + str(p['usage_limit']) if p['usage_limit'] else ''}", f"pm:v:{p['id']}")]
            for p in promos[:40]]
    rows.append([("➕ Yangi promo-kod", "pm:new")])
    return "\n".join(lines), rows


@router.message(StateFilter(None), F.text == B.PROMOS)
async def promos(message: Message) -> None:
    text, rows = await _promos_view()
    await message.answer(text, reply_markup=ikb(rows))


@router.callback_query(F.data == "pm:list")
async def promos_cb(call: CallbackQuery) -> None:
    text, rows = await _promos_view()
    await call.message.edit_text(text, reply_markup=ikb(rows))
    await call.answer()


async def _promo_card(promo_id: int) -> tuple[str, list] | None:
    p = await db.get_promo(promo_id)
    if not p:
        return None
    value = {"percent": f"{p['value']}%", "fixed": money(p["value"]), "free_delivery": "—"}[p["kind"]]
    lines = [
        f"🎁 <b>{h(p['code'])}</b> — {_promo_status(p)}\n",
        f"Turi: {KIND_LABELS[p['kind']]}",
        f"Qiymati: <b>{value}</b>",
        f"🧾 Minimal buyurtma: {money(p['min_order']) if p['min_order'] else 'cheklovsiz'}",
    ]
    if p["kind"] == "percent":
        lines.append(f"🔝 Maksimal chegirma: {money(p['max_discount']) if p['max_discount'] else 'cheklovsiz'}")
    lines += [
        f"👥 Umumiy limit: {p['usage_limit'] or 'cheklovsiz'}",
        f"👤 Bir mijozga: {p['per_user_limit'] or 'cheklovsiz'} marta",
        f"🆕 Faqat birinchi buyurtma: {'ha' if p['first_order_only'] else 'yo`q'}",
        f"📅 Boshlanish: {fmt_dt(p['starts_at']) if p['starts_at'] else 'darhol'}",
        f"⏳ Tugash: {fmt_dt(p['ends_at']) if p['ends_at'] else 'muddatsiz'}",
        "",
        f"📊 Ishlatilgan: <b>{p['used']}</b> marta · berilgan chegirma: {money(p['discount_sum'])}",
    ]
    pid = p["id"]
    rows = []
    if p["kind"] != "free_delivery":
        rows.append([("💯 Qiymat", f"pm:e:{pid}:value"), ("🧾 Min. summa", f"pm:e:{pid}:min_order")])
    else:
        rows.append([("🧾 Min. summa", f"pm:e:{pid}:min_order")])
    if p["kind"] == "percent":
        rows.append([("🔝 Maks. chegirma", f"pm:e:{pid}:max_discount")])
    rows += [
        [("👥 Umumiy limit", f"pm:e:{pid}:usage_limit"), ("👤 Bir kishiga", f"pm:e:{pid}:per_user_limit")],
        [(("✅" if p["first_order_only"] else "▫️") + " Faqat 1-buyurtma", f"pm:fo:{pid}")],
        [("📅 Boshlanish", f"pm:e:{pid}:starts_at"), ("⏳ Tugash", f"pm:e:{pid}:ends_at")],
        [("⏸ O'chirish" if p["is_active"] else "▶️ Yoqish", f"pm:tg:{pid}"), ("🗑 O'chirib tashlash", f"pm:del:{pid}")],
        [("⬅️ Ro'yxat", "pm:list")],
    ]
    return "\n".join(lines), rows


@router.callback_query(F.data.startswith("pm:v:"))
async def promo_view(call: CallbackQuery) -> None:
    card = await _promo_card(int(call.data.split(":")[2]))
    if not card:
        await call.answer("Topilmadi", show_alert=True)
        return
    await call.message.edit_text(card[0], reply_markup=ikb(card[1]))
    await call.answer()


@router.callback_query(F.data.startswith("pm:tg:"))
async def promo_toggle(call: CallbackQuery) -> None:
    pid = int(call.data.split(":")[2])
    p = await db.get_promo(pid)
    await db.update_promo(pid, is_active=0 if p["is_active"] else 1)
    card = await _promo_card(pid)
    await call.message.edit_text(card[0], reply_markup=ikb(card[1]))
    await call.answer("Saqlandi")


@router.callback_query(F.data.startswith("pm:fo:"))
async def promo_first_order(call: CallbackQuery) -> None:
    pid = int(call.data.split(":")[2])
    p = await db.get_promo(pid)
    await db.update_promo(pid, first_order_only=0 if p["first_order_only"] else 1)
    card = await _promo_card(pid)
    await call.message.edit_text(card[0], reply_markup=ikb(card[1]))
    await call.answer("Saqlandi")


@router.callback_query(F.data.startswith("pm:del:"))
async def promo_delete_ask(call: CallbackQuery) -> None:
    pid = int(call.data.split(":")[2])
    await call.message.edit_reply_markup(reply_markup=ikb([[("✅ Ha, o'chirish", f"pm:dy:{pid}"),
                                                            ("🚫 Yo'q", f"pm:v:{pid}")]]))
    await call.answer("Rostdan o'chirasizmi? (Statistika buyurtmalarda saqlanib qoladi)")


@router.callback_query(F.data.startswith("pm:dy:"))
async def promo_delete(call: CallbackQuery) -> None:
    await db.delete_promo(int(call.data.split(":")[2]))
    text, rows = await _promos_view()
    await call.message.edit_text(text, reply_markup=ikb(rows))
    await call.answer("O'chirildi")


# ---------- yangi promo-kod ----------

@router.callback_query(F.data == "pm:new")
async def promo_new(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PromoNew.code)
    await call.message.answer(
        "➕ <b>Yangi promo-kod</b>\n\n1/3. Kodni yuboring (lotin harflari va raqamlar, 3–20 belgi), "
        "masalan <code>YAPROQ20</code>.\nAvtomatik kod uchun <code>auto</code> yozing.",
        reply_markup=cancel_kb(),
    )
    await call.answer()


@router.message(PromoNew.code, F.text)
async def promo_new_code(message: Message, state: FSMContext) -> None:
    code = message.text.strip().upper()
    if code == "AUTO":
        code = "YG" + secrets.token_hex(3).upper()
    if not CODE_RE.match(code):
        await message.answer("❗️ Faqat lotin harflari, raqamlar, «-» va «_» (3–20 belgi). Qaytadan yuboring:")
        return
    if await db.get_promo_by_code(code):
        await message.answer("❗️ Bunday kod allaqachon bor. Boshqasini yuboring:")
        return
    await state.update_data(code=code)
    await message.answer(
        f"Kod: <b>{code}</b>\n\n2/3. Chegirma turini tanlang:",
        reply_markup=ikb([[(KIND_LABELS["percent"], "pmk:percent")],
                          [(KIND_LABELS["fixed"], "pmk:fixed")],
                          [(KIND_LABELS["free_delivery"], "pmk:free_delivery")]]),
    )


@router.callback_query(F.data.startswith("pmk:"), PromoNew.code)
async def promo_new_kind(call: CallbackQuery, state: FSMContext) -> None:
    kind = call.data.split(":")[1]
    await state.update_data(kind=kind)
    await call.answer()
    if kind == "free_delivery":
        await _promo_create(call.message, state, 0)
        return
    await state.set_state(PromoNew.value)
    prompt = "3/3. Chegirma foizini yuboring (1–100), masalan <code>20</code>:" if kind == "percent" else \
        "3/3. Chegirma summasini yuboring (so'mda), masalan <code>10000</code>:"
    await call.message.edit_text(f"Turi: {KIND_LABELS[kind]}\n\n{prompt}")


@router.message(PromoNew.value, F.text)
async def promo_new_value(message: Message, state: FSMContext) -> None:
    kind = (await state.get_data())["kind"]
    value = _parse_int(message.text)
    if value is None or value <= 0 or (kind == "percent" and value > 100):
        await message.answer("❗️ Noto'g'ri qiymat. Qaytadan yuboring:")
        return
    await _promo_create(message, state, value)


async def _promo_create(message: Message, state: FSMContext, value: int) -> None:
    data = await state.get_data()
    pid = await db.add_promo(code=data["code"], kind=data["kind"], value=value)
    await state.clear()
    await message.answer("✅ Promo-kod yaratildi va faol! Quyida shartlarini sozlashingiz mumkin.",
                         reply_markup=manager_kb())
    card = await _promo_card(pid)
    await message.answer(card[0], reply_markup=ikb(card[1]))


# ---------- maydonlarni tahrirlash ----------

PROMO_PROMPTS = {
    "value": "Yangi qiymatni yuboring (foiz yoki so'm):",
    "min_order": "Minimal buyurtma summasini yuboring (so'mda, 0 — cheklovsiz):",
    "max_discount": "Maksimal chegirma summasini yuboring (so'mda, 0 — cheklovsiz).\n"
                    "Masalan 20% chegirma, lekin 30 000 so'mdan oshmasin:",
    "usage_limit": "Umumiy foydalanish limitini yuboring (masalan 100; 0 — cheklovsiz):",
    "per_user_limit": "Bir mijoz necha marta ishlata oladi? (masalan 1; 0 — cheklovsiz):",
    "starts_at": "Boshlanish vaqtini yuboring:\n<code>05.10.2026</code> yoki <code>05.10.2026 18:00</code>\n"
                 "Darhol boshlash uchun <code>-</code>",
    "ends_at": "Tugash vaqtini yuboring:\n<code>31.10.2026</code>, <code>31.10.2026 23:00</code> yoki "
               "<code>7</code> (7 kundan keyin)\nMuddatsiz uchun <code>-</code>",
}


def _parse_int(text: str) -> int | None:
    digits = re.sub(r"[\s']", "", text)
    return int(digits) if digits.isdigit() else None


def _parse_when(text: str, end: bool) -> str | None:
    """'-' -> '' ; '7' -> +7 kun ; 'DD.MM.YYYY [HH:MM]' -> 'YYYY-MM-DD HH:MM:SS'. Xato -> None."""
    text = text.strip()
    if text == "-":
        return ""
    if text.isdigit() and end:
        return (now() + timedelta(days=int(text))).strftime("%Y-%m-%d 23:59:59")
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})(?:\s+(\d{1,2}):(\d{2}))?$", text)
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        date(y, mo, d)
    except ValueError:
        return None
    if m.group(4):
        hh, mm = int(m.group(4)), int(m.group(5))
        if hh > 23 or mm > 59:
            return None
        return f"{y:04d}-{mo:02d}-{d:02d} {hh:02d}:{mm:02d}:00"
    return f"{y:04d}-{mo:02d}-{d:02d} " + ("23:59:59" if end else "00:00:00")


@router.callback_query(F.data.startswith("pm:e:"))
async def promo_edit_start(call: CallbackQuery, state: FSMContext) -> None:
    _, _, pid, field = call.data.split(":")
    await state.set_state(PromoEdit.value)
    await state.update_data(pid=int(pid), field=field)
    await call.message.answer(PROMO_PROMPTS[field], reply_markup=cancel_kb())
    await call.answer()


@router.message(PromoEdit.value, F.text)
async def promo_edit_save(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    pid, field = data["pid"], data["field"]
    promo = await db.get_promo(pid)
    if not promo:
        await state.clear()
        await message.answer("Topilmadi", reply_markup=manager_kb())
        return
    if field in ("starts_at", "ends_at"):
        value = _parse_when(message.text, end=field == "ends_at")
        if value is None:
            await message.answer("❗️ Format noto'g'ri. Masalan: <code>31.10.2026</code> yoki <code>-</code>")
            return
    else:
        value = _parse_int(message.text)
        if value is None or value < 0:
            await message.answer("❗️ Faqat raqam yuboring:")
            return
        if field == "value" and (value == 0 or (promo["kind"] == "percent" and value > 100)):
            await message.answer("❗️ Foiz 1–100 oralig'ida, summa 0 dan katta bo'lsin:")
            return
    await db.update_promo(pid, **{field: value})
    await state.clear()
    await message.answer("✅ Saqlandi", reply_markup=manager_kb())
    card = await _promo_card(pid)
    await message.answer(card[0], reply_markup=ikb(card[1]))


# ====================== baholar ======================

async def _reviews_view(only_low: bool = False) -> tuple[str, list]:
    since = (now() - timedelta(days=29)).strftime("%Y-%m-%d 00:00:00")
    total, month = await db.review_stats(), await db.review_stats(since)
    lines = ["⭐ <b>Baholar</b>\n"]
    if not total["count"]:
        lines.append("Hali baholar yo'q. Buyurtma yetkazilgach, bot mijozdan baho so'raydi.")
        return "\n".join(lines), []
    lines += [
        f"O'rtacha (barcha vaqt): <b>{total['avg']}</b> / 5 · {total['count']} ta",
        f"O'rtacha (30 kun): <b>{month['avg']}</b> / 5 · {month['count']} ta",
        "",
    ]
    for n in range(5, 0, -1):
        c = total["dist"].get(n, 0)
        bar = "█" * round(10 * c / total["count"]) if total["count"] else ""
        lines.append(f"{n}⭐ {bar} {c}")
    reviews = await db.get_reviews(10, 3 if only_low else None)
    lines.append("\n<b>" + ("Past baholar (≤3):" if only_low else "Oxirgi baholar:") + "</b>")
    if not reviews:
        lines.append("—")
    for r in reviews:
        comment = f"\n   💬 {h(r['comment'])}" if r["comment"] else ""
        lines.append(f"{'⭐' * r['rating']} · <code>{r['code']}</code> · {h(r['name'] or '')} · "
                     f"{r['created_at'][5:16]}{comment}")
    rows = [[("⚠️ Faqat past baholar", "rvl:low") if not only_low else ("📋 Barchasi", "rvl:all")]]
    return "\n".join(lines), rows


@router.message(StateFilter(None), F.text == B.REVIEWS)
async def reviews(message: Message) -> None:
    text, rows = await _reviews_view()
    await message.answer(text, reply_markup=ikb(rows) if rows else None)


@router.callback_query(F.data.startswith("rvl:"))
async def reviews_filter(call: CallbackQuery) -> None:
    text, rows = await _reviews_view(call.data == "rvl:low")
    await call.message.edit_text(text, reply_markup=ikb(rows) if rows else None)
    await call.answer()
