from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.types import CallbackQuery, Message

from .. import db
from ..keyboards import B, ikb, order_staff_kb, staff_kb
from ..notify import notify_status_change, refresh_staff_messages
from ..roles import IsStaff
from ..utils import ACTIVE_STATUSES, format_order, money, next_status, now, status_label

router = Router(name="staff")
router.message.filter(IsStaff)
router.callback_query.filter(IsStaff)

CANCEL_REASONS = [
    "Mijoz bekor qildi",
    "Mijoz bilan bog'lanib bo'lmadi",
    "Mahsulot tugagan",
    "Manzil yetkazish hududidan tashqarida",
    "Boshqa sabab",
]


@router.message(StateFilter(None), F.text == B.STAFF)
@router.message(Command("staff"))
async def staff_home(message: Message) -> None:
    new = len(await db.get_orders_by_status(("new",), limit=100))
    active = len(await db.get_orders_by_status(("accepted", "cooking", "delivering"), limit=100))
    await message.answer(
        "👷 <b>Xodim kabineti</b>\n\n"
        f"🆕 Yangi buyurtmalar: <b>{new}</b>\n"
        f"🔄 Jarayondagi: <b>{active}</b>\n\n"
        "Yangi buyurtma tushganda sizga avtomatik xabar keladi. "
        "Xabardagi tugmalar orqali holatni yangilang.",
        reply_markup=staff_kb(),
    )


async def _send_order_list(message: Message, orders: list[dict], empty: str) -> None:
    if not orders:
        await message.answer(empty)
        return
    for o in reversed(orders[:10]):
        items = await db.get_order_items(o["id"])
        msg = await message.answer(format_order(o, items), reply_markup=order_staff_kb(o))
        # shu xabar ham holat o'zgarganda yangilanib turadi
        await db.save_order_message(o["id"], msg.chat.id, msg.message_id)
    if len(orders) > 10:
        await message.answer(f"... va yana {len(orders) - 10} ta buyurtma.")


@router.message(StateFilter(None), F.text == B.NEW_ORDERS)
async def new_orders(message: Message) -> None:
    await _send_order_list(message, await db.get_orders_by_status(("new",)), "✅ Yangi buyurtmalar yo'q.")


@router.message(StateFilter(None), F.text == B.ACTIVE_ORDERS)
async def active_orders(message: Message) -> None:
    orders = await db.get_orders_by_status(("accepted", "cooking", "delivering"))
    await _send_order_list(message, orders, "Jarayondagi buyurtmalar yo'q.")


@router.message(StateFilter(None), F.text == B.MY_TASKS)
async def my_tasks(message: Message) -> None:
    orders = await db.get_orders_by_status(ACTIVE_STATUSES, staff_id=message.from_user.id)
    await _send_order_list(message, orders, "Sizga biriktirilgan faol buyurtmalar yo'q.")


@router.message(StateFilter(None), F.text == B.TODAY)
async def today(message: Message) -> None:
    since = now().strftime("%Y-%m-%d 00:00:00")
    uid = message.from_user.id
    mine = await db.fetchone(
        "SELECT COUNT(*) c, COALESCE(SUM(total), 0) s FROM orders"
        " WHERE staff_id = ? AND status = 'delivered' AND created_at >= ?", uid, since,
    )
    allc = await db.fetchone(
        "SELECT COUNT(*) c, COALESCE(SUM(total), 0) s FROM orders"
        " WHERE status = 'delivered' AND created_at >= ?", since,
    )
    await message.answer(
        "📈 <b>Bugungi natija</b>\n\n"
        f"Siz yetkazgan: <b>{mine['c']}</b> ta · {money(mine['s'])}\n"
        f"Jami yetkazilgan: <b>{allc['c']}</b> ta · {money(allc['s'])}"
    )


@router.message(Command("order"))
async def show_order(message: Message, command: CommandObject) -> None:
    if not command.args:
        await message.answer("Foydalanish: /order YG-482917 (yoki faqat 482917)")
        return
    order = await db.find_order(command.args)
    if not order:
        await message.answer("Buyurtma topilmadi.")
        return
    await _send_order_list(message, [order], "")


@router.callback_query(F.data.startswith("ov:"))
async def view_order(call: CallbackQuery) -> None:
    order = await db.get_order(int(call.data.split(":")[1]))
    if not order:
        await call.answer("Topilmadi", show_alert=True)
        return
    await call.answer()
    await _send_order_list(call.message, [order], "")


@router.callback_query(F.data.startswith("ost:"))
async def change_status(call: CallbackQuery, bot: Bot) -> None:
    _, order_id, new_status = call.data.split(":")
    order = await db.get_order(int(order_id))
    if not order:
        await call.answer("Buyurtma topilmadi", show_alert=True)
        return
    otype = order.get("order_type") or "delivery"
    expected = (next_status(order["status"], otype) or (None,))[0]
    if expected != new_status:
        # boshqa xodim allaqachon o'zgartirgan
        await call.answer(f"Holat allaqachon: {status_label(order['status'], otype)}", show_alert=True)
        await refresh_staff_messages(bot, order["id"])
        return
    await db.set_order_status(order["id"], new_status, call.from_user.id)
    await call.answer(status_label(new_status, otype))
    await notify_status_change(bot, order["id"])


@router.callback_query(F.data.startswith("ocn:"))
async def cancel_ask(call: CallbackQuery) -> None:
    order_id = int(call.data.split(":")[1])
    rows = [[(r, f"ocr:{order_id}:{i}")] for i, r in enumerate(CANCEL_REASONS)]
    rows.append([("⬅️ Ortga", f"ocb:{order_id}")])
    await call.message.edit_reply_markup(reply_markup=ikb(rows))
    await call.answer("Bekor qilish sababini tanlang")


@router.callback_query(F.data.startswith("ocb:"))
async def cancel_back(call: CallbackQuery) -> None:
    order = await db.get_order(int(call.data.split(":")[1]))
    await call.message.edit_reply_markup(reply_markup=order_staff_kb(order))
    await call.answer()


@router.callback_query(F.data.startswith("ocr:"))
async def cancel_confirm(call: CallbackQuery, bot: Bot) -> None:
    _, order_id, idx = call.data.split(":")
    order = await db.get_order(int(order_id))
    if not order or order["status"] not in ACTIVE_STATUSES:
        await call.answer("Bu buyurtmani bekor qilib bo'lmaydi", show_alert=True)
        return
    await db.set_order_status(order["id"], "cancelled", call.from_user.id, CANCEL_REASONS[int(idx)])
    await call.answer("Buyurtma bekor qilindi")
    await notify_status_change(bot, order["id"])
