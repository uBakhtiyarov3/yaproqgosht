from aiogram import Router

from . import admin, common, shop, staff


def setup_routers() -> Router:
    root = Router()
    # tartib muhim: buyurtma va menejer FSM holatlari umumiy tugmalardan oldin tekshiriladi
    root.include_routers(shop.router, admin.router, staff.router, common.router, common.fallback_router)
    return root
