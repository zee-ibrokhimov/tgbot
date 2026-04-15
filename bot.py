import logging
import json
import os
from datetime import datetime, date
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── CONFIG ───────────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "YOUR_TELEGRAM_ID_HERE"))
BOOKINGS_FILE = "bookings.json"

# ─── PRODUCTS ─────────────────────────────────────────────────────────────────
PRODUCTS = {
    "earpiece": {
        "name_ru": "🎧 Микронаушник",
        "name_en": "🎧 Micro Earpiece",
        "price_per_day": 20,
        "deposit": 80,
        "currency": "€",
        "desc_ru": "Невидимый микронаушник для конференций и выступлений",
        "desc_en": "Invisible micro earpiece for conferences and speeches",
    },
    "earpiece_camera": {
        "name_ru": "📷 Микронаушник + Камера",
        "name_en": "📷 Micro Earpiece + Camera",
        "price_per_day": 40,
        "deposit": 160,
        "currency": "€",
        "desc_ru": "Микронаушник с миниатюрной скрытой камерой",
        "desc_en": "Micro earpiece with miniature hidden camera",
    },
}

FAQ = {
    "ru": [
        ("Как работает наушник?", "Это миниатюрное bluetooth-устройство, практически невидимое. Вы получаете звук через смартфон."),
        ("Как оплатить?", "Оплата по договорённости — наличными или переводом. Депозит возвращается после аренды."),
        ("Доставка?", "Самовывоз или курьер — обсудим при подтверждении заявки."),
        ("Что если сломается?", "Депозит покрывает ущерб. Мы рассматриваем каждый случай индивидуально."),
    ],
    "en": [
        ("How does the earpiece work?", "It's a tiny bluetooth device, almost invisible. You receive sound via your smartphone."),
        ("How to pay?", "Payment by agreement — cash or bank transfer. Deposit is returned after rental."),
        ("Delivery?", "Pickup or courier — we'll discuss when confirming your booking."),
        ("What if it breaks?", "The deposit covers damage. We review each case individually."),
    ],
}

# ─── CONVERSATION STATES ──────────────────────────────────────────────────────
(
    LANG, MAIN_MENU,
    BOOKING_PRODUCT, BOOKING_NAME, BOOKING_PHONE,
    BOOKING_START_DATE, BOOKING_END_DATE, BOOKING_CONFIRM,
    FAQ_VIEW
) = range(9)

# ─── BOOKINGS STORAGE ─────────────────────────────────────────────────────────
def load_bookings():
    if os.path.exists(BOOKINGS_FILE):
        with open(BOOKINGS_FILE, "r") as f:
            return json.load(f)
    return []

def save_bookings(bookings):
    with open(BOOKINGS_FILE, "w") as f:
        json.dump(bookings, f, ensure_ascii=False, indent=2)

def get_booked_dates():
    bookings = load_bookings()
    booked = set()
    for b in bookings:
        if b.get("status") == "confirmed":
            try:
                start = datetime.strptime(b["start_date"], "%d.%m.%Y").date()
                end = datetime.strptime(b["end_date"], "%d.%m.%Y").date()
                d = start
                while d <= end:
                    booked.add(d.strftime("%d.%m.%Y"))
                    d = date.fromordinal(d.toordinal() + 1)
            except:
                pass
    return booked

def is_available(start_str, end_str):
    booked = get_booked_dates()
    try:
        start = datetime.strptime(start_str, "%d.%m.%Y").date()
        end = datetime.strptime(end_str, "%d.%m.%Y").date()
        if start > end:
            return False, "start_after_end"
        d = start
        while d <= end:
            if d.strftime("%d.%m.%Y") in booked:
                return False, d.strftime("%d.%m.%Y")
            d = date.fromordinal(d.toordinal() + 1)
        return True, None
    except:
        return False, "invalid_date"

def calc_price(product_key, start_str, end_str):
    start = datetime.strptime(start_str, "%d.%m.%Y").date()
    end = datetime.strptime(end_str, "%d.%m.%Y").date()
    days = (end - start).days + 1
    p = PRODUCTS[product_key]
    rental = days * p["price_per_day"]
    deposit = p["deposit"]
    return days, rental, deposit

# ─── TEXTS ────────────────────────────────────────────────────────────────────
def t(lang, key, **kw):
    texts = {
        "ru": {
            "welcome": "👋 Привет! Я бот для аренды профессионального оборудования для выступлений.\n\nВыберите язык:",
            "main_menu": "📋 Главное меню",
            "btn_products": "🛍 Продукты и цены",
            "btn_book": "📅 Забронировать",
            "btn_availability": "📆 Проверить доступность",
            "btn_faq": "❓ FAQ",
            "btn_contact": "📞 Связаться",
            "products_title": "🎧 *Наше оборудование:*\n\n",
            "product_info": "*{name}*\n{desc}\n\n💰 Аренда: {price}€/день\n🔐 Депозит: {deposit}€\n",
            "book_choose": "Что хотите арендовать?",
            "book_name": "Введите ваше *имя и фамилию*:",
            "book_phone": "Введите ваш *номер телефона* (с кодом страны, например +7...):",
            "book_start": "Введите *дату начала* аренды (формат: ДД.ММ.ГГГГ):",
            "book_end": "Введите *дату окончания* аренды (формат: ДД.ММ.ГГГГ):",
            "book_unavailable": "❌ К сожалению, оборудование занято {date}. Выберите другие даты.",
            "book_invalid_date": "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ (например: 25.06.2025)",
            "book_date_order": "❌ Дата начала должна быть раньше даты окончания.",
            "book_past_date": "❌ Нельзя выбрать прошедшую дату.",
            "book_summary": (
                "✅ *Проверьте вашу заявку:*\n\n"
                "📦 Продукт: {product}\n"
                "👤 Имя: {name}\n"
                "📞 Телефон: {phone}\n"
                "📅 Даты: {start} — {end} ({days} дн.)\n"
                "💰 Стоимость аренды: {rental}€\n"
                "🔐 Депозит: {deposit}€\n"
                "💵 *Итого к оплате: {total}€*\n\n"
                "Подтвердить заявку?"
            ),
            "book_confirmed": "🎉 Заявка отправлена! Мы свяжемся с вами в ближайшее время.",
            "book_cancelled": "❌ Заявка отменена.",
            "btn_confirm": "✅ Подтвердить",
            "btn_cancel": "❌ Отмена",
            "availability_title": "📆 *Занятые даты:*\n\n",
            "availability_free": "✅ Оборудование свободно — занятых дат нет!",
            "faq_title": "❓ *Часто задаваемые вопросы:*\n\n",
            "contact_text": "📞 Для связи напишите нам напрямую:\n\nTelegram: @your_username\nWhatsApp: +XX XXX XXX XXXX",
            "back": "⬅️ Назад",
            "new_booking_notify": (
                "🔔 *Новая заявка на аренду!*\n\n"
                "📦 {product}\n"
                "👤 {name}\n"
                "📞 {phone}\n"
                "📅 {start} — {end} ({days} дн.)\n"
                "💰 Аренда: {rental}€ | Депозит: {deposit}€\n"
                "💵 Итого: {total}€\n"
                "🆔 ID заявки: #{booking_id}"
            ),
            "btn_confirm_booking": "✅ Подтвердить заявку #{id}",
            "admin_confirmed": "✅ Заявка #{id} подтверждена!",
        },
        "en": {
            "welcome": "👋 Hello! I'm a bot for renting professional equipment for public speaking.\n\nChoose your language:",
            "main_menu": "📋 Main Menu",
            "btn_products": "🛍 Products & Pricing",
            "btn_book": "📅 Book Now",
            "btn_availability": "📆 Check Availability",
            "btn_faq": "❓ FAQ",
            "btn_contact": "📞 Contact Us",
            "products_title": "🎧 *Our Equipment:*\n\n",
            "product_info": "*{name}*\n{desc}\n\n💰 Rental: {price}€/day\n🔐 Deposit: {deposit}€\n",
            "book_choose": "What would you like to rent?",
            "book_name": "Enter your *full name*:",
            "book_phone": "Enter your *phone number* (with country code, e.g. +1...):",
            "book_start": "Enter *start date* of rental (format: DD.MM.YYYY):",
            "book_end": "Enter *end date* of rental (format: DD.MM.YYYY):",
            "book_unavailable": "❌ Sorry, the device is booked on {date}. Please choose different dates.",
            "book_invalid_date": "❌ Invalid date format. Use DD.MM.YYYY (e.g. 25.06.2025)",
            "book_date_order": "❌ Start date must be before end date.",
            "book_past_date": "❌ You cannot select a past date.",
            "book_summary": (
                "✅ *Review your booking:*\n\n"
                "📦 Product: {product}\n"
                "👤 Name: {name}\n"
                "📞 Phone: {phone}\n"
                "📅 Dates: {start} — {end} ({days} days)\n"
                "💰 Rental cost: {rental}€\n"
                "🔐 Deposit: {deposit}€\n"
                "💵 *Total payable: {total}€*\n\n"
                "Confirm booking?"
            ),
            "book_confirmed": "🎉 Booking submitted! We'll contact you shortly.",
            "book_cancelled": "❌ Booking cancelled.",
            "btn_confirm": "✅ Confirm",
            "btn_cancel": "❌ Cancel",
            "availability_title": "📆 *Booked dates:*\n\n",
            "availability_free": "✅ Equipment is available — no booked dates!",
            "faq_title": "❓ *Frequently Asked Questions:*\n\n",
            "contact_text": "📞 Contact us directly:\n\nTelegram: @your_username\nWhatsApp: +XX XXX XXX XXXX",
            "back": "⬅️ Back",
            "new_booking_notify": (
                "🔔 *New Rental Request!*\n\n"
                "📦 {product}\n"
                "👤 {name}\n"
                "📞 {phone}\n"
                "📅 {start} — {end} ({days} days)\n"
                "💰 Rental: {rental}€ | Deposit: {deposit}€\n"
                "💵 Total: {total}€\n"
                "🆔 Booking ID: #{booking_id}"
            ),
            "btn_confirm_booking": "✅ Confirm Booking #{id}",
            "admin_confirmed": "✅ Booking #{id} confirmed!",
        }
    }
    return texts[lang][key].format(**kw)

# ─── KEYBOARDS ────────────────────────────────────────────────────────────────
def lang_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
        InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
    ]])

def main_menu_keyboard(lang):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "btn_products"), callback_data="products")],
        [InlineKeyboardButton(t(lang, "btn_book"), callback_data="book")],
        [InlineKeyboardButton(t(lang, "btn_availability"), callback_data="availability")],
        [InlineKeyboardButton(t(lang, "btn_faq"), callback_data="faq")],
        [InlineKeyboardButton(t(lang, "btn_contact"), callback_data="contact")],
    ])

def product_keyboard(lang):
    p = PRODUCTS
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(p["earpiece"][f"name_{lang}"], callback_data="prod_earpiece")],
        [InlineKeyboardButton(p["earpiece_camera"][f"name_{lang}"], callback_data="prod_earpiece_camera")],
        [InlineKeyboardButton(t(lang, "back"), callback_data="main_menu")],
    ])

def confirm_keyboard(lang):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(t(lang, "btn_confirm"), callback_data="booking_yes"),
        InlineKeyboardButton(t(lang, "btn_cancel"), callback_data="booking_no"),
    ]])

def back_keyboard(lang):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(t(lang, "back"), callback_data="main_menu")
    ]])

# ─── HANDLERS ─────────────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text(
        "👋 Привет / Hello!\n\nВыберите язык / Choose language:",
        reply_markup=lang_keyboard()
    )
    return LANG

async def lang_chosen(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang = q.data.split("_")[1]
    ctx.user_data["lang"] = lang
    await q.edit_message_text(t(lang, "main_menu"), reply_markup=main_menu_keyboard(lang))
    return MAIN_MENU

async def main_menu_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang = ctx.user_data.get("lang", "ru")
    action = q.data

    if action == "main_menu":
        await q.edit_message_text(t(lang, "main_menu"), reply_markup=main_menu_keyboard(lang))
        return MAIN_MENU

    elif action == "products":
        text = t(lang, "products_title")
        for key, p in PRODUCTS.items():
            text += t(lang, "product_info",
                name=p[f"name_{lang}"],
                desc=p[f"desc_{lang}"],
                price=p["price_per_day"],
                deposit=p["deposit"]
            ) + "\n"
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=back_keyboard(lang))
        return MAIN_MENU

    elif action == "book":
        await q.edit_message_text(t(lang, "book_choose"), reply_markup=product_keyboard(lang))
        return BOOKING_PRODUCT

    elif action == "availability":
        booked = get_booked_dates()
        if booked:
            sorted_dates = sorted(booked, key=lambda d: datetime.strptime(d, "%d.%m.%Y"))
            text = t(lang, "availability_title") + "\n".join(f"• {d}" for d in sorted_dates)
        else:
            text = t(lang, "availability_free")
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=back_keyboard(lang))
        return MAIN_MENU

    elif action == "faq":
        text = t(lang, "faq_title")
        for q_text, a_text in FAQ[lang]:
            text += f"*❓ {q_text}*\n_{a_text}_\n\n"
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=back_keyboard(lang))
        return MAIN_MENU

    elif action == "contact":
        await q.edit_message_text(t(lang, "contact_text"), reply_markup=back_keyboard(lang))
        return MAIN_MENU

async def booking_product(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang = ctx.user_data.get("lang", "ru")

    if q.data == "main_menu":
        await q.edit_message_text(t(lang, "main_menu"), reply_markup=main_menu_keyboard(lang))
        return MAIN_MENU

    product_key = q.data.replace("prod_", "")
    ctx.user_data["product_key"] = product_key
    await q.edit_message_text(t(lang, "book_name"), parse_mode="Markdown")
    return BOOKING_NAME

async def booking_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = ctx.user_data.get("lang", "ru")
    ctx.user_data["name"] = update.message.text.strip()
    await update.message.reply_text(t(lang, "book_phone"), parse_mode="Markdown")
    return BOOKING_PHONE

async def booking_phone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = ctx.user_data.get("lang", "ru")
    ctx.user_data["phone"] = update.message.text.strip()
    await update.message.reply_text(t(lang, "book_start"), parse_mode="Markdown")
    return BOOKING_START_DATE

async def booking_start_date(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = ctx.user_data.get("lang", "ru")
    date_str = update.message.text.strip()
    try:
        d = datetime.strptime(date_str, "%d.%m.%Y").date()
        if d < date.today():
            await update.message.reply_text(t(lang, "book_past_date"))
            return BOOKING_START_DATE
        ctx.user_data["start_date"] = date_str
        await update.message.reply_text(t(lang, "book_end"), parse_mode="Markdown")
        return BOOKING_END_DATE
    except ValueError:
        await update.message.reply_text(t(lang, "book_invalid_date"))
        return BOOKING_START_DATE

async def booking_end_date(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = ctx.user_data.get("lang", "ru")
    date_str = update.message.text.strip()
    try:
        datetime.strptime(date_str, "%d.%m.%Y")
    except ValueError:
        await update.message.reply_text(t(lang, "book_invalid_date"))
        return BOOKING_END_DATE

    start_str = ctx.user_data["start_date"]
    available, reason = is_available(start_str, date_str)

    if not available:
        if reason == "start_after_end":
            await update.message.reply_text(t(lang, "book_date_order"))
        elif reason == "invalid_date":
            await update.message.reply_text(t(lang, "book_invalid_date"))
        else:
            await update.message.reply_text(t(lang, "book_unavailable", date=reason))
        return BOOKING_END_DATE

    ctx.user_data["end_date"] = date_str
    product_key = ctx.user_data["product_key"]
    days, rental, deposit = calc_price(product_key, start_str, date_str)
    p = PRODUCTS[product_key]

    summary = t(lang, "book_summary",
        product=p[f"name_{lang}"],
        name=ctx.user_data["name"],
        phone=ctx.user_data["phone"],
        start=start_str,
        end=date_str,
        days=days,
        rental=rental,
        deposit=deposit,
        total=rental + deposit
    )
    await update.message.reply_text(summary, parse_mode="Markdown", reply_markup=confirm_keyboard(lang))
    return BOOKING_CONFIRM

async def booking_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang = ctx.user_data.get("lang", "ru")

    if q.data == "booking_no":
        await q.edit_message_text(t(lang, "book_cancelled"))
        await q.message.reply_text(t(lang, "main_menu"), reply_markup=main_menu_keyboard(lang))
        return MAIN_MENU

    # Save booking
    bookings = load_bookings()
    product_key = ctx.user_data["product_key"]
    start_str = ctx.user_data["start_date"]
    end_str = ctx.user_data["end_date"]
    days, rental, deposit = calc_price(product_key, start_str, end_str)
    p = PRODUCTS[product_key]

    booking_id = len(bookings) + 1
    booking = {
        "id": booking_id,
        "user_id": update.effective_user.id,
        "username": update.effective_user.username or "",
        "product": product_key,
        "name": ctx.user_data["name"],
        "phone": ctx.user_data["phone"],
        "start_date": start_str,
        "end_date": end_str,
        "days": days,
        "rental": rental,
        "deposit": deposit,
        "total": rental + deposit,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "lang": lang,
    }
    bookings.append(booking)
    save_bookings(bookings)

    await q.edit_message_text(t(lang, "book_confirmed"))

    # Notify admin
    admin_text = t("ru", "new_booking_notify",
        product=p[f"name_ru"],
        name=booking["name"],
        phone=booking["phone"],
        start=start_str,
        end=end_str,
        days=days,
        rental=rental,
        deposit=deposit,
        total=rental + deposit,
        booking_id=booking_id
    )
    confirm_btn = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"✅ Подтвердить #{booking_id}", callback_data=f"admin_confirm_{booking_id}")
    ]])
    await ctx.bot.send_message(ADMIN_CHAT_ID, admin_text, parse_mode="Markdown", reply_markup=confirm_btn)

    await q.message.reply_text(t(lang, "main_menu"), reply_markup=main_menu_keyboard(lang))
    return MAIN_MENU

async def admin_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if update.effective_user.id != ADMIN_CHAT_ID:
        return

    booking_id = int(q.data.split("_")[-1])
    bookings = load_bookings()
    for b in bookings:
        if b["id"] == booking_id:
            b["status"] = "confirmed"
            break
    save_bookings(bookings)
    await q.edit_message_text(f"✅ Заявка #{booking_id} подтверждена и даты заблокированы!")

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = ctx.user_data.get("lang", "ru")
    await update.message.reply_text(t(lang, "main_menu"), reply_markup=main_menu_keyboard(lang))
    return MAIN_MENU

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            LANG: [CallbackQueryHandler(lang_chosen, pattern="^lang_")],
            MAIN_MENU: [CallbackQueryHandler(main_menu_handler)],
            BOOKING_PRODUCT: [CallbackQueryHandler(booking_product)],
            BOOKING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, booking_name)],
            BOOKING_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, booking_phone)],
            BOOKING_START_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, booking_start_date)],
            BOOKING_END_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, booking_end_date)],
            BOOKING_CONFIRM: [CallbackQueryHandler(booking_confirm)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(admin_confirm, pattern="^admin_confirm_"))

    print("🤖 Bot started!")
    app.run_polling()

if __name__ == "__main__":
    main()
