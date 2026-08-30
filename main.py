import os
import json
import random
import string
import base64
import asyncio
import time
import threading
from datetime import datetime

import requests
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ConversationHandler,
    MessageHandler, filters, ContextTypes
)

# ---------- Environment ----------
BOT_TOKEN = os.getenv("BOT_TOKEN")
FIREBASE_URL = os.getenv("FIREBASE_URL")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
REFER_CODE = os.getenv("REFER_CODE", "U28X0K")

if not BOT_TOKEN or not FIREBASE_URL or not ADMIN_CHAT_ID:
    raise Exception("Missing environment variables")

API_KEY = "anMd4snJZwmAgQNIqYfSuOoqZFES8bOz"
BASE_API = "https://app.turboreward.in/new-api/"
SIGNUP_URL = BASE_API + "signup.php"
PROFILE_URL = BASE_API + "complete_profile.php"
DF_URL = BASE_API + "df.php"
HISTORY_URL = BASE_API + "getcoinhistory.php"

HEADERS = {
    'User-Agent': "okhttp/4.12.0",
    'Accept-Encoding': "gzip",
    'api-key': API_KEY
}

# ---------- Firebase Helpers ----------
def firebase_read(path):
    url = f"{FIREBASE_URL}/{path}.json"
    resp = requests.get(url)
    if resp.status_code == 200:
        return resp.json()
    return None

def firebase_write(path, data):
    url = f"{FIREBASE_URL}/{path}.json"
    resp = requests.put(url, json=data)
    return resp.status_code == 200

def firebase_update(path, data):
    url = f"{FIREBASE_URL}/{path}.json"
    resp = requests.patch(url, json=data)
    return resp.status_code == 200

# ---------- Utility ----------
def generate_device_id():
    return ''.join(random.choices(string.digits, k=16))

def generate_base64_id():
    rand_num = str(random.randint(10000, 99999))
    return base64.b64encode(rand_num.encode()).decode()

def get_timestamp_ms():
    return int(time.time() * 1000)

def post(endpoint, data):
    url = BASE_API + endpoint
    payload = {'data': json.dumps(data)}
    try:
        resp = requests.post(url, data=payload, headers=HEADERS)
        return resp
    except Exception:
        return None

# ---------- Account Creation ----------
def create_account(email, full_name, phone):
    device_id = generate_device_id()
    base64_id = generate_base64_id()

    signup_data = {
        "Login_Status": "Check",
        "ReferCode": REFER_CODE,
        "Signup_OTP": "123456",
        "Signup_Token": "yj2OCSrYU9K5bvqGs5Vt4F9dtHMaOwOk",
        "Token": "",
        "did": device_id,
        "email_id": email,
        "id": base64_id
    }
    resp = requests.post(SIGNUP_URL, data={'l': json.dumps(signup_data)}, headers=HEADERS)
    if resp.status_code != 200:
        return None, None, None

    text = resp.text.strip()
    if "Login Successfully" in text or "Register Successfully" in text:
        parts = text.split(',')
        if len(parts) >= 2:
            numeric_key = parts[1]  # Token from server (e.g., "2727663415")
            # Complete profile with numeric key
            profile_data = {
                "Token": numeric_key,
                "did": device_id,
                "email_id": email,
                "full_name": full_name,
                "phone_number": phone
            }
            requests.post(PROFILE_URL, data={'l': json.dumps(profile_data)}, headers=HEADERS)
            return device_id, base64_id, numeric_key
    return None, None, None

# ---------- Task Runner (using base64_id as key_id) ----------
def run_tasks(device_id, key_id, bot, chat_id):
    def notify(msg):
        asyncio.run_coroutine_threadsafe(
            bot.send_message(chat_id, msg),
            asyncio.get_event_loop()
        )

    try:
        notify("🔄 Claiming daily spins... (Step 1/6)")
        post("spin/claim_daily_spins.php", {"device_id": device_id, "key_id": key_id, "milisecond": get_timestamp_ms()})
        notify("✅ Daily spins claimed!")
        delay = random.randint(40, 90)
        notify(f"⏳ Waiting {delay}s before next task...")
        time.sleep(delay)

        notify("🎡 Spinning... (0.99) (Step 2/6)")
        post("spin/new_save_spin_coins.php", {"device_id": device_id, "key_id": key_id, "milisecond": get_timestamp_ms(), "coins": "0.99"})
        notify("✅ Spin completed! (0.99)")
        delay = random.randint(40, 90)
        notify(f"⏳ Waiting {delay}s...")
        time.sleep(delay)

        notify("🎡 Spinning again... (0.99) (Step 3/6)")
        post("spin/new_save_spin_coins.php", {"device_id": device_id, "key_id": key_id, "milisecond": get_timestamp_ms(), "coins": "0.99"})
        notify("✅ Second spin completed! (0.99)")
        delay = random.randint(40, 90)
        notify(f"⏳ Waiting {delay}s...")
        time.sleep(delay)

        notify("🪙 Scratching card... (0.22) (Step 4/6)")
        post("scratch-card/save_coins.php", {"device_id": device_id, "key_id": key_id, "milisecond": get_timestamp_ms(), "coins": "0.22"})
        notify("✅ Scratch card completed! (0.22)")
        delay = random.randint(40, 90)
        notify(f"⏳ Waiting {delay}s...")
        time.sleep(delay)

        notify("📅 Daily checkin... (0.22) (Step 5/6)")
        post("daily-checkin/save_coins.php", {"device_id": device_id, "key_id": key_id, "milisecond": get_timestamp_ms(), "coins": "0.22"})
        notify("✅ Daily checkin completed! (0.22)")
        delay = random.randint(40, 90)
        notify(f"⏳ Waiting {delay}s...")
        time.sleep(delay)

        notify("📺 Watching video... (0.40) (Step 6/6)")
        post("watch-video/save_coins.php", {"device_id": device_id, "key_id": key_id, "milisecond": get_timestamp_ms(), "coins": "0.40"})
        notify("✅ Video watched! (0.40)")

        resp = requests.get(DF_URL, headers=HEADERS)
        total = "0.00"
        if resp.status_code == 200:
            parts = resp.text.split(',')
            if parts:
                total = parts[0]
        notify(f"🎉 *All tasks completed!*\nToday's total: ₹{total}")
        return total
    except Exception as e:
        notify(f"❌ Error: {e}")
        return "0.00"

def get_coin_history():
    pages = []
    for page in [None, 1, 2, 3, 4]:
        url = HISTORY_URL
        if page is not None:
            url += f"?page={page}"
        resp = requests.get(url, headers=HEADERS)
        if resp.status_code == 200:
            try:
                data = resp.json()
                if data:
                    pages.append(data)
                else:
                    break
            except:
                break
        else:
            break
    return pages

# ---------- Telegram Bot ----------
GET_FULLNAME, GET_PHONE, GET_EMAIL = range(3)

def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("➕ Create Account", callback_data="create_account")],
        [InlineKeyboardButton("👤 My Account", callback_data="my_account")],
        [InlineKeyboardButton("📞 Support", callback_data="support")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    user_data = {
        "chat_id": str(chat_id),
        "username": user.username or "No username",
        "full_name": user.full_name or "No name",
        "started_at": datetime.now().isoformat()
    }
    firebase_update(f"turbo/{chat_id}", user_data)
    await context.bot.send_message(ADMIN_CHAT_ID, f"🆕 New user: {user.full_name} (@{user.username})")

    msg = (
        "🎉 *Welcome to Turbo Reward Script!*\n"
        "👨‍💻 Script by Dr. Dev || Dr. Hamza\n"
        "📱 Official App: [TurboReward](https://app.turboreward.in)\n\n"
        "🔹 *Create Account* – बनाएं नया अकाउंट\n"
        "🔹 *My Account* – देखें अपने अकाउंट की डिटेल\n"
        "🔹 *Support* – किसी भी समस्या के लिए\n\n"
        "चुनें नीचे दिए गए बटन से 👇"
    )
    await update.message.reply_text(msg, reply_markup=get_main_menu(), parse_mode="Markdown")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat.id

    if data == "my_account":
        accounts = firebase_read(f"turbo/{chat_id}/accounts")
        if not accounts:
            await query.message.reply_text("❌ आपका कोई अकाउंट नहीं है। पहले *Create Account* करें।", reply_markup=get_main_menu(), parse_mode="Markdown")
            return
        keyboard = []
        for idx, acc in enumerate(accounts):
            label = f"📧 {acc.get('email', 'Unknown')}"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"view_acc_{idx}")])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back_main")])
        await query.message.reply_text("👤 *Your Accounts*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    elif data.startswith("view_acc_"):
        try:
            idx = int(data.split("_")[2])
        except:
            await query.message.reply_text("❌ Invalid account.", reply_markup=get_main_menu())
            return
        accounts = firebase_read(f"turbo/{chat_id}/accounts")
        if not accounts or idx >= len(accounts):
            await query.message.reply_text("❌ अकाउंट नहीं मिला।", reply_markup=get_main_menu())
            return
        acc = accounts[idx]
        context.user_data['current_account'] = acc
        context.user_data['current_account_idx'] = idx

        details = (
            f"📧 *Email:* {acc.get('email')}\n"
            f"👤 *Name:* {acc.get('full_name')}\n"
            f"📱 *Phone:* {acc.get('phone')}\n"
            f"🆔 *Device ID:* `{acc.get('device_id')}`\n"
            f"🔑 *Base64 ID (key_id):* `{acc.get('base64_id')}`\n"
            f"🔢 *Numeric Key:* `{acc.get('numeric_key')}`\n"
            f"📅 *Created:* {acc.get('created_at', 'Unknown')}\n"
        )
        keyboard = [
            [InlineKeyboardButton("✅ Complete Today Task", callback_data="do_task")],
            [InlineKeyboardButton("💰 Balance", callback_data="balance")],
            [InlineKeyboardButton("📜 Coin History", callback_data="history")],
            [InlineKeyboardButton("💸 Withdraw", callback_data="withdraw")],
            [InlineKeyboardButton("🔙 Back", callback_data="back_main")]
        ]
        await query.message.reply_text(details, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    elif data == "do_task":
        acc = context.user_data.get('current_account')
        if not acc:
            await query.message.reply_text("❌ पहले कोई अकाउंट सेलेक्ट करें।", reply_markup=get_main_menu())
            return
        device_id = acc['device_id']
        key_id = acc['base64_id']   # use base64_id as key_id
        await query.message.reply_text("⏳ *Task in progress...* कृपया wait करें।\nयह कुछ मिनट लग सकते हैं।", parse_mode="Markdown")

        loop = asyncio.get_event_loop()
        bot = context.bot
        await loop.run_in_executor(None, run_tasks, device_id, key_id, bot, chat_id)
        await context.bot.send_message(chat_id, "✅ *Task Completed!*", reply_markup=get_main_menu(), parse_mode="Markdown")
        return

    elif data == "balance":
        acc = context.user_data.get('current_account')
        if not acc:
            await query.message.reply_text("❌ कोई अकाउंट सेलेक्ट नहीं।", reply_markup=get_main_menu())
            return
        resp = requests.get(DF_URL, headers=HEADERS)
        total = "0.00"
        if resp.status_code == 200:
            parts = resp.text.split(',')
            if parts:
                total = parts[0]
        await query.message.reply_text(f"💰 *Current Balance:* ₹{total}\n\n(यह df.php से fetch किया गया है)", reply_markup=get_main_menu(), parse_mode="Markdown")
        return

    elif data == "history":
        acc = context.user_data.get('current_account')
        if not acc:
            await query.message.reply_text("❌ कोई अकाउंट सेलेक्ट नहीं।", reply_markup=get_main_menu())
            return
        await query.message.reply_text("⏳ *Fetching history...*", parse_mode="Markdown")

        loop = asyncio.get_event_loop()
        pages = await loop.run_in_executor(None, get_coin_history)
        if not pages:
            await context.bot.send_message(chat_id, "📭 कोई इतिहास नहीं मिला।", reply_markup=get_main_menu())
        else:
            total_entries = sum(len(p) for p in pages)
            await context.bot.send_message(chat_id, f"📜 *Coin History*\nTotal entries: {total_entries}\n\nपहले 3 पेज दिखाए जा रहे हैं।", parse_mode="Markdown")
            for i, page in enumerate(pages[:3]):
                msg = f"*Page {i+1}*\n" + json.dumps(page, indent=2)
                if len(msg) > 4000:
                    msg = msg[:4000] + "..."
                await context.bot.send_message(chat_id, msg, parse_mode="Markdown")
        return

    elif data == "withdraw":
        keyboard = [
            [InlineKeyboardButton("₹10", callback_data="withdraw_10"),
             InlineKeyboardButton("₹15", callback_data="withdraw_15")],
            [InlineKeyboardButton("₹25", callback_data="withdraw_25"),
             InlineKeyboardButton("₹50", callback_data="withdraw_50")],
            [InlineKeyboardButton("₹100", callback_data="withdraw_100"),
             InlineKeyboardButton("₹250", callback_data="withdraw_250")],
            [InlineKeyboardButton("🔙 Back", callback_data="back_main")]
        ]
        await query.message.reply_text("💸 *Withdraw Amount*\n\nअपनी राशि चुनें:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    elif data.startswith("withdraw_"):
        amount = data.split("_")[1]
        await query.message.reply_text(f"❌ *Insufficient Balance!*\nआपके पास ₹{amount} निकालने के लिए पर्याप्त बैलेंस नहीं है।\n\nपहले *Complete Today Task* करें।", reply_markup=get_main_menu(), parse_mode="Markdown")
        return

    elif data == "support":
        await query.message.reply_text(
            "📞 *Support*\n\nकिसी भी समस्या के लिए DM करें:\n[@Hamza3895](https://t.me/Hamza3895)\n\nया ऐप का इस्तेमाल करें: [TurboReward](https://app.turboreward.in)",
            reply_markup=get_main_menu(),
            parse_mode="Markdown"
        )
        return

    elif data == "back_main":
        await query.message.reply_text("मुख्य मेनू पर वापस।", reply_markup=get_main_menu())
        return

# ---------- Conversation for Create Account ----------
async def create_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("📝 *Create Account*\n\nअपना *Full Name* डालें:", parse_mode="Markdown")
    return GET_FULLNAME

async def get_fullname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['full_name'] = update.message.text.strip()
    await update.message.reply_text("अब *Phone Number* डालें (10 अंक):")
    return GET_PHONE

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    if not phone.isdigit() or len(phone) != 10:
        await update.message.reply_text("❌ कृपया 10 अंकों का सही फोन नंबर डालें।")
        return GET_PHONE
    context.user_data['phone'] = phone
    await update.message.reply_text("अब *Email* डालें:")
    return GET_EMAIL

async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = update.message.text.strip()
    if '@' not in email:
        await update.message.reply_text("❌ सही email डालें (जैसे name@example.com)")
        return GET_EMAIL
    context.user_data['email'] = email

    full_name = context.user_data['full_name']
    phone = context.user_data['phone']
    email = context.user_data['email']

    await update.message.reply_text("⏳ *Creating account...* कृपया wait करें।", parse_mode="Markdown")

    loop = asyncio.get_event_loop()
    device_id, base64_id, numeric_key = await loop.run_in_executor(None, create_account, email, full_name, phone)
    if not device_id:
        await update.message.reply_text("❌ Account creation failed. शायद email already exist या server error. कृपया फिर try करें।", reply_markup=get_main_menu())
        return ConversationHandler.END

    account_data = {
        "device_id": device_id,
        "base64_id": base64_id,      # this is the key_id for claims
        "numeric_key": numeric_key,  # server token (for profile)
        "email": email,
        "full_name": full_name,
        "phone": phone,
        "refer_code": REFER_CODE,
        "created_at": datetime.now().isoformat()
    }
    chat_id = update.effective_chat.id
    accounts = firebase_read(f"turbo/{chat_id}/accounts") or []
    accounts.append(account_data)
    firebase_write(f"turbo/{chat_id}/accounts", accounts)

    await update.message.reply_text(
        f"✅ *Account Created Successfully!*\n\n"
        f"📧 Email: {email}\n"
        f"👤 Name: {full_name}\n"
        f"📱 Phone: {phone}\n"
        f"🆔 Device ID: `{device_id}`\n"
        f"🔑 Base64 ID (key_id): `{base64_id}`\n"
        f"🔢 Numeric Key: `{numeric_key}`\n\n"
        "अब आप *Complete Today Task* कर सकते हैं या *My Account* से देख सकते हैं।",
        reply_markup=get_main_menu(),
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.", reply_markup=get_main_menu())
    return ConversationHandler.END

# ---------- Flask Server ----------
flask_app = Flask(__name__)

@flask_app.route('/')
def health():
    return "Bot is running!"

def run_flask():
    flask_app.run(host='0.0.0.0', port=8080)

# ---------- Main ----------
def main():
    threading.Thread(target=run_flask, daemon=True).start()

    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(create_account_start, pattern="^create_account$")],
        states={
            GET_FULLNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_fullname)],
            GET_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            GET_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_email)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    application.add_handler(conv_handler)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(
        button_callback,
        pattern="^(my_account|view_acc_\\d+|do_task|balance|history|withdraw|back_main|withdraw_\\d+|support)$"
    ))

    application.run_polling()

if __name__ == "__main__":
    main()
