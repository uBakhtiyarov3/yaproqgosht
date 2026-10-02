# 👑 Yaproq go'sht — yetkazib berish boti + Mini App

"Yaproq go'sht" kafesining Telegram boti. Mijozlar mini ilova (Telegram Mini App) orqali buyurtma beradi, xodimlar buyurtma holatini bot ichida boshqaradi, menejer esa statistika, menyu, rassilka va sozlamalarni boshqaradi.

## Imkoniyatlar

### 🙋 Mijoz
- `/start` bosilganda **akkaunt avtomatik ochiladi**, keyin mini ilovani ochish taklif qilinadi (pastdagi menyu tugmasi ham mini ilovani ochadi).
- **Mini App**: kategoriyalar, rasmli mahsulotlar va narxlar, o'lcham tanlash (O'rta/Katta, 60g/80g), savat.
- **Rasmiylashtirish**: qabul qiluvchining ismi, telefon (`+998` prefiksi doim turadi, raqam o'zi `+998 90 123 45 67` ko'rinishiga keladi), manzil, ixtiyoriy izoh va joylashuv. To'lov: **Naqd** (faol) va **Karta** (yopiq, "Tez kunda" belgisi bilan).
- Har bir buyurtmaga **unikal uzun ID** beriladi: `YG-261002-7K3Q-9XM2`.
- **Holatni kuzatish** (avtomatik yangilanadi): Buyurtma berildi → Qabul qilindi → Tayyorlanmoqda → Yetkazilmoqda → Yetkazildi. Har bir o'zgarishda bot xabar ham yuboradi.
- Hali qabul qilinmagan buyurtmani mijoz o'zi bekor qila oladi.
- Botga yozilgan erkin xabarlar menejerga boradi, menejer reply qilib javob beradi.

### 👷 Xodim kabineti
- Yangi buyurtma tushishi bilan barcha xodimlarga **avtomatik xabar** keladi, ichida holatni o'zgartirish tugmalari bor.
- Bir xodim holatni o'zgartirsa, xabar boshqa xodimlarda ham yangilanadi (bitta buyurtmani ikki kishi ikki marta qabul qilib qo'ymaydi).
- Bekor qilish (sababini tanlab), yangi/faol/o'z buyurtmalari ro'yxatlari, bugungi natija, `/order <ID>` orqali qidirish.

### 👑 Menejer paneli (`/admin`)
- 📊 **Statistika**: bugun / 7 kun / 30 kun / barcha vaqt — tushum, o'rtacha chek, holatlar kesimida buyurtmalar, top mahsulotlar, xodimlar natijasi, kunlik tushum, yangi foydalanuvchilar.
- 📦 **Barcha buyurtmalar**: faol, yetkazilgan va bekor qilingan buyurtmalar.
- 🍔 **Menyuni boshqarish**:
  - kategoriyalar: qo'shish, nomi/emojini o'zgartirish, yashirish/ko'rsatish, tartibini o'zgartirish (⬆️/⬇️), o'chirish;
  - mahsulotlar: qo'shish (nomi, tavsifi, narx(lar)i, rasmi), har bir maydonni tahrirlash, boshqa kategoriyaga ko'chirish, sotuvdan olish, o'chirish.
- 📢 **Rassilka**: istalgan xabarni (matn, rasm, video) barcha foydalanuvchilarga yuborish (oldin ko'rib tasdiqlanadi).
- 👥 **Xodimlar**: xodim yoki menejer qo'shish (kontaktdan tanlab, ID yoki @username orqali) va olib tashlash.
- 🙋 **Mijozlar**: soni, eng faol mijozlar, ID/telefon/username bo'yicha qidirish.
- ⚙️ **Sozlamalar**: buyurtma qabul qilishni to'xtatish/ochish, yetkazish narxi, minimal summa, telefon, ish vaqti.
- 📥 **Hisobot**: buyurtmalarni CSV qilib yuklab olish (Excel to'g'ri ochadi).

## Tez ishga tushirish

```bash
git clone <repo> && cd yaproqgosht
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # keyin .env ni to'ldiring
python main.py
```

`.env` fayli:

```env
BOT_TOKEN=<BotFather bergan token>
ADMIN_IDS=2076925033
WEBAPP_URL=https://<sizning-domeningiz>
PORT=8080
DEBUG=0
```

> ⚠️ Tokenni hech qachon repoga commit qilmang — `.env` `.gitignore` ga qo'shilgan.

### Mini App uchun HTTPS manzil

Telegram mini ilovani faqat **https** manzilda ochadi. Bot o'zi `PORT` (8080) da web server ko'taradi, unga https manzil kerak:

**Test uchun (domensiz, 1 daqiqada)** — Cloudflare tunnel:
```bash
# boshqa terminalda
cloudflared tunnel --url http://localhost:8080
# chiqqan https://xxxx.trycloudflare.com manzilini .env dagi WEBAPP_URL ga yozing va botni qayta ishga tushiring
```
(`ngrok http 8080` ham bo'ladi.)

**Doimiy ishlatish uchun** — VPS + domen + Caddy (SSL avtomatik):
```
# /etc/caddy/Caddyfile
bot.yaproqgosht.uz {
    reverse_proxy localhost:8080
}
```
Keyin `docker compose up -d --build` (baza va rasmlar `./data` papkasida saqlanadi).

## Test qilish

1. `.env` dagi `ADMIN_IDS` ga o'z ID ingizni yozing → botga `/start` bosing → **👑 Menejer paneli** va **👷 Xodim kabineti** tugmalari chiqadi.
2. **🍔 Menyu** → mahsulot qo'shing → savat → buyurtma bering.
3. Shu zahoti botga "🔔 YANGI BUYURTMA" xabari keladi → tugmalar orqali holatni o'zgartiring → mini ilovadagi buyurtma sahifasi va mijozga keladigan xabarlar o'zgarishini kuzating.
4. Ikkinchi akkauntni **👥 Xodimlar → ➕ Xodim qo'shish** orqali xodim qilib, buyurtmalar unga ham kelishini tekshiring.

Avtomatik testlar (Telegram'ga ulanmasdan):
```bash
pip install -r requirements-dev.txt
pytest
```

Mini ilovani oddiy brauzerda ko'rish uchun: `.env` da `DEBUG=1` qilib, `http://localhost:8080/?dev_user=123` ni oching (prod da `DEBUG=0` bo'lishi shart).

## Tuzilma

```
main.py               — bot (polling) + web server
app/config.py         — .env sozlamalari
app/db.py             — SQLite sxema, menyu seed, so'rovlar, statistika
app/webapp.py         — Mini App API (Telegram initData tekshiruvi bilan)
app/notify.py         — xodim/mijozga bildirishnomalar, rassilka
app/handlers/common.py — /start, mijoz tugmalari, fikr-mulohaza
app/handlers/staff.py  — xodim kabineti, holat tugmalari
app/handlers/admin.py  — menejer paneli
webapp/               — Mini App (HTML/CSS/JS) va mahsulot rasmlari
tests/                — API va bot oqimlari testlari
```

## Keyingi qadamlar (taklif)
- 💳 Click / Payme orqali karta to'lovi (interfeysda "Tez kunda" bo'lib turibdi).
- Yetkazish hududi/masofasiga qarab narx, promo-kodlar, bonus tizimi.
- Kuryer roli (alohida "Yetkazilmoqda" bosqichi uchun).
