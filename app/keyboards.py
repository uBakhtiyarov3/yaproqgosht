from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from .config import config
from .utils import NEXT_STATUS


def webapp_ready() -> bool:
    return config.webapp_url.startswith("https://")


def webapp_url(section: str = "") -> str:
    return config.webapp_url + "/" + (f"#{section}" if section else "")


# ---------------- reply keyboards ----------------

class B:
    """Reply tugmalar matnlari (handlerlarda filtr sifatida ishlatiladi)."""
    MENU = "🍔 Mini ilovada buyurtma"
    BOT_MENU = "📋 Menyu"
    CART = "🛒 Savat"
    MY_ORDERS = "📦 Buyurtmalarim"
    CONTACT = "📞 Aloqa"
    ABOUT = "ℹ️ Biz haqimizda"
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

    CANCEL = "🚫 Bekor qilish"


def main_kb(role: str) -> ReplyKeyboardMarkup:
    rows = []
    if webapp_ready():
        # Eslatma: reply-klaviatura orqali ochilgan Mini App ga Telegram initData bermaydi,
        # shuning uchun bu oddiy tugma — bosilganda bot inline web_app tugmasini yuboradi.
        rows.append([KeyboardButton(text=B.MENU)])
    rows += [
        [KeyboardButton(text=B.BOT_MENU), KeyboardButton(text=B.CART)],
        [KeyboardButton(text=B.MY_ORDERS), KeyboardButton(text=B.CONTACT)],
        [KeyboardButton(text=B.ABOUT)],
    ]
    if role in ("staff", "manager"):
        rows.append([KeyboardButton(text=B.STAFF)])
    if role == "manager":
        rows[-1].append(KeyboardButton(text=B.MANAGER))
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def start_inline_kb() -> InlineKeyboardMarkup:
    """/start dagi ikki yo'l: Mini App yoki bot ichida buyurtma."""
    rows = []
    if webapp_ready():
        rows.append([InlineKeyboardButton(text="🍔 Mini ilovada buyurtma berish", web_app=WebAppInfo(url=webapp_url()))])
    rows.append([InlineKeyboardButton(text="📋 Botning o'zida buyurtma berish", callback_data="sh:cats")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def order_track_kb(code: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="📦 Buyurtmani kuzatish", callback_data=f"sh:o:{code}")]]
    if webapp_ready():
        rows.append([InlineKeyboardButton(text="🍔 Mini ilovada ochish", web_app=WebAppInfo(url=webapp_url("orders")))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
    status = order["status"]
    if status not in NEXT_STATUS:
        return None
    nxt, label = NEXT_STATUS[status]
    return ikb([
        [(label, f"ost:{order['id']}:{nxt}")],
        [("❌ Bekor qilish", f"ocn:{order['id']}")],
    ])
