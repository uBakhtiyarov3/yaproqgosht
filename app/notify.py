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
from .order_card import edit_order_card, send_order_card
from .utils import h

log = logging.getLogger(__name__)


async def manager_ids() -> set[int]:
    return set(config.admin_ids) | {u["id"] for u in await db.get_staff() if u["role"] == "manager"}


async def staff_recipients() -> list[int]:
    """Buyurtma xabarlari (tasdiqlash, yetkazish tugmalari) faqat xodimlarga boradi.
    Menejerlarga bormaydi — ular faqat bajarilgan buyurtma haqida hisobot oladi.
    Bitta ham xodim bo'lmasa, buyurtma yo'qolmasligi uchun menejerlarga yuboriladi."""
    managers = await manager_ids()
    ids = {u["id"] for u in await db.get_staff() if u["role"] == "staff"} - managers
    return sorted(ids or managers)


async def notify_managers_done(bot: Bot, order: dict) -> None:
    """Buyurtma bajarilganda menejerlarga qisqa hisobot: summa va bugungi tushum."""
    from .utils import money, now, status_label

    since = now().strftime("%Y-%m-%d 00:00:00")
    row = await db.fetchone(
        "SELECT COUNT(*) c, COALESCE(SUM(total), 0) s FROM orders WHERE status = 'delivered' AND created_at >= ?",
        since,
    )
    otype = order.get("order_type") or "delivery"
    text = (
        f"✅ <b>Buyurtma bajarildi</b> — <code>{order['code']}</code>\n"
        f"{status_label('delivered', otype)}\n\n"
        f"💰 Tushum: <b>{money(order['total'])}</b>"
        + (f" (chegirma {money(order['discount'])})" if order.get("discount") else "")
        + (f"\n👷 Xodim: {h(order['staff_name'])}" if order.get("staff_name") else "")
        + f"\n\n📊 Bugun: <b>{row['c']}</b> ta buyurtma, jami <b>{money(row['s'])}</b>"
    )
    for chat_id in await manager_ids():
        try:
            await bot.send_message(chat_id, text)
        except (TelegramForbiddenError, TelegramBadRequest):
            pass


async def notify_new_order(bot: Bot, order_id: int, notify_customer: bool = True) -> None:
    order = await db.get_order(order_id)
    items = await db.get_order_items(order_id)
    kb = order_staff_kb(order)
    for chat_id in await staff_recipients():
        try:
            msg = await send_order_card(bot, chat_id, order, items, "🔔 YANGI BUYURTMA", kb)
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
    kb: InlineKeyboardMarkup | None = order_staff_kb(order)
    for m in await db.get_order_messages(order_id):
        try:
            await edit_order_card(bot, m["chat_id"], m["message_id"], order, items, kb)
        except TelegramBadRequest as e:
            if "not modified" not in str(e):
                log.debug("Edit failed: %s", e)
        except TelegramForbiddenError:
            pass


async def delete_order(bot: Bot | None, order: dict) -> None:
    """Buyurtmani o'chiradi va xodimlardagi xabarlarni «o'chirildi» deb yangilaydi (tugmalarsiz)."""
    messages = await db.delete_order(order["id"])
    if not bot:
        return
    text = f"🗑 <s>Buyurtma {order['code']}</s>\n\nMenejer tomonidan o'chirildi."
    from aiogram.types import InputRichBlockParagraph, InputRichMessage, RichTextStrikethrough

    rich = InputRichMessage(blocks=[InputRichBlockParagraph(text=[
        "🗑 ", RichTextStrikethrough(text=f"Buyurtma {order['code']}"), " — menejer tomonidan o'chirildi."])])
    for m in messages:
        for kwargs in ({"rich_message": rich}, {"text": text}):  # rich kartani rich bilan, eskisini matn bilan
            try:
                await bot.edit_message_text(chat_id=m["chat_id"], message_id=m["message_id"], reply_markup=None,
                                            **kwargs)
                break
            except TelegramBadRequest:
                continue
            except TelegramForbiddenError:
                break


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
    if order["status"] == "delivered":
        await notify_managers_done(bot, order)
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
    for chat_id in await manager_ids():
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
        for chat_id in await staff_recipients():
            try:
                msg = await send_order_card(bot, chat_id, order, items, "⏰ ESLATMA: tayyorlash vaqti",
                                            order_staff_kb(order))
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
