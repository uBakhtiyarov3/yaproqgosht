"""Admin panel uchun matnlar katalogi: guruhlar, turi (HTML/oddiy) va saqlashdan oldingi tekshiruv."""
from html.parser import HTMLParser

from .i18n import T, default_text, placeholders

GROUPS: list[tuple[str, list[str]]] = [
    ("🏠 Start va umumiy", [
        "choose_lang", "lang_saved", "greet", "account_created", "closed_now", "opens_short", "opens_at",
        "how_order", "ways_mini", "ways_bot", "start_mini_btn", "start_bot_btn", "main_menu", "open_mini_text",
        "open_mini_btn", "contact", "phone_soon", "address_line", "about", "feedback_sent", "help",
        "reply_from_cafe",
    ]),
    ("⌨️ Pastki menyu tugmalari", ["b_"]),
    ("📋 Menyu (bot ichida)", [
        "menu_title", "choose_product", "cat_empty", "back_cats", "back", "cart_btn", "orders_btn", "mini_inline",
        "from", "chosen", "pcs", "add_btn", "added", "added_toast", "unavailable", "qty_limit",
    ]),
    ("🛒 Savat", [
        "cart_empty", "to_menu", "cart_title", "items_sum", "delivery", "free", "discount", "total",
        "min_order_warn", "clear", "menu_btn", "checkout_btn", "cart_cleared",
    ]),
    ("📝 Rasmiylashtirish", [
        "co_", "ask_", "bad_", "send_", "location_", "type_", "asap", "today", "tomorrow", "pick_time", "no_slots",
        "promo_ok", "payment_hint", "pay_", "check_title", "payment", "confirm_btn", "refill_btn", "cancel_btn",
        "form_stale", "order_placed", "order_sent_toast", "thanks", "pickup_", "when_",
    ]),
    ("📦 Buyurtmalarim", [
        "no_orders", "orders_title", "order_title", "reason", "refresh", "refreshed", "cancel_order_btn",
        "repeat_btn", "back_orders", "order_not_found", "cancel_not_allowed", "order_cancelled_toast",
        "repeat_added", "repeat_none", "your_rating", "rate_btn",
    ]),
    ("🔔 Holat o'zgarishi xabarlari", ["sent_new", "track_btn", "st_"]),
    ("⭐ Baholash", ["rate_ask", "rate_thanks", "review_saved", "already_rated", "rate_not_ready"]),
    ("🏷 Holat nomlari", ["s_", "step_new"]),
    ("⚠️ Xato xabarlari", ["e_"]),
    ("🎁 Promo-kod turlari", ["promo_percent", "promo_fixed", "promo_free_delivery"]),
    ("📱 Mini ilova", ["w_"]),
]

# Oddiy matn (HTML teglarisiz) bo'lishi kerak bo'lganlar: tugmalar, ogohlantirishlar, Mini App matnlari
PLAIN_PREFIXES = ("b_", "w_", "e_", "s_", "pay_", "type_", "co_")
PLAIN_KEYS = {
    "start_mini_btn", "start_bot_btn", "open_mini_btn", "back_cats", "back", "cart_btn", "orders_btn", "mini_inline",
    "from", "pcs", "add_btn", "added_toast", "unavailable", "qty_limit", "to_menu", "clear", "menu_btn",
    "checkout_btn", "send_phone_btn", "send_location_btn", "asap", "today", "tomorrow", "confirm_btn",
    "refill_btn", "cancel_btn", "form_stale", "order_sent_toast", "refresh", "refreshed", "cancel_order_btn",
    "repeat_btn", "back_orders", "order_not_found", "cancel_not_allowed", "order_cancelled_toast", "rate_btn",
    "track_btn", "already_rated", "rate_not_ready", "lang_saved", "step_new", "location_label",
    "promo_percent", "promo_fixed", "promo_free_delivery", "pay_card_alert", "items_sum", "delivery", "free",
    "discount", "total", "payment", "phone_soon", "chosen", "when_asap", "when_at", "pickup_cafe",
}
# Telegram callback alert (answerCallbackQuery) — 200 belgigacha
ALERT_KEYS = {"pay_card_alert", "form_stale", "already_rated", "rate_not_ready", "order_not_found",
              "cancel_not_allowed", "unavailable", "qty_limit", "no_slots", "added_toast", "lang_saved"}
ALLOWED_TAGS = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "code", "pre", "a", "tg-spoiler",
                "blockquote", "span", "tg-emoji"}


def group_of(key: str) -> str:
    for title, items in GROUPS:
        for item in items:
            if key == item or (item.endswith("_") and key.startswith(item)):
                return title
    return "Boshqa"


def is_plain(key: str) -> bool:
    return key in PLAIN_KEYS or key.startswith(PLAIN_PREFIXES)


def max_len(key: str) -> int:
    if key in ALERT_KEYS:
        return 200
    if key.startswith("b_") or key.endswith("_btn") or key in PLAIN_KEYS:
        return 120
    return 3500


class _Checker(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in ALLOWED_TAGS:
            self.errors.append(f"<{tag}> tegi Telegramda ishlamaydi")
            return
        if tag == "a" and not dict(attrs).get("href"):
            self.errors.append("<a> tegida href bo'lishi kerak")
        if tag == "span" and dict(attrs).get("class") != "tg-spoiler":
            self.errors.append('<span> faqat class="tg-spoiler" bilan')
        self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag not in ALLOWED_TAGS:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"</{tag}> noto'g'ri yopilgan")
            return
        self.stack.pop()


def validate(key: str, lang: str, value: str) -> list[str]:
    """Xatolar ro'yxati (bo'sh — saqlash mumkin)."""
    errors = []
    if key not in T:
        return ["Bunday matn kaliti yo'q"]
    if len(value) > max_len(key):
        errors.append(f"Juda uzun: {len(value)} / {max_len(key)} belgi")
    allowed = placeholders(default_text(key, lang)) | placeholders(default_text(key, "uz"))
    used = placeholders(value)
    unknown = used - allowed
    if "<xato>" in used:
        errors.append("Figurali qavslar { } noto'g'ri ishlatilgan")
    elif unknown:
        errors.append("Noma'lum o'zgaruvchi: " + ", ".join("{" + u + "}" for u in sorted(unknown))
                      + ". Ruxsat: " + (", ".join("{" + a + "}" for a in sorted(allowed)) or "yo'q"))
    if is_plain(key):
        if "<" in value and ">" in value:
            errors.append("Bu matnda formatlash (teglar) ishlatib bo'lmaydi — tugma yoki oddiy matn")
    else:
        checker = _Checker()
        checker.feed(value)
        checker.close()
        errors += checker.errors
        if checker.stack:
            errors.append("Yopilmagan teg: " + ", ".join(f"<{t}>" for t in checker.stack))
    return errors


def catalog(overrides: dict) -> list[dict]:
    """Admin panel uchun barcha matnlar: guruh, turi, asl va joriy qiymatlar."""
    items = []
    for key in T:
        items.append({
            "key": key,
            "group": group_of(key),
            "plain": is_plain(key),
            "max": max_len(key),
            "vars": sorted(placeholders(default_text(key, "uz")) | placeholders(default_text(key, "ru"))),
            "uz": {"default": default_text(key, "uz"), "value": overrides.get((key, "uz"))},
            "ru": {"default": default_text(key, "ru"), "value": overrides.get((key, "ru"))},
        })
    order = {title: i for i, (title, _) in enumerate(GROUPS)}
    items.sort(key=lambda x: order.get(x["group"], 99))
    return items
