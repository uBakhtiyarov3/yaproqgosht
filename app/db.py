import json
import secrets
from pathlib import Path

import aiosqlite

from .utils import ACTIVE_STATUSES, now, now_str

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
    code TEXT NOT NULL UNIQUE,                  -- unikal uzun ID: YG-261002-7K3Q-9XM2
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

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_code ON orders(code);
CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at);
"""

DEFAULT_SETTINGS = {
    "is_open": "1",
    "delivery_fee": "0",
    "min_order": "0",
    "phone": "",
    "work_hours": "10:00 - 23:00",
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
    for k, v in DEFAULT_SETTINGS.items():
        await _db.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))
    await _db.commit()
    await _seed_menu()


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


PRODUCT_FIELDS = {"name", "description", "image", "variants", "is_available", "category_id", "is_deleted"}


async def update_product(product_id: int, **fields) -> None:
    for key, value in fields.items():
        assert key in PRODUCT_FIELDS, key
        if key == "variants":
            value = json.dumps(value, ensure_ascii=False)
        await db().execute(f"UPDATE products SET {key} = ? WHERE id = ?", (value, product_id))
    await db().commit()


async def get_menu() -> list[dict]:
    """Mini app uchun: faol kategoriyalar + mavjud mahsulotlar."""
    cats = await get_categories(only_active=True)
    products = await get_products(only_available=True)
    result = []
    for c in cats:
        items = [p for p in products if p["category_id"] == c["id"]]
        if items:
            result.append({
                "id": c["id"], "name": c["name"], "emoji": c["emoji"],
                "products": [
                    {k: p[k] for k in ("id", "name", "description", "image", "variants")}
                    for p in items
                ],
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
        v = p["variants"][r["variant"]]
        items.append({
            "product_id": p["id"], "variant": r["variant"], "qty": r["qty"],
            "name": p["name"], "variant_name": v["name"], "price": v["price"],
        })
    return items


async def cart_count(user_id: int) -> int:
    return await scalar("SELECT COALESCE(SUM(qty), 0) FROM cart_items WHERE user_id = ?", user_id)


# ---------------- orders ----------------

# chalkashtiradigan belgilarsiz (0/O, 1/I/L yo'q)
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


def generate_order_code() -> str:
    rnd = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    return f"YG-{now().strftime('%y%m%d')}-{rnd[:4]}-{rnd[4:]}"


async def create_order(user_id: int, data: dict, items: list[dict], delivery_fee: int) -> int:
    subtotal = sum(i["price"] * i["qty"] for i in items)
    ts = now_str()
    code = generate_order_code()
    while await scalar("SELECT 1 FROM orders WHERE code = ?", code):
        code = generate_order_code()
    cur = await db().execute(
        "INSERT INTO orders(code, user_id, customer_name, phone, address, comment, payment_method,"
        " subtotal, delivery_fee, total, status, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?)",
        (
            code, user_id, data["name"], data["phone"], data["address"], data.get("comment", ""),
            data["payment_method"], subtotal, delivery_fee, subtotal + delivery_fee, ts, ts,
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
        return await get_order(int(q))
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
    return {
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
