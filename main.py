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

# ---------- Version & Config ----------
BOT_VERSION = "3.0 Turbo Reward All Task Bypass"
# Add as many channels as you want to this list
CHANNELS = ["@drdevstudio", "@zxkaiinfo"]

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

# ---------- Channel Force Sub Helper ----------
async def is_user_subscribed(bot, user_id):
    # Loop through all required channels
    for channel in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            # If they left or were kicked from ANY channel, return False
            if member.status not in ['member', 'administrator', 'creator', 'restricted']:
                return False
        except Exception as e:
            print(f"[ERROR] Sub check failed for {channel}: {e}")
            return False
    # If the loop finishes, they are in all channels
    return True

async def send_force_sub_message(message_obj):
    keyboard = []
    # Create a join button for every channel in the list
    for idx, channel in enumerate(CHANNELS):
        keyboard.append([InlineKeyboardButton(f"📢 Join Channel {idx + 1}", url=f"https://t.me/{channel.replace('@', '')}")])
    
    keyboard.append([InlineKeyboardButton("✅ Verify", callback_data="verify_sub")])
    
    await message_obj.reply_text(
        "❌ *Access Denied!*\n\nआपको पहले हमारे सभी चैनल join करने होंगे।\nकृपया नीचे दिए गए सभी चैनल join करें और फिर 'Verify' पर क्लिक करें।",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# ---------- Utility ----------
def generate_device_id():
    return ''.join(random.choices(string.digits, k=16))

def generate_base64_id():
    rand_num = str(random.randint(10000, 99999))
    return base64.b64encode(rand_num.encode()).decode()

def get_timestamp_ms():
    return int(time.time() * 1000)

def post(endpoint, data, field='data'):
    url = BASE_API + endpoint
    # Task endpoints strongly require NO SPACES in JSON payload
    payload = {field: json.dumps(data, separators=(',', ':'))}
    try:
        resp = requests.post(url, data=payload, headers=HEADERS, timeout=30)
        return resp
    except Exception as e:
        print(f"[ERROR] post to {endpoint}: {e}")
        return None

def print_response(label, resp):
    if resp is None:
        return f"{label}: No response"
    output = f"{label} [Status {resp.status_code}]\n"
    try:
        output += json.dumps(resp.json(), indent=2)
    except:
        output += resp.text
    return output

# ---------- Account Creation ----------
def create_account(email, full_name, phone):
    device_id = generate_device_id()
    base64_id = generate_base64_id()

    refer = REFER_CODE if REFER_CODE else "Demo"

    signup_data = {
        "Login_Status": "Check",
        "ReferCode": refer,
        "Signup_OTP": "123456",
        "Signup_Token": "yj2OCSrYU9K5bvqGs5Vt4F9dtHMaOwOk",
        "Token": "",
        "did": device_id,
        "email_id": email,
        "id": base64_id
    }

    try:
        resp = requests.post(SIGNUP_URL, data={'l': json.dumps(signup_data)}, headers=HEADERS, timeout=60)
        
        if resp.status_code != 200:
            return None, None, None, f"HTTP Error {resp.status_code}: {resp.text}"
            
        text = resp.text.strip()
        if "Login Successfully" in text or "Register Successfully" in text:
            parts = text.split(',')
            if len(parts) >= 2:
                numeric_key = parts[1]
                profile_data = {
                    "Token": numeric_key,
                    "did": device_id,
                    "email_id": email,
                    "full_name": full_name,
                    "phone_number": phone
                }
                p_resp = requests.post(PROFILE_URL, data={'l': json.dumps(profile_data)}, headers=HEADERS, timeout=30)
                return device_id, base64_id, numeric_key, f"Success! Profile Resp: {p_resp.text}"
            else:
                return None, None, None, f"Parsing failed. Expected comma-separated string, got: {text}"
        else:
            return None, None, None, f"API Rejected Payload. Response: {text}"
    except Exception as e:
        return None, None, None, f"Python Exception: {str(e)}"

# ---------- Balance Fetching ----------
def get_balance(device_id, key_id):
    try:
        resp = post("df.php", {"device_id": device_id, "key_id": key_id}, field='d')
        if resp and resp.status_code == 200:
            parts = resp.text.split(',')
            if parts:
                return parts[0]
    except Exception as e:
        print(f"[ERROR] Balance: {e}")
    return "0.00"

# ---------- Coin History Fetching ----------
def get_coin_history(device_id, key_id):
    pages = []
    page = 1
    while True:
        payload = {
            "device_id": device_id,
            "key_id": key_id,
            "milisecond": get_timestamp_ms()
        }
        endpoint = f"{HISTORY_URL}?page={page}" if page > 1 else HISTORY_URL
        try:
            resp = requests.post(endpoint, data={'dataa': json.dumps(payload, separators=(',', ':'))}, headers=HEADERS, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if data and len(data) > 0:
                    pages.append(data)
                    page += 1
                else:
                    break
            else:
                break
        except Exception as e:
            print(f"[ERROR] History page {page}: {e}")
            break
    return pages

# ---------- Fully Async Task Runner ----------
async def run_tasks_async(device_id, key_id, bot, chat_id):
    async def notify(msg):
        try:
            await bot.send_message(chat_id, msg, parse_mode="Markdown")
        except Exception as e:
            print(f"[ERROR] notify: {e}")

    await notify(f"🧪 DEBUG: Running version `{BOT_VERSION}`")

    base_delays = [45, 60, 55, 75, 35]
    delays = [d + random.randint(-5, 5) for d in base_delays]
    total_seconds = sum(delays) + 10
    minutes = total_seconds // 60
    seconds = total_seconds % 60

    await notify(f"⏳ *Task started!*\nEstimated time: ~{minutes}m {seconds}s\n\nI'll send each API response as they happen.")

    try:
        # 1) Claim daily spins
        await notify("🔄 Claiming daily spins... (1/6)")
        resp = await asyncio.to_thread(post, "spin/claim_daily_spins.php", {"device_id": device_id, "key_id": key_id, "milisecond": get_timestamp_ms()}, 'data')
        await notify(f"✅ Daily spins claimed!\n{print_response('Claim Daily Spins', resp)[:200]}")
        await asyncio.sleep(delays[0])

        # 2) Save spin coin
        await notify("🎡 Spinning... (0.99) (2/6)")
        resp = await asyncio.to_thread(post, "spin/new_save_spin_coins.php", {"device_id": device_id, "key_id": key_id, "milisecond": get_timestamp_ms(), "coins": "0.99"}, 'data')
        await notify(f"✅ Spin completed! (0.99)\n{print_response('Save Spin Coins (0.99)', resp)[:200]}")
        await asyncio.sleep(delays[1])

        # 3) Second spin
        await notify("🎡 Spinning again... (0.99) (3/6)")
        resp = await asyncio.to_thread(post, "spin/new_save_spin_coins.php", {"device_id": device_id, "key_id": key_id, "milisecond": get_timestamp_ms(), "coins": "0.99"}, 'data')
        await notify(f"✅ Second spin completed! (0.99)\n{print_response('Save Spin Coins (0.99) #2', resp)[:200]}")
        await asyncio.sleep(delays[2])

        # 4) Scratch
        await notify("🪙 Scratching card... (0.39) (4/6)")
        resp = await asyncio.to_thread(post, "scratch-card/save_coins.php", {"device_id": device_id, "key_id": key_id, "milisecond": get_timestamp_ms(), "coins": "0.39"}, 'data')
        await notify(f"✅ Scratch card completed! (0.39)\n{print_response('Save Scratch Coins (0.39)', resp)[:200]}")
        await asyncio.sleep(delays[3])

        # 5) Checkin
        await notify("📅 Daily checkin... (0.50) (5/6)")
        resp = await asyncio.to_thread(post, "daily-checkin/save_coins.php", {"device_id": device_id, "key_id": key_id, "milisecond": get_timestamp_ms(), "coins": "0.50"}, 'data')
        await notify(f"✅ Daily checkin completed! (0.50)\n{print_response('Save Daily Checkin (0.50)', resp)[:200]}")
        await asyncio.sleep(delays[4])

        # 6) Video
        await notify("📺 Watching video... (0.40) (6/6)")
        resp = await asyncio.to_thread(post, "watch-video/save_coins.php", {"device_id": device_id, "key_id": key_id, "milisecond": get_timestamp_ms(), "coins": "0.40"}, 'data')
        await notify(f"✅ Video watched! (0.40)\n{print_response('Save Watch Video (0.40)', resp)[:200]}")

        balance = await asyncio.to_thread(get_balance, device_id, key_id)
        await notify(f"🎉 *All tasks completed!*\nToday's total: ₹{balance}")
        
    except Exception as e:
        await notify(f"❌ Error: {e}")

async def do_tasks_wrapper(device_id, key_id, bot, chat_id, user_data):
    try:
        await run_tasks_async(device_id, key_id, bot, chat_id)
    finally:
        user_data['task_running'] = False

# ---------- Telegram Bot GUI ----------
GET_FULLNAME, GET_PHONE, GET_EMAIL = range(3)

def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("➕ Create Account", callback_data="create_account")],
        [InlineKeyboardButton("👤 My Account", callback_data="my_account")],
        [InlineKeyboardButton("📞 Support", callback_data="support")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def show_main_menu(update, context, message_obj=None):
    msg = (
        "🎉 *Welcome to Turbo Reward Script!*\n"
        "👨‍💻 Script by Dr. Dev || Dr. Hamza\n"
        "📱 Official App: [TurboReward](https://app.turboreward.in)\n\n"
        "🔹 *Create Account* – बनाएं नया अकाउंट\n"
        "🔹 *My Account* – देखें अपने अकाउंट की डिटेल\n"
        "🔹 *Support* – किसी भी समस्या के लिए\n\n"
        "चुनें नीचे दिए गए बटन से 👇"
    )
    if message_obj:
        await message_obj.reply_text(msg, reply_markup=get_main_menu(), parse_mode="Markdown")
        await message_obj.reply_text(f"🤖 *Bot Version:* `{BOT_VERSION}`", parse_mode="Markdown")
    else:
        await update.message.reply_text(msg, reply_markup=get_main_menu(), parse_mode="Markdown")
        await update.message.reply_text(f"🤖 *Bot Version:* `{BOT_VERSION}`", parse_mode="Markdown")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    user_data = {
        "chat_id": str(chat_id),
        "username": user.username or "No username",
        "full_name": user.full_name or "No name",
        "started_at": datetime.now().isoformat()
    }
    
    await asyncio.to_thread(firebase_update, f"turbo/{chat_id}", user_data)
    
    try:
        await context.bot.send_message(ADMIN_CHAT_ID, f"🆕 New user: {user.full_name} (@{user.username})")
    except:
        pass

    if not await is_user_subscribed(context.bot, user.id):
        await send_force_sub_message(update.message)
        return

    await show_main_menu(update, context)

# ---------- Broadcast Command ----------
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != str(ADMIN_CHAT_ID):
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return

    is_reply = bool(update.message.reply_to_message)
    has_text = bool(context.args)

    if not is_reply and not has_text:
        await update.message.reply_text(
            "⚠️ *Usage:*\n"
            "1. Reply to any message (text, photo, video) with `/broadcast`\n"
            "2. Or type directly: `/broadcast Your message here`",
            parse_mode="Markdown"
        )
        return

    status_msg = await update.message.reply_text("⏳ *Starting broadcast...*", parse_mode="Markdown")

    users = await asyncio.to_thread(firebase_read, "turbo")
    if not users or not isinstance(users, dict):
        await status_msg.edit_text("❌ No users found in database.")
        return

    message_text = update.message.text.partition(' ')[2] if has_text else None
    success_count = 0
    fail_count = 0

    for user_id_str in users.keys():
        try:
            if is_reply:
                # Accurately copy pictures, videos, and texts when replying
                await context.bot.copy_message(
                    chat_id=user_id_str,
                    from_chat_id=update.message.chat_id,
                    message_id=update.message.reply_to_message.message_id
                )
            else:
                try:
                    await context.bot.send_message(chat_id=user_id_str, text=message_text, parse_mode="Markdown")
                except:
                    # Fallback to standard text if markdown parsing fails
                    await context.bot.send_message(chat_id=user_id_str, text=message_text)
            
            success_count += 1
            await asyncio.sleep(0.05) # Prevent Telegram flood limits (approx 20 msgs/second)
        except Exception as e:
            fail_count += 1

    await status_msg.edit_text(f"✅ *Broadcast Complete!*\n\n🟢 Success: {success_count}\n🔴 Failed: {fail_count}", parse_mode="Markdown")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat.id
    user_id = query.from_user.id

    if data == "verify_sub":
        if await is_user_subscribed(context.bot, user_id):
            try:
                await query.message.delete()
            except:
                pass
            await show_main_menu(update, context, query.message)
        else:
            await query.answer("❌ आपने अभी तक सभी चैनल join नहीं किए हैं!", show_alert=True)
        return

    if not await is_user_subscribed(context.bot, user_id):
        await send_force_sub_message(query.message)
        return

    if data == "my_account":
        accounts = await asyncio.to_thread(firebase_read, f"turbo/{chat_id}/accounts")
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
        accounts = await asyncio.to_thread(firebase_read, f"turbo/{chat_id}/accounts")
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
        if context.user_data.get('task_running', False):
            await query.message.reply_text("⏳ *Task already in progress!*\nकृपया wait करें।", parse_mode="Markdown")
            return

        acc = context.user_data.get('current_account')
        if not acc:
            await query.message.reply_text("❌ पहले कोई अकाउंट सेलेक्ट करें।", reply_markup=get_main_menu())
            return

        device_id = acc['device_id']
        key_id = acc['base64_id']

        context.user_data['task_running'] = True
        await query.message.reply_text("⏳ *Task started...*\nI'll send each API response as they happen.", parse_mode="Markdown")

        asyncio.create_task(do_tasks_wrapper(device_id, key_id, context.bot, chat_id, context.user_data))
        return

    elif data == "balance":
        acc = context.user_data.get('current_account')
        if not acc:
            await query.message.reply_text("❌ कोई अकाउंट सेलेक्ट नहीं।", reply_markup=get_main_menu())
            return
        device_id = acc['device_id']
        key_id = acc['base64_id']
        balance = await asyncio.to_thread(get_balance, device_id, key_id)
        await query.message.reply_text(f"💰 *Current Balance:* ₹{balance}", reply_markup=get_main_menu(), parse_mode="Markdown")
        return

    elif data == "history":
        acc = context.user_data.get('current_account')
        if not acc:
            await query.message.reply_text("❌ कोई अकाउंट सेलेक्ट नहीं।", reply_markup=get_main_menu())
            return
        device_id = acc['device_id']
        key_id = acc['base64_id']
        await query.message.reply_text("⏳ *Fetching history...*", parse_mode="Markdown")

        pages = await asyncio.to_thread(get_coin_history, device_id, key_id)
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
        await query.message.reply_text(f"❌ *Insufficient Balance!*\nआपके पास ₹{amount} निकालने के लिए पर्याप्त बैलेंस কমপক্ষে नहीं है।\n\nपहले *Complete Today Task* करें।", reply_markup=get_main_menu(), parse_mode="Markdown")
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

    if not await is_user_subscribed(context.bot, query.from_user.id):
        await send_force_sub_message(query.message)
        return ConversationHandler.END

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

    await update.message.reply_text("⏳ <b>Creating account...</b> कृपया wait करें।", parse_mode="HTML")

    device_id, base64_id, numeric_key, debug_msg = await asyncio.to_thread(create_account, email, full_name, phone)
    
    if not device_id:
        error_text = (
            f"❌ <b>Account creation failed!</b>\n\n"
            f"🔍 <b>DEBUG INFO:</b>\n<code>{debug_msg}</code>\n\n"
            f"शायद email already exist या server error. कृपया फिर try करें।"
        )
        await update.message.reply_text(error_text, reply_markup=get_main_menu(), parse_mode="HTML")
        return ConversationHandler.END

    account_data = {
        "device_id": device_id,
        "base64_id": base64_id,
        "numeric_key": numeric_key,
        "email": email,
        "full_name": full_name,
        "phone": phone,
        "refer_code": REFER_CODE,
        "created_at": datetime.now().isoformat()
    }
    
    chat_id = update.effective_chat.id
    accounts = await asyncio.to_thread(firebase_read, f"turbo/{chat_id}/accounts") or []
    accounts.append(account_data)
    await asyncio.to_thread(firebase_write, f"turbo/{chat_id}/accounts", accounts)

    success_msg = (
        f"✅ <b>Account Created Successfully!</b>\n\n"
        f"📧 Email: {email}\n"
        f"👤 Name: {full_name}\n"
        f"📱 Phone: {phone}\n"
        f"🆔 Device ID: <code>{device_id}</code>\n"
        f"🔑 Base64 ID (key_id): <code>{base64_id}</code>\n"
        f"🔢 Numeric Key: <code>{numeric_key}</code>\n\n"
        "अब आप <b>Complete Today Task</b> कर सकते हैं या <b>My Account</b> से देख सकते हैं।"
    )
    
    try:
        await update.message.reply_text(success_msg, reply_markup=get_main_menu(), parse_mode="HTML")
    except Exception as e:
        print(f"[ERROR] Failed to send success message: {e}")
        await update.message.reply_text("✅ Account Created Successfully! (Check 'My Account')", reply_markup=get_main_menu())

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
    # Register the broadcast command handler
    application.add_handler(CommandHandler("broadcast", broadcast))

    application.add_handler(CallbackQueryHandler(
        button_callback,
        pattern="^(my_account|view_acc_\\d+|do_task|balance|history|withdraw|back_main|withdraw_\\d+|support|verify_sub)$"
    ))

    application.run_polling()

if __name__ == "__main__":
    main()
