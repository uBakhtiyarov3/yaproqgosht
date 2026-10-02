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
ACTIVE_STATUSES = ("new", "accepted", "cooking", "delivering")

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
    lines = [
        f"<b>🧾 Buyurtma</b> <code>{order['code']}</code>",
        f"Holati: <b>{STATUS_LABELS.get(order['status'], order['status'])}</b>",
        "",
    ]
    for it in items:
        variant = f" ({h(it['variant'])})" if it["variant"] else ""
        lines.append(
            f"• {h(it['name'])}{variant} × {it['qty']} = {money(it['price'] * it['qty'])}"
        )
    lines.append("")
    lines.append(f"Mahsulotlar: {money(order['subtotal'])}")
    lines.append(f"Yetkazish: {money(order['delivery_fee']) if order['delivery_fee'] else 'bepul'}")
    lines.append(f"<b>Jami: {money(order['total'])}</b>")
    lines.append(f"To'lov: {PAYMENT_LABELS.get(order['payment_method'], order['payment_method'])}")
    lines.append("")
    lines.append(f"👤 {h(order['customer_name'])}")
    lines.append(f"📞 {h(phone_fmt(order['phone']))}")
    lines.append(f"📍 {h(order['address'])}")
    if order.get("comment"):
        lines.append(f"💬 {h(order['comment'])}")
    if order.get("cancel_reason"):
        lines.append(f"Bekor qilish sababi: {h(order['cancel_reason'])}")
    lines.append(f"🕒 {order['created_at'][:16]}")
    if for_staff and order.get("staff_name"):
        lines.append(f"👷 Mas'ul: {h(order['staff_name'])}")
    return "\n".join(lines)
