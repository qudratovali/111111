import os
import sqlite3
import logging
from datetime import datetime, timedelta
from telebot import TeleBot, types
from telebot.types import LabeledPrice

# ===================== CONFIG =====================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8257704799:AAHKz6r02oL8SKhdehg6niT3IflvzeUFqJY")
ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "7514690928").split(",")]
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-100" + "3915777311"))
CHANNEL_INVITE = os.environ.get("CHANNEL_INVITE", "https://t.me/+dcERdSVwCUhkNzYy")
STARS_PRICE = int(os.environ.get("STARS_PRICE", "150"))
DB_PATH = "bot.db"

# ===================== LOGGING =====================
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ===================== BOT =====================
bot = TeleBot(BOT_TOKEN)

# ===================== DATABASE =====================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT,
            full_name   TEXT,
            joined_at   TEXT,
            is_member   INTEGER DEFAULT 0,
            expires_at  TEXT,
            total_paid  INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            username    TEXT,
            full_name   TEXT,
            stars       INTEGER,
            paid_at     TEXT,
            charge_id   TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    # Default settings
    c.execute("INSERT OR IGNORE INTO settings VALUES ('channel_name', 'POZALAR 18+')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('welcome_msg', 'Yopiq kanalga kirish uchun atigi {price} Stars tolag!')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('stars_price', ?)", (str(STARS_PRICE),))
    conn.commit()
    conn.close()

def get_db():
    return sqlite3.connect(DB_PATH)

def get_setting(key):
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row[0] if row else None

def set_setting(key, value):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, value))
    conn.commit()
    conn.close()

def upsert_user(user):
    conn = get_db()
    conn.execute("""
        INSERT INTO users (user_id, username, full_name, joined_at)
        VALUES (?,?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET
            username=excluded.username,
            full_name=excluded.full_name
    """, (user.id, user.username or "", user.full_name, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    if row:
        return dict(zip(["user_id","username","full_name","joined_at","is_member","expires_at","total_paid"], row))
    return None

def set_member(user_id, stars):
    conn = get_db()
    conn.execute("""
        UPDATE users SET is_member=1, expires_at=NULL, total_paid=total_paid+?
        WHERE user_id=?
    """, (stars, user_id))
    conn.commit()
    conn.close()

def log_payment(user_id, username, full_name, stars, charge_id):
    conn = get_db()
    conn.execute("""
        INSERT INTO payments (user_id, username, full_name, stars, paid_at, charge_id)
        VALUES (?,?,?,?,?,?)
    """, (user_id, username or "", full_name, stars, datetime.now().isoformat(), charge_id))
    conn.commit()
    conn.close()

def get_stats():
    conn = get_db()
    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_members = conn.execute("SELECT COUNT(*) FROM users WHERE is_member=1").fetchone()[0]
    total_payments = conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0]
    total_stars = conn.execute("SELECT COALESCE(SUM(stars),0) FROM payments").fetchone()[0]
    today = datetime.now().strftime("%Y-%m-%d")
    today_payments = conn.execute("SELECT COUNT(*) FROM payments WHERE paid_at LIKE ?", (today+"%",)).fetchone()[0]
    today_stars = conn.execute("SELECT COALESCE(SUM(stars),0) FROM payments WHERE paid_at LIKE ?", (today+"%",)).fetchone()[0]
    conn.close()
    return {
        "total_users": total_users,
        "total_members": total_members,
        "total_payments": total_payments,
        "total_stars": total_stars,
        "today_payments": today_payments,
        "today_stars": today_stars,
    }

def get_recent_payments(limit=10):
    conn = get_db()
    rows = conn.execute("""
        SELECT user_id, username, full_name, stars, paid_at
        FROM payments ORDER BY paid_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return rows

def get_all_user_ids():
    conn = get_db()
    rows = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    return [r[0] for r in rows]

def is_active_member(user_id):
    u = get_user(user_id)
    if not u or not u["is_member"]:
        return False
    return True

# ===================== KEYBOARDS =====================
def main_kb(user_id):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    price = get_setting("stars_price") or str(STARS_PRICE)
    kb.add(types.KeyboardButton(f"🔓 Yopiq kanalga qo'shilish — {price} ⭐"))
    kb.row(
        types.KeyboardButton("💳 Stars olish"),
        types.KeyboardButton("👤 Mening profilim")
    )
    kb.row(
        types.KeyboardButton("🆘 Yordam"),
        types.KeyboardButton("❓ Savollar")
    )
    if user_id in ADMIN_IDS:
        kb.add(types.KeyboardButton("🔧 Admin Panel"))
    return kb

def admin_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        types.KeyboardButton("📊 Statistika"),
        types.KeyboardButton("💳 To'lovlar tarixi")
    )
    kb.add(
        types.KeyboardButton("💰 Narx o'zgartirish"),
        types.KeyboardButton("📢 Xabar yuborish")
    )
    kb.add(
        types.KeyboardButton("📝 Kanal nomi o'zgartirish"),
        types.KeyboardButton("✉️ Xush kelibsiz xabar")
    )
    kb.add(types.KeyboardButton("🔙 Asosiy menyu"))
    return kb

def back_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("🔙 Orqaga"))
    return kb

# ===================== STATES =====================
user_states = {}

def set_state(user_id, state, data=None):
    user_states[user_id] = {"state": state, "data": data or {}}

def get_state(user_id):
    return user_states.get(user_id, {})

def clear_state(user_id):
    user_states.pop(user_id, None)

# ===================== HELPERS =====================
def format_date(iso_str):
    try:
        return datetime.fromisoformat(iso_str).strftime("%d.%m.%Y %H:%M")
    except:
        return iso_str

def stars_emoji(n):
    return "⭐" * min(n // 50, 5)

# ===================== HANDLERS =====================

@bot.message_handler(commands=["start"])
def cmd_start(msg):
    upsert_user(msg.from_user)
    user_id = msg.from_user.id
    name = msg.from_user.first_name or "Do'st"
    channel_name = get_setting("channel_name") or "Yopiq kanal"
    price = get_setting("stars_price") or str(STARS_PRICE)

    if user_id in ADMIN_IDS:
        bot.send_message(user_id,
            f"👋 Xush kelibsiz, Admin!\n\n"
            f"🤖 Bot ishlayapti. Quyidan kerakli bo'limni tanlang.",
            reply_markup=admin_kb()
        )
        return

    welcome = get_setting("welcome_msg") or "Yopiq kanalga kirish uchun atigi {price} Stars tolag!"
    welcome = welcome.replace("{price}", price).replace("{name}", name).replace("{channel}", channel_name)

    text = (
        f"👋 Assalomu alaykum, {name}!\n\n"
        f"🔞 <b>{channel_name}</b> — maxsus yopiq kanal.\n\n"
        f"🔑 Kirish uchun: <b>{price} Stars</b>\n"
        f"♾️ Obuna: <b>Doimiy</b>\n\n"
        f"{welcome}\n\n"
        f"Quyidagi tugmani bosing 👇"
    )
    bot.send_message(user_id, text, parse_mode="HTML", reply_markup=main_kb(user_id))

@bot.message_handler(func=lambda m: m.text == "👤 Mening profilim")
def profile_handler(msg):
    u = get_user(msg.from_user.id)
    if not u:
        upsert_user(msg.from_user)
        u = get_user(msg.from_user.id)

    status = "✅ Faol a'zo" if is_active_member(msg.from_user.id) else "❌ A'zo emas"
    joined = format_date(u["joined_at"]) if u.get("joined_at") else "—"

    text = (
        f"👤 <b>Profilingiz</b>\n\n"
        f"🆔 ID: <code>{u['user_id']}</code>\n"
        f"📛 Ism: {u['full_name']}\n"
        f"🔗 Username: @{u['username'] or '—'}\n\n"
        f"📊 Status: {status}\n"
        f"♾️ Obuna: <b>Doimiy</b>\n"
        f"⭐ Jami to'langan: {u['total_paid']} Stars\n"
        f"🗓 Bot'ga qo'shilgan: {joined}"
    )
    bot.send_message(msg.chat.id, text, parse_mode="HTML", reply_markup=main_kb(msg.from_user.id))

@bot.message_handler(func=lambda m: m.text and m.text.startswith("🔓 Yopiq kanalga"))
def pay_handler(msg):
    price_str = get_setting("stars_price") or str(STARS_PRICE)
    price = int(price_str)

    if is_active_member(msg.from_user.id):
        u = get_user(msg.from_user.id)
        expires = format_date(u["expires_at"]) if u.get("expires_at") else "—"
        bot.send_message(msg.chat.id,
            f"✅ Siz allaqachon <b>faol a'zo</b>siz!\n\n"
            f"♾️ Obuna: <b>Doimiy</b>\n\n"
            f"🔗 Kanal: {CHANNEL_INVITE}",
            parse_mode="HTML",
            reply_markup=main_kb(msg.from_user.id)
        )
        return

    bot.send_invoice(
        chat_id=msg.chat.id,
        title="⭐ VIP A'zolik",
        description="Doimiy VIP a'zolik. Barcha maxsus kontentga kirish imkoniyati.",
        invoice_payload="vip_membership",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice("VIP A'zolik (Doimiy)", price)]
    )

@bot.pre_checkout_query_handler(func=lambda q: True)
def pre_checkout(query):
    bot.answer_pre_checkout_query(query.id, ok=True)

@bot.message_handler(content_types=["successful_payment"])
def successful_payment(msg):
    user_id = msg.from_user.id
    stars = msg.successful_payment.total_amount
    charge_id = msg.successful_payment.telegram_payment_charge_id
    username = msg.from_user.username or ""
    full_name = msg.from_user.full_name

    upsert_user(msg.from_user)
    set_member(user_id, stars)
    log_payment(user_id, username, full_name, stars, charge_id)

    # Add to channel
    try:
        bot.approve_chat_join_request(CHANNEL_ID, user_id)
    except:
        pass

    bot.send_message(user_id,
        f"🎉 <b>To'lov muvaffaqiyatli!</b>\n\n"
        f"⭐ To'langan: <b>{stars} Stars</b>\n"
        f"♾️ Obuna: <b>Doimiy</b>\n\n"
        f"✅ Endi kanalga kiring:\n"
        f"👉 {CHANNEL_INVITE}\n\n"
        f"Rahmat! Enjoy 🔞",
        parse_mode="HTML",
        reply_markup=main_kb(user_id)
    )

    # Notify admins
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(admin_id,
                f"💰 <b>Yangi to'lov!</b>\n\n"
                f"👤 {full_name} (@{username or '—'})\n"
                f"🆔 ID: <code>{user_id}</code>\n"
                f"⭐ Stars: <b>{stars}</b>\n"
                f"🕐 Vaqt: {format_date(datetime.now().isoformat())}",
                parse_mode="HTML"
            )
        except:
            pass

@bot.message_handler(func=lambda m: m.text == "💳 Stars olish")
def stars_info(msg):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("⭐ Stars sotib olish", url="https://t.me/tezstar_bot/app?startapp=6940175396"))
    bot.send_message(msg.chat.id, "⭐ <b>Stars sotib olish uchun quyidagi tugmani bosing:</b>",
                     parse_mode="HTML", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "❓ Savollar")
def faq_handler(msg):
    text = (
        "❓ <b>Ko'p so'raladigan savollar</b>\n\n"
        "🔹 <b>To'lov qildim, lekin kirish yo'q?</b>\n"
        f"   → Admin bilan bog'laning\n\n"
        "🔹 <b>Stars qaytariladi?</b>\n"
        "   → Xarid qilingan Stars qaytarilmaydi\n\n"
        "🔹 <b>Profilimni qanday ko'raman?</b>\n"
        "   → «👤 Mening profilim» tugmasini bosing"
    )
    bot.send_message(msg.chat.id, text, parse_mode="HTML",
                     reply_markup=main_kb(msg.from_user.id),
                     disable_web_page_preview=True)

@bot.message_handler(func=lambda m: m.text == "🆘 Yordam")
def help_handler(msg):
    text = (
        "🆘 <b>Yordam</b>\n\n"
        "❓ Savol yoki muammo bo'lsa:\n"
        "👉 @noozii_a bilan bog'laning\n\n"
        "📌 Batafsil savollar uchun «❓ Savollar» tugmasini bosing."
    )
    bot.send_message(msg.chat.id, text, parse_mode="HTML",
                     reply_markup=main_kb(msg.from_user.id))

# ===================== ADMIN HANDLERS =====================

@bot.message_handler(func=lambda m: m.text == "🔧 Admin Panel" and m.from_user.id in ADMIN_IDS)
def admin_panel(msg):
    bot.send_message(msg.chat.id,
        "🔧 <b>Admin Panel</b>\n\nQuyidan kerakli bo'limni tanlang:",
        parse_mode="HTML", reply_markup=admin_kb()
    )

@bot.message_handler(func=lambda m: m.text == "🔙 Asosiy menyu" and m.from_user.id in ADMIN_IDS)
def back_to_main(msg):
    bot.send_message(msg.chat.id, "🏠 Asosiy menyu", reply_markup=main_kb(msg.from_user.id))

@bot.message_handler(func=lambda m: m.text == "📊 Statistika" and m.from_user.id in ADMIN_IDS)
def admin_stats(msg):
    s = get_stats()
    text = (
        f"📊 <b>Statistika</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{s['total_users']}</b>\n"
        f"✅ Faol a'zolar: <b>{s['total_members']}</b>\n\n"
        f"💳 Jami to'lovlar: <b>{s['total_payments']}</b>\n"
        f"⭐ Jami Stars: <b>{s['total_stars']}</b>\n\n"
        f"📅 <b>Bugun:</b>\n"
        f"   • To'lovlar: <b>{s['today_payments']}</b>\n"
        f"   • Stars: <b>{s['today_stars']}</b>\n\n"
        f"💰 Joriy narx: <b>{get_setting('stars_price') or STARS_PRICE} Stars</b>"
    )
    bot.send_message(msg.chat.id, text, parse_mode="HTML", reply_markup=admin_kb())

@bot.message_handler(func=lambda m: m.text == "💳 To'lovlar tarixi" and m.from_user.id in ADMIN_IDS)
def admin_payments(msg):
    rows = get_recent_payments(15)
    if not rows:
        bot.send_message(msg.chat.id, "❌ Hali to'lovlar yo'q.", reply_markup=admin_kb())
        return

    lines = ["💳 <b>So'nggi 15 ta to'lov:</b>\n"]
    for i, (uid, uname, fname, stars, paid_at) in enumerate(rows, 1):
        lines.append(
            f"{i}. {fname} (@{uname or '—'})\n"
            f"   ⭐ {stars} Stars • {format_date(paid_at)}"
        )

    bot.send_message(msg.chat.id, "\n".join(lines), parse_mode="HTML", reply_markup=admin_kb())

@bot.message_handler(func=lambda m: m.text == "💰 Narx o'zgartirish" and m.from_user.id in ADMIN_IDS)
def admin_set_price(msg):
    current = get_setting("stars_price") or str(STARS_PRICE)
    set_state(msg.from_user.id, "set_price")
    bot.send_message(msg.chat.id,
        f"💰 Joriy narx: <b>{current} Stars</b>\n\nYangi narxni kiriting (faqat son):",
        parse_mode="HTML", reply_markup=back_kb()
    )

@bot.message_handler(func=lambda m: m.text == "📝 Kanal nomi o'zgartirish" and m.from_user.id in ADMIN_IDS)
def admin_set_name(msg):
    current = get_setting("channel_name") or "Yopiq kanal"
    set_state(msg.from_user.id, "set_name")
    bot.send_message(msg.chat.id,
        f"📝 Joriy kanal nomi: <b>{current}</b>\n\nYangi nomni kiriting:",
        parse_mode="HTML", reply_markup=back_kb()
    )

@bot.message_handler(func=lambda m: m.text == "✉️ Xush kelibsiz xabar" and m.from_user.id in ADMIN_IDS)
def admin_set_welcome(msg):
    current = get_setting("welcome_msg") or ""
    set_state(msg.from_user.id, "set_welcome")
    bot.send_message(msg.chat.id,
        f"✉️ Joriy xabar:\n<i>{current}</i>\n\n"
        f"Yangi xabar kiriting.\n"
        f"Ishlatish mumkin: <code>{{price}}</code>, <code>{{name}}</code>, <code>{{channel}}</code>",
        parse_mode="HTML", reply_markup=back_kb()
    )

@bot.message_handler(func=lambda m: m.text == "📢 Xabar yuborish" and m.from_user.id in ADMIN_IDS)
def admin_broadcast(msg):
    set_state(msg.from_user.id, "broadcast")
    bot.send_message(msg.chat.id,
        "📢 Barcha foydalanuvchilarga yuboriladigan xabarni kiriting:\n\n"
        "<i>HTML formatlash ishlaydi: <b>bold</b>, <i>italic</i>, <code>code</code></i>",
        parse_mode="HTML", reply_markup=back_kb()
    )

@bot.message_handler(func=lambda m: m.text == "🔙 Orqaga")
def back_handler(msg):
    clear_state(msg.from_user.id)
    if msg.from_user.id in ADMIN_IDS:
        bot.send_message(msg.chat.id, "🔧 Admin Panel", reply_markup=admin_kb())
    else:
        bot.send_message(msg.chat.id, "🏠 Asosiy menyu", reply_markup=main_kb(msg.from_user.id))

@bot.message_handler(func=lambda m: True)
def state_handler(msg):
    uid = msg.from_user.id
    st = get_state(uid)
    state = st.get("state")

    if state == "set_price":
        if not msg.text.isdigit() or int(msg.text) < 1:
            bot.send_message(msg.chat.id, "❌ Faqat musbat son kiriting!", reply_markup=back_kb())
            return
        set_setting("stars_price", msg.text)
        clear_state(uid)
        bot.send_message(msg.chat.id,
            f"✅ Narx <b>{msg.text} Stars</b> ga o'zgartirildi!",
            parse_mode="HTML", reply_markup=admin_kb()
        )

    elif state == "set_name":
        set_setting("channel_name", msg.text.strip())
        clear_state(uid)
        bot.send_message(msg.chat.id,
            f"✅ Kanal nomi <b>{msg.text.strip()}</b> ga o'zgartirildi!",
            parse_mode="HTML", reply_markup=admin_kb()
        )

    elif state == "set_welcome":
        set_setting("welcome_msg", msg.text.strip())
        clear_state(uid)
        bot.send_message(msg.chat.id,
            "✅ Xush kelibsiz xabari yangilandi!",
            parse_mode="HTML", reply_markup=admin_kb()
        )

    elif state == "broadcast":
        clear_state(uid)
        user_ids = get_all_user_ids()
        sent, failed = 0, 0
        bot.send_message(msg.chat.id, f"📤 {len(user_ids)} ta foydalanuvchiga yuborilmoqda...", reply_markup=admin_kb())
        for target_id in user_ids:
            try:
                bot.send_message(target_id, msg.text, parse_mode="HTML")
                sent += 1
            except:
                failed += 1
        bot.send_message(msg.chat.id,
            f"📢 <b>Broadcast tugadi!</b>\n\n✅ Yuborildi: {sent}\n❌ Xato: {failed}",
            parse_mode="HTML", reply_markup=admin_kb()
        )

    else:
        # Unknown command
        bot.send_message(msg.chat.id,
            "❓ Noma'lum buyruq. /start bosing.",
            reply_markup=main_kb(uid)
        )

# ===================== MAIN =====================
if __name__ == "__main__":
    init_db()
    log.info("Bot ishga tushdi!")
    bot.infinity_polling(skip_pending=True)
