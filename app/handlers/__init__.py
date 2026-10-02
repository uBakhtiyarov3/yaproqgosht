from aiogram import Router

from . import admin, common, staff


def setup_routers() -> Router:
    root = Router()
    # tartib muhim: menejer FSM holatlari umumiy tugmalardan oldin tekshiriladi
    root.include_routers(admin.router, staff.router, common.router, common.fallback_router)
    return root
