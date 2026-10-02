"""Xodimlarga boradigan buyurtma kartasi: Telegram rich message (sarlavha, jadvallar, izoh bloki).

Rich xabar qabul qilinmasa (eski API / xato), avtomatik oddiy HTML matnga qaytadi.
"""
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import (
    InlineKeyboardMarkup,
    InputRichBlockBlockQuotation,
    InputRichBlockFooter,
    InputRichBlockParagraph,
    InputRichBlockSectionHeading,
    InputRichBlockTable,
    InputRichMessage,
    Message,
    RichBlockTableCell,
    RichTextBold,
    RichTextPhoneNumber,
)

from .utils import PAYMENT_LABELS, TYPE_LABELS, fmt_dt, format_order, money, phone_fmt, status_label

log = logging.getLogger(__name__)


def _cell(text, align: str = "left", header: bool = False, colspan: int | None = None) -> RichBlockTableCell:
    return RichBlockTableCell(align=align, valign="middle", text=text, is_header=header or None, colspan=colspan)


def _sum_row(label, value, bold: bool = False) -> list[RichBlockTableCell]:
    if bold:
        label, value = RichTextBold(text=label), RichTextBold(text=value)
    return [_cell(label, colspan=2), _cell(value, "right")]


def rich_order(order: dict, items: list[dict], header: str = "") -> InputRichMessage:
    otype = order.get("order_type") or "delivery"
    blocks = [
        InputRichBlockSectionHeading(text=f"{header or '🧾 Buyurtma'} · {order['code']}", size=2),
        InputRichBlockParagraph(text=[RichTextBold(text=status_label(order["status"], otype)),
                                      f"  ·  {TYPE_LABELS[otype]}"]),
        InputRichBlockParagraph(text=RichTextBold(text=f"⏰ VAQTGA: {fmt_dt(order['scheduled_at'])}")
                                if order.get("scheduled_at") else "⚡ Imkon qadar tez"),
    ]

    # mahsulotlar jadvali
    rows = [[_cell("Mahsulot", header=True), _cell("Soni", "center", True), _cell("Summa", "right", True)]]
    for it in items:
        name = it["name"] + (f" ({it['variant']})" if it["variant"] else "")
        rows.append([_cell(name), _cell(f"×{it['qty']}", "center"), _cell(money(it["price"] * it["qty"]), "right")])
    rows.append(_sum_row("Mahsulotlar", money(order["subtotal"])))
    if order.get("discount"):
        rows.append(_sum_row(f"🎁 Promo {order.get('promo_code') or ''}".strip(), "−" + money(order["discount"])))
    elif order.get("promo_code"):
        rows.append(_sum_row(f"🎁 Promo {order['promo_code']}", "bepul yetkazish"))
    if otype == "delivery":
        rows.append(_sum_row("Yetkazish", money(order["delivery_fee"]) if order["delivery_fee"] else "bepul"))
    rows.append(_sum_row("JAMI", money(order["total"]), bold=True))
    blocks.append(InputRichBlockTable(cells=rows, is_bordered=True, is_striped=True, is_compact=True))

    # mijoz jadvali
    phone = phone_fmt(order["phone"])
    info = [
        [_cell("👤 Mijoz"), _cell(RichTextBold(text=order["customer_name"] + (" 🇷🇺" if order.get("lang") == "ru" else "")))],
        [_cell("📞 Telefon"), _cell(RichTextPhoneNumber(text=phone, phone_number=phone.replace(" ", "")))],
    ]
    if otype == "delivery":
        info.append([_cell("📍 Manzil"), _cell(order["address"])])
    info.append([_cell("💵 To'lov"), _cell(PAYMENT_LABELS.get(order["payment_method"], order["payment_method"]))])
    if order.get("staff_name"):
        info.append([_cell("👷 Mas'ul"), _cell(order["staff_name"])])
    blocks.append(InputRichBlockTable(cells=info, is_bordered=True, is_compact=True))

    if order.get("comment"):
        blocks.append(InputRichBlockBlockQuotation(
            blocks=[InputRichBlockParagraph(text=[RichTextBold(text="💬 Izoh: "), order["comment"]])]))
    if order.get("cancel_reason"):
        blocks.append(InputRichBlockParagraph(text=[RichTextBold(text="Bekor qilish sababi: "), order["cancel_reason"]]))
    blocks.append(InputRichBlockFooter(text=f"🕒 {order['created_at'][:16]}"))
    return InputRichMessage(blocks=blocks)


def plain_order(order: dict, items: list[dict], header: str = "") -> str:
    return (f"<b>{header}</b>\n\n" if header else "") + format_order(order, items)


async def send_order_card(bot: Bot, chat_id: int, order: dict, items: list[dict], header: str = "",
                          reply_markup: InlineKeyboardMarkup | None = None) -> Message:
    try:
        return await bot.send_rich_message(chat_id, rich_order(order, items, header), reply_markup=reply_markup)
    except TelegramForbiddenError:
        raise
    except TelegramBadRequest as e:
        log.warning("Rich xabar yuborilmadi, oddiy matnga o'tildi: %s", e)
        return await bot.send_message(chat_id, plain_order(order, items, header), reply_markup=reply_markup)


async def edit_order_card(bot: Bot, chat_id: int, message_id: int, order: dict, items: list[dict],
                          reply_markup: InlineKeyboardMarkup | None = None) -> None:
    try:
        await bot.edit_message_text(chat_id=chat_id, message_id=message_id, rich_message=rich_order(order, items),
                                    reply_markup=reply_markup)
        return
    except TelegramBadRequest as e:
        if "not modified" in str(e):
            return
    # eski (oddiy matnli) xabar yoki rich qo'llab-quvvatlanmasa
    await bot.edit_message_text(plain_order(order, items), chat_id=chat_id, message_id=message_id,
                                reply_markup=reply_markup)
