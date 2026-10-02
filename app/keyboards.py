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
    MENU = "🍔 Menyu / Buyurtma berish"
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

    CANCEL = "🚫 Bekor qilish"


def main_kb(role: str) -> ReplyKeyboardMarkup:
    menu_btn = (
        KeyboardButton(text=B.MENU, web_app=WebAppInfo(url=webapp_url()))
        if webapp_ready() else KeyboardButton(text=B.MENU)
    )
    rows = [[menu_btn], [KeyboardButton(text=B.MY_ORDERS), KeyboardButton(text=B.CONTACT)],
            [KeyboardButton(text=B.ABOUT)]]
    if role in ("staff", "manager"):
        rows.append([KeyboardButton(text=B.STAFF)])
    if role == "manager":
        rows[-1].append(KeyboardButton(text=B.MANAGER))
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


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
