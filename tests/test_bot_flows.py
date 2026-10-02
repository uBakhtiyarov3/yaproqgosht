"""Bot handlerlarini Telegram'ga ulanmasdan (soxta sessiya bilan) tekshirish."""
import datetime as dt
import itertools

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.methods import TelegramMethod
from aiogram.types import CallbackQuery, Contact, File, Location, Chat, Message, PhotoSize, Update, User

from app import db
from app.handlers import setup_routers
from app.notify import notify_new_order

ADMIN, STAFF, CUSTOMER = 1, 2, 3
_ids = itertools.count(1000)


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls = []

    async def make_request(self, bot, method: TelegramMethod, timeout=None):
        self.calls.append(method)
        if type(method).__name__ == "GetFile":
            return File(file_id="f", file_unique_id="u", file_path="photos/f.jpg")
        if method.__returning__ is Message:
            chat_id = getattr(method, "chat_id", 0) or 0
            return Message(message_id=next(_ids), date=dt.datetime.now(), chat=Chat(id=chat_id, type="private"),
                           text=getattr(method, "text", None))
        return True

    async def stream_content(self, *a, **kw):
        yield b"\xff\xd8fakejpeg"

    async def close(self):
        pass

    def texts(self, chat_id=None):
        return [getattr(c, "text", None) or getattr(c, "caption", None) or "" for c in self.calls
                if chat_id is None or getattr(c, "chat_id", None) == chat_id]


@pytest.fixture
async def env(tmp_path, monkeypatch):
    from app.config import config
    monkeypatch.setattr(config, "admin_ids", {ADMIN})
    monkeypatch.setattr(config, "uploads_dir", tmp_path / "uploads")
    # modul darajasidagi routerlarni har testda qayta ulash uchun ajratamiz
    from app.handlers import admin, admin_extra, common, shop, staff
    for r in (shop.router, admin.router, admin_extra.router, staff.router, common.router, common.fallback_router):
        r._parent_router = None
    session = FakeSession()
    bot = Bot("42:TEST", session=session, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()
    dp.include_router(setup_routers())
    await db.init_db(str(tmp_path / "bot.db"))
    await db.set_setting("mode", "open")
    yield bot, dp, session
    await db.close_db()


def user(uid):
    return User(id=uid, is_bot=False, first_name=f"U{uid}", username=f"u{uid}")


async def send(bot, dp, uid, text=None, **kw):
    msg = Message(message_id=next(_ids), date=dt.datetime.now(), chat=Chat(id=uid, type="private"),
                  from_user=user(uid), text=text, **kw)
    await dp.feed_update(bot, Update(update_id=next(_ids), message=msg))


async def click(bot, dp, uid, data, photo=False):
    msg = Message(message_id=next(_ids), date=dt.datetime.now(), chat=Chat(id=uid, type="private"),
                  text=None if photo else "x", caption="x" if photo else None,
                  photo=[PhotoSize(file_id="f", file_unique_id="u", width=1, height=1)] if photo else None)
    cq = CallbackQuery(id=str(next(_ids)), from_user=user(uid), chat_instance="c", data=data, message=msg)
    await dp.feed_update(bot, Update(update_id=next(_ids), callback_query=cq))


async def test_start_creates_account(env):
    bot, dp, s = env
    await send(bot, dp, CUSTOMER, "/start")
    assert await db.get_user(CUSTOMER)
    assert any("Tilni tanlang" in t for t in s.texts(CUSTOMER))
    await click(bot, dp, CUSTOMER, "lang:ru")
    assert (await db.get_user(CUSTOMER))["lang"] == "ru"
    assert any("автоматически создан" in t for t in s.texts(CUSTOMER))
    s.calls.clear()
    await send(bot, dp, CUSTOMER, "📋 Меню")
    assert any("Хотдоги" in str(getattr(c, "reply_markup", "")) for c in s.calls)


async def test_full_order_lifecycle(env):
    bot, dp, s = env
    for uid in (ADMIN, STAFF, CUSTOMER):
        await send(bot, dp, uid, "/start")
    # menejer xodim qo'shadi
    await click(bot, dp, ADMIN, "sadd:staff")
    await send(bot, dp, ADMIN, str(STAFF))
    assert (await db.get_user(STAFF))["role"] == "staff"

    oid = await db.create_order(CUSTOMER, {"name": "Ali", "phone": "+998901234567", "address": "Toshkent",
                                           "payment_method": "cash"},
                                [{"product_id": 1, "name": "Klassik hot-dog", "variant": "O'rta", "price": 15000, "qty": 2}], 0)
    s.calls.clear()
    await notify_new_order(bot, oid)
    assert any("YANGI BUYURTMA" in t for t in s.texts(STAFF))
    # menejerga tasdiqlash/yetkazish xabarlari bormaydi
    assert not any("YANGI BUYURTMA" in t for t in s.texts(ADMIN))

    for st in ("accepted", "cooking", "delivering", "delivered"):
        await click(bot, dp, STAFF, f"ost:{oid}:{st}")
        assert (await db.get_order(oid))["status"] == st
        if st != "delivered":
            assert not any("bajarildi" in t for t in s.texts(ADMIN))
    # bajarilgach menejerga faqat hisobot: summa va bugungi tushum
    done = [t for t in s.texts(ADMIN) if "Buyurtma bajarildi" in t]
    assert len(done) == 1 and "30 000 so'm" in done[0] and "Bugun" in done[0]
    assert (await db.get_order(oid))["staff_id"] == STAFF
    assert any("yetkazildi" in t for t in s.texts(CUSTOMER))
    # eski tugmani qayta bosish holatni buzmaydi
    await click(bot, dp, STAFF, f"ost:{oid}:cooking")
    assert (await db.get_order(oid))["status"] == "delivered"
    # mijoz xodim callbackini ishlata olmaydi
    oid2 = await db.create_order(CUSTOMER, {"name": "Ali", "phone": "+998901234567", "address": "T",
                                            "payment_method": "cash"},
                                 [{"product_id": 1, "name": "X", "variant": "", "price": 1, "qty": 1}], 0)
    await click(bot, dp, CUSTOMER, f"ost:{oid2}:accepted")
    assert (await db.get_order(oid2))["status"] == "new"
    await click(bot, dp, STAFF, f"ocr:{oid2}:2")
    o2 = await db.get_order(oid2)
    assert o2["status"] == "cancelled" and o2["cancel_reason"] == "Mahsulot tugagan"


async def test_manager_screens(env):
    bot, dp, s = env
    for text in ("/admin", "📊 Statistika", "📦 Barcha buyurtmalar", "🍔 Menyuni boshqarish",
                 "👥 Xodimlar", "⚙️ Sozlamalar", "🙋 Mijozlar", "🎁 Promo-kodlar", "⭐ Baholar", "👷 Xodim kabineti",
                 "🆕 Yangi buyurtmalar", "📈 Bugungi natija"):
        await send(bot, dp, ADMIN, text)
    for data in ("st:week", "st:all", "ol:done", "cat:1", "pr:1", "ptg:1", "ex:all", "set:mode", "sch:view", "pbg:1", "pbt:1:hit"):
        await click(bot, dp, ADMIN, data)
    assert (await db.get_setting("mode")) == "closed"
    assert (await db.get_product(1))["badges"] == "hit"
    assert (await db.get_product(1))["is_available"] == 0
    # oddiy mijoz menejer panelini ko'ra olmaydi
    s.calls.clear()
    await send(bot, dp, CUSTOMER, "/admin")
    assert not any("Menejer paneli" in t for t in s.texts(CUSTOMER))


async def test_add_and_edit_product(env):
    bot, dp, s = env
    await click(bot, dp, ADMIN, "padd:3")
    await send(bot, dp, ADMIN, "Tovuq burger")
    await send(bot, dp, ADMIN, "Tovuq filesi, salat")
    await send(bot, dp, ADMIN, "noto'g'ri narx")
    await send(bot, dp, ADMIN, "O'rta 24000\nKatta 29 000")
    await send(bot, dp, ADMIN, None, photo=[PhotoSize(file_id="f", file_unique_id="u", width=1, height=1)])
    p = (await db.get_products(3))[-1]
    assert p["name"] == "Tovuq burger" and p["variants"][1]["price"] == 29000
    assert p["image"].startswith("uploads/")
    await click(bot, dp, ADMIN, f"pe:{p['id']}:variants")
    await send(bot, dp, ADMIN, "30000")
    assert (await db.get_product(p["id"]))["variants"] == [{"name": "", "price": 30000}]
    await click(bot, dp, ADMIN, f"pdy:{p['id']}", photo=True)
    assert await db.get_product(p["id"]) is None


async def test_settings_and_broadcast(env):
    bot, dp, s = env
    await send(bot, dp, CUSTOMER, "/start")
    await click(bot, dp, ADMIN, "set:delivery_fee")
    await send(bot, dp, ADMIN, "12 000")
    assert await db.get_setting("delivery_fee") == "12000"
    await send(bot, dp, ADMIN, "📢 Xabar yuborish")
    await send(bot, dp, ADMIN, "Aksiya! Bugun 20% chegirma")
    await click(bot, dp, ADMIN, "bc:order")
    await click(bot, dp, ADMIN, "bc:link")
    await send(bot, dp, ADMIN, "Instagram - https://instagram.com/yaproqgosht")
    s.calls.clear()
    await click(bot, dp, ADMIN, "bc:send")
    import asyncio
    await asyncio.sleep(0.3)
    sent = [c for c in s.calls if type(c).__name__ == "CopyMessage" and c.chat_id == CUSTOMER]
    assert sent
    kb = sent[0].reply_markup.inline_keyboard
    assert kb[0][0].url == "https://instagram.com/yaproqgosht" and kb[1][0].callback_data == "sh:cats"


async def test_feedback_and_reply(env):
    bot, dp, s = env
    await send(bot, dp, CUSTOMER, "Salom, qachon ochilasiz?")
    header = next(c for c in s.calls if getattr(c, "chat_id", None) == ADMIN and "#u" in (getattr(c, "text", "") or ""))
    reply_to = Message(message_id=5, date=dt.datetime.now(), chat=Chat(id=ADMIN, type="private"), text=header.text.replace("<b>", "").replace("</b>", ""))
    s.calls.clear()
    await send(bot, dp, ADMIN, "Soat 10 da", reply_to_message=reply_to)
    assert any(type(c).__name__ == "CopyMessage" and c.chat_id == CUSTOMER for c in s.calls)


async def test_category_management(env):
    bot, dp, s = env
    await click(bot, dp, ADMIN, "cadd")
    await send(bot, dp, ADMIN, "☕ Ichimliklar")
    cat = (await db.get_categories())[-1]
    assert cat["name"] == "Ichimliklar" and cat["emoji"] == "☕"
    await click(bot, dp, ADMIN, f"cren:{cat['id']}")
    await send(bot, dp, ADMIN, "🥤 Salqin ichimliklar")
    assert (await db.get_category(cat["id"]))["name"] == "Salqin ichimliklar"
    await click(bot, dp, ADMIN, f"cmv:{cat['id']}:-1")
    assert [c["id"] for c in await db.get_categories()][-2] == cat["id"]
    # mahsulotni yangi kategoriyaga ko'chirish
    await click(bot, dp, ADMIN, f"pmv:1:{cat['id']}")
    assert (await db.get_product(1))["category_id"] == cat["id"]
    # mahsuloti bor kategoriya o'chmaydi
    await click(bot, dp, ADMIN, f"cdy:{cat['id']}")
    assert await db.get_category(cat["id"])
    await click(bot, dp, ADMIN, "pmv:1:1")
    await click(bot, dp, ADMIN, f"cdy:{cat['id']}")
    assert await db.get_category(cat["id"]) is None


async def test_album_broadcast(env):
    import asyncio
    bot, dp, s = env
    await send(bot, dp, CUSTOMER, "/start")
    await send(bot, dp, ADMIN, "📢 Xabar yuborish")
    photo = [PhotoSize(file_id="f", file_unique_id="u", width=1, height=1)]
    await asyncio.gather(*[
        send(bot, dp, ADMIN, None, photo=photo, media_group_id="mg1") for _ in range(3)
    ])
    s.calls.clear()
    await click(bot, dp, ADMIN, "bc:send")
    await asyncio.sleep(0.3)
    sent = [c for c in s.calls if type(c).__name__ == "CopyMessages" and c.chat_id == CUSTOMER]
    assert sent and len(sent[0].message_ids) == 3


async def test_shop_order_in_bot(env):
    bot, dp, s = env
    await send(bot, dp, STAFF, "/start")
    await db.set_role(STAFF, "staff")
    await send(bot, dp, CUSTOMER, "/start")
    await send(bot, dp, CUSTOMER, "📋 Menyu")
    assert any("Kategoriyani tanlang" in t for t in s.texts(CUSTOMER))
    await click(bot, dp, CUSTOMER, "sh:cat:1")
    await click(bot, dp, CUSTOMER, "sh:p:1:1:1")      # Katta
    await click(bot, dp, CUSTOMER, "sh:p:1:1:2", photo=True)
    await click(bot, dp, CUSTOMER, "sh:add:1:1:2", photo=True)
    await click(bot, dp, CUSTOMER, "sh:add:9:0:1")
    cart = await db.cart_get(CUSTOMER)
    assert [(i["product_id"], i["variant"], i["qty"]) for i in cart] == [(1, 1, 2), (9, 0, 1)]
    await click(bot, dp, CUSTOMER, "sh:ci:9:0:1")
    await click(bot, dp, CUSTOMER, "sh:ci:9:0:-2")
    assert len(await db.cart_get(CUSTOMER)) == 1
    s.calls.clear()
    await send(bot, dp, CUSTOMER, "🛒 Savat")
    assert any("40 000 so'm" in t for t in s.texts(CUSTOMER))

    await click(bot, dp, CUSTOMER, "sh:co")
    await click(bot, dp, CUSTOMER, "sh:ot:delivery")
    await send(bot, dp, CUSTOMER, "Ali Valiyev")
    await send(bot, dp, CUSTOMER, "12345")                       # noto'g'ri
    await send(bot, dp, CUSTOMER, None, contact=Contact(phone_number="998998081212", first_name="Ali"))
    await send(bot, dp, CUSTOMER, None, location=Location(latitude=41.31, longitude=69.24))
    await click(bot, dp, CUSTOMER, "sh:tm:asap")
    await send(bot, dp, CUSTOMER, "Domofon 25")
    await send(bot, dp, CUSTOMER, "➡️ O'tkazib yuborish")        # promo-kodsiz
    await click(bot, dp, CUSTOMER, "sh:pay:card")                # tez kunda
    await click(bot, dp, CUSTOMER, "sh:pay:cash")
    s.calls.clear()
    await click(bot, dp, CUSTOMER, "sh:ok")
    orders = await db.get_user_orders(CUSTOMER)
    assert len(orders) == 1
    o = orders[0]
    assert o["phone"] == "+998998081212" and o["total"] == 40000 and "maps.google.com" in o["address"]
    assert o["comment"] == "Domofon 25" and o["payment_method"] == "cash"
    assert await db.cart_get(CUSTOMER) == []
    assert any("YANGI BUYURTMA" in t for t in s.texts(STAFF))
    assert any(o["code"] in t for t in s.texts(CUSTOMER))
    # kuzatish va qayta buyurtma
    await click(bot, dp, CUSTOMER, f"sh:o:{o['code']}")
    await click(bot, dp, STAFF, f"sh:o:{o['code']}")             # boshqa odam ko'ra olmaydi
    await click(bot, dp, CUSTOMER, f"sh:oc:{o['code']}")
    assert (await db.get_order(o["id"]))["status"] == "cancelled"
    await click(bot, dp, CUSTOMER, f"sh:rp:{o['code']}")
    assert (await db.cart_get(CUSTOMER))[0]["qty"] == 2


async def test_checkout_cancel_keeps_cart(env):
    bot, dp, s = env
    await click(bot, dp, CUSTOMER, "sh:add:9:0:1")
    await click(bot, dp, CUSTOMER, "sh:co")
    await send(bot, dp, CUSTOMER, "❌ Buyurtmani bekor qilish")
    assert len(await db.cart_get(CUSTOMER)) == 1
    s.calls.clear()
    await send(bot, dp, CUSTOMER, "📦 Buyurtmalarim")   # holat tozalangan, tugmalar ishlaydi
    assert any("buyurtmalar yo'q" in t for t in s.texts(CUSTOMER))


async def test_backup(env):
    import io, zipfile
    bot, dp, s = env
    s.calls.clear()
    await send(bot, dp, ADMIN, "💾 Zaxira nusxa")
    doc = next(c for c in s.calls if type(c).__name__ == "SendDocument")
    zf = zipfile.ZipFile(io.BytesIO(doc.document.data))
    assert "data/bot.db" in zf.namelist()


async def test_bot_pickup_scheduled_promo_and_rating(env):
    import json as _json
    from app import hours
    bot, dp, s = env
    await db.set_setting("mode", "auto")
    await db.set_setting("schedule", _json.dumps({d: ["00:00", "23:59"] for d in hours.DAYS}))
    await db.set_setting("cafe_address", "Chilonzor 5")
    await db.add_promo(code="TEN", kind="percent", value=10)
    await send(bot, dp, STAFF, "/start")
    await db.set_role(STAFF, "staff")
    await click(bot, dp, CUSTOMER, "sh:add:9:0:2")      # 2 ta burger = 50 000
    await click(bot, dp, CUSTOMER, "sh:co")
    await click(bot, dp, CUSTOMER, "sh:ot:pickup")
    await send(bot, dp, CUSTOMER, "Vali")
    await send(bot, dp, CUSTOMER, "+998 90 111 22 33")    # manzil so'ralmaydi (pickup)
    slots = hours.slots(await db.get_settings())
    day_idx = len(slots) - 1
    await click(bot, dp, CUSTOMER, f"sh:td:{day_idx}")
    value = slots[day_idx]["times"][0]["value"]
    await click(bot, dp, CUSTOMER, "sh:tt:" + value.replace("-", "").replace(" ", "").replace(":", ""))
    await send(bot, dp, CUSTOMER, "Piyozsiz bo'lsin")
    await send(bot, dp, CUSTOMER, "XATO")                  # noto'g'ri promo -> qayta so'raydi
    assert any("topilmadi" in t for t in s.texts(CUSTOMER))
    await send(bot, dp, CUSTOMER, "ten")
    await click(bot, dp, CUSTOMER, "sh:pay:cash")
    assert any("Chilonzor 5" in t for t in s.texts(CUSTOMER))
    s.calls.clear()
    await click(bot, dp, CUSTOMER, "sh:ok")
    o = (await db.get_user_orders(CUSTOMER))[0]
    assert o["order_type"] == "pickup" and o["scheduled_at"] == value and o["promo_code"] == "TEN"
    assert o["discount"] == 5000 and o["total"] == 45000 and o["comment"] == "Piyozsiz bo'lsin"
    staff_text = next(t for t in s.texts(STAFF) if "YANGI BUYURTMA" in t)
    assert "Olib ketish" in staff_text and "VAQTGA" in staff_text and "Piyozsiz" in staff_text

    # xodim: pickup holatlari
    for st in ("accepted", "cooking", "delivering", "delivered"):
        await click(bot, dp, STAFF, f"ost:{o['id']}:{st}")
    assert any("olib ketishingiz mumkin" in t.lower() for t in s.texts(CUSTOMER))
    assert any("baholang" in t.lower() for t in s.texts(CUSTOMER))
    # baho + izoh
    s.calls.clear()
    await click(bot, dp, CUSTOMER, f"rv:{o['id']}:2")
    await send(bot, dp, CUSTOMER, "Sovuq edi")
    r = await db.get_review(o["id"])
    assert r["rating"] == 2 and r["comment"] == "Sovuq edi"
    assert any("PAST BAHO" in t for t in s.texts(ADMIN))
    await click(bot, dp, CUSTOMER, f"rv:{o['id']}:5")       # qayta baholab bo'lmaydi
    assert (await db.get_review(o["id"]))["rating"] == 2


async def test_admin_promo_schedule_discount(env):
    bot, dp, s = env
    await send(bot, dp, ADMIN, "🎁 Promo-kodlar")
    await click(bot, dp, ADMIN, "pm:new")
    await send(bot, dp, ADMIN, "bahor 2026")                 # bo'sh joy — noto'g'ri
    await send(bot, dp, ADMIN, "bahor26")
    await click(bot, dp, ADMIN, "pmk:percent")
    await send(bot, dp, ADMIN, "150")                        # >100 — noto'g'ri
    await send(bot, dp, ADMIN, "15")
    p = await db.get_promo_by_code("BAHOR26")
    assert p["kind"] == "percent" and p["value"] == 15
    await click(bot, dp, ADMIN, f"pm:e:{p['id']}:ends_at")
    await send(bot, dp, ADMIN, "7")
    await click(bot, dp, ADMIN, f"pm:e:{p['id']}:usage_limit")
    await send(bot, dp, ADMIN, "100")
    await click(bot, dp, ADMIN, f"pm:fo:{p['id']}")
    p = await db.get_promo(p["id"])
    assert p["ends_at"] and p["usage_limit"] == 100 and p["first_order_only"] == 1
    await click(bot, dp, ADMIN, f"pm:tg:{p['id']}")
    assert (await db.get_promo(p["id"]))["is_active"] == 0

    await click(bot, dp, ADMIN, "sch:d:sun")
    await send(bot, dp, ADMIN, "dam")
    await click(bot, dp, ADMIN, "sch:d:mon")
    await send(bot, dp, ADMIN, "18:00-02:00")
    from app import hours
    sch = hours.load_schedule(await db.get_settings())
    assert sch["sun"] is None and sch["mon"] == ["18:00", "02:00"]

    await click(bot, dp, ADMIN, "pe:1:discount")
    await send(bot, dp, ADMIN, "25 3")
    prod = await db.get_product(1)
    assert prod["discount_percent"] == 25 and prod["discount_until"]
    await click(bot, dp, ADMIN, "pe:1:name_ru")
    await send(bot, dp, ADMIN, "Хотдог классика")
    assert (await db.get_product(1))["name_ru"] == "Хотдог классика"
    await click(bot, dp, ADMIN, "set:tgl:pickup_enabled")
    await click(bot, dp, ADMIN, "set:tgl:delivery_enabled")  # ikkalasini o'chirib bo'lmaydi
    st = await db.get_settings()
    assert st["pickup_enabled"] == "0" and st["delivery_enabled"] == "1"
    await send(bot, dp, ADMIN, "⭐ Baholar")


async def test_orders_go_to_managers_when_no_staff(env):
    bot, dp, s = env
    await send(bot, dp, CUSTOMER, "/start")
    oid = await db.create_order(CUSTOMER, {"name": "Ali", "phone": "+998901234567", "address": "Toshkent",
                                           "payment_method": "cash"},
                                [{"product_id": 1, "name": "X", "variant": "", "price": 15000, "qty": 1}], 0)
    s.calls.clear()
    await notify_new_order(bot, oid)
    # xodim yo'q — buyurtma yo'qolmasligi uchun menejerga boradi
    assert any("YANGI BUYURTMA" in t for t in s.texts(ADMIN))


async def test_delete_order_manager_only(env):
    bot, dp, s = env
    for uid in (ADMIN, STAFF, CUSTOMER):
        await send(bot, dp, uid, "/start")
    await db.set_role(STAFF, "staff")
    oid = await db.create_order(CUSTOMER, {"name": "Ali", "phone": "+998901234567", "address": "Toshkent",
                                           "payment_method": "cash"},
                                [{"product_id": 1, "name": "X", "variant": "", "price": 15000, "qty": 1}], 0)
    code = (await db.get_order(oid))["code"]
    await notify_new_order(bot, oid)
    # xodim o'chira olmaydi
    await send(bot, dp, STAFF, f"/delorder {code}")
    await click(bot, dp, STAFF, f"odl:{oid}")
    assert await db.get_order(oid)
    # menejer o'chiradi
    await send(bot, dp, ADMIN, f"/delorder {code}")
    s.calls.clear()
    await click(bot, dp, ADMIN, f"odl:{oid}")
    assert await db.get_order(oid) is None
    assert any("o'chirildi" in t for t in s.texts(STAFF))  # xodimdagi xabar yangilandi
