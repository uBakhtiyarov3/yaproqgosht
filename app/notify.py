import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardMarkup

from . import db
from .config import config
from .keyboards import order_staff_kb, webapp_inline_kb
from .utils import STATUS_LABELS, format_order

log = logging.getLogger(__name__)

CUSTOMER_TEXTS = {
    "accepted": "✅ Buyurtmangiz <code>{code}</code> qabul qilindi! Tez orada tayyorlashni boshlaymiz.",
    "cooking": "👨‍🍳 Buyurtmangiz <code>{code}</code> tayyorlanmoqda...",
    "delivering": "🛵 Buyurtmangiz <code>{code}</code> yo'lda! Kuryer tez orada yetib boradi.",
    "delivered": "🎉 Buyurtmangiz <code>{code}</code> yetkazildi. Yoqimli ishtaha! Yana kutamiz 😊",
    "cancelled": "❌ Afsuski, buyurtmangiz <code>{code}</code> bekor qilindi.{reason}\nSavollar bo'lsa, biz bilan bog'laning.",
}


async def staff_recipients() -> list[int]:
    ids = {u["id"] for u in await db.get_staff()}
    ids |= config.admin_ids
    return sorted(ids)


async def notify_new_order(bot: Bot, order_id: int) -> None:
    order = await db.get_order(order_id)
    items = await db.get_order_items(order_id)
    text = "🔔 <b>YANGI BUYURTMA!</b>\n\n" + format_order(order, items)
    kb = order_staff_kb(order)
    for chat_id in await staff_recipients():
        try:
            msg = await bot.send_message(chat_id, text, reply_markup=kb)
            await db.save_order_message(order_id, chat_id, msg.message_id)
        except (TelegramForbiddenError, TelegramBadRequest) as e:
            log.warning("Xodimga yuborib bo'lmadi %s: %s", chat_id, e)

    # Mijozga tasdiq
    try:
        await bot.send_message(
            order["user_id"],
            f"🧾 Buyurtmangiz <code>{order['code']}</code> qabul qilish uchun yuborildi!\n"
            f"Holati: {STATUS_LABELS['new']}\n\n"
            "Holat o'zgarganda sizga shu yerda xabar beramiz. "
            "Jarayonni mini ilovadagi «Buyurtmalarim» bo'limida ham kuzatishingiz mumkin.",
            reply_markup=webapp_inline_kb("📦 Buyurtmani kuzatish", "orders"),
        )
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        log.warning("Mijozga yuborib bo'lmadi %s: %s", order["user_id"], e)


async def refresh_staff_messages(bot: Bot, order_id: int) -> None:
    """Holat o'zgarganda barcha xodimlardagi xabarni yangilaydi."""
    order = await db.get_order(order_id)
    items = await db.get_order_items(order_id)
    text = format_order(order, items)
    kb: InlineKeyboardMarkup | None = order_staff_kb(order)
    for m in await db.get_order_messages(order_id):
        try:
            await bot.edit_message_text(
                text, chat_id=m["chat_id"], message_id=m["message_id"], reply_markup=kb
            )
        except TelegramBadRequest as e:
            if "not modified" not in str(e):
                log.debug("Edit failed: %s", e)
        except TelegramForbiddenError:
            pass


async def notify_status_change(bot: Bot, order_id: int) -> None:
    order = await db.get_order(order_id)
    await refresh_staff_messages(bot, order_id)
    template = CUSTOMER_TEXTS.get(order["status"])
    if not template:
        return
    reason = f"\nSabab: {order['cancel_reason']}" if order.get("cancel_reason") else ""
    try:
        await bot.send_message(
            order["user_id"],
            template.format(code=order['code'], reason=reason),
            reply_markup=webapp_inline_kb("📦 Buyurtmani ko'rish", "orders")
            if order["status"] not in ("delivered", "cancelled") else None,
        )
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        log.warning("Mijozga holat yuborilmadi %s: %s", order["user_id"], e)


async def broadcast(bot: Bot, from_chat_id: int, message_id: int, progress_cb=None) -> tuple[int, int]:
    """Xabarni barcha foydalanuvchilarga nusxalaydi. (yuborildi, xato) qaytaradi."""
    ok = fail = 0
    user_ids = await db.all_user_ids()
    for i, uid in enumerate(user_ids, 1):
        try:
            await bot.copy_message(uid, from_chat_id, message_id)
            ok += 1
        except TelegramForbiddenError:
            await db.set_blocked(uid, True)
            fail += 1
        except TelegramBadRequest:
            fail += 1
        except Exception as e:  # flood limit va boshqalar
            log.warning("Broadcast error %s: %s", uid, e)
            fail += 1
        await asyncio.sleep(0.05)  # Telegram limiti: ~30 xabar/soniya
        if progress_cb and i % 50 == 0:
            await progress_cb(i, len(user_ids))
    return ok, fail
