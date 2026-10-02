import json
import secrets
from pathlib import Path

import aiosqlite

from .utils import ACTIVE_STATUSES, now_str

_db: aiosqlite.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    first_name TEXT,
    last_name TEXT,
    username TEXT,
    full_name TEXT,
    phone TEXT,
    address TEXT,
    role TEXT NOT NULL DEFAULT 'user',          -- user | staff | manager
    is_blocked INTEGER NOT NULL DEFAULT 0,      -- botni bloklagan
    created_at TEXT NOT NULL,
    last_active TEXT
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    emoji TEXT DEFAULT '',
    sort INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL REFERENCES categories(id),
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    image TEXT DEFAULT '',
    variants TEXT NOT NULL,                     -- JSON: [{"name": "O'rta", "price": 15000}]
    is_available INTEGER NOT NULL DEFAULT 1,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    sort INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,                  -- unikal ID: YG-482917
    user_id INTEGER NOT NULL REFERENCES users(id),
    customer_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    address TEXT NOT NULL,
    comment TEXT DEFAULT '',
    payment_method TEXT NOT NULL,
    subtotal INTEGER NOT NULL,
    delivery_fee INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    staff_id INTEGER,
    cancel_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER,
    name TEXT NOT NULL,
    variant TEXT DEFAULT '',
    price INTEGER NOT NULL,
    qty INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS order_status_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    by_user INTEGER,
    at TEXT NOT NULL
);

-- xodimlarga yuborilgan xabarlar (holat o'zgarsa hammasida yangilash uchun)
CREATE TABLE IF NOT EXISTS order_messages (
    order_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL
);

-- bot ichidagi savat (Mini App savati brauzerda saqlanadi)
CREATE TABLE IF NOT EXISTS cart_items (
    user_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    variant INTEGER NOT NULL DEFAULT 0,
    qty INTEGER NOT NULL,
    PRIMARY KEY (user_id, product_id, variant)
);

CREATE TABLE IF NOT EXISTS promo_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,                         -- percent | fixed | free_delivery
    value INTEGER NOT NULL DEFAULT 0,
    min_order INTEGER NOT NULL DEFAULT 0,
    max_discount INTEGER NOT NULL DEFAULT 0,    -- 0 = cheklovsiz (foiz uchun)
    usage_limit INTEGER NOT NULL DEFAULT 0,     -- 0 = cheklovsiz
    per_user_limit INTEGER NOT NULL DEFAULT 1,  -- 0 = cheklovsiz
    first_order_only INTEGER NOT NULL DEFAULT 0,
    starts_at TEXT NOT NULL DEFAULT '',
    ends_at TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL UNIQUE,
    user_id INTEGER NOT NULL,
    rating INTEGER NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

-- admin web panel sessiyalari (token xeshi saqlanadi)
CREATE TABLE IF NOT EXISTS admin_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    kind TEXT NOT NULL,                         -- login (bir martalik kod) | session
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- admin paneldan tahrirlangan bot/Mini App matnlari
CREATE TABLE IF NOT EXISTS texts (
    key TEXT NOT NULL,
    lang TEXT NOT NULL,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (key, lang)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_code ON orders(code);
CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at);
"""

# Mavjud bazaga yangi ustunlarni qo'shish (eski o'rnatishlar ham buzilmasdan yangilanadi)
MIGRATIONS = [
    ("users", "lang", "TEXT NOT NULL DEFAULT ''"),
    ("categories", "name_ru", "TEXT NOT NULL DEFAULT ''"),
    ("products", "name_ru", "TEXT NOT NULL DEFAULT ''"),
    ("products", "description_ru", "TEXT NOT NULL DEFAULT ''"),
    ("products", "badges", "TEXT NOT NULL DEFAULT ''"),            # hit,new,top,spicy
    ("products", "discount_percent", "INTEGER NOT NULL DEFAULT 0"),
    ("products", "discount_until", "TEXT NOT NULL DEFAULT ''"),
    ("orders", "order_type", "TEXT NOT NULL DEFAULT 'delivery'"),  # delivery | pickup
    ("orders", "scheduled_at", "TEXT NOT NULL DEFAULT ''"),        # '' = imkon qadar tez
    ("orders", "promo_code", "TEXT NOT NULL DEFAULT ''"),
    ("orders", "discount", "INTEGER NOT NULL DEFAULT 0"),
    ("orders", "lang", "TEXT NOT NULL DEFAULT 'uz'"),
    ("orders", "reminded", "INTEGER NOT NULL DEFAULT 0"),
]

DEFAULT_SETTINGS = {
    "mode": "auto",                 # auto (jadval bo'yicha) | open | closed
    "schedule": json.dumps({d: ["10:00", "23:00"] for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}),
    "delivery_fee": "0",
    "min_order": "0",
    "phone": "",
    "delivery_enabled": "1",
    "pickup_enabled": "1",
    "cafe_address": "",
    "prep_time": "40",              # vaqtga buyurtma uchun minimal tayyorlash vaqti (daqiqa)
    "slot_step": "30",              # vaqt tanlash qadami (daqiqa)
}

SEED_RU_CATEGORIES = {
    "Hot-doglar": "Хотдоги", "Frensh hot-dog": "Френч хотдог", "Burgerlar": "Бургеры",
    "Donar va lavash": "Донар и лаваш", "Kartoshka fri": "Картошка фри",
}
SEED_RU_PRODUCTS = {
    "hotdog-classic": ("Классический хотдог", "Сосиска, мягкая булочка, кетчуп и горчица"),
    "hotdog-cheese": ("Сырный хотдог", "Сосиска, сырный соус, кетчуп"),
    "hotdog-royal": ("Классик Рояль", "Сосиска, жареный лук, фирменный соус"),
    "hotdog-mexican": ("Мексиканский хотдог", "Сосиска, халапеньо, острый соус"),
    "french-jalapeno": ("Френч Халапеньо", "Хрустящая булочка, сосиска, халапеньо"),
    "french-classic": ("Френч Классический", "Хрустящая булочка, сосиска, кетчуп"),
    "french-tartar": ("Френч Тар-тар", "Хрустящая булочка, сосиска, соус тар-тар"),
    "french-cheese": ("Френч Сырный", "Хрустящая булочка, сосиска, сырный соус"),
    "burger": ("Бургер", "Говяжья котлета, помидор, лист салата, соус"),
    "burger-cheese": ("Чизбургер", "Говяжья котлета, сыр чеддер, помидор, салат"),
    "burger-double": ("Дабл бургер", "Две котлеты, помидор, салат, соус"),
    "burger-double-cheese": ("Дабл чизбургер", "Две котлеты, двойной чеддер, лук, помидор"),
    "donar": ("Донар", "Традиционный донар — мясо, овощи, соус"),
    "lavash": ("Лаваш", "Мясо, овощи, фирменный соус, лаваш"),
    "fries": ("Картошка фри", "Хрустящий золотистый картофель"),
}

M, L = "O'rta", "Katta"
SEED_MENU = [
    ("Hot-doglar", "🌭", [
        ("Klassik hot-dog", "Sosiska, yumshoq bulochka, ketchup va xantal", "hotdog-classic", [(M, 15000), (L, 20000)]),
        ("Pishloqli hot-dog", "Sosiska, eritilgan pishloq sousi, ketchup", "hotdog-cheese", [(M, 15000), (L, 20000)]),
        ("Klassik Royal", "Sosiska, qovurilgan piyoz, maxsus sous", "hotdog-royal", [(M, 15000)]),
        ("Meksikancha hot-dog", "Sosiska, xalapenyo, achchiq sous", "hotdog-mexican", [(M, 15000), (L, 20000)]),
    ]),
    ("Frensh hot-dog", "🥖", [
        ("Frensh Xalapenyo", "Qarsildoq bulochka, sosiska, xalapenyo", "french-jalapeno", [("", 12000)]),
        ("Frensh Klassik", "Qarsildoq bulochka, sosiska, ketchup", "french-classic", [("", 12000)]),
        ("Frensh Tar-tar", "Qarsildoq bulochka, sosiska, tar-tar sousi", "french-tartar", [("", 12000)]),
        ("Frensh Pishloqli", "Qarsildoq bulochka, sosiska, pishloq sousi", "french-cheese", [("", 12000)]),
    ]),
    ("Burgerlar", "🍔", [
        ("Burger", "Mol go'shti kotleti, pomidor, salat bargi, sous", "burger", [("", 25000)]),
        ("Chizburger", "Mol go'shti kotleti, cheddar pishlog'i, pomidor, salat", "burger-cheese", [("", 26000)]),
        ("Dabl burger", "Ikkita go'sht kotleti, pomidor, salat, sous", "burger-double", [("", 35000)]),
        ("Dabl chizburger", "Ikkita kotlet, ikki qavat cheddar, piyoz, pomidor", "burger-double-cheese", [("", 37000)]),
    ]),
    ("Donar va lavash", "🌯", [
        ("Donar", "An'anaviy donar — go'sht, sabzavotlar, sous", "donar", [(M, 22000), (L, 26000)]),
        ("Lavash", "Go'sht, sabzavotlar, maxsus sous, lavash", "lavash", [(M, 30000), (L, 35000)]),
    ]),
    ("Kartoshka fri", "🍟", [
        ("Kartoshka fri", "Qarsildoq oltin rang kartoshka", "fries", [("60 g", 6000), ("80 g", 8000)]),
    ]),
]


def db() -> aiosqlite.Connection:
    assert _db is not None, "DB is not initialised"
    return _db


async def init_db(path: str) -> None:
    global _db
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    _db = await aiosqlite.connect(path)
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.execute("PRAGMA foreign_keys=ON")
    await _db.executescript(SCHEMA)
    await _migrate()
    for k, v in DEFAULT_SETTINGS.items():
        await _db.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))
    await _db.commit()
    await _seed_menu()
    await _seed_ru()
    await reload_texts()


async def _migrate() -> None:
    for table, column, ddl in MIGRATIONS:
        cur = await db().execute(f"PRAGMA table_info({table})")
        cols = {r[1] for r in await cur.fetchall()}
        if column not in cols:
            await db().execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    # eski "is_open" sozlamasi -> yangi "mode"
    cur = await db().execute("SELECT value FROM settings WHERE key = 'is_open'")
    old = await cur.fetchone()
    cur = await db().execute("SELECT 1 FROM settings WHERE key = 'mode'")
    if old and not await cur.fetchone():
        await db().execute("INSERT INTO settings(key, value) VALUES ('mode', ?)",
                           ("closed" if old[0] == "0" else "auto",))
    await db().commit()


async def _seed_ru() -> None:
    """Boshlang'ich menyuga ruscha nomlar (faqat bo'sh bo'lsa)."""
    for uz, ru in SEED_RU_CATEGORIES.items():
        await db().execute("UPDATE categories SET name_ru = ? WHERE name = ? AND name_ru = ''", (ru, uz))
    for img, (name, desc) in SEED_RU_PRODUCTS.items():
        await db().execute(
            "UPDATE products SET name_ru = ?, description_ru = ? WHERE image = ? AND name_ru = ''",
            (name, desc, f"img/products/{img}.jpg"),
        )
    await db().commit()


async def close_db() -> None:
    global _db
    if _db:
        await _db.close()
        _db = None


async def _seed_menu() -> None:
    cur = await db().execute("SELECT COUNT(*) FROM categories")
    if (await cur.fetchone())[0]:
        return
    for ci, (cname, emoji, products) in enumerate(SEED_MENU):
        cur = await db().execute(
            "INSERT INTO categories(name, emoji, sort) VALUES (?, ?, ?)", (cname, emoji, ci)
        )
        cat_id = cur.lastrowid
        for pi, (name, desc, img, variants) in enumerate(products):
            await db().execute(
                "INSERT INTO products(category_id, name, description, image, variants, sort, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    cat_id, name, desc, f"img/products/{img}.jpg",
                    json.dumps([{"name": n, "price": p} for n, p in variants], ensure_ascii=False),
                    pi, now_str(),
                ),
            )
    await db().commit()


def _row(r) -> dict | None:
    return dict(r) if r else None


async def fetchone(sql: str, *args) -> dict | None:
    cur = await db().execute(sql, args)
    return _row(await cur.fetchone())


async def fetchall(sql: str, *args) -> list[dict]:
    cur = await db().execute(sql, args)
    return [dict(r) for r in await cur.fetchall()]


async def scalar(sql: str, *args):
    cur = await db().execute(sql, args)
    row = await cur.fetchone()
    return row[0] if row else None


async def execute(sql: str, *args) -> int:
    cur = await db().execute(sql, args)
    await db().commit()
    return cur.lastrowid


# ---------------- settings ----------------

async def get_settings() -> dict:
    rows = await fetchall("SELECT key, value FROM settings")
    return {r["key"]: r["value"] for r in rows}


async def get_setting(key: str) -> str:
    return await scalar("SELECT value FROM settings WHERE key = ?", key) or ""


async def set_setting(key: str, value) -> None:
    await execute(
        "INSERT INTO settings(key, value) VALUES (?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        key, str(value),
    )


# ---------------- matnlar ----------------

async def reload_texts() -> None:
    from .i18n import set_overrides

    set_overrides(await fetchall("SELECT key, lang, value FROM texts"))


async def set_text(key: str, lang: str, value: str | None) -> None:
    """value=None yoki bo'sh — asl matnga qaytarish."""
    if value:
        await execute(
            "INSERT INTO texts(key, lang, value, updated_at) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(key, lang) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            key, lang, value, now_str(),
        )
    else:
        await execute("DELETE FROM texts WHERE key = ? AND lang = ?", key, lang)
    await reload_texts()


# ---------------- admin sessiyalari ----------------

def _hash(token: str) -> str:
    import hashlib

    return hashlib.sha256(token.encode()).hexdigest()


async def create_admin_token(user_id: int, kind: str, ttl_minutes: int) -> str:
    from datetime import timedelta

    from .utils import now

    token = secrets.token_urlsafe(32)
    expires = (now() + timedelta(minutes=ttl_minutes)).strftime("%Y-%m-%d %H:%M:%S")
    await execute("DELETE FROM admin_sessions WHERE expires_at < ?", now_str())
    await execute(
        "INSERT INTO admin_sessions(token_hash, user_id, kind, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
        _hash(token), user_id, kind, expires, now_str(),
    )
    return token


async def check_admin_token(token: str, kind: str, consume: bool = False) -> int | None:
    row = await fetchone(
        "SELECT user_id FROM admin_sessions WHERE token_hash = ? AND kind = ? AND expires_at > ?",
        _hash(token), kind, now_str(),
    )
    if row and consume:
        await execute("DELETE FROM admin_sessions WHERE token_hash = ?", _hash(token))
    return row["user_id"] if row else None


async def delete_admin_token(token: str) -> None:
    await execute("DELETE FROM admin_sessions WHERE token_hash = ?", _hash(token))


# ---------------- users ----------------

async def upsert_user(user_id: int, first_name: str, last_name: str | None, username: str | None) -> tuple[dict, bool]:
    """Foydalanuvchini yaratadi yoki yangilaydi. (user, is_new) qaytaradi."""
    existing = await get_user(user_id)
    if existing:
        await execute(
            "UPDATE users SET first_name=?, last_name=?, username=?, last_active=?, is_blocked=0 WHERE id=?",
            first_name, last_name, username, now_str(), user_id,
        )
    else:
        await execute(
            "INSERT INTO users(id, first_name, last_name, username, created_at, last_active)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            user_id, first_name, last_name, username, now_str(), now_str(),
        )
    return await get_user(user_id), existing is None


async def get_user(user_id: int) -> dict | None:
    return await fetchone("SELECT * FROM users WHERE id = ?", user_id)


async def find_user(query: str) -> dict | None:
    query = query.strip().lstrip("@")
    if query.lstrip("-").isdigit():
        return await get_user(int(query))
    return await fetchone("SELECT * FROM users WHERE lower(username) = lower(?)", query)


async def update_user_profile(user_id: int, full_name: str, phone: str, address: str) -> None:
    await execute(
        "UPDATE users SET full_name=?, phone=?, address=? WHERE id=?",
        full_name, phone, address, user_id,
    )


async def set_lang(user_id: int, lang: str) -> None:
    await execute("UPDATE users SET lang=? WHERE id=?", lang, user_id)


async def set_role(user_id: int, role: str) -> None:
    await execute("UPDATE users SET role=? WHERE id=?", role, user_id)


async def get_staff() -> list[dict]:
    return await fetchall("SELECT * FROM users WHERE role IN ('staff', 'manager') ORDER BY role, id")


async def set_blocked(user_id: int, blocked: bool) -> None:
    await execute("UPDATE users SET is_blocked=? WHERE id=?", int(blocked), user_id)


async def all_user_ids() -> list[int]:
    rows = await fetchall("SELECT id FROM users WHERE is_blocked = 0")
    return [r["id"] for r in rows]


# ---------------- menu ----------------

def _product(r: dict) -> dict:
    r["variants"] = json.loads(r["variants"])
    return r


async def get_categories(only_active: bool = False) -> list[dict]:
    sql = "SELECT * FROM categories"
    if only_active:
        sql += " WHERE is_active = 1"
    return await fetchall(sql + " ORDER BY sort, id")


async def get_category(cat_id: int) -> dict | None:
    return await fetchone("SELECT * FROM categories WHERE id = ?", cat_id)


async def add_category(name: str, emoji: str = "") -> int:
    sort = await scalar("SELECT COALESCE(MAX(sort), 0) + 1 FROM categories")
    return await execute("INSERT INTO categories(name, emoji, sort) VALUES (?, ?, ?)", name, emoji, sort)


async def get_products(category_id: int | None = None, only_available: bool = False) -> list[dict]:
    sql = "SELECT * FROM products WHERE is_deleted = 0"
    args: list = []
    if category_id is not None:
        sql += " AND category_id = ?"
        args.append(category_id)
    if only_available:
        sql += " AND is_available = 1"
    return [_product(r) for r in await fetchall(sql + " ORDER BY sort, id", *args)]


async def get_product(product_id: int) -> dict | None:
    r = await fetchone("SELECT * FROM products WHERE id = ? AND is_deleted = 0", product_id)
    return _product(r) if r else None


async def add_product(category_id: int, name: str, description: str, image: str, variants: list[dict]) -> int:
    sort = await scalar(
        "SELECT COALESCE(MAX(sort), 0) + 1 FROM products WHERE category_id = ?", category_id
    )
    return await execute(
        "INSERT INTO products(category_id, name, description, image, variants, sort, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        category_id, name, description, image,
        json.dumps(variants, ensure_ascii=False), sort, now_str(),
    )


PRODUCT_FIELDS = {
    "name", "description", "image", "variants", "is_available", "category_id", "is_deleted",
    "name_ru", "description_ru", "badges", "discount_percent", "discount_until", "sort",
}


async def update_product(product_id: int, **fields) -> None:
    for key, value in fields.items():
        assert key in PRODUCT_FIELDS, key
        if key == "variants":
            value = json.dumps(value, ensure_ascii=False)
        await db().execute(f"UPDATE products SET {key} = ? WHERE id = ?", (value, product_id))
    await db().commit()


async def get_menu(lang: str = "uz") -> list[dict]:
    """Mini app uchun: faol kategoriyalar + mavjud mahsulotlar (tanlangan tilda, chegirmalar bilan)."""
    from .catalog import category_name, product_public

    cats = await get_categories(only_active=True)
    products = await get_products(only_available=True)
    result = []
    for c in cats:
        items = [p for p in products if p["category_id"] == c["id"]]
        if items:
            result.append({
                "id": c["id"], "name": category_name(c, lang), "emoji": c["emoji"],
                "products": [product_public(p, lang) for p in items],
            })
    return result


# ---------------- bot savati ----------------

async def cart_add(user_id: int, product_id: int, variant: int, qty: int) -> None:
    await execute(
        "INSERT INTO cart_items(user_id, product_id, variant, qty) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(user_id, product_id, variant) DO UPDATE SET qty = MIN(50, qty + excluded.qty)",
        user_id, product_id, variant, qty,
    )


async def cart_change(user_id: int, product_id: int, variant: int, delta: int) -> None:
    await db().execute(
        "UPDATE cart_items SET qty = MIN(50, qty + ?) WHERE user_id = ? AND product_id = ? AND variant = ?",
        (delta, user_id, product_id, variant),
    )
    await db().execute("DELETE FROM cart_items WHERE user_id = ? AND qty <= 0", (user_id,))
    await db().commit()


async def cart_clear(user_id: int) -> None:
    await execute("DELETE FROM cart_items WHERE user_id = ?", user_id)


async def cart_get(user_id: int) -> list[dict]:
    """Savat pozitsiyalari joriy narxlar bilan; mavjud bo'lmaganlari avtomatik olib tashlanadi."""
    rows = await fetchall("SELECT * FROM cart_items WHERE user_id = ? ORDER BY rowid", user_id)
    items = []
    for r in rows:
        p = await get_product(r["product_id"])
        cat = await get_category(p["category_id"]) if p else None
        if not p or not p["is_available"] or not cat or not cat["is_active"] or r["variant"] >= len(p["variants"]):
            await execute("DELETE FROM cart_items WHERE user_id = ? AND product_id = ? AND variant = ?",
                          user_id, r["product_id"], r["variant"])
            continue
        from .catalog import variant_price

        v = p["variants"][r["variant"]]
        price, old = variant_price(p, r["variant"])
        items.append({
            "product_id": p["id"], "variant": r["variant"], "qty": r["qty"],
            "name": p["name"], "variant_name": v["name"], "price": price, "old_price": old,
            "product": p,
        })
    return items


async def cart_count(user_id: int) -> int:
    return await scalar("SELECT COALESCE(SUM(qty), 0) FROM cart_items WHERE user_id = ?", user_id)


# ---------------- orders ----------------

def generate_order_code() -> str:
    """Qisqa va o'qish oson ID: YG-482917 (6 ta raqam)."""
    return f"YG-{secrets.randbelow(900_000) + 100_000}"


async def create_order(user_id: int, data: dict, items: list[dict], delivery_fee: int, discount: int = 0) -> int:
    subtotal = sum(i["price"] * i["qty"] for i in items)
    ts = now_str()
    code = generate_order_code()
    while await scalar("SELECT 1 FROM orders WHERE code = ?", code):
        code = generate_order_code()
    cur = await db().execute(
        "INSERT INTO orders(code, user_id, customer_name, phone, address, comment, payment_method,"
        " subtotal, delivery_fee, total, status, created_at, updated_at,"
        " order_type, scheduled_at, promo_code, discount, lang)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?, ?, ?, ?, ?, ?)",
        (
            code, user_id, data["name"], data["phone"], data.get("address", ""), data.get("comment", ""),
            data["payment_method"], subtotal, delivery_fee, max(0, subtotal - discount) + delivery_fee, ts, ts,
            data.get("order_type", "delivery"), data.get("scheduled_at", ""), data.get("promo_code", ""),
            discount, data.get("lang", "uz"),
        ),
    )
    order_id = cur.lastrowid
    await db().executemany(
        "INSERT INTO order_items(order_id, product_id, name, variant, price, qty) VALUES (?, ?, ?, ?, ?, ?)",
        [(order_id, i["product_id"], i["name"], i["variant"], i["price"], i["qty"]) for i in items],
    )
    await db().execute(
        "INSERT INTO order_status_log(order_id, status, by_user, at) VALUES (?, 'new', ?, ?)",
        (order_id, user_id, ts),
    )
    await db().commit()
    return order_id


ORDER_SELECT = (
    "SELECT o.*, COALESCE(s.full_name, s.first_name) AS staff_name FROM orders o"
    " LEFT JOIN users s ON s.id = o.staff_id"
)


async def get_order(order_id: int) -> dict | None:
    return await fetchone(ORDER_SELECT + " WHERE o.id = ?", order_id)


async def get_order_by_code(code: str) -> dict | None:
    return await fetchone(ORDER_SELECT + " WHERE o.code = ?", code.strip().upper())


async def find_order(query: str) -> dict | None:
    """Unikal kod (YG-...) yoki ichki raqam bo'yicha qidiradi."""
    q = query.strip().lstrip("#")
    if q.isdigit():
        # "482917" -> YG-482917; aks holda ichki raqam
        return await get_order_by_code(f"YG-{q}") or await get_order(int(q))
    order = await get_order_by_code(q)
    if not order and len(q) >= 4:
        # kodning bir qismi bo'yicha (masalan oxirgi 4 belgi)
        order = await fetchone(ORDER_SELECT + " WHERE o.code LIKE ? ORDER BY o.id DESC", f"%{q.upper()}%")
    return order


async def get_order_items(order_id: int) -> list[dict]:
    return await fetchall("SELECT * FROM order_items WHERE order_id = ? ORDER BY id", order_id)


async def get_order_log(order_id: int) -> list[dict]:
    return await fetchall(
        "SELECT status, at FROM order_status_log WHERE order_id = ? ORDER BY id", order_id
    )


async def get_user_orders(user_id: int, limit: int = 20) -> list[dict]:
    return await fetchall(
        ORDER_SELECT + " WHERE o.user_id = ? ORDER BY o.id DESC LIMIT ?", user_id, limit
    )


async def get_orders_by_status(statuses: tuple[str, ...], limit: int = 30, staff_id: int | None = None) -> list[dict]:
    marks = ",".join("?" * len(statuses))
    sql = ORDER_SELECT + f" WHERE o.status IN ({marks})"
    args: list = list(statuses)
    if staff_id is not None:
        sql += " AND o.staff_id = ?"
        args.append(staff_id)
    return await fetchall(sql + " ORDER BY o.id DESC LIMIT ?", *args, limit)


async def get_active_orders() -> list[dict]:
    return await get_orders_by_status(ACTIVE_STATUSES, limit=50)


async def set_order_status(order_id: int, status: str, by_user: int | None, cancel_reason: str | None = None) -> None:
    ts = now_str()
    if status == "accepted" and by_user:
        await db().execute(
            "UPDATE orders SET status=?, staff_id=?, updated_at=? WHERE id=?",
            (status, by_user, ts, order_id),
        )
    else:
        await db().execute(
            "UPDATE orders SET status=?, cancel_reason=COALESCE(?, cancel_reason), updated_at=? WHERE id=?",
            (status, cancel_reason, ts, order_id),
        )
    await db().execute(
        "INSERT INTO order_status_log(order_id, status, by_user, at) VALUES (?, ?, ?, ?)",
        (order_id, status, by_user, ts),
    )
    await db().commit()


async def save_order_message(order_id: int, chat_id: int, message_id: int) -> None:
    await execute(
        "INSERT INTO order_messages(order_id, chat_id, message_id) VALUES (?, ?, ?)",
        order_id, chat_id, message_id,
    )


async def get_order_messages(order_id: int) -> list[dict]:
    return await fetchall("SELECT * FROM order_messages WHERE order_id = ?", order_id)


async def delete_order(order_id: int) -> list[dict]:
    """Buyurtmani butunlay o'chiradi (faqat menejer). Xodimlardagi xabarlar ro'yxatini qaytaradi."""
    messages = await get_order_messages(order_id)
    for table in ("order_items", "order_status_log", "order_messages", "reviews"):
        await db().execute(f"DELETE FROM {table} WHERE order_id = ?", (order_id,))
    await db().execute("DELETE FROM orders WHERE id = ?", (order_id,))
    await db().commit()
    return messages


# ---------------- promo-kodlar ----------------

PROMO_FIELDS = {
    "code", "kind", "value", "min_order", "max_discount", "usage_limit", "per_user_limit",
    "first_order_only", "starts_at", "ends_at", "is_active",
}


async def get_promos() -> list[dict]:
    return await fetchall(
        "SELECT p.*, (SELECT COUNT(*) FROM orders o WHERE o.promo_code = p.code AND o.status != 'cancelled') AS used"
        " FROM promo_codes p ORDER BY p.is_active DESC, p.id DESC"
    )


async def get_promo(promo_id: int) -> dict | None:
    return await fetchone(
        "SELECT p.*, (SELECT COUNT(*) FROM orders o WHERE o.promo_code = p.code AND o.status != 'cancelled') AS used,"
        " (SELECT COALESCE(SUM(o.discount), 0) FROM orders o WHERE o.promo_code = p.code AND o.status != 'cancelled')"
        " AS discount_sum FROM promo_codes p WHERE p.id = ?",
        promo_id,
    )


async def get_promo_by_code(code: str) -> dict | None:
    return await fetchone("SELECT * FROM promo_codes WHERE code = ?", code.strip().upper())


async def add_promo(**fields) -> int:
    assert set(fields) <= PROMO_FIELDS
    fields["code"] = fields["code"].strip().upper()
    cols = ", ".join(fields) + ", created_at"
    marks = ", ".join("?" * (len(fields) + 1))
    return await execute(f"INSERT INTO promo_codes({cols}) VALUES ({marks})", *fields.values(), now_str())


async def update_promo(promo_id: int, **fields) -> None:
    for key, value in fields.items():
        assert key in PROMO_FIELDS, key
        await db().execute(f"UPDATE promo_codes SET {key} = ? WHERE id = ?", (value, promo_id))
    await db().commit()


async def delete_promo(promo_id: int) -> None:
    await execute("DELETE FROM promo_codes WHERE id = ?", promo_id)


async def promo_uses(code: str, user_id: int | None = None) -> int:
    sql = "SELECT COUNT(*) FROM orders WHERE promo_code = ? AND status != 'cancelled'"
    args: list = [code]
    if user_id is not None:
        sql += " AND user_id = ?"
        args.append(user_id)
    return await scalar(sql, *args)


async def user_order_count(user_id: int) -> int:
    return await scalar("SELECT COUNT(*) FROM orders WHERE user_id = ? AND status != 'cancelled'", user_id)


# ---------------- baholar ----------------

async def add_review(order_id: int, user_id: int, rating: int, comment: str = "") -> bool:
    """Har bir buyurtmaga bitta baho. Yangi qo'shilsa True."""
    cur = await db().execute(
        "INSERT OR IGNORE INTO reviews(order_id, user_id, rating, comment, created_at) VALUES (?, ?, ?, ?, ?)",
        (order_id, user_id, rating, comment, now_str()),
    )
    await db().commit()
    return cur.rowcount > 0


async def set_review_comment(order_id: int, comment: str) -> None:
    await execute("UPDATE reviews SET comment = ? WHERE order_id = ?", comment[:500], order_id)


async def get_review(order_id: int) -> dict | None:
    return await fetchone("SELECT * FROM reviews WHERE order_id = ?", order_id)


async def get_reviews(limit: int = 10, max_rating: int | None = None) -> list[dict]:
    sql = ("SELECT r.*, o.code, COALESCE(u.full_name, u.first_name) AS name FROM reviews r"
           " JOIN orders o ON o.id = r.order_id LEFT JOIN users u ON u.id = r.user_id")
    args: list = []
    if max_rating is not None:
        sql += " WHERE r.rating <= ?"
        args.append(max_rating)
    return await fetchall(sql + " ORDER BY r.id DESC LIMIT ?", *args, limit)


async def review_stats(since: str | None = None) -> dict:
    where, args = ("WHERE created_at >= ?", [since]) if since else ("", [])
    row = await fetchone(f"SELECT COUNT(*) c, COALESCE(AVG(rating), 0) avg FROM reviews {where}", *args)
    dist = {r["rating"]: r["c"] for r in await fetchall(
        f"SELECT rating, COUNT(*) c FROM reviews {where} GROUP BY rating", *args)}
    return {"count": row["c"], "avg": round(row["avg"], 2), "dist": dist}


# ---------------- vaqtga buyurtmalar ----------------

async def due_scheduled_orders(until: str) -> list[dict]:
    """Eslatma yuborilmagan, vaqti yaqinlashgan faol vaqtga buyurtmalar."""
    marks = ",".join("?" * len(ACTIVE_STATUSES))
    return await fetchall(
        ORDER_SELECT + f" WHERE o.scheduled_at != '' AND o.reminded = 0 AND o.scheduled_at <= ?"
        f" AND o.status IN ({marks})", until, *ACTIVE_STATUSES,
    )


async def mark_reminded(order_id: int) -> None:
    await execute("UPDATE orders SET reminded = 1 WHERE id = ?", order_id)


# ---------------- statistics ----------------

async def stats(since: str | None) -> dict:
    where, args = ("WHERE created_at >= ?", [since]) if since else ("", [])
    and_ = "AND" if since else "WHERE"
    total_orders = await scalar(f"SELECT COUNT(*) FROM orders {where}", *args)
    by_status = {
        r["status"]: r["c"]
        for r in await fetchall(f"SELECT status, COUNT(*) c FROM orders {where} GROUP BY status", *args)
    }
    revenue = await scalar(
        f"SELECT COALESCE(SUM(total), 0) FROM orders {where} {and_} status = 'delivered'", *args
    )
    delivered = by_status.get("delivered", 0)
    pending_sum = await scalar(
        f"SELECT COALESCE(SUM(total), 0) FROM orders {where} {and_} status IN "
        f"({','.join('?' * len(ACTIVE_STATUSES))})", *args, *ACTIVE_STATUSES,
    )
    top = await fetchall(
        "SELECT i.name, SUM(i.qty) qty, SUM(i.qty * i.price) amount FROM order_items i"
        " JOIN orders o ON o.id = i.order_id"
        f" WHERE o.status = 'delivered' {'AND o.created_at >= ?' if since else ''}"
        " GROUP BY i.name ORDER BY qty DESC LIMIT 5",
        *args,
    )
    new_users = await scalar(
        f"SELECT COUNT(*) FROM users {where}", *args
    )
    customers = await scalar(
        f"SELECT COUNT(DISTINCT user_id) FROM orders {where}", *args
    )
    by_type = {
        r["order_type"]: r["c"]
        for r in await fetchall(
            f"SELECT order_type, COUNT(*) c FROM orders {where} {and_} status != 'cancelled' GROUP BY order_type",
            *args)
    }
    promo_sum = await scalar(
        f"SELECT COALESCE(SUM(discount), 0) FROM orders {where} {and_} status = 'delivered'", *args
    )
    return {
        "by_type": by_type,
        "promo_sum": promo_sum,
        "rating": await review_stats(since),
        "total_orders": total_orders,
        "by_status": by_status,
        "revenue": revenue,
        "avg_check": revenue // delivered if delivered else 0,
        "pending_sum": pending_sum,
        "top": top,
        "new_users": new_users,
        "customers": customers,
        "users_total": await scalar("SELECT COUNT(*) FROM users"),
    }


async def daily_revenue(days: int = 7) -> list[dict]:
    return await fetchall(
        "SELECT substr(created_at, 1, 10) day, COUNT(*) orders, COALESCE(SUM(total), 0) amount"
        " FROM orders WHERE status = 'delivered' AND created_at >= date('now', '+5 hours', ?)"
        " GROUP BY day ORDER BY day DESC",
        f"-{days - 1} days",
    )


async def staff_stats(since: str | None) -> list[dict]:
    extra = "AND o.created_at >= ?" if since else ""
    args = [since] if since else []
    return await fetchall(
        "SELECT COALESCE(u.full_name, u.first_name) name, COUNT(*) c, COALESCE(SUM(o.total), 0) amount"
        " FROM orders o JOIN users u ON u.id = o.staff_id"
        f" WHERE o.status = 'delivered' {extra} GROUP BY o.staff_id ORDER BY c DESC",
        *args,
    )


async def all_orders_for_export(since: str | None) -> list[dict]:
    where, args = ("WHERE o.created_at >= ?", [since]) if since else ("", [])
    return await fetchall(
        ORDER_SELECT.replace("SELECT o.*,", "SELECT o.*, (SELECT GROUP_CONCAT(i.name || "
                             "CASE WHEN i.variant != '' THEN ' (' || i.variant || ')' ELSE '' END"
                             " || ' x' || i.qty, '; ') FROM order_items i WHERE i.order_id = o.id) AS items,")
        + f" {where} ORDER BY o.id",
        *args,
    )
