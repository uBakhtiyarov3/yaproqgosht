import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup

from . import db
from .config import config
from .i18n import t
from .keyboards import order_staff_kb, order_track_kb, rating_kb
from .roles import lang_of
from .utils import format_order, h

log = logging.getLogger(__name__)


async def staff_recipients() -> list[int]:
    ids = {u["id"] for u in await db.get_staff()}
    ids |= config.admin_ids
    return sorted(ids)


async def notify_new_order(bot: Bot, order_id: int, notify_customer: bool = True) -> None:
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

    if not notify_customer:  # bot ichidagi savatdan berilganda mijozga tasdiq allaqachon ko'rsatilgan
        return
    # Mijozga tasdiq
    lang = await lang_of(order["user_id"])
    try:
        await bot.send_message(
            order["user_id"],
            t("sent_new", lang, code=order["code"]),
            reply_markup=order_track_kb(order["code"], lang),
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


def customer_status_text(order: dict, lang: str, cafe_address: str = "") -> str | None:
    status, otype = order["status"], order.get("order_type") or "delivery"
    if status not in ("accepted", "cooking", "delivering", "delivered", "cancelled"):
        return None
    key = f"st_{status}"
    if otype == "pickup" and status in ("delivering", "delivered"):
        key += "_pickup"
    reason = ""
    if status == "cancelled" and order.get("cancel_reason"):
        reason = "\n" + t("reason", lang, reason=h(order["cancel_reason"]))
    address = f"\n📍 {h(cafe_address)}" if cafe_address else ""
    return t(key, lang, code=order["code"], reason=reason, address=address)


async def notify_status_change(bot: Bot, order_id: int) -> None:
    order = await db.get_order(order_id)
    await refresh_staff_messages(bot, order_id)
    lang = await lang_of(order["user_id"])
    text = customer_status_text(order, lang, await db.get_setting("cafe_address"))
    if not text:
        return
    try:
        await bot.send_message(order["user_id"], text, reply_markup=order_track_kb(order["code"], lang))
        if order["status"] == "delivered" and not await db.get_review(order_id):
            await bot.send_message(order["user_id"], t("rate_ask", lang), reply_markup=rating_kb(order_id))
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        log.warning("Mijozga holat yuborilmadi %s: %s", order["user_id"], e)


async def notify_review(bot: Bot, order_id: int) -> None:
    """Yangi baho haqida menejerlarga xabar (past baholar ajratib ko'rsatiladi)."""
    review = await db.get_review(order_id)
    order = await db.get_order(order_id)
    if not review or not order:
        return
    head = "⚠️ <b>PAST BAHO!</b>" if review["rating"] <= 3 else "⭐ <b>Yangi baho</b>"
    text = (
        f"{head}\n\n{'⭐' * review['rating']}{'☆' * (5 - review['rating'])} ({review['rating']}/5)\n"
        f"Buyurtma: <code>{order['code']}</code>\n👤 {h(order['customer_name'])} · {h(order['phone'])}"
    )
    if review["comment"]:
        text += f"\n💬 {h(review['comment'])}"
    managers = set(config.admin_ids) | {u["id"] for u in await db.get_staff() if u["role"] == "manager"}
    for chat_id in managers:
        try:
            await bot.send_message(chat_id, text)
        except (TelegramForbiddenError, TelegramBadRequest):
            pass


async def remind_scheduled(bot: Bot) -> None:
    """Vaqtga buyurtmalar uchun xodimlarga eslatma (tayyorlash vaqti yaqinlashganda)."""
    from datetime import timedelta

    from .utils import now

    prep = int(await db.get_setting("prep_time") or 40)
    until = (now() + timedelta(minutes=prep + 10)).strftime("%Y-%m-%d %H:%M")
    for order in await db.due_scheduled_orders(until):
        await db.mark_reminded(order["id"])
        items = await db.get_order_items(order["id"])
        text = "⏰ <b>ESLATMA: vaqtga buyurtmani tayyorlash vaqti!</b>\n\n" + format_order(order, items)
        for chat_id in await staff_recipients():
            try:
                msg = await bot.send_message(chat_id, text, reply_markup=order_staff_kb(order))
                await db.save_order_message(order["id"], chat_id, msg.message_id)
            except (TelegramForbiddenError, TelegramBadRequest):
                pass


async def scheduler_loop(bot: Bot) -> None:
    while True:
        try:
            await remind_scheduled(bot)
        except Exception:
            log.exception("Eslatma xatosi")
        await asyncio.sleep(60)


async def send_post(bot: Bot, chat_id: int, from_chat_id: int, message_ids: list[int],
                    mode: str = "copy", reply_markup: InlineKeyboardMarkup | None = None) -> None:
    """Bitta qabul qiluvchiga post yuboradi: nusxa (copy) yoki forward, albomlar bilan."""
    if mode == "forward":
        if len(message_ids) > 1:
            await bot.forward_messages(chat_id, from_chat_id, message_ids)
        else:
            await bot.forward_message(chat_id, from_chat_id, message_ids[0])
    elif len(message_ids) > 1:
        # albom: Telegram albomga inline tugma biriktirishga ruxsat bermaydi
        await bot.copy_messages(chat_id, from_chat_id, message_ids)
    else:
        await bot.copy_message(chat_id, from_chat_id, message_ids[0], reply_markup=reply_markup)


async def broadcast(bot: Bot, from_chat_id: int, message_ids: list[int], mode: str = "copy",
                    reply_markup: InlineKeyboardMarkup | None = None, progress_cb=None) -> tuple[int, int]:
    """Postni barcha foydalanuvchilarga yuboradi. (yuborildi, xato) qaytaradi."""
    ok = fail = 0
    user_ids = await db.all_user_ids()
    for i, uid in enumerate(user_ids, 1):
        for attempt in range(2):
            try:
                await send_post(bot, uid, from_chat_id, message_ids, mode, reply_markup)
                ok += 1
            except TelegramRetryAfter as e:  # flood limit — kutib qayta urinamiz
                if attempt == 0:
                    await asyncio.sleep(e.retry_after + 1)
                    continue
                fail += 1
            except TelegramForbiddenError:
                await db.set_blocked(uid, True)
                fail += 1
            except TelegramBadRequest:
                fail += 1
            except Exception as e:
                log.warning("Broadcast error %s: %s", uid, e)
                fail += 1
            break
        await asyncio.sleep(0.05)  # Telegram limiti: ~30 xabar/soniya
        if progress_cb and i % 50 == 0:
            await progress_cb(i, len(user_ids))
    return ok, fail
