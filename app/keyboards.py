from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from .config import config
from .i18n import t
from .utils import next_status


def webapp_ready() -> bool:
    return config.webapp_url.startswith("https://")


def webapp_url(section: str = "") -> str:
    return config.webapp_url + "/" + (f"#{section}" if section else "")


# ---------------- reply keyboards ----------------

class B:
    """Reply tugmalar matnlari (handlerlarda filtr sifatida ishlatiladi)."""
    # Mijoz tugmalari ikki tilli — i18n.py dagi b_* kalitlari (handlerlarda both("b_...") bilan)
    STAFF = "👷 Xodim kabineti"
    MANAGER = "👑 Menejer paneli"
    BACK = "⬅️ Asosiy menyu"

    # xodim
    NEW_ORDERS = "🆕 Yangi buyurtmalar"
    ACTIVE_ORDERS = "🔄 Faol buyurtmalar"
    MY_TASKS = "📋 Mening buyurtmalarim"
    TODAY = "📈 Bugungi natija"

    # menejer
    STATS = "📊 Statistika"
    ORDERS = "📦 Barcha buyurtmalar"
    MENU_EDIT = "🍔 Menyuni boshqarish"
    BROADCAST = "📢 Xabar yuborish"
    STAFF_LIST = "👥 Xodimlar"
    SETTINGS = "⚙️ Sozlamalar"
    EXPORT = "📥 Hisobot (CSV)"
    USERS = "🙋 Mijozlar"
    BACKUP = "💾 Zaxira nusxa"
    PROMOS = "🎁 Promo-kodlar"
    REVIEWS = "⭐ Baholar"

    CANCEL = "🚫 Bekor qilish"


def main_kb(role: str, lang: str = "uz") -> ReplyKeyboardMarkup:
    rows = []
    if webapp_ready():
        # Eslatma: reply-klaviatura orqali ochilgan Mini App ga Telegram initData bermaydi,
        # shuning uchun bu oddiy tugma — bosilganda bot inline web_app tugmasini yuboradi.
        rows.append([KeyboardButton(text=t("b_menu_mini", lang))])
    rows += [
        [KeyboardButton(text=t("b_menu", lang)), KeyboardButton(text=t("b_cart", lang))],
        [KeyboardButton(text=t("b_orders", lang)), KeyboardButton(text=t("b_contact", lang))],
        [KeyboardButton(text=t("b_about", lang)), KeyboardButton(text=t("b_lang", lang))],
    ]
    if role in ("staff", "manager"):
        rows.append([KeyboardButton(text=B.STAFF)])
    if role == "manager":
        rows[-1].append(KeyboardButton(text=B.MANAGER))
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def start_inline_kb(lang: str = "uz") -> InlineKeyboardMarkup:
    """/start dagi ikki yo'l: Mini App yoki bot ichida buyurtma."""
    rows = []
    if webapp_ready():
        rows.append([InlineKeyboardButton(text=t("start_mini_btn", lang), web_app=WebAppInfo(url=webapp_url()))])
    rows.append([InlineKeyboardButton(text=t("start_bot_btn", lang), callback_data="sh:cats")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def lang_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang:uz"),
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
    ]])


def order_track_kb(code: str, lang: str = "uz") -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=t("track_btn", lang), callback_data=f"sh:o:{code}")]]
    if webapp_ready():
        rows.append([InlineKeyboardButton(text=t("mini_inline", lang), web_app=WebAppInfo(url=webapp_url("orders")))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def rating_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"{n}⭐", callback_data=f"rv:{order_id}:{n}") for n in range(1, 6)
    ]])


def staff_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=B.NEW_ORDERS), KeyboardButton(text=B.ACTIVE_ORDERS)],
            [KeyboardButton(text=B.MY_TASKS), KeyboardButton(text=B.TODAY)],
            [KeyboardButton(text=B.BACK)],
        ],
        resize_keyboard=True,
    )


def manager_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=B.STATS), KeyboardButton(text=B.ORDERS)],
            [KeyboardButton(text=B.MENU_EDIT), KeyboardButton(text=B.BROADCAST)],
            [KeyboardButton(text=B.STAFF_LIST), KeyboardButton(text=B.USERS)],
            [KeyboardButton(text=B.PROMOS), KeyboardButton(text=B.REVIEWS)],
            [KeyboardButton(text=B.SETTINGS), KeyboardButton(text=B.EXPORT)],
            [KeyboardButton(text=B.BACKUP)],
            [KeyboardButton(text=B.STAFF), KeyboardButton(text=B.BACK)],
        ],
        resize_keyboard=True,
    )


def cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=B.CANCEL)]], resize_keyboard=True)


# ---------------- inline keyboards ----------------

def ikb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=d) for t, d in row] for row in rows]
    )


def webapp_inline_kb(text: str = "🍔 Menyuni ochish", section: str = "") -> InlineKeyboardMarkup | None:
    if not webapp_ready():
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, web_app=WebAppInfo(url=webapp_url(section)))]]
    )


def order_staff_kb(order: dict) -> InlineKeyboardMarkup | None:
    step = next_status(order["status"], order.get("order_type") or "delivery")
    if not step:
        return None
    nxt, label = step
    return ikb([
        [(label, f"ost:{order['id']}:{nxt}")],
        [("❌ Bekor qilish", f"ocn:{order['id']}")],
    ])
