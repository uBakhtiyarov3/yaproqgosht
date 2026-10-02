"""Promo-kod, olib ketish, vaqtga buyurtma, jadval, chegirma, baho va rus tili."""
import json
from datetime import datetime, timedelta

import pytest

from app import db, hours
from app.catalog import apply_percent, variant_price
from app.utils import TZ, now
from app.webapp import create_app
from test_api import H, ORDER

PICK = {**ORDER, "order_type": "pickup", "address": ""}


@pytest.fixture
async def client(aiohttp_client, tmp_path):
    await db.init_db(str(tmp_path / "f.db"))
    await db.set_setting("mode", "open")
    c = await aiohttp_client(create_app(None))
    yield c
    await db.close_db()


async def post(client, path, body, uid=300):
    r = await client.post(path, json=body, headers=H(uid))
    return r.status, await r.json()


# ---------- jadval ----------

def test_hours_overnight_and_slots():
    s = {"mode": "auto", "schedule": json.dumps({d: ["18:00", "02:00"] for d in hours.DAYS}),
         "prep_time": "40", "slot_step": "30"}
    day = datetime(2026, 10, 5, tzinfo=TZ)
    assert hours.is_open_at(s, day.replace(hour=1, minute=30))       # tun 01:30 — oldingi kun oynasi
    assert not hours.is_open_at(s, day.replace(hour=3))
    assert hours.is_open_at(s, day.replace(hour=19))
    assert hours.next_opening(s, day.replace(hour=3)) == day.replace(hour=18)
    sl = hours.slots(s, day.replace(hour=17, minute=0))
    assert sl[0]["day"] == "today" and sl[0]["times"][0]["label"] == "18:00"
    assert sl[0]["times"][-1]["value"].endswith("01:30")              # yarim tundan keyin ham
    assert hours.valid_slot(s, sl[0]["times"][3]["value"], day.replace(hour=17))
    assert not hours.slots({**s, "mode": "closed"}, day)
    off = {**s, "schedule": json.dumps({**{d: ["10:00", "22:00"] for d in hours.DAYS}, "sun": None})}
    assert not hours.is_open_at(off, datetime(2026, 10, 4, 12, tzinfo=TZ))  # yakshanba dam


# ---------- chegirma ----------

async def test_product_discount(client):
    p = await db.get_product(1)
    assert variant_price(p, 1) == (20000, None)
    await db.update_product(1, discount_percent=20)
    p = await db.get_product(1)
    assert variant_price(p, 1) == (16000, 20000)
    menu = (await (await client.get("/api/menu", headers=H(300))).json())["categories"]
    v = menu[0]["products"][0]["variants"][1]
    assert v == {"name": "Katta", "price": 16000, "old_price": 20000}
    # muddati o'tgan chegirma ishlamaydi
    await db.update_product(1, discount_until=(now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"))
    assert variant_price(await db.get_product(1), 1) == (20000, None)
    assert apply_percent(15000, 15) == 12800  # 12750 -> 100 ga yaxlitlash


# ---------- olib ketish ----------

async def test_pickup_order(client):
    await db.set_setting("delivery_fee", "10000")
    await db.set_setting("min_order", "100000")   # olib ketishga taalluqli emas
    st, data = await post(client, "/api/orders", PICK)
    assert st == 200, data
    o = data["order"]
    assert o["order_type"] == "pickup" and o["address"] == "" and o["total"] == 40000
    await db.set_setting("pickup_enabled", "0")
    st, data = await post(client, "/api/orders", PICK, uid=301)
    assert st == 400 and "mavjud emas" in data["error"]


# ---------- vaqtga buyurtma ----------

async def test_scheduled_order(client):
    await db.set_setting("mode", "auto")
    raw = await db.get_settings()
    slots = hours.slots(raw)
    if hours.is_open_at(raw):
        pass
    else:
        st, data = await post(client, "/api/orders", ORDER)
        assert st == 400 and "vaqtni tanlab" in data["error"]
    value = slots[-1]["times"][-1]["value"]
    st, data = await post(client, "/api/orders", {**ORDER, "scheduled_at": value}, uid=302)
    assert st == 200, data
    assert data["order"]["scheduled_at"] == value
    st, data = await post(client, "/api/orders", {**ORDER, "scheduled_at": "2020-01-01 10:00"}, uid=303)
    assert st == 400 and "vaqt" in data["error"].lower()
    menu = await (await client.get("/api/menu", headers=H(300))).json()
    assert menu["slots"] and "is_open" in menu["settings"]


# ---------- promo-kod ----------

async def test_promo_rules(client):
    await db.add_promo(code="SALE20", kind="percent", value=20, max_discount=5000, per_user_limit=1)
    st, data = await post(client, "/api/quote", {"items": ORDER["items"], "promo_code": "sale20"})
    assert st == 200 and data["quote"]["discount"] == 5000 and data["quote"]["total"] == 35000
    st, data = await post(client, "/api/orders", {**ORDER, "promo_code": "SALE20"})
    assert data["order"]["discount"] == 5000 and data["order"]["total"] == 35000
    # bir kishiga 1 marta
    st, data = await post(client, "/api/quote", {"items": ORDER["items"], "promo_code": "SALE20"})
    assert st == 400 and "allaqachon" in data["error"]
    # boshqa mijoz uchun ishlaydi
    st, _ = await post(client, "/api/quote", {"items": ORDER["items"], "promo_code": "SALE20"}, uid=310)
    assert st == 200

    await db.add_promo(code="FIRST", kind="fixed", value=7000, first_order_only=1, min_order=30000)
    st, data = await post(client, "/api/quote", {"items": ORDER["items"], "promo_code": "FIRST"})
    assert "birinchi" in data["error"]
    st, data = await post(client, "/api/quote", {"items": [{"product_id": 9, "qty": 1}], "promo_code": "FIRST"}, uid=311)
    assert "30 000" in data["error"]
    st, data = await post(client, "/api/quote", {"items": ORDER["items"], "promo_code": "FIRST"}, uid=311)
    assert data["quote"]["discount"] == 7000

    await db.set_setting("delivery_fee", "12000")
    await db.add_promo(code="FREE", kind="free_delivery", value=0, per_user_limit=0)
    st, data = await post(client, "/api/quote", {"items": ORDER["items"], "promo_code": "FREE"}, uid=312)
    assert data["quote"]["delivery_fee"] == 0
    st, data = await post(client, "/api/quote",
                          {"items": ORDER["items"], "promo_code": "FREE", "order_type": "pickup"}, uid=312)
    assert "yetkazib berish uchun" in data["error"]

    past = (now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    await db.add_promo(code="OLD", kind="percent", value=10, ends_at=past)
    st, data = await post(client, "/api/quote", {"items": ORDER["items"], "promo_code": "OLD"}, uid=313)
    assert "muddati" in data["error"]
    pid = await db.add_promo(code="LIM", kind="percent", value=10, usage_limit=1, per_user_limit=0)
    await post(client, "/api/orders", {**ORDER, "promo_code": "LIM"}, uid=314)
    st, data = await post(client, "/api/quote", {"items": ORDER["items"], "promo_code": "LIM"}, uid=315)
    assert "limit" in data["error"]
    assert (await db.get_promo(pid))["used"] == 1
    st, data = await post(client, "/api/quote", {"items": ORDER["items"], "promo_code": "NOPE"})
    assert "topilmadi" in data["error"]


# ---------- baho ----------

async def test_review_api(client):
    st, data = await post(client, "/api/orders", ORDER, uid=320)
    code = data["order"]["code"]
    st, data = await post(client, f"/api/orders/{code}/review", {"rating": 5}, uid=320)
    assert st == 400  # hali yetkazilmagan
    oid = (await db.get_order_by_code(code))["id"]
    await db.set_order_status(oid, "delivered", 1)
    st, data = await post(client, f"/api/orders/{code}/review", {"rating": 4, "comment": "Mazali!"}, uid=320)
    assert st == 200 and data["order"]["review"] == {"rating": 4, "comment": "Mazali!"}
    st, data = await post(client, f"/api/orders/{code}/review", {"rating": 1}, uid=320)
    assert st == 400
    st, _ = await post(client, f"/api/orders/{code}/review", {"rating": 5}, uid=321)
    assert st == 404
    assert (await db.review_stats())["avg"] == 4


# ---------- rus tili ----------

async def test_russian_api(client):
    st, data = await post(client, "/api/me/lang", {"lang": "ru"})
    assert data["lang"] == "ru"
    menu = await (await client.get("/api/menu", headers=H(300))).json()
    assert menu["categories"][0]["name"] == "Хотдоги"
    p = menu["categories"][0]["products"][0]
    assert p["name"] == "Классический хотдог" and p["variants"][0]["name"] == "Средний"
    st, data = await post(client, "/api/orders", {**ORDER, "phone": "1"})
    assert "Неверный телефон" in data["error"]
    st, data = await post(client, "/api/orders", ORDER)
    assert data["order"]["items"][0]["name"] == "Классический хотдог"
    assert data["order"]["status_label"].endswith("Ожидает подтверждения")


def test_slots_today_only():
    from datetime import datetime

    from app import hours
    from app.utils import TZ

    settings = {"mode": "auto", "schedule": '{"mon":["10:00","23:00"],"tue":["10:00","23:00"],"wed":["10:00","23:00"],'
                '"thu":["10:00","23:00"],"fri":["10:00","23:00"],"sat":["10:00","23:00"],"sun":["10:00","23:00"]}',
                "prep_time": "40", "slot_step": "30"}
    days = hours.slots(settings, datetime(2026, 10, 2, 12, 0, tzinfo=TZ))
    assert [d["day"] for d in days] == ["today"]
    # kech kirilganda ertangi kun taklif qilinmaydi
    assert hours.slots(settings, datetime(2026, 10, 2, 22, 50, tzinfo=TZ)) == []
    assert not hours.valid_slot(settings, "2026-10-03 12:00", datetime(2026, 10, 2, 12, 0, tzinfo=TZ))
