from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from . import db
from .config import config


async def get_role(user_id: int) -> str:
    if user_id in config.admin_ids:
        return "manager"
    user = await db.get_user(user_id)
    return user["role"] if user else "user"


class RoleFilter(BaseFilter):
    """Faqat ko'rsatilgan rollar uchun handler."""

    def __init__(self, *roles: str):
        self.roles = roles

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        return await get_role(event.from_user.id) in self.roles


IsStaff = RoleFilter("staff", "manager")
IsManager = RoleFilter("manager")
