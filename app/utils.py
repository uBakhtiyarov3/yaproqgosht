from datetime import datetime, timedelta, timezone
from html import escape

# O'zbekiston vaqti (UTC+5, yozgi vaqt yo'q)
TZ = timezone(timedelta(hours=5))

STATUSES = ["new", "accepted", "cooking", "delivering", "delivered"]
STATUS_LABELS = {
    "new": "🕐 Yangi (tasdiqlanmagan)",
    "accepted": "✅ Qabul qilindi",
    "cooking": "👨‍🍳 Tayyorlanmoqda",
    "delivering": "🛵 Yetkazilmoqda",
    "delivered": "🎉 Yetkazildi",
    "cancelled": "❌ Bekor qilindi",
}
# Xodim bosadigan "keyingi qadam" tugmalari
NEXT_STATUS = {
    "new": ("accepted", "✅ Qabul qilish"),
    "accepted": ("cooking", "👨‍🍳 Tayyorlashni boshlash"),
    "cooking": ("delivering", "🛵 Yetkazishga berish"),
    "delivering": ("delivered", "🎉 Yetkazildi"),
}
# Olib ketish (pickup) uchun boshqacha nomlar
PICKUP_LABELS = {"delivering": "🛍 Tayyor — olib ketishni kutmoqda", "delivered": "🎉 Mijozga berildi"}
PICKUP_NEXT = {
    "cooking": ("delivering", "🛍 Tayyor (olib ketishga)"),
    "delivering": ("delivered", "🎉 Mijozga berildi"),
}
ACTIVE_STATUSES = ("new", "accepted", "cooking", "delivering")
TYPE_LABELS = {"delivery": "🛵 Yetkazib berish", "pickup": "🏃 Olib ketish"}


def status_label(status: str, order_type: str = "delivery") -> str:
    if order_type == "pickup" and status in PICKUP_LABELS:
        return PICKUP_LABELS[status]
    return STATUS_LABELS.get(status, status)


def next_status(status: str, order_type: str = "delivery") -> tuple[str, str] | None:
    if order_type == "pickup" and status in PICKUP_NEXT:
        return PICKUP_NEXT[status]
    return NEXT_STATUS.get(status)


def fmt_dt(value: str) -> str:
    """'2026-10-02 19:00' -> '02.10 19:00' (bugun bo'lsa faqat vaqt bilan 'bugun')."""
    try:
        dt = datetime.strptime(value[:16], "%Y-%m-%d %H:%M")
    except ValueError:
        return value
    if dt.date() == now().date():
        return "bugun " + dt.strftime("%H:%M")
    if (dt.date() - now().date()).days == 1:
        return "ertaga " + dt.strftime("%H:%M")
    return dt.strftime("%d.%m %H:%M")

PAYMENT_LABELS = {"cash": "💵 Naqd", "card": "💳 Karta"}


def now() -> datetime:
    return datetime.now(TZ)


def now_str() -> str:
    return now().strftime("%Y-%m-%d %H:%M:%S")


def money(amount: int | float) -> str:
    return f"{int(amount):,}".replace(",", " ") + " so'm"


def phone_fmt(phone: str) -> str:
    """+998901234567 -> +998 90 123 45 67"""
    d = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if len(d) == 12 and d.startswith("998"):
        return f"+998 {d[3:5]} {d[5:8]} {d[8:10]} {d[10:12]}"
    return str(phone or "")


def h(text) -> str:
    return escape(str(text or ""), quote=False)


def format_order(order: dict, items: list[dict], for_staff: bool = True) -> str:
    otype = order.get("order_type") or "delivery"
    lines = [
        f"<b>🧾 Buyurtma</b> <code>{order['code']}</code> · {TYPE_LABELS[otype]}",
        f"Holati: <b>{status_label(order['status'], otype)}</b>",
    ]
    if order.get("scheduled_at"):
        lines.append(f"⏰ <b>VAQTGA: {fmt_dt(order['scheduled_at'])}</b>")
    else:
        lines.append("⚡ Imkon qadar tez")
    lines.append("")
    for it in items:
        variant = f" ({h(it['variant'])})" if it["variant"] else ""
        lines.append(
            f"• {h(it['name'])}{variant} × {it['qty']} = {money(it['price'] * it['qty'])}"
        )
    lines.append("")
    lines.append(f"Mahsulotlar: {money(order['subtotal'])}")
    if order.get("discount"):
        lines.append(f"🎁 Promo-kod {h(order.get('promo_code'))}: −{money(order['discount'])}")
    elif order.get("promo_code"):
        lines.append(f"🎁 Promo-kod {h(order['promo_code'])}: bepul yetkazish")
    if otype == "delivery":
        lines.append(f"Yetkazish: {money(order['delivery_fee']) if order['delivery_fee'] else 'bepul'}")
    lines.append(f"<b>Jami: {money(order['total'])}</b>")
    lines.append(f"To'lov: {PAYMENT_LABELS.get(order['payment_method'], order['payment_method'])}")
    lines.append("")
    lines.append(f"👤 {h(order['customer_name'])}" + (" 🇷🇺" if order.get("lang") == "ru" else ""))
    lines.append(f"📞 {h(phone_fmt(order['phone']))}")
    if otype == "delivery":
        lines.append(f"📍 {h(order['address'])}")
    if order.get("comment"):
        lines.append(f"💬 <b>Izoh:</b> {h(order['comment'])}")
    if order.get("cancel_reason"):
        lines.append(f"Bekor qilish sababi: {h(order['cancel_reason'])}")
    lines.append(f"🕒 {order['created_at'][:16]}")
    if for_staff and order.get("staff_name"):
        lines.append(f"👷 Mas'ul: {h(order['staff_name'])}")
    return "\n".join(lines)
