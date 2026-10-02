"""Tahrirlanadigan tugma matnlari uchun dinamik filtr (admin panelda o'zgartirilsa ham ishlaydi)."""
from aiogram.filters import BaseFilter
from aiogram.types import Message

from .i18n import both


class Btn(BaseFilter):
    def __init__(self, key: str):
        self.key = key

    async def __call__(self, message: Message) -> bool:
        return bool(message.text) and message.text in both(self.key)
