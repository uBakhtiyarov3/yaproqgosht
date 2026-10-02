# 🚀 Yaproq go'sht botini bepul va doimiy ishga tushirish

Bot **doim ishlab turishi** kerak: Telegram'dan yangi xabarlarni kutadi, xodimlarga buyurtma yuboradi, har kuni zaxira nusxa oladi. Shuning uchun unga **24/7 yoqilgan server** kerak. "Uxlab qoladigan" bepul xostinglar (Render, Koyeb free va h.k.) bu bot uchun mos emas.

Bepul va doimiy ishlaydigan eng yaxshi variantlar — yirik bulut provayderlarining **"Always Free" virtual serverlari**:

| Variant | Narx | Resurs | Eslatma |
|---|---|---|---|
| **Oracle Cloud Always Free** (tavsiya) | 0 so'm | Ampere A1: 2 OCPU / 12 GB RAMgacha (biz 1 OCPU / 6 GB olamiz) | Ro'yxatdan o'tishda karta tasdiqlanadi (pul yechilmaydi) |
| **Google Cloud e2-micro** | 0 so'm | 2 vCPU (shared) / 1 GB RAM, 30 GB disk | Faqat us-west1, us-central1, us-east1 regionlarida bepul. Karta kerak |
| Arzon VPS (zaxira variant) | ~$4–6/oy | 1–2 GB RAM | Karta/ro'yxatdan o'tish muammosi bo'lsa, eng ishonchli yo'l |

Qaysi variantni tanlasangiz ham keyingi qadamlar bir xil: **Ubuntu server → domen → `install.sh` skripti**.

---

## 1-qadam. Tayyorgarlik (5 daqiqa)

1. **Yangi bot token oling.** Eski token chatda ochiq yuborilgan, shuning uchun @BotFather → `/mybots` → botingiz → *API Token* → **Revoke current token**. Yangi tokenni saqlab qo'ying.
2. **Telegram ID ingiz:** `2076925033` (bosh menejer). Boshqa menejerlar keyin bot ichidan qo'shiladi.

## 2-qadam. Bepul server ochish

### Variant A — Oracle Cloud (tavsiya)

1. https://signup.cloud.oracle.com → ro'yxatdan o'ting. **Home region** ni yaqinroq tanlang (masalan *Germany Central (Frankfurt)*) — keyin uni o'zgartirib bo'lmaydi.
2. *Compute → Instances → Create instance*:
   - **Image:** Canonical Ubuntu 24.04
   - **Shape:** *Ampere* → `VM.Standard.A1.Flex`, **1 OCPU, 6 GB RAM** (Always Free chegarasida)
   - **Networking:** "Assign a public IPv4 address" — yoqilgan
   - **SSH keys:** "Generate a key pair" → **private key ni yuklab oling** (`.key` fayl)
3. Instance yaratilgach **Public IP** ni yozib oling.
4. Portlarni oching: instance sahifasi → *Subnet* → *Security List* → **Add Ingress Rules**:
   - Source CIDR `0.0.0.0/0`, TCP, Destination port **80**
   - Source CIDR `0.0.0.0/0`, TCP, Destination port **443**

   (Server ichidagi firewall ni `install.sh` o'zi ochadi.)

> ⚠️ Oracle uzoq vaqt deyarli yuklamasiz turgan Always Free serverlarni qaytarib olishi mumkin. Akkauntni **Pay As You Go** ga o'tkazsangiz (bepul limit ichida baribir 0 so'm) bu xavf yo'qoladi. Har holda bot har kuni zaxira nusxani sizga yuboradi.

> "Out of capacity" xatosi chiqsa — bir necha soatdan keyin qayta urinib ko'ring yoki boshqa *Availability Domain* ni tanlang.

### Variant B — Google Cloud e2-micro

1. https://console.cloud.google.com → billing yoqing (karta tasdiqlash).
2. *Compute Engine → VM instances → Create*:
   - **Region:** `us-central1` (yoki us-west1 / us-east1 — **boshqasi pullik!**)
   - **Machine type:** `e2-micro`
   - **Boot disk:** Ubuntu 24.04, *Standard persistent disk*, 30 GB
   - **Firewall:** ✅ Allow HTTP traffic, ✅ Allow HTTPS traffic
3. *External IP* ni yozib oling. (Statik IP olmang — u pullik; IP o'zgarsa DuckDNS/domen yozuvini yangilaysiz.)

## 3-qadam. Domen (Mini App uchun HTTPS majburiy)

Telegram Mini App faqat `https://` manzilda ochiladi. SSL sertifikatni Caddy avtomatik oladi, sizdan faqat domen kerak.

**a) O'z domeningiz bo'lsa (masalan webspace.uz dagi saytingiz domeni)** — eng yaxshisi:
DirectAdmin → *DNS Management* → yangi **A** yozuv: nomi `bot`, qiymati — serveringiz Public IP si.
Natija: `bot.sizningdomen.uz` → .env da `DOMAIN=bot.sizningdomen.uz`.

**b) Domen bo'lmasa — bepul DuckDNS:**
https://www.duckdns.org → Google/GitHub bilan kiring → subdomen yarating (masalan `yaproqgosht`) → IP ga server IP sini yozing → sahifadagi **token** ni saqlang.
Natija: `yaproqgosht.duckdns.org`.

**c) Umuman hech narsa qilmasangiz** — skript `IP.sslip.io` dan foydalanadi (test uchun yetarli).

## 4-qadam. O'rnatish (bitta buyruq)

Kompyuteringizdan serverga ulaning:

```bash
# Oracle (Ubuntu foydalanuvchisi "ubuntu"):
ssh -i ~/Downloads/ssh-key.key ubuntu@SERVER_IP
# Google Cloud: konsoldagi "SSH" tugmasini bosish kifoya
```

Serverda:

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/uBakhtiyarov3/yaproqgosht.git
cd yaproqgosht
git checkout claude/zen-euler-bvolwi     # (main ga birlashtirilgach bu qator kerak emas)
bash deploy/install.sh
```

Skript so'raydi: **BOT_TOKEN**, **ADMIN_IDS** (`2076925033`), **DOMAIN**, **DUCKDNS_TOKEN** (bo'lsa).
Keyin o'zi: swap yaratadi, Docker o'rnatadi, portlarni ochadi, botni va HTTPS ni ishga tushiradi.

> Repo private bo'lsa, `git clone` paytida GitHub login + **Personal Access Token** so'raladi (GitHub → Settings → Developer settings → Tokens).

## 5-qadam. Tekshirish

1. Brauzerda `https://DOMAIN/health` → `{"ok": true, ...}` chiqishi kerak.
2. Botga `/start` → **👑 Menejer paneli** tugmasi chiqadi.
3. **📋 Menyu** (bot ichida) va **🍔 Mini ilovada buyurtma** — ikkalasidan test buyurtma bering.
4. Xodim qo'shing: *Menejer paneli → 👥 Xodimlar → ➕ Xodim qo'shish*.
5. *⚙️ Sozlamalar* da telefon, ish vaqti, yetkazish narxini kiriting.

## Kundalik ishlatish

| Vazifa | Buyruq (serverda, `yaproqgosht` papkasida) |
|---|---|
| Loglarni ko'rish | `sudo docker compose logs -f bot` |
| Qayta ishga tushirish | `sudo docker compose restart bot` |
| Kodni yangilash | `bash deploy/update.sh` |
| To'xtatish | `sudo docker compose down` |

- Server qayta yuklansa, bot **o'zi avtomatik ishga tushadi** (`restart: unless-stopped`).
- **Zaxira nusxa:** har kuni soat 04:00 da bosh menejerga `.zip` fayl keladi. Qo'lda olish: *Menejer paneli → 💾 Zaxira nusxa*.
- **Tiklash:** `sudo docker compose down` → zip ichidagi `data/` papkani loyiha papkasiga ko'chiring → `sudo docker compose up -d`.

---

## ❓ webspace.uz shared hosting (DirectAdmin) ga qo'ysa bo'ladimi?

**Qisqa javob: botning o'zini qo'yish tavsiya etilmaydi, lekin domeningizni ishlatsa bo'ladi (yuqoridagi 3a-qadam).**

Sabablari:
- Shared hosting sayt (PHP/WordPress) uchun mo'ljallangan: so'rov kelganda ishlaydigan dasturlar uchun. Bizning bot esa **doim ishlab turadigan jarayon**. Shared hostingda bunday jarayonlar odatda ma'lum vaqtdan keyin o'chirib yuboriladi va qoidalar bo'yicha ham taqiqlangan bo'ladi.
- Docker yo'q, root huquqi yo'q, ixtiyoriy port ochib bo'lmaydi.
- Fondagi ishlar ham to'xtab qoladi: rassilka, xodimlarga bildirishnoma, kunlik zaxira nusxa.

Tarifingizda **"Setup Python App"** va **SSH** bo'lsa ham, bot faqat webhook rejimida va ko'p cheklovlar bilan ishlaydi. Natijada vaqti-vaqti bilan xabarlar kechikadi yoki yo'qoladi — buyurtma boti uchun bu qabul qilinmaydi.

**Eng to'g'ri sxema:**
- 🌐 webspace.uz — kafe sayti va domen (`yaproqgosht.uz`);
- 🤖 Bepul Oracle/Google serveri — bot + Mini App, `bot.yaproqgosht.uz` subdomeni orqali (DirectAdmin → DNS → A yozuv).

Shunda domen ham o'zingizniki bo'ladi, bot ham barqaror va bepul ishlaydi.
