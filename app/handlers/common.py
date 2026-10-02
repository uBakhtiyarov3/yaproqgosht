from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import db, hours
from ..catalog import norm_lang
from ..config import config
from ..filters import Btn
from ..i18n import t
from ..keyboards import lang_kb, main_kb, start_inline_kb, webapp_ready
from ..orders import public_settings
from ..roles import get_role, lang_of
from ..utils import h

router = Router(name="common")


async def send_main_menu(message: Message, user_id: int, text: str | None = None) -> None:
    lang = await lang_of(user_id)
    await message.answer(text or t("main_menu", lang), reply_markup=main_kb(await get_role(user_id), lang))


async def send_welcome(message: Message, user_id: int, first_name: str, is_new: bool) -> None:
    lang = await lang_of(user_id)
    role = await get_role(user_id)
    greeting = t("greet", lang, name=h(first_name)) + "\n\n"
    if is_new:
        greeting += t("account_created", lang) + "\n\n"
    settings = public_settings(await db.get_settings())
    if not settings["is_open"]:
        greeting += t("closed_now", lang)
        if settings["next_open"]:
            greeting += " " + t("opens_at", lang, when=settings["next_open"])
        greeting += "\n\n"
    greeting += t("how_order", lang)
    await message.answer(greeting, reply_markup=main_kb(role, lang))

    ways = t("ways_bot", lang)
    if webapp_ready():
        ways = t("ways_mini", lang) + "\n" + ways
    await message.answer(ways, reply_markup=start_inline_kb(lang))
    if not webapp_ready() and role == "manager":
        await message.answer(
            "ℹ️ <b>WEBAPP_URL</b> sozlanmagan yoki https emas — hozircha faqat bot ichida buyurtma ishlaydi.\n"
            ".env faylida WEBAPP_URL=https://... ni ko'rsatsangiz, mini ilova tugmasi ham chiqadi."
        )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    u = message.from_user
    user, is_new = await db.upsert_user(u.id, u.first_name, u.last_name, u.username)
    if not user.get("lang"):
        # birinchi marta — tilni so'raymiz (Telegram tiliga qarab taklif)
        await state.update_data(new_user=is_new)
        await message.answer(t("choose_lang"), reply_markup=lang_kb())
        return
    await send_welcome(message, u.id, u.first_name, is_new)


@router.message(Command("lang"))
@router.message(StateFilter(None), Btn("b_lang"))
async def change_lang(message: Message) -> None:
    await message.answer(t("choose_lang"), reply_markup=lang_kb())


@router.callback_query(F.data.startswith("lang:"))
async def set_lang(call: CallbackQuery, state: FSMContext) -> None:
    lang = norm_lang(call.data.split(":")[1])
    first_time = not (await db.get_user(call.from_user.id) or {}).get("lang")
    await db.upsert_user(call.from_user.id, call.from_user.first_name, call.from_user.last_name,
                         call.from_user.username)
    await db.set_lang(call.from_user.id, lang)
    await call.answer(t("lang_saved", lang))
    try:
        await call.message.edit_text(t("lang_saved", lang))
    except Exception:
        pass
    if first_time:
        is_new = (await state.get_data()).get("new_user", True)
        await state.clear()
        await send_welcome(call.message, call.from_user.id, call.from_user.first_name, is_new)
    else:
        await send_main_menu(call.message, call.from_user.id)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    role = await get_role(message.from_user.id)
    text = t("help", await lang_of(message.from_user.id))
    if role in ("staff", "manager"):
        text += "\n<b>Xodim:</b>\n/staff — xodim kabineti\n/order &lt;ID&gt; — buyurtmani ID bo'yicha topish\n"
    if role == "manager":
        text += "\n<b>Menejer:</b>\n/admin — menejer paneli\n"
    await message.answer(text)


@router.message(StateFilter(None), Btn("b_contact"))
async def contact(message: Message) -> None:
    lang = await lang_of(message.from_user.id)
    s = await db.get_settings()
    address = s.get("cafe_address") or ""
    await message.answer(t(
        "contact", lang,
        phone=h(s.get("phone") or t("phone_soon", lang)),
        hours=h(hours.schedule_summary(s, lang)),
        address=t("address_line", lang, address=h(address)) if address else "",
    ))


@router.message(StateFilter(None), Btn("b_about"))
async def about(message: Message) -> None:
    await message.answer(t("about", await lang_of(message.from_user.id)))


@router.message(Btn("b_back"))
async def back(message: Message, state: FSMContext) -> None:
    await state.clear()
    await send_main_menu(message, message.from_user.id)


# Oxirgi handler: mijozning boshqa xabarlari menejerlarga yuboriladi (fikr-mulohaza)
fallback_router = Router(name="fallback")


@fallback_router.message(StateFilter(None))
async def feedback(message: Message) -> None:
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
        await message.answer(t("feedback_sent", await lang_of(u.id)))
