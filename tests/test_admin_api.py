import io

import pytest
from aiohttp import FormData

from app import db
from app.admin_api import make_login_link
from app.config import config
from app.i18n import t
from app.webapp import create_app
from tests.test_api import make_init_data


@pytest.fixture
async def client(aiohttp_client, tmp_path):
    await db.init_db(str(tmp_path / "test.db"))
    await db.set_setting("mode", "open")
    old_dir = config.uploads_dir
    config.uploads_dir = tmp_path / "uploads"
    c = await aiohttp_client(create_app(None))
    yield c
    config.uploads_dir = old_dir
    await db.set_text("greet", "uz", None)
    await db.close_db()


async def login(client, uid=1) -> dict:
    await db.upsert_user(uid, "Boss", None, None)
    link = await make_login_link(uid)
    code = link.split("#code=")[1]
    r = await client.post("/api/admin/login", json={"code": code})
    assert r.status == 200, await r.text()
    token = (await r.json())["token"]
    # kod bir martalik
    r = await client.post("/api/admin/login", json={"code": code})
    assert r.status == 401
    return {"X-Admin-Token": token}


async def test_admin_access_control(client):
    assert (await client.get("/api/admin/menu")).status == 401
    # oddiy foydalanuvchi initData bilan kira olmaydi
    r = await client.get("/api/admin/menu", headers={"X-Telegram-Init-Data": make_init_data(555)})
    assert r.status == 401
    # menejer initData bilan kiradi
    r = await client.get("/api/admin/menu", headers={"X-Telegram-Init-Data": make_init_data(1)})
    assert r.status == 200
    assert (await client.get("/api/admin/me", headers={"X-Admin-Token": "nope"})).status == 401
    hdr = await login(client)
    r = await client.get("/api/admin/me", headers=hdr)
    assert (await r.json())["user"]["id"] == 1
    await client.post("/api/admin/logout", headers=hdr)
    assert (await client.get("/api/admin/me", headers=hdr)).status == 401


async def test_menu_crud(client):
    hdr = await login(client)
    r = await client.post("/api/admin/categories", headers=hdr, json={"name": "Salatlar", "emoji": "🥗",
                                                                      "name_ru": "Салаты"})
    cat = (await r.json())["category"]
    assert cat["name_ru"] == "Салаты"
    r = await client.post("/api/admin/products", headers=hdr, json={
        "category_id": cat["id"], "name": "Sezar", "name_ru": "Цезарь", "description": "Yangi",
        "variants": [{"name": "", "price": 40000}], "badges": ["new", "bad"], "discount_percent": 10,
    })
    assert r.status == 200, await r.text()
    p = (await r.json())["product"]
    assert p["badges"] == ["new"] and p["prices_now"] == [36000]
    r = await client.patch(f"/api/admin/products/{p['id']}", headers=hdr, json={"variants": []})
    assert r.status == 400
    r = await client.patch(f"/api/admin/products/{p['id']}", headers=hdr, json={"is_available": False})
    assert (await r.json())["product"]["is_available"] is False
    # kategoriyada mahsulot bor — o'chirilmaydi
    assert (await client.delete(f"/api/admin/categories/{cat['id']}", headers=hdr)).status == 400
    await client.delete(f"/api/admin/products/{p['id']}", headers=hdr)
    assert (await client.delete(f"/api/admin/categories/{cat['id']}", headers=hdr)).status == 200
    # mijoz menyusida darhol aks etadi
    r = await client.get("/api/admin/menu", headers=hdr)
    assert all(c["name"] != "Salatlar" for c in (await r.json())["categories"])


async def test_upload_processes_image(client):
    from PIL import Image

    hdr = await login(client)
    buf = io.BytesIO()
    Image.new("RGBA", (1000, 1000), (255, 0, 0, 128)).save(buf, "PNG")
    form = FormData()
    form.add_field("file", buf.getvalue(), filename="a.png", content_type="image/png")
    r = await client.post("/api/admin/upload", headers=hdr, data=form)
    data = await r.json()
    assert data["ok"] and data["path"].startswith("uploads/")
    assert abs(data["width"] / data["height"] - 4 / 3) < 0.01
    assert data["warnings"]
    assert (await client.get("/" + data["path"])).status == 200
    form = FormData()
    form.add_field("file", b"not an image", filename="x.png")
    assert (await client.post("/api/admin/upload", headers=hdr, data=form)).status == 400


async def test_texts_edit_applies_to_bot(client):
    hdr = await login(client)
    r = await client.get("/api/admin/texts", headers=hdr)
    items = (await r.json())["texts"]
    assert any(i["key"] == "greet" for i in items)
    r = await client.put("/api/admin/texts", headers=hdr, json={"key": "greet", "lang": "uz", "value": "<b>Salom"})
    assert r.status == 400
    r = await client.put("/api/admin/texts", headers=hdr, json={"key": "greet", "lang": "uz", "value": "Hi {nope}"})
    assert r.status == 400
    r = await client.put("/api/admin/texts", headers=hdr,
                         json={"key": "greet", "lang": "uz", "value": "<b>Xush kelibsiz!</b> 🍔"})
    assert r.status == 200
    assert t("greet", "uz", name="X") == "<b>Xush kelibsiz!</b> 🍔"
    await client.put("/api/admin/texts", headers=hdr, json={"key": "greet", "lang": "uz", "value": ""})
    assert "Xush kelibsiz!</b> 🍔" != t("greet", "uz", name="X")


async def test_settings_and_promos(client):
    hdr = await login(client)
    r = await client.put("/api/admin/settings", headers=hdr, json={
        "delivery_fee": 12000, "schedule": {"mon": ["09:00", "02:00"], "sun": None}, "mode": "auto"})
    s = (await r.json())["settings"]
    assert s["delivery_fee"] == 12000 and s["schedule"]["mon"] == ["09:00", "02:00"] and s["schedule"]["sun"] is None
    r = await client.put("/api/admin/settings", headers=hdr, json={"delivery_enabled": False, "pickup_enabled": False})
    assert r.status == 400
    r = await client.post("/api/admin/promos", headers=hdr, json={"code": "yoz20", "kind": "percent", "value": 20})
    promo = (await r.json())["promo"]
    assert promo["code"] == "YOZ20"
    assert (await client.post("/api/admin/promos", headers=hdr,
                              json={"code": "YOZ20", "kind": "fixed", "value": 5})).status == 400
    r = await client.patch(f"/api/admin/promos/{promo['id']}", headers=hdr, json={"is_active": False})
    assert (await r.json())["promo"]["is_active"] == 0


async def test_order_status_flow(client):
    hdr = await login(client)
    from tests.test_api import ORDER

    r = await client.post("/api/orders", headers={"X-Telegram-Init-Data": make_init_data(300)}, json=ORDER)
    assert r.status == 200, await r.text()
    r = await client.get("/api/admin/orders", headers=hdr)
    order = (await r.json())["orders"][0]
    assert order["next"][0] == "accepted"
    r = await client.post(f"/api/admin/orders/{order['id']}/status", headers=hdr, json={"status": "delivered"})
    assert r.status == 409
    r = await client.post(f"/api/admin/orders/{order['id']}/status", headers=hdr, json={"status": "accepted"})
    assert (await r.json())["order"]["status"] == "accepted"
    r = await client.get(f"/api/admin/orders/{order['id']}", headers=hdr)
    assert len((await r.json())["log"]) == 2
    r = await client.get("/api/admin/dashboard?period=today", headers=hdr)
    assert (await r.json())["active_orders"] == 1
    r = await client.get("/api/admin/export.csv", headers=hdr)
    assert order["code"] in (await r.text())


async def test_cors(client):
    config.cors_origins = {"https://nexiaacademy.uz"}
    try:
        r = await client.options("/api/admin/menu", headers={"Origin": "https://nexiaacademy.uz"})
        assert r.status == 204 and r.headers["Access-Control-Allow-Origin"] == "https://nexiaacademy.uz"
        r = await client.get("/api/admin/menu", headers={"Origin": "https://evil.com"})
        assert "Access-Control-Allow-Origin" not in r.headers
    finally:
        config.cors_origins = set()
