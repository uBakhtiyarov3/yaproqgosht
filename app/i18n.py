"""Mijozga ko'rinadigan matnlar: o'zbek (uz) va rus (ru). Xodim/menejer paneli o'zbekcha qoladi."""
from .catalog import norm_lang

T: dict[str, dict[str, str]] = {
    # ---------- umumiy / start ----------
    "choose_lang": {"uz": "🌐 Tilni tanlang / Выберите язык:", "ru": "🌐 Tilni tanlang / Выберите язык:"},
    "lang_saved": {"uz": "✅ Til: O'zbekcha", "ru": "✅ Язык: Русский"},
    "greet": {
        "uz": "👋 Assalomu alaykum, <b>{name}</b>!\n\n<b>Yaproq go'sht</b> — Burger • Coffee • Good mood 👑\n"
              "Mazali, tez va siz uchun!",
        "ru": "👋 Здравствуйте, <b>{name}</b>!\n\n<b>Yaproq go'sht</b> — Burger • Coffee • Good mood 👑\n"
              "Вкусно, быстро и для вас!",
    },
    "account_created": {"uz": "✅ Siz uchun shaxsiy akkaunt avtomatik ochildi.",
                        "ru": "✅ Для вас автоматически создан личный аккаунт."},
    "closed_now": {"uz": "⏸ Hozir yopiqmiz.", "ru": "⏸ Сейчас мы закрыты."},
    "opens_at": {"uz": "Ochilamiz: {when}. Hozir ham vaqtga buyurtma berishingiz mumkin ⏰",
                 "ru": "Откроемся: {when}. Уже сейчас можно оформить заказ ко времени ⏰"},
    "opens_short": {"uz": "Ochilamiz: {when}.", "ru": "Откроемся: {when}."},
    "how_order": {"uz": "Buyurtmani qanday berasiz? 👇", "ru": "Как будете заказывать? 👇"},
    "ways_mini": {"uz": "🍔 <b>Mini ilova</b> — rasmli menyu va qulay savat.",
                  "ru": "🍔 <b>Мини-приложение</b> — меню с фото и удобная корзина."},
    "ways_bot": {"uz": "📋 <b>Botning o'zida</b> — tugmalar orqali, shu chatning ichida.",
                 "ru": "📋 <b>Прямо в боте</b> — кнопками, в этом чате."},
    "start_mini_btn": {"uz": "🍔 Mini ilovada buyurtma berish", "ru": "🍔 Заказать в мини-приложении"},
    "start_bot_btn": {"uz": "📋 Botning o'zida buyurtma berish", "ru": "📋 Заказать прямо в боте"},
    "main_menu": {"uz": "🏠 Asosiy menyu", "ru": "🏠 Главное меню"},
    "open_mini_text": {"uz": "🍔 Mini ilovani ochish uchun pastdagi tugmani bosing 👇",
                       "ru": "🍔 Нажмите кнопку ниже, чтобы открыть мини-приложение 👇"},
    "open_mini_btn": {"uz": "🍔 Mini ilovani ochish", "ru": "🍔 Открыть мини-приложение"},
    "contact": {
        "uz": "📞 <b>Biz bilan bog'lanish</b>\n\nTelefon: {phone}\nIsh vaqti: {hours}\n{address}\n"
              "Savol va takliflaringizni shu yerga yozib qoldirishingiz ham mumkin.",
        "ru": "📞 <b>Связаться с нами</b>\n\nТелефон: {phone}\nВремя работы: {hours}\n{address}\n"
              "Вопросы и предложения можно написать прямо сюда.",
    },
    "phone_soon": {"uz": "tez orada qo'shiladi", "ru": "скоро добавим"},
    "address_line": {"uz": "📍 Manzil: {address}\n", "ru": "📍 Адрес: {address}\n"},
    "about": {
        "uz": "👑 <b>Yaproq go'sht</b>\n<i>Good Food · Good Mood</i>\n\n"
              "🌭 Hot-doglar · 🥖 Frensh hot-dog · 🍔 Burgerlar\n🌯 Donar va lavash · 🍟 Kartoshka fri · ☕ Kofe\n\n"
              "✅ Yangi ingredientlar\n☕ Issiq kofe\n😊 Yaxshi kayfiyat\n\nSee you soon! ❤️",
        "ru": "👑 <b>Yaproq go'sht</b>\n<i>Good Food · Good Mood</i>\n\n"
              "🌭 Хотдоги · 🥖 Френч хотдог · 🍔 Бургеры\n🌯 Донар и лаваш · 🍟 Картошка фри · ☕ Кофе\n\n"
              "✅ Свежие ингредиенты\n☕ Горячий кофе\n😊 Хорошее настроение\n\nSee you soon! ❤️",
    },
    "feedback_sent": {"uz": "✅ Xabaringiz yuborildi. Tez orada javob beramiz!",
                      "ru": "✅ Сообщение отправлено. Скоро ответим!"},
    "help": {
        "uz": "ℹ️ <b>Yordam</b>\n\n/start — botni qayta ishga tushirish\n/menu — menyu (bot ichida buyurtma)\n"
              "/cart — savat\n/orders — buyurtmalarim\n/lang — tilni o'zgartirish\n",
        "ru": "ℹ️ <b>Помощь</b>\n\n/start — перезапустить бота\n/menu — меню (заказ в боте)\n"
              "/cart — корзина\n/orders — мои заказы\n/lang — сменить язык\n",
    },
    "reply_from_cafe": {"uz": "💬 <b>Yaproq go'sht javobi:</b>", "ru": "💬 <b>Ответ Yaproq go'sht:</b>"},

    # ---------- reply tugmalar ----------
    "b_menu_mini": {"uz": "🍔 Mini ilovada buyurtma", "ru": "🍔 Заказ в мини-приложении"},
    "b_menu": {"uz": "📋 Menyu", "ru": "📋 Меню"},
    "b_cart": {"uz": "🛒 Savat", "ru": "🛒 Корзина"},
    "b_orders": {"uz": "📦 Buyurtmalarim", "ru": "📦 Мои заказы"},
    "b_contact": {"uz": "📞 Aloqa", "ru": "📞 Контакты"},
    "b_about": {"uz": "ℹ️ Biz haqimizda", "ru": "ℹ️ О нас"},
    "b_lang": {"uz": "🌐 Til / Язык", "ru": "🌐 Til / Язык"},
    "b_back": {"uz": "⬅️ Asosiy menyu", "ru": "⬅️ Главное меню"},

    # ---------- menyu ----------
    "menu_title": {"uz": "📋 <b>Menyu</b>\n\nKategoriyani tanlang 👇", "ru": "📋 <b>Меню</b>\n\nВыберите категорию 👇"},
    "choose_product": {"uz": "Mahsulotni tanlang 👇", "ru": "Выберите блюдо 👇"},
    "cat_empty": {"uz": "Bu kategoriya hozircha bo'sh.", "ru": "В этой категории пока пусто."},
    "back_cats": {"uz": "⬅️ Kategoriyalar", "ru": "⬅️ Категории"},
    "back": {"uz": "⬅️ Ortga", "ru": "⬅️ Назад"},
    "cart_btn": {"uz": "🛒 Savat ({count} ta · {sum})", "ru": "🛒 Корзина ({count} шт · {sum})"},
    "orders_btn": {"uz": "📦 Buyurtmalarim", "ru": "📦 Мои заказы"},
    "mini_inline": {"uz": "🍔 Mini ilovada ochish", "ru": "🍔 Открыть мини-приложение"},
    "from": {"uz": "dan ", "ru": "от "},
    "chosen": {"uz": "Tanlandi", "ru": "Выбрано"},
    "pcs": {"uz": "{n} ta", "ru": "{n} шт"},
    "add_btn": {"uz": "🛒 Savatga qo'shish · {sum}", "ru": "🛒 В корзину · {sum}"},
    "added": {"uz": "✅ <b>{item}</b> savatga qo'shildi!", "ru": "✅ <b>{item}</b> добавлен в корзину!"},
    "added_toast": {"uz": "✅ Savatga qo'shildi", "ru": "✅ Добавлено в корзину"},
    "unavailable": {"uz": "Bu mahsulot hozir mavjud emas", "ru": "Это блюдо сейчас недоступно"},
    "qty_limit": {"uz": "1 dan 50 tagacha", "ru": "От 1 до 50"},

    # ---------- savat ----------
    "cart_empty": {"uz": "🛒 Savatingiz bo'sh.\n\nMenyudan mahsulot tanlang 👇",
                   "ru": "🛒 Корзина пуста.\n\nВыберите что-нибудь в меню 👇"},
    "to_menu": {"uz": "📋 Menyuga o'tish", "ru": "📋 Перейти в меню"},
    "cart_title": {"uz": "🛒 <b>Savat</b>", "ru": "🛒 <b>Корзина</b>"},
    "items_sum": {"uz": "Mahsulotlar", "ru": "Товары"},
    "delivery": {"uz": "Yetkazib berish", "ru": "Доставка"},
    "free": {"uz": "bepul", "ru": "бесплатно"},
    "discount": {"uz": "Chegirma", "ru": "Скидка"},
    "total": {"uz": "Jami", "ru": "Итого"},
    "min_order_warn": {"uz": "⚠️ Yetkazib berish uchun minimal buyurtma: {min}.",
                       "ru": "⚠️ Минимальный заказ на доставку: {min}."},
    "clear": {"uz": "🗑 Tozalash", "ru": "🗑 Очистить"},
    "menu_btn": {"uz": "📋 Menyu", "ru": "📋 Меню"},
    "checkout_btn": {"uz": "✅ Buyurtma berish · {sum}", "ru": "✅ Оформить · {sum}"},
    "cart_cleared": {"uz": "🗑 Savat tozalandi.", "ru": "🗑 Корзина очищена."},

    # ---------- rasmiylashtirish ----------
    "co_cancel": {"uz": "❌ Buyurtmani bekor qilish", "ru": "❌ Отменить оформление"},
    "co_skip": {"uz": "➡️ O'tkazib yuborish", "ru": "➡️ Пропустить"},
    "co_title": {"uz": "📝 <b>Buyurtmani rasmiylashtirish</b>", "ru": "📝 <b>Оформление заказа</b>"},
    "ask_type": {"uz": "Buyurtmani qanday olasiz?", "ru": "Как получите заказ?"},
    "type_delivery": {"uz": "🛵 Yetkazib berish", "ru": "🛵 Доставка"},
    "type_pickup": {"uz": "🏃 Olib ketish", "ru": "🏃 Самовывоз"},
    "ask_name": {"uz": "👤 Qabul qiluvchining <b>ismini</b> yozing:", "ru": "👤 Напишите <b>имя</b> получателя:"},
    "bad_name": {"uz": "Ism 2 dan 64 belgigacha bo'lsin. Qaytadan yozing:",
                 "ru": "Имя должно быть от 2 до 64 символов. Напишите ещё раз:"},
    "ask_phone": {"uz": "📞 <b>Telefon raqamingizni</b> yuboring.\n\nPastdagi tugmani bosing yoki yozing: "
                        "<code>+998 90 123 45 67</code>",
                  "ru": "📞 Отправьте <b>номер телефона</b>.\n\nНажмите кнопку ниже или напишите: "
                        "<code>+998 90 123 45 67</code>"},
    "send_phone_btn": {"uz": "📱 Raqamimni yuborish", "ru": "📱 Отправить мой номер"},
    "bad_phone": {"uz": "❗️ Raqam noto'g'ri. Masalan: <code>+998 90 123 45 67</code>",
                  "ru": "❗️ Неверный номер. Например: <code>+998 90 123 45 67</code>"},
    "ask_address": {"uz": "📍 <b>Yetkazish manzilini</b> yozing (ko'cha, uy, mo'ljal) yoki joylashuvingizni yuboring:",
                    "ru": "📍 Напишите <b>адрес доставки</b> (улица, дом, ориентир) или отправьте геолокацию:"},
    "send_location_btn": {"uz": "📍 Joylashuvni yuborish", "ru": "📍 Отправить геолокацию"},
    "location_ok": {"uz": "Joylashuv qabul qilindi ✅", "ru": "Геолокация получена ✅"},
    "location_label": {"uz": "📍 Lokatsiya", "ru": "📍 Геолокация"},
    "bad_address": {"uz": "❗️ Manzilni to'liqroq yozing (kamida 5 belgi):",
                    "ru": "❗️ Напишите адрес подробнее (минимум 5 символов):"},
    "ask_time": {"uz": "⏰ <b>Qachonga tayyorlaylik?</b>", "ru": "⏰ <b>К какому времени приготовить?</b>"},
    "asap": {"uz": "⚡ Imkon qadar tez", "ru": "⚡ Как можно скорее"},
    "today": {"uz": "📅 Bugun", "ru": "📅 Сегодня"},
    "tomorrow": {"uz": "📅 Ertaga", "ru": "📅 Завтра"},
    "pick_time": {"uz": "🕒 Vaqtni tanlang ({day}):", "ru": "🕒 Выберите время ({day}):"},
    "no_slots": {"uz": "Afsuski, yaqin kunlarda bo'sh vaqt yo'q. Keyinroq urinib ko'ring.",
                 "ru": "К сожалению, свободного времени в ближайшие дни нет. Попробуйте позже."},
    "ask_comment": {"uz": "💬 <b>Izoh</b> (ixtiyoriy)\n\nManzil bo'yicha (podyezd, qavat, domofon) yoki "
                          "ovqat bo'yicha (piyozsiz, achchiqroq, sousni alohida...) istaklaringizni yozing.",
                    "ru": "💬 <b>Комментарий</b> (необязательно)\n\nПо адресу (подъезд, этаж, домофон) или "
                          "по блюдам (без лука, поострее, соус отдельно...)."},
    "ask_promo": {"uz": "🎁 <b>Promo-kodingiz bormi?</b>\nKodni yozing yoki o'tkazib yuboring.",
                  "ru": "🎁 <b>Есть промокод?</b>\nНапишите его или пропустите."},
    "promo_ok": {"uz": "✅ Promo-kod qo'llandi: <b>{code}</b> — {label}", "ru": "✅ Промокод применён: <b>{code}</b> — {label}"},
    "ask_payment": {"uz": "💳 <b>To'lov usulini tanlang:</b>", "ru": "💳 <b>Выберите способ оплаты:</b>"},
    "payment_hint": {"uz": "Hozircha naqd to'lov mavjud. Karta orqali to'lov tez kunda qo'shiladi.",
                     "ru": "Пока доступна оплата наличными. Оплата картой скоро появится."},
    "pay_cash": {"uz": "💵 Naqd", "ru": "💵 Наличные"},
    "pay_card": {"uz": "💳 Karta · tez kunda", "ru": "💳 Карта · скоро"},
    "pay_card_alert": {"uz": "💳 Karta orqali to'lov tez kunda ishga tushadi! Hozircha naqd to'lovni tanlang.",
                       "ru": "💳 Оплата картой скоро появится! Пока выберите наличные."},
    "check_title": {"uz": "🧾 <b>Buyurtmani tekshiring</b>", "ru": "🧾 <b>Проверьте заказ</b>"},
    "payment": {"uz": "To'lov", "ru": "Оплата"},
    "confirm_btn": {"uz": "✅ Tasdiqlash", "ru": "✅ Подтвердить"},
    "refill_btn": {"uz": "✏️ Qaytadan to'ldirish", "ru": "✏️ Заполнить заново"},
    "cancel_btn": {"uz": "❌ Bekor qilish", "ru": "❌ Отмена"},
    "co_cancelled": {"uz": "Rasmiylashtirish bekor qilindi. Savatingiz saqlanib qoldi 🛒",
                     "ru": "Оформление отменено. Корзина сохранена 🛒"},
    "form_stale": {"uz": "Bu forma eskirgan. Savatdan qaytadan rasmiylashtiring.",
                   "ru": "Эта форма устарела. Оформите заказ заново из корзины."},
    "order_placed": {"uz": "🎉 <b>Buyurtmangiz qabul qilindi!</b>\n\nBuyurtma ID: <code>{code}</code>\nJami: <b>{total}</b>\n\n"
                           "Holat o'zgarganda shu yerda xabar beramiz.",
                     "ru": "🎉 <b>Заказ принят!</b>\n\nНомер заказа: <code>{code}</code>\nИтого: <b>{total}</b>\n\n"
                           "Сообщим здесь, когда статус изменится."},
    "order_sent_toast": {"uz": "✅ Buyurtma yuborildi!", "ru": "✅ Заказ отправлен!"},
    "thanks": {"uz": "Rahmat! 😊", "ru": "Спасибо! 😊"},
    "pickup_from": {"uz": "🏃 Olib ketish: {address}", "ru": "🏃 Самовывоз: {address}"},
    "pickup_cafe": {"uz": "kafedan", "ru": "из кафе"},
    "when_asap": {"uz": "⚡ Imkon qadar tez", "ru": "⚡ Как можно скорее"},
    "when_at": {"uz": "⏰ Vaqtga: {when}", "ru": "⏰ Ко времени: {when}"},

    # ---------- buyurtmalar ----------
    "no_orders": {"uz": "Sizda hali buyurtmalar yo'q. Keling, birinchisini beramiz! 🍔",
                  "ru": "У вас пока нет заказов. Давайте сделаем первый! 🍔"},
    "orders_title": {"uz": "📦 <b>Buyurtmalarim</b>\n\nBatafsil ko'rish uchun tanlang:",
                     "ru": "📦 <b>Мои заказы</b>\n\nВыберите для подробностей:"},
    "order_title": {"uz": "🧾 <b>Buyurtma</b> <code>{code}</code>", "ru": "🧾 <b>Заказ</b> <code>{code}</code>"},
    "reason": {"uz": "Sabab: {reason}", "ru": "Причина: {reason}"},
    "refresh": {"uz": "🔄 Yangilash", "ru": "🔄 Обновить"},
    "refreshed": {"uz": "🔄 Yangilandi", "ru": "🔄 Обновлено"},
    "cancel_order_btn": {"uz": "❌ Buyurtmani bekor qilish", "ru": "❌ Отменить заказ"},
    "repeat_btn": {"uz": "🔁 Qayta buyurtma berish", "ru": "🔁 Повторить заказ"},
    "back_orders": {"uz": "⬅️ Buyurtmalarim", "ru": "⬅️ Мои заказы"},
    "order_not_found": {"uz": "Buyurtma topilmadi", "ru": "Заказ не найден"},
    "cancel_not_allowed": {"uz": "Buyurtma allaqachon qabul qilingan — bekor qilish uchun kafe bilan bog'laning.",
                           "ru": "Заказ уже принят — для отмены свяжитесь с кафе."},
    "order_cancelled_toast": {"uz": "Buyurtma bekor qilindi", "ru": "Заказ отменён"},
    "repeat_added": {"uz": "🔁 Oldingi buyurtma savatga qo'shildi (narxlar joriy menyu bo'yicha).",
                     "ru": "🔁 Прошлый заказ добавлен в корзину (по текущим ценам)."},
    "repeat_none": {"uz": "Afsuski, bu buyurtmadagi mahsulotlar hozir mavjud emas.",
                    "ru": "К сожалению, блюд из этого заказа сейчас нет."},
    "your_rating": {"uz": "Sizning bahoingiz: {stars}", "ru": "Ваша оценка: {stars}"},
    "rate_btn": {"uz": "⭐ Baholash", "ru": "⭐ Оценить"},

    # ---------- bildirishnomalar ----------
    "sent_new": {"uz": "🧾 Buyurtmangiz <code>{code}</code> qabul qilish uchun yuborildi!\n\n"
                       "Holat o'zgarganda sizga shu yerda xabar beramiz.",
                 "ru": "🧾 Ваш заказ <code>{code}</code> отправлен!\n\nСообщим здесь, когда статус изменится."},
    "track_btn": {"uz": "📦 Buyurtmani kuzatish", "ru": "📦 Отследить заказ"},
    "st_accepted": {"uz": "✅ Buyurtmangiz <code>{code}</code> qabul qilindi!",
                    "ru": "✅ Ваш заказ <code>{code}</code> принят!"},
    "st_cooking": {"uz": "👨‍🍳 Buyurtmangiz <code>{code}</code> tayyorlanmoqda...",
                   "ru": "👨‍🍳 Ваш заказ <code>{code}</code> готовится..."},
    "st_delivering": {"uz": "🛵 Buyurtmangiz <code>{code}</code> yo'lda! Kuryer tez orada yetib boradi.",
                      "ru": "🛵 Ваш заказ <code>{code}</code> в пути! Курьер скоро будет."},
    "st_delivering_pickup": {"uz": "🛍 Buyurtmangiz <code>{code}</code> tayyor! Olib ketishingiz mumkin.{address}",
                             "ru": "🛍 Ваш заказ <code>{code}</code> готов! Можно забирать.{address}"},
    "st_delivered": {"uz": "🎉 Buyurtmangiz <code>{code}</code> yetkazildi. Yoqimli ishtaha! 😊",
                     "ru": "🎉 Ваш заказ <code>{code}</code> доставлен. Приятного аппетита! 😊"},
    "st_delivered_pickup": {"uz": "🎉 Buyurtmangiz <code>{code}</code> berildi. Yoqimli ishtaha! 😊",
                            "ru": "🎉 Ваш заказ <code>{code}</code> выдан. Приятного аппетита! 😊"},
    "st_cancelled": {"uz": "❌ Afsuski, buyurtmangiz <code>{code}</code> bekor qilindi.{reason}\n"
                           "Savollar bo'lsa, biz bilan bog'laning.",
                     "ru": "❌ К сожалению, ваш заказ <code>{code}</code> отменён.{reason}\nЕсли есть вопросы — свяжитесь с нами."},

    # ---------- baholash ----------
    "rate_ask": {"uz": "⭐ <b>Buyurtmani baholang!</b>\nFikringiz biz uchun juda muhim.",
                 "ru": "⭐ <b>Оцените заказ!</b>\nВаше мнение очень важно для нас."},
    "rate_thanks": {"uz": "Rahmat! 🙏 {stars}\n\nIzoh qoldirasizmi? Yozing yoki «O'tkazib yuborish»ni bosing.",
                    "ru": "Спасибо! 🙏 {stars}\n\nОставите комментарий? Напишите или нажмите «Пропустить»."},
    "review_saved": {"uz": "✅ Fikringiz uchun rahmat! Sizni yana kutamiz 😊",
                     "ru": "✅ Спасибо за отзыв! Ждём вас снова 😊"},
    "already_rated": {"uz": "Bu buyurtma allaqachon baholangan", "ru": "Этот заказ уже оценён"},
    "rate_not_ready": {"uz": "Buyurtma hali yakunlanmagan", "ru": "Заказ ещё не завершён"},

    # ---------- holatlar (mijoz uchun) ----------
    "s_new": {"uz": "🕐 Tasdiqlash kutilmoqda", "ru": "🕐 Ожидает подтверждения"},
    "s_accepted": {"uz": "✅ Qabul qilindi", "ru": "✅ Принят"},
    "s_cooking": {"uz": "👨‍🍳 Tayyorlanmoqda", "ru": "👨‍🍳 Готовится"},
    "s_delivering": {"uz": "🛵 Yetkazilmoqda", "ru": "🛵 В пути"},
    "s_delivering_pickup": {"uz": "🛍 Tayyor — olib keting", "ru": "🛍 Готов — можно забрать"},
    "s_delivered": {"uz": "🎉 Yetkazildi", "ru": "🎉 Доставлен"},
    "s_delivered_pickup": {"uz": "🎉 Berildi", "ru": "🎉 Выдан"},
    "s_cancelled": {"uz": "❌ Bekor qilindi", "ru": "❌ Отменён"},
    "step_new": {"uz": "Buyurtma berildi", "ru": "Заказ оформлен"},

    # ---------- xatolar (OrderError) ----------
    "e_empty_cart": {"uz": "Savat bo'sh", "ru": "Корзина пуста"},
    "e_too_many": {"uz": "Savatda juda ko'p mahsulot", "ru": "Слишком много позиций в корзине"},
    "e_cart": {"uz": "Savatda xato bor", "ru": "Ошибка в корзине"},
    "e_qty": {"uz": "Mahsulot soni 1 dan 50 gacha bo'lishi kerak", "ru": "Количество — от 1 до 50"},
    "e_unavailable": {"uz": "Savatdagi ba'zi mahsulotlar endi mavjud emas. Savatni yangilang.",
                      "ru": "Некоторых блюд из корзины больше нет. Обновите корзину."},
    "e_variant": {"uz": "Mahsulot o'lchami topilmadi. Savatni yangilang.",
                  "ru": "Размер блюда не найден. Обновите корзину."},
    "e_closed": {"uz": "Hozir yopiqmiz — vaqtni tanlab buyurtma bering.{next}",
                 "ru": "Сейчас мы закрыты — выберите время заказа.{next}"},
    "e_closed_full": {"uz": "Hozir buyurtma qabul qilinmayapti.", "ru": "Сейчас заказы не принимаются."},
    "e_name": {"uz": "Qabul qiluvchi ismini kiriting", "ru": "Укажите имя получателя"},
    "e_phone": {"uz": "Telefon raqam noto'g'ri. Format: +998 90 123 45 67",
                "ru": "Неверный телефон. Формат: +998 90 123 45 67"},
    "e_address": {"uz": "Manzilni to'liqroq kiriting", "ru": "Укажите адрес подробнее"},
    "e_card": {"uz": "Karta orqali to'lov tez kunda ishga tushadi. Hozircha naqd to'lovni tanlang.",
               "ru": "Оплата картой скоро появится. Пока выберите наличные."},
    "e_payment": {"uz": "To'lov usulini tanlang", "ru": "Выберите способ оплаты"},
    "e_min_order": {"uz": "Yetkazib berish uchun minimal buyurtma: {min}", "ru": "Минимальный заказ на доставку: {min}"},
    "e_cooldown": {"uz": "Iltimos, biroz kuting va qayta urinib ko'ring", "ru": "Подождите немного и попробуйте снова"},
    "e_type": {"uz": "Bu buyurtma turi hozir mavjud emas", "ru": "Этот способ получения сейчас недоступен"},
    "e_slot": {"uz": "Tanlangan vaqt endi mavjud emas. Boshqa vaqtni tanlang.",
               "ru": "Выбранное время недоступно. Выберите другое."},
    "e_promo_not_found": {"uz": "Bunday promo-kod topilmadi", "ru": "Промокод не найден"},
    "e_promo_inactive": {"uz": "Bu promo-kod faol emas", "ru": "Промокод неактивен"},
    "e_promo_not_started": {"uz": "Bu promo-kod hali boshlanmagan", "ru": "Промокод ещё не действует"},
    "e_promo_expired": {"uz": "Bu promo-kodning muddati tugagan", "ru": "Срок действия промокода истёк"},
    "e_promo_min": {"uz": "Bu promo-kod {min} dan ortiq buyurtmaga amal qiladi",
                    "ru": "Промокод действует на заказ от {min}"},
    "e_promo_limit": {"uz": "Bu promo-kod limiti tugagan", "ru": "Лимит использования промокода исчерпан"},
    "e_promo_user_limit": {"uz": "Siz bu promo-koddan allaqachon foydalangansiz", "ru": "Вы уже использовали этот промокод"},
    "e_promo_first": {"uz": "Bu promo-kod faqat birinchi buyurtma uchun", "ru": "Промокод только для первого заказа"},
    "e_promo_pickup": {"uz": "Bu promo-kod faqat yetkazib berish uchun", "ru": "Промокод только для доставки"},

    # ---------- promo turlari ----------
    "promo_percent": {"uz": "-{value}% chegirma", "ru": "скидка {value}%"},
    "promo_fixed": {"uz": "-{value} chegirma", "ru": "скидка {value}"},
    "promo_free_delivery": {"uz": "bepul yetkazib berish", "ru": "бесплатная доставка"},
}

# ---------- Mini App matnlari (w_ prefiksi bilan T ga qo'shiladi) ----------
W: dict[str, dict[str, str]] = {
    "search": {"uz": "Taom qidirish...", "ru": "Поиск блюд..."},
    "searchEmpty": {"uz": "Hech narsa topilmadi", "ru": "Ничего не найдено"},
    "perk1": {"uz": "🍔 Yangi ingredientlar", "ru": "🍔 Свежие ингредиенты"},
    "perk2": {"uz": "☕ Issiq kofe", "ru": "☕ Горячий кофе"},
    "perk3": {"uz": "😊 Yaxshi kayfiyat", "ru": "😊 Хорошее настроение"},
    "tabMenu": {"uz": "Menyu", "ru": "Меню"},
    "tabOrders": {"uz": "Buyurtmalar", "ru": "Заказы"},
    "cart": {"uz": "Savat", "ru": "Корзина"},
    "clear": {"uz": "Tozalash", "ru": "Очистить"},
    "clearConfirm": {"uz": "Savatni tozalaysizmi?", "ru": "Очистить корзину?"},
    "checkout": {"uz": "Rasmiylashtirish", "ru": "Оформить заказ"},
    "checkoutTitle": {"uz": "Buyurtma berish", "ru": "Оформление"},
    "closed": {"uz": "⏸ Hozir yopiqmiz.", "ru": "⏸ Сейчас мы закрыты."},
    "opensAt": {"uz": "Ochilamiz: {time}.", "ru": "Откроемся: {time}."},
    "laterOnly": {"uz": "Vaqtga buyurtma berishingiz mumkin ⏰", "ru": "Можно заказать ко времени ⏰"},
    "notAccepting": {"uz": "⏸ Hozir buyurtma qabul qilinmayapti", "ru": "⏸ Сейчас заказы не принимаются"},
    "from": {"uz": "dan", "ru": "от"},
    "add": {"uz": "Qo'shish", "ru": "Добавить"},
    "added": {"uz": "✓ Savatga qo'shildi", "ru": "✓ Добавлено в корзину"},
    "emptyMenu": {"uz": "Menyu hozircha bo'sh", "ru": "Меню пока пусто"},
    "emptyCart": {"uz": "Savatingiz bo'sh", "ru": "Корзина пуста"},
    "toMenu": {"uz": "Menyuga o'tish", "ru": "Перейти в меню"},
    "items": {"uz": "Mahsulotlar", "ru": "Товары"},
    "deliveryFee": {"uz": "Yetkazib berish", "ru": "Доставка"},
    "free": {"uz": "bepul", "ru": "бесплатно"},
    "discount": {"uz": "Chegirma", "ru": "Скидка"},
    "total": {"uz": "Jami", "ru": "Итого"},
    "minOrder": {"uz": "Yetkazib berish uchun minimal buyurtma: {sum}. Yana {left} qo'shing.",
                 "ru": "Минимальный заказ на доставку: {sum}. Добавьте ещё {left}."},
    "delivery": {"uz": "🛵 Yetkazib berish", "ru": "🛵 Доставка"},
    "pickup": {"uz": "🏃 Olib ketish", "ru": "🏃 Самовывоз"},
    "pickupFrom": {"uz": "🏃 Buyurtmani kafedan olib ketasiz", "ru": "🏃 Заберёте заказ в кафе"},
    "name": {"uz": "Qabul qiluvchi ismi", "ru": "Имя получателя"},
    "namePh": {"uz": "Ismingiz", "ru": "Ваше имя"},
    "phone": {"uz": "Telefon raqam", "ru": "Телефон"},
    "address": {"uz": "Yetkazish manzili", "ru": "Адрес доставки"},
    "addressPh": {"uz": "Shahar, ko'cha, uy, xonadon, mo'ljal", "ru": "Город, улица, дом, квартира, ориентир"},
    "geo": {"uz": "📍 Joriy joylashuvimni qo'shish", "ru": "📍 Добавить мою геолокацию"},
    "geoLoading": {"uz": "⏳ Aniqlanmoqda...", "ru": "⏳ Определяем..."},
    "geoAdded": {"uz": "✓ Joylashuv qo'shildi", "ru": "✓ Геолокация добавлена"},
    "geoFail": {"uz": "Joylashuvni aniqlab bo'lmadi", "ru": "Не удалось определить геолокацию"},
    "when": {"uz": "Qachonga?", "ru": "Когда?"},
    "asap": {"uz": "⚡ Imkon qadar tez", "ru": "⚡ Как можно скорее"},
    "later": {"uz": "⏰ Vaqtni tanlash", "ru": "⏰ Ко времени"},
    "today": {"uz": "Bugun", "ru": "Сегодня"},
    "tomorrow": {"uz": "Ertaga", "ru": "Завтра"},
    "noSlots": {"uz": "Yaqin kunlarda bo'sh vaqt yo'q", "ru": "Нет свободного времени"},
    "comment": {"uz": "Izoh (ixtiyoriy)", "ru": "Комментарий (необязательно)"},
    "commentPh": {"uz": "Manzil bo'yicha (podyezd, qavat, domofon) yoki ovqat bo'yicha (piyozsiz, achchiqroq...)",
                  "ru": "По адресу (подъезд, этаж, домофон) или по блюдам (без лука, поострее...)"},
    "promo": {"uz": "Promo-kod", "ru": "Промокод"},
    "promoPh": {"uz": "Kodni kiriting", "ru": "Введите код"},
    "apply": {"uz": "Qo'llash", "ru": "Применить"},
    "remove": {"uz": "Olib tashlash", "ru": "Убрать"},
    "payment": {"uz": "To'lov usuli", "ru": "Способ оплаты"},
    "cash": {"uz": "💵 Naqd", "ru": "💵 Наличные"},
    "cashSub": {"uz": "Qabul qilganda to'lash", "ru": "Оплата при получении"},
    "card": {"uz": "💳 Karta", "ru": "💳 Карта"},
    "soon": {"uz": "Tez kunda", "ru": "Скоро"},
    "cardSoon": {"uz": "💳 Karta orqali to'lov tez kunda!", "ru": "💳 Оплата картой скоро!"},
    "confirm": {"uz": "Buyurtmani tasdiqlash", "ru": "Подтвердить заказ"},
    "sending": {"uz": "Yuborilmoqda...", "ru": "Отправляем..."},
    "errName": {"uz": "Qabul qiluvchi ismini kiriting", "ru": "Укажите имя получателя"},
    "errPhone": {"uz": "Telefon raqamni to'liq kiriting: +998 90 123 45 67", "ru": "Введите номер полностью: +998 90 123 45 67"},
    "errAddress": {"uz": "Yetkazish manzilini to'liqroq kiriting", "ru": "Укажите адрес подробнее"},
    "errTime": {"uz": "Vaqtni tanlang", "ru": "Выберите время"},
    "placed": {"uz": "Buyurtma qabul qilindi!", "ru": "Заказ принят!"},
    "orderId": {"uz": "Buyurtma ID:", "ru": "Номер заказа:"},
    "placedSub": {"uz": "Holat o'zgarishi haqida botda xabar beramiz.", "ru": "Сообщим в боте, когда статус изменится."},
    "track": {"uz": "Buyurtmani kuzatish", "ru": "Отследить заказ"},
    "backToMenu": {"uz": "Menyuga qaytish", "ru": "Вернуться в меню"},
    "myOrders": {"uz": "Buyurtmalarim", "ru": "Мои заказы"},
    "noOrders": {"uz": "Hali buyurtmalar yo'q", "ru": "Заказов пока нет"},
    "orderNow": {"uz": "Buyurtma berish", "ru": "Сделать заказ"},
    "ordersBack": {"uz": "← Buyurtmalar", "ru": "← Заказы"},
    "pcs": {"uz": "ta", "ru": "шт"},
    "stepNew": {"uz": "Buyurtma berildi", "ru": "Заказ оформлен"},
    "cancelOrder": {"uz": "Buyurtmani bekor qilish", "ru": "Отменить заказ"},
    "cancelConfirm": {"uz": "Buyurtmani bekor qilasizmi?", "ru": "Отменить заказ?"},
    "cancelledToast": {"uz": "Buyurtma bekor qilindi", "ru": "Заказ отменён"},
    "cancelledTitle": {"uz": "❌ Buyurtma bekor qilindi", "ru": "❌ Заказ отменён"},
    "reason": {"uz": "Sabab", "ru": "Причина"},
    "rateTitle": {"uz": "Buyurtmani baholang", "ru": "Оцените заказ"},
    "ratePh": {"uz": "Izoh (ixtiyoriy)", "ru": "Комментарий (необязательно)"},
    "rateSend": {"uz": "Yuborish", "ru": "Отправить"},
    "rateThanks": {"uz": "Rahmat! Fikringiz biz uchun muhim 🙏", "ru": "Спасибо за отзыв! 🙏"},
    "yourRating": {"uz": "Sizning bahoingiz", "ru": "Ваша оценка"},
    "questions": {"uz": "Savollar uchun", "ru": "По вопросам"},
    "retry": {"uz": "Qayta urinish", "ru": "Повторить"},
    "openInTg": {"uz": "Iltimos, ushbu ilovani Telegram bot orqali oching.", "ru": "Пожалуйста, откройте приложение через Telegram-бота."},
    "network": {"uz": "Internet aloqasini tekshiring", "ru": "Проверьте интернет-соединение"},
}
T.update({f"w_{k}": v for k, v in W.items()})


# Admin paneldan tahrirlangan matnlar: {(kalit, til): matn}. Saqlanganda darhol yangilanadi.
OVERRIDES: dict[tuple[str, str], str] = {}


def set_overrides(rows: list[dict]) -> None:
    OVERRIDES.clear()
    OVERRIDES.update({(r["key"], r["lang"]): r["value"] for r in rows if r["key"] in T})


def default_text(key: str, lang: str) -> str:
    entry = T.get(key) or {}
    return entry.get(lang) or entry.get("uz") or key


def t(key: str, lang: str = "uz", **kw) -> str:
    if key not in T:
        return key
    lang = norm_lang(lang)
    text = OVERRIDES.get((key, lang)) or default_text(key, lang)
    if not kw:
        return text
    try:
        return text.format(**kw)
    except (KeyError, IndexError, ValueError):
        # tahrirlangan matnda xato bo'lsa — asl matn (bot to'xtab qolmasin)
        return default_text(key, lang).format(**kw)


def placeholders(text: str) -> set[str]:
    import string

    try:
        return {name for _, name, _, _ in string.Formatter().parse(text) if name}
    except ValueError:
        return {"<xato>"}


def web_texts(lang: str) -> dict[str, str]:
    """Mini App uchun barcha matnlar (tahrirlanganlari bilan)."""
    return {k[2:]: t(k, lang) for k in T if k.startswith("w_")}


def both(key: str) -> set[str]:
    """Reply tugma matnini ikkala tilda (handler filtrlari uchun), tahrirlanganlari ham."""
    return {t(key, "uz"), t(key, "ru"), *T[key].values()}


def money_l(amount: int | float, lang: str = "uz") -> str:
    s = f"{int(amount):,}".replace(",", " ")
    return f"{s} сум" if norm_lang(lang) == "ru" else f"{s} so'm"


def status_text(status: str, order_type: str, lang: str) -> str:
    if order_type == "pickup" and status in ("delivering", "delivered"):
        return t(f"s_{status}_pickup", lang)
    return t(f"s_{status}", lang)


def stars(n: int) -> str:
    return "⭐" * int(n)
