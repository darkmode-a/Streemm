import os
import json
import asyncio
import logging
import threading
import time
import re
from datetime import datetime
from telebot import TeleBot, types
from telethon import TelegramClient, functions as tl_functions
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from telethon.tl.types import DataJSON
from flask import Flask

BOT_TOKEN = "8920720185:AAF2sj4Rl_5XY3-Ohhc1X60G0yLYMBjSAIc"
ADMIN_ID = 7374203179
API_ID = 35055508
API_HASH = "e5b9b02c6a3e789158d243fd2a0e24b4"

app = Flask(__name__)

@app.route('/')
def home():
    return "Combo Bot is running!"

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

bot = TeleBot(BOT_TOKEN, threaded=True, parse_mode="HTML")

DATABASE_FILE = "combo_database.json"

def load_db():
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, 'r') as f:
            return json.load(f)
    return {"accounts": {}, "states": {}, "pending": {}}

def save_db():
    with open(DATABASE_FILE, 'w') as f:
        json.dump(db, f, indent=2)

db = load_db()

telethon_loop = asyncio.new_event_loop()
telethon_thread = threading.Thread(target=telethon_loop.run_forever, daemon=True)
telethon_thread.start()

active_clients = {}

def run_async(coro):
    future = asyncio.run_coroutine_threadsafe(coro, telethon_loop)
    return future.result(timeout=120)

def get_main_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📱 Add Number", callback_data="add_number"),
        types.InlineKeyboardButton("📡 Stream", callback_data="stream")
    )
    markup.add(
        types.InlineKeyboardButton("👥 My Accounts", callback_data="my_accounts"),
        types.InlineKeyboardButton("ℹ️ Help", callback_data="help")
    )
    return markup

def get_cancel():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("❌ Cancel", callback_data="cancel"))
    return markup

def is_admin(user_id):
    return user_id == ADMIN_ID

@bot.message_handler(commands=['start'])
def cmd_start(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ Unauthorized")
        return
    db["states"][str(message.from_user.id)] = "idle"
    save_db()
    
    text = (
        "🤖 <b>Combo Bot - All In One</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "📱 <b>Add Number:</b> Login accounts safely\n"
        "📡 <b>Stream:</b> Join VC with all accounts\n"
        "👥 <b>My Accounts:</b> View saved accounts\n"
    )
    bot.reply_to(message, text, reply_markup=get_main_menu())

@bot.callback_query_handler(func=lambda call: call.data == "add_number")
def cb_add_number(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔", show_alert=True)
        return
    db["states"][str(call.from_user.id)] = "awaiting_number"
    save_db()
    bot.edit_message_text(
        "📱 <b>Send your phone number:</b>\n\nFormat: <code>+919876543210</code>",
        chat_id=call.from_user.id,
        message_id=call.message.message_id,
        reply_markup=get_cancel()
    )
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: db["states"].get(str(m.from_user.id)) == "awaiting_number")
def handle_number(m):
    user_id = m.from_user.id
    phone = m.text.strip().replace("+", "").replace(" ", "").replace("-", "")
    
    if not phone.isdigit() or len(phone) < 10:
        bot.reply_to(m, "❌ Invalid number format. Use: <code>+919876543210</code>", reply_markup=get_cancel())
        return
    
    db["states"][str(user_id)] = "awaiting_otp"
    save_db()
    
    status_msg = bot.reply_to(m, "⏳ <b>Connecting & sending OTP...</b>")
    
    def send_otp():
        async def _send():
            client = TelegramClient(StringSession(), API_ID, API_HASH)
            await client.connect()
            result = await client.send_code_request(phone)
            active_clients[str(user_id)] = {
                "client": client,
                "phone": phone,
                "code_hash": result.phone_code_hash
            }
            return result.phone_code_hash
        
        try:
            run_async(_send())
            msg = (
                f"✅ <b>OTP sent to +{phone}!</b>\n\n"
                f"📥 Please enter your OTP with watermark/quotes format:\n"
                f"👉 <code>mrking\"83838\"</code>\n\n"
                f"<i>(Bot automatically extracts exact numbers safely)</i>"
            )
            bot.edit_message_text(msg, chat_id=user_id, message_id=status_msg.message_id, reply_markup=get_cancel())
        except Exception as e:
            bot.edit_message_text(f"❌ Failed: {str(e)}", chat_id=user_id, message_id=status_msg.message_id, reply_markup=get_main_menu())
            db["states"][str(user_id)] = "idle"
            save_db()
    
    threading.Thread(target=send_otp, daemon=True).start()

# ========== SMART OTP EXTRACTION (ANTI-PHISHING BYPASS) ==========
@bot.message_handler(func=lambda m: db["states"].get(str(m.from_user.id)) == "awaiting_otp")
def handle_otp(m):
    user_id = m.from_user.id
    raw_text = m.text.strip()
    
    digits_found = re.findall(r'\d+', raw_text)
    if not digits_found:
        bot.reply_to(m, "❌ <b>Koi OTP nahi mila!</b>\nKripya is format me bhejein:\n<code>mrking\"83838\"</code>", reply_markup=get_cancel())
        return
    
    otp = "".join(digits_found)
    
    client_data = active_clients.get(str(user_id))
    if not client_data:
        bot.reply_to(m, "❌ Session expired. Start again.", reply_markup=get_main_menu())
        db["states"][str(user_id)] = "idle"
        save_db()
        return
    
    status_msg = bot.reply_to(m, f"⏳ <b>Verifying OTP Code: <code>{otp}</code>...</b>")
    
    def verify_otp():
        async def _verify():
            client = client_data["client"]
            phone = client_data["phone"]
            code_hash = client_data["code_hash"]
            
            try:
                await client.sign_in(phone=phone, code=otp, phone_code_hash=code_hash)
            except SessionPasswordNeededError:
                db["states"][str(user_id)] = "awaiting_2fa"
                save_db()
                bot.edit_message_text("🔐 <b>2FA Password Required!</b>\nEnter your Telegram password:", chat_id=user_id, message_id=status_msg.message_id, reply_markup=get_cancel())
                return
            
            session_string = client.session.save()
            me = await client.get_me()
            
            if str(user_id) not in db["accounts"]:
                db["accounts"][str(user_id)] = []
            
            db["accounts"][str(user_id)].append({
                "phone": phone,
                "session": session_string,
                "name": me.first_name or "Unknown",
                "username": me.username or "",
                "added_at": datetime.now().isoformat()
            })
            
            db["states"][str(user_id)] = "idle"
            save_db()
            await client.disconnect()
            active_clients.pop(str(user_id), None)
            
            total = len(db["accounts"][str(user_id)])
            bot.edit_message_text(
                f"🎉 <b>Account Added Successfully!</b>\n\n📱 +{phone}\n👤 {me.first_name}\n📊 Total Accounts: {total}",
                chat_id=user_id,
                message_id=status_msg.message_id,
                reply_markup=get_main_menu()
            )
        
        try:
            run_async(_verify())
        except Exception as e:
            bot.edit_message_text(f"❌ Verification Failed: {str(e)}", chat_id=user_id, message_id=status_msg.message_id, reply_markup=get_cancel())
    
    threading.Thread(target=verify_otp, daemon=True).start()

@bot.message_handler(func=lambda m: db["states"].get(str(m.from_user.id)) == "awaiting_2fa")
def handle_2fa(m):
    user_id = m.from_user.id
    password = m.text.strip()
    
    client_data = active_clients.get(str(user_id))
    if not client_data:
        bot.reply_to(m, "❌ Session expired.", reply_markup=get_main_menu())
        return
    
    status_msg = bot.reply_to(m, "⏳ <b>Verifying 2FA Password...</b>")
    
    def verify_2fa():
        async def _2fa():
            client = client_data["client"]
            await client.sign_in(password=password)
            
            session_string = client.session.save()
            me = await client.get_me()
            
            if str(user_id) not in db["accounts"]:
                db["accounts"][str(user_id)] = []
            
            db["accounts"][str(user_id)].append({
                "phone": client_data["phone"],
                "session": session_string,
                "name": me.first_name or "Unknown",
                "username": me.username or "",
                "added_at": datetime.now().isoformat()
            })
            
            db["states"][str(user_id)] = "idle"
            save_db()
            await client.disconnect()
            active_clients.pop(str(user_id), None)
            
            bot.edit_message_text(
                f"🎉 <b>Account Added with 2FA!</b>\n\n📱 +{client_data['phone']}\n👤 {me.first_name}",
                chat_id=user_id,
                message_id=status_msg.message_id,
                reply_markup=get_main_menu()
            )
        
        try:
            run_async(_2fa())
        except Exception as e:
            bot.edit_message_text(f"❌ 2FA Failed: {str(e)}", chat_id=user_id, message_id=status_msg.message_id, reply_markup=get_cancel())
    
    threading.Thread(target=verify_2fa, daemon=True).start()

# ========== STREAM & VOICE CHAT JOIN SYSTEM (SMART PARSER + DIRECT VC) ==========
@bot.callback_query_handler(func=lambda call: call.data == "stream")
def cb_stream(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔", show_alert=True)
        return
    accounts = db["accounts"].get(str(call.from_user.id), [])
    if not accounts:
        bot.answer_callback_query(call.id, "❌ No accounts added yet!", show_alert=True)
        return
    db["states"][str(call.from_user.id)] = "awaiting_stream"
    save_db()
    bot.edit_message_text(
        f"📡 <b>Send Channel Link (VC Link):</b>\n\nActive Accounts: {len(accounts)}",
        chat_id=call.from_user.id,
        message_id=call.message.message_id,
        reply_markup=get_cancel()
    )
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: db["states"].get(str(m.from_user.id)) == "awaiting_stream")
def handle_stream(m):
    user_id = m.from_user.id
    link = m.text.strip()
    db["states"][str(user_id)] = "idle"
    save_db()
    accounts = db["accounts"].get(str(user_id), [])
    
    status_msg = bot.reply_to(m, f"🚀 <b>Joining {len(accounts)} accounts to VC...</b>", reply_markup=get_main_menu())
    
    # 🔍 Smart Link Parser (Ignores message IDs like /123 and handles post links securely)
    clean_link = link.split("?")[0].rstrip("/")
    parts = [p for p in clean_link.split("/") if p and p not in ["https:", "http:", "t.me", "telegram.dog"]]
    
    username = parts[0] if parts else ""
    username = username.replace("@", "").strip()
    
    if not username:
        bot.edit_message_text("❌ <b>Invalid link!</b> Kripya sahi channel link bhejein.", chat_id=user_id, message_id=status_msg.message_id, reply_markup=get_main_menu())
        return

    def join_stream():
        success = 0
        failed = 0
        
        for i, acc in enumerate(accounts, 1):
            async def _join_vc():
                client = TelegramClient(StringSession(acc["session"]), API_ID, API_HASH)
                await client.connect()
                
                try:
                    me = await client.get_me()
                    entity = await client.get_entity(username)
                    
                    # Get full channel - call object ke liye
                    full_channel = await client(tl_functions.channels.GetFullChannelRequest(entity))
                    
                    if full_channel and full_channel.full_chat and full_channel.full_chat.call:
                        call_obj = full_channel.full_chat.call
                        
                        # DIRECT VC JOIN - SSRC Retry logic ke sath (3 attempts)
                        for retry in range(3):
                            try:
                                await client(tl_functions.phone.JoinGroupCallRequest(
                                    call=call_obj,
                                    params=DataJSON(data="{}"),
                                    muted=False,
                                    join_as=me
                                ))
                                await client.disconnect()
                                return True
                            except Exception as e:
                                error_str = str(e)
                                if "SSRC" in error_str.upper() or "RETRY" in error_str.upper():
                                    await asyncio.sleep(2)
                                    continue
                                else:
                                    raise e
                        
                        await client.disconnect()
                        return False
                    else:
                        logger.warning(f"No active VC for {username}")
                        await client.disconnect()
                        return False
                        
                except Exception as e:
                    logger.error(f"VC join failed for {acc['phone']}: {e}")
                    try:
                        await client.disconnect()
                    except:
                        pass
                    return False
            
            try:
                joined = run_async(_join_vc())
                if joined:
                    success += 1
                else:
                    failed += 1
            except:
                failed += 1
            
            try:
                bot.edit_message_text(
                    f"🚀 <b>Joining VC...</b>\nTarget: <code>@{username}</code>\n✅ Success: {success}\n❌ Failed: {failed}",
                    chat_id=user_id,
                    message_id=status_msg.message_id
                )
            except:
                pass
            
            time.sleep(2)
        
        bot.edit_message_text(
            f"✅ <b>Complete!</b>\n\nTarget: <code>@{username}</code>\n✅ Success: {success}\n❌ Failed: {failed}",
            chat_id=user_id,
            message_id=status_msg.message_id,
            reply_markup=get_main_menu()
        )
    
    threading.Thread(target=join_stream, daemon=True).start()

# ========== OTHER HANDLERS ==========
@bot.callback_query_handler(func=lambda call: call.data == "my_accounts")
def cb_accounts(call):
    accounts = db["accounts"].get(str(call.from_user.id), [])
    account_list = ""
    for i, acc in enumerate(accounts, 1):
        account_list += f"\n{i}. <code>+{acc['phone']}</code> - {acc.get('name', 'Unknown')}"
    
    text = f"👥 <b>Saved Accounts (Total: {len(accounts)})</b>\n━━━━━━━━━━━━━━━━━━━━{account_list}"
    bot.edit_message_text(text, chat_id=call.from_user.id, message_id=call.message.message_id, reply_markup=get_main_menu())
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "help")
def cb_help(call):
    help_text = (
        "📚 <b>Bot Instructions:</b>\n\n"
        "1️⃣ Click <b>Add Number</b> & send phone number.\n"
        "2️⃣ Send OTP with watermark format: <code>mrking\"83838\"</code>\n"
        "3️⃣ Click <b>Stream</b> & send channel link to join VC automatically."
    )
    bot.edit_message_text(help_text, chat_id=call.from_user.id, message_id=call.message.message_id, reply_markup=get_main_menu())
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "cancel")
def cb_cancel(call):
    db["states"][str(call.from_user.id)] = "idle"
    active_clients.pop(str(call.from_user.id), None)
    save_db()
    bot.edit_message_text("❌ <b>Operation Cancelled.</b>", chat_id=call.from_user.id, message_id=call.message.message_id, reply_markup=get_main_menu())
    bot.answer_callback_query(call.id)

def run_bot():
    logger.info("Combo Bot starting...")
    try:
        bot_info = bot.get_me()
        logger.info(f"Logged in as @{bot_info.username}")
        bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)
    except Exception as e:
        logger.critical(f"Critical error: {e}")

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
