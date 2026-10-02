import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from app import db
from app.config import config
from app.handlers.admin import parse_prices
from app.webapp import create_app, normalize_phone


def make_init_data(user_id: int, token: str = None, auth_date: int = None) -> str:
    token = token or config.bot_token
    fields = {
        "auth_date": str(auth_date or int(time.time())),
        "query_id": "AAE",
        "user": json.dumps({"id": user_id, "first_name": "Ali", "username": "ali"}),
    }
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


@pytest.fixture
async def client(aiohttp_client, tmp_path):
    await db.init_db(str(tmp_path / "test.db"))
    c = await aiohttp_client(create_app(None))
    yield c
    await db.close_db()


def H(uid=100):
    return {"X-Telegram-Init-Data": make_init_data(uid)}


ORDER = {
    "name": "Ali Valiyev", "phone": "+998 90 123 45 67", "address": "Toshkent, Chilonzor 5-uy",
    "payment_method": "cash", "items": [{"product_id": 1, "variant": 1, "qty": 2}],
}


async def test_auth_required(client):
    r = await client.get("/api/menu")
    assert r.status == 401
    r = await client.get("/api/menu", headers={"X-Telegram-Init-Data": make_init_data(5, token="1:fake")})
    assert r.status == 401
    old = int(time.time()) - 2 * 86400
    r = await client.get("/api/menu", headers={"X-Telegram-Init-Data": make_init_data(5, auth_date=old)})
    assert r.status == 401


async def test_menu_and_auto_account(client):
    r = await client.get("/api/menu", headers=H(100))
    data = await r.json()
    assert r.status == 200 and data["ok"]
    assert len(data["categories"]) == 5
    assert data["categories"][0]["products"][0]["variants"][1]["price"] == 20000
    assert (await db.get_user(100))["first_name"] == "Ali"   # akkaunt avtomatik ochildi


async def test_create_order_flow(client):
    r = await client.post("/api/orders", json=ORDER, headers=H(100))
    data = await r.json()
    assert r.status == 200, data
    o = data["order"]
    assert o["total"] == 40000 and o["status"] == "new"
    assert o["code"].startswith("YG-") and len(o["code"]) == 19
    assert o["phone"] == "+998901234567"
    # profil saqlandi
    me = await (await client.get("/api/me", headers=H(100))).json()
    assert me["user"]["address"] == ORDER["address"]
    # boshqa foydalanuvchi ko'ra olmaydi
    r = await client.get(f"/api/orders/{o['code']}", headers=H(200))
    assert r.status == 404
    # holat o'zgarishi
    await db.set_order_status(o["id"], "accepted", 1)
    r = await client.get(f"/api/orders/{o['code']}", headers=H(100))
    got = (await r.json())["order"]
    assert got["status"] == "accepted" and "accepted" in got["timeline"]
    # qabul qilingandan keyin mijoz bekor qila olmaydi
    r = await client.post(f"/api/orders/{o['code']}/cancel", headers=H(100))
    assert r.status == 400


async def test_customer_cancel_new(client):
    o = (await (await client.post("/api/orders", json=ORDER, headers=H(101))).json())["order"]
    r = await client.post(f"/api/orders/{o['code']}/cancel", headers=H(101))
    assert (await r.json())["order"]["status"] == "cancelled"


async def test_order_validation(client):
    bad = [
        ({**ORDER, "payment_method": "card"}, "tez kunda"),
        ({**ORDER, "phone": "12345"}, "Telefon"),
        ({**ORDER, "name": ""}, "ism"),
        ({**ORDER, "items": []}, "bo'sh"),
        ({**ORDER, "items": [{"product_id": 999, "qty": 1}]}, "mavjud emas"),
        ({**ORDER, "items": [{"product_id": 3, "variant": 1, "qty": 1}]}, "o'lcham"),
        ({**ORDER, "items": [{"product_id": 1, "qty": 0}]}, "1 dan 50"),
    ]
    for body, msg in bad:
        r = await client.post("/api/orders", json=body, headers=H(102))
        data = await r.json()
        assert r.status >= 400 and msg.lower() in data["error"].lower(), (body, data)


async def test_closed_min_order_and_cooldown(client):
    await db.set_setting("is_open", "0")
    r = await client.post("/api/orders", json=ORDER, headers=H(103))
    assert "qabul qilinmayapti" in (await r.json())["error"]
    await db.set_setting("is_open", "1")
    await db.set_setting("min_order", "100000")
    r = await client.post("/api/orders", json=ORDER, headers=H(103))
    assert "Minimal" in (await r.json())["error"]
    await db.set_setting("min_order", "0")
    await db.set_setting("delivery_fee", "10000")
    r = await client.post("/api/orders", json=ORDER, headers=H(103))
    assert (await r.json())["order"]["total"] == 50000
    r = await client.post("/api/orders", json=ORDER, headers=H(103))
    assert r.status == 429


async def test_unavailable_product_hidden(client):
    await db.update_product(1, is_available=0)
    data = await (await client.get("/api/menu", headers=H(104))).json()
    ids = [p["id"] for c in data["categories"] for p in c["products"]]
    assert 1 not in ids
    r = await client.post("/api/orders", json=ORDER, headers=H(104))
    assert r.status == 409


async def test_stats(client):
    o = (await (await client.post("/api/orders", json=ORDER, headers=H(105))).json())["order"]
    for st in ("accepted", "cooking", "delivering", "delivered"):
        await db.set_order_status(o["id"], st, 1)
    s = await db.stats(None)
    assert s["revenue"] == 40000 and s["by_status"]["delivered"] == 1
    assert s["top"][0]["name"] == "Klassik hot-dog"
    assert (await db.find_order(o["code"][-4:]))["id"] == o["id"]
    assert len(await db.all_orders_for_export(None)) == 1


async def test_static(client):
    r = await client.get("/")
    assert r.status == 200 and "Yaproq" in await r.text()
    r = await client.get("/img/products/burger.jpg")
    assert r.status == 200


def test_parse_prices():
    assert parse_prices("25000") == [{"name": "", "price": 25000}]
    assert parse_prices("25 000 so'm") == [{"name": "", "price": 25000}]
    assert parse_prices("O'rta 15000\nKatta - 20 000") == [
        {"name": "O'rta", "price": 15000}, {"name": "Katta", "price": 20000}]
    assert parse_prices("60 g: 6000") == [{"name": "60 g", "price": 6000}]
    assert parse_prices("abc") is None
    assert parse_prices("15000\nKatta 20000") is None


def test_normalize_phone():
    assert normalize_phone("90 123 45 67") == "+998901234567"
    assert normalize_phone("+998 (90) 123-45-67") == "+998901234567"
    assert normalize_phone("123") is None
