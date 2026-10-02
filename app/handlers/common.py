from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from .. import db
from ..keyboards import B, main_kb, webapp_inline_kb, webapp_ready
from ..roles import get_role
from ..utils import STATUS_LABELS, h, money

router = Router(name="common")


async def send_main_menu(message: Message, text: str | None = None) -> None:
    role = await get_role(message.from_user.id)
    await message.answer(text or "🏠 Asosiy menyu", reply_markup=main_kb(role))


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    u = message.from_user
    user, is_new = await db.upsert_user(u.id, u.first_name, u.last_name, u.username)
    role = await get_role(u.id)

    greeting = (
        f"👋 Assalomu alaykum, <b>{h(u.first_name)}</b>!\n\n"
        "<b>Yaproq go'sht</b> — Burger • Coffee • Good mood 👑\n"
        "Mazali, tez va siz uchun!\n\n"
    )
    if is_new:
        greeting += "✅ Siz uchun shaxsiy akkaunt avtomatik ochildi.\n\n"
    settings = await db.get_settings()
    if settings.get("is_open") != "1":
        greeting += "⏸ Hozir buyurtma qabul qilinmayapti. Ish vaqti: " + h(settings.get("work_hours")) + "\n\n"
    greeting += "🍔 Buyurtma berish uchun pastdagi <b>«Menyuni ochish»</b> tugmasini bosing."

    await message.answer(greeting, reply_markup=main_kb(role))
    kb = webapp_inline_kb("🍔 Menyuni ochish")
    if kb:
        await message.answer("👇 Mini ilova orqali menyu, savat va buyurtmalaringiz:", reply_markup=kb)
    elif role == "manager":
        await message.answer(
            "⚠️ <b>WEBAPP_URL</b> sozlanmagan yoki https emas — mini app tugmasi chiqmaydi.\n"
            ".env faylida WEBAPP_URL=https://... ni ko'rsating."
        )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    role = await get_role(message.from_user.id)
    text = (
        "ℹ️ <b>Yordam</b>\n\n"
        "/start — botni qayta ishga tushirish\n"
        "/menu — menyuni ochish\n"
        "/orders — buyurtmalarim\n"
    )
    if role in ("staff", "manager"):
        text += "\n<b>Xodim:</b>\n/staff — xodim kabineti\n/order &lt;ID&gt; — buyurtmani ID bo'yicha topish\n"
    if role == "manager":
        text += "\n<b>Menejer:</b>\n/admin — menejer paneli\n"
    await message.answer(text)


@router.message(StateFilter(None), F.text == B.MENU)
@router.message(Command("menu"))
async def open_menu(message: Message) -> None:
    kb = webapp_inline_kb("🍔 Menyuni ochish")
    if kb:
        await message.answer("Menyuni ochish uchun bosing 👇", reply_markup=kb)
    else:
        await message.answer("⏳ Mini ilova hali sozlanmagan. Tez orada ishga tushadi!")


@router.message(StateFilter(None), F.text == B.MY_ORDERS)
@router.message(Command("orders"))
async def my_orders(message: Message) -> None:
    orders = await db.get_user_orders(message.from_user.id, limit=5)
    if not orders:
        await message.answer(
            "Sizda hali buyurtmalar yo'q. Keling, birinchisini beramiz! 🍔",
            reply_markup=webapp_inline_kb("🍔 Menyuni ochish"),
        )
        return
    lines = ["📦 <b>Oxirgi buyurtmalaringiz:</b>\n"]
    for o in orders:
        lines.append(
            f"<code>{o['code']}</code> — {money(o['total'])}\n"
            f"   {STATUS_LABELS.get(o['status'])} · {o['created_at'][:16]}"
        )
    await message.answer(
        "\n".join(lines), reply_markup=webapp_inline_kb("📦 Batafsil kuzatish", "orders")
    )


@router.message(StateFilter(None), F.text == B.CONTACT)
async def contact(message: Message) -> None:
    s = await db.get_settings()
    phone = s.get("phone") or "tez orada qo'shiladi"
    await message.answer(
        "📞 <b>Biz bilan bog'lanish</b>\n\n"
        f"Telefon: {h(phone)}\n"
        f"Ish vaqti: {h(s.get('work_hours'))}\n\n"
        "Savol va takliflaringizni shu yerga yozib qoldirishingiz ham mumkin."
    )


@router.message(StateFilter(None), F.text == B.ABOUT)
async def about(message: Message) -> None:
    await message.answer(
        "👑 <b>Yaproq go'sht</b>\n"
        "<i>Good Food · Good Mood</i>\n\n"
        "🌭 Hot-doglar · 🥖 Frensh hot-dog · 🍔 Burgerlar\n"
        "🌯 Donar va lavash · 🍟 Kartoshka fri · ☕ Kofe\n\n"
        "✅ Yangi ingredientlar\n☕ Issiq kofe\n😊 Yaxshi kayfiyat\n\n"
        "See you soon! ❤️"
    )


@router.message(F.text == B.BACK)
async def back(message: Message, state: FSMContext) -> None:
    await state.clear()
    await send_main_menu(message)


# Oxirgi handler: mijozning boshqa xabarlari menejerlarga yuboriladi (fikr-mulohaza)
fallback_router = Router(name="fallback")


@fallback_router.message(StateFilter(None))
async def feedback(message: Message) -> None:
    from ..config import config

    if await get_role(message.from_user.id) == "manager":
        await message.answer("Buyruq tushunilmadi. /admin — menejer paneli, /help — yordam.")
        return
    u = message.from_user
    header = (
        f"💬 <b>Mijozdan xabar</b>\n{h(u.full_name)}"
        f"{' @' + h(u.username) if u.username else ''} #u{u.id}\n\n"
        "<i>Javob berish uchun shu xabarga reply qiling.</i>"
    )
    sent = False
    for admin_id in config.admin_ids | {s["id"] for s in await db.get_staff() if s["role"] == "manager"}:
        try:
            await message.bot.send_message(admin_id, header)
            await message.forward(admin_id)
            sent = True
        except Exception:
            pass
    if sent:
        await message.answer("✅ Xabaringiz yuborildi. Tez orada javob beramiz!")
