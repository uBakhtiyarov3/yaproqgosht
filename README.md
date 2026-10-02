# 👑 Yaproq go'sht — yetkazib berish boti + Mini App

"Yaproq go'sht" kafesining Telegram boti. Mijozlar mini ilova (Telegram Mini App) orqali buyurtma beradi, xodimlar buyurtma holatini bot ichida boshqaradi, menejer esa statistika, menyu, rassilka va sozlamalarni boshqaradi.

## Imkoniyatlar

### 🙋 Mijoz
- `/start` bosilganda **akkaunt avtomatik ochiladi**, keyin ikki yo'l taklif qilinadi: Mini App yoki botning o'zida buyurtma.
- **Bot ichida buyurtma (Mini Appsiz)**: «📋 Menyu» → kategoriya → mahsulot kartasi (rasm, o'lcham, ➖/➕ soni) → «🛒 Savat» (sonini o'zgartirish, tozalash) → rasmiylashtirish: ism, telefon («📱 Raqamimni yuborish» tugmasi yoki yozib), manzil (matn yoki «📍 Joylashuv»), izoh, to'lov (Naqd / Karta — tez kunda), tasdiqlash. Oldingi ism, telefon va manzil tugma bo'lib chiqadi. «📦 Buyurtmalarim» da holat, bekor qilish va «🔁 Qayta buyurtma».
- **Mini App**: kategoriyalar, rasmli mahsulotlar va narxlar, o'lcham tanlash (O'rta/Katta, 60g/80g), savat.
- **Rasmiylashtirish**: qabul qiluvchining ismi, telefon (`+998` prefiksi doim turadi, raqam o'zi `+998 90 123 45 67` ko'rinishiga keladi), manzil, ixtiyoriy izoh va joylashuv. To'lov: **Naqd** (faol) va **Karta** (yopiq, "Tez kunda" belgisi bilan).
- Har bir buyurtmaga **unikal ID** beriladi: `YG-482917`.
- **Holatni kuzatish** (avtomatik yangilanadi): Buyurtma berildi → Qabul qilindi → Tayyorlanmoqda → Yetkazilmoqda → Yetkazildi. Har bir o'zgarishda bot xabar ham yuboradi.
- Hali qabul qilinmagan buyurtmani mijoz o'zi bekor qila oladi.
- Botga yozilgan erkin xabarlar menejerga boradi, menejer reply qilib javob beradi.

### 👷 Xodim kabineti
- Yangi buyurtma tushishi bilan barcha xodimlarga **avtomatik xabar** keladi, ichida holatni o'zgartirish tugmalari bor.
- Bir xodim holatni o'zgartirsa, xabar boshqa xodimlarda ham yangilanadi (bitta buyurtmani ikki kishi ikki marta qabul qilib qo'ymaydi).
- Bekor qilish (sababini tanlab), yangi/faol/o'z buyurtmalari ro'yxatlari, bugungi natija, `/order <ID>` orqali qidirish.

### 🖥 Admin web panel (`/admin/`)
Botning **hamma narsasi** brauzerdagi panelda boshqariladi. Saqlash tugmasi bosilishi bilan bot va Mini App **darhol** yangilanadi (qayta ishga tushirish kerak emas).
- **Kirish:** botda *👑 Menejer paneli → 🖥 Web panel* → bir martalik havola (15 daqiqa). Sessiya 14 kun saqlanadi. Faqat menejerlar kira oladi.
- 📊 Statistika (tushum, holatlar, kunlik grafik, top mahsulotlar, xodimlar, reyting, promo chegirmalar).
- 📦 Buyurtmalar: filtr, qidiruv, tafsilot, holatni o'zgartirish va bekor qilish (mijozga avtomatik xabar), yangi buyurtma ovozli signali.
- 🍔 Menyu: kategoriyalar (qo'shish, uz/ru nomi, emoji, yashirish, tartib, o'chirish); mahsulotlar (uz/ru nomi va tavsifi, o'lcham va narxlar, badge'lar, chegirma va muddati, sotuvda/yo'q, tartib).
- 📸 Rasm yuklash: drag-and-drop, nisbat/o'lcham/hajm ko'rsatkichlari, ideal rasm talablari, avtomatik 4:3 kesish va 1200×900 JPG optimallashtirish.
- 💬 **Bot xabarlari**: barcha menyulardagi barcha xabarlar va tugmalar (uz/ru) — formatlash paneli (qalin, kursiv, tagiga chizilgan, kod, spoiler, iqtibos, havola), o'zgaruvchilar (`{name}`...), Telegram'dagi ko'rinishi, xatolarni tekshirish, asl holiga qaytarish.
- ⚙️ Sozlamalar: avto/ochiq/yopiq rejim, kunlik ish vaqti, yetkazish/olib ketish, narxlar, tayyorlash vaqti, slot qadami, telefon, manzil.
- 🎁 Promo-kodlar, ⭐ baholar, 📢 rassilka (rasm, formatlash, havola tugmalari, test), 🙋 mijozlar, 👥 xodimlar, 📥 CSV hisobot va 💾 zaxira nusxa.

### 👑 Menejer paneli (bot ichida, `/admin`)
- 📊 **Statistika**: bugun / 7 kun / 30 kun / barcha vaqt — tushum, o'rtacha chek, holatlar kesimida buyurtmalar, top mahsulotlar, xodimlar natijasi, kunlik tushum, yangi foydalanuvchilar.
- 📦 **Barcha buyurtmalar**: faol, yetkazilgan va bekor qilingan buyurtmalar.
- 🍔 **Menyuni boshqarish**:
  - kategoriyalar: qo'shish, nomi/emojini o'zgartirish, yashirish/ko'rsatish, tartibini o'zgartirish (⬆️/⬇️), o'chirish;
  - mahsulotlar: qo'shish (nomi, tavsifi, narx(lar)i, rasmi), har bir maydonni tahrirlash, boshqa kategoriyaga ko'chirish, sotuvdan olish, o'chirish.
- 📢 **Rassilka**: matn, rasm/video, **albom** yoki kanaldan **forward qilingan tayyor rasmli post** — barcha foydalanuvchilarga. «Nusxa» (bot nomidan) yoki «Forward» (manba ko'rinadi) rejimi, havola tugmalar (`Matn - https://...`) va «📋 Buyurtma berish» tugmasini qo'shish, yuborishdan oldin aynan qanday ko'rinishini ko'rsatadi.
- 👥 **Xodimlar**: xodim yoki menejer qo'shish (kontaktdan tanlab, ID yoki @username orqali) va olib tashlash.
- 🙋 **Mijozlar**: soni, eng faol mijozlar, ID/telefon/username bo'yicha qidirish.
- ⚙️ **Sozlamalar**: buyurtma qabul qilishni to'xtatish/ochish, yetkazish narxi, minimal summa, telefon, ish vaqti.
- 📥 **Hisobot**: buyurtmalarni CSV qilib yuklab olish (Excel to'g'ri ochadi).
- 💾 **Zaxira nusxa**: baza + rasmlar `.zip` — tugma orqali va har kuni avtomatik.

## Ishga tushirish

📘 **Serverga bepul va doimiy o'rnatish bo'yicha to'liq qo'llanma: [DEPLOY.md](DEPLOY.md)**
(Oracle Cloud / Google Cloud bepul server + domen + `bash deploy/install.sh`).

Lokal kompyuterda sinash:

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # BOT_TOKEN va ADMIN_IDS ni yozing
python main.py
```

`WEBAPP_URL` bo'lmasa ham bot ishlaydi — buyurtma bot ichida (inline tugmalar) beriladi. Mini App uchun https manzil kerak: tez test uchun `cloudflared tunnel --url http://localhost:8080` bergan manzilni `WEBAPP_URL` ga yozing.

> ⚠️ Tokenni hech qachon repoga commit qilmang — `.env` `.gitignore` ga qo'shilgan.

## Test qilish

1. `.env` dagi `ADMIN_IDS` ga o'z ID ingizni yozing → botga `/start` bosing → **👑 Menejer paneli** va **👷 Xodim kabineti** tugmalari chiqadi.
2. **📋 Menyu** (bot ichida) yoki **🍔 Mini ilova** → mahsulot qo'shing → savat → buyurtma bering.
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
app/orders.py         — buyurtma tekshiruv qoidalari (Mini App va bot uchun umumiy)
app/handlers/shop.py   — bot ichida menyu, savat, rasmiylashtirish, buyurtmalarim
app/handlers/common.py — /start, aloqa, fikr-mulohaza
app/handlers/staff.py  — xodim kabineti, holat tugmalari
app/handlers/admin.py  — menejer paneli (bot ichida)
app/admin_api.py      — admin web panel API (/api/admin/*)
app/texts_admin.py    — tahrirlanadigan bot matnlari katalogi va tekshiruvi
app/backup.py         — zaxira nusxa (qo'lda va har kuni 04:00 da)
deploy/               — install.sh, update.sh, Caddyfile (HTTPS)
webapp/               — Mini App (HTML/CSS/JS) va mahsulot rasmlari
webapp/admin/         — admin web panel
deploy/build_static.sh — Mini App + admin panelni shared hostingga tayyorlash
tests/                — API va bot oqimlari testlari
```

## Keyingi qadamlar (taklif)
- 💳 Click / Payme orqali karta to'lovi (interfeysda "Tez kunda" bo'lib turibdi).
- Yetkazish hududi/masofasiga qarab narx, promo-kodlar, bonus tizimi.
- Kuryer roli (alohida "Yetkazilmoqda" bosqichi uchun).
