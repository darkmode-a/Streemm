import os
import json
import asyncio
import logging
import threading
import time
from datetime import datetime
from telebot import TeleBot, types
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.phone import JoinGroupCallRequest
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

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

bot = TeleBot(BOT_TOKEN, threaded=True, parse_mode="HTML")

DATABASE_FILE = "combo_database.json"

def load_db():
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, 'r') as f:
            return json.load(f)
    return {
        "accounts": {},
        "states": {},
        "pending": {}
    }

def save_db():
    with open(DATABASE_FILE, 'w') as f:
        json.dump(db, f, indent=2)

db = load_db()
active_clients = {}

def get_main_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_add = types.InlineKeyboardButton("📱 Add Number", callback_data="add_number")
    btn_stream = types.InlineKeyboardButton("📡 Stream", callback_data="stream")
    btn_accounts = types.InlineKeyboardButton("👥 My Accounts", callback_data="my_accounts")
    btn_help = types.InlineKeyboardButton("ℹ️ Help", callback_data="help")
    markup.add(btn_add, btn_stream)
    markup.add(btn_accounts, btn_help)
    return markup

def get_cancel():
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_cancel = types.InlineKeyboardButton("❌ Cancel", callback_data="cancel")
    markup.add(btn_cancel)
    return markup

def get_otp_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_resend = types.InlineKeyboardButton("🔄 Resend OTP", callback_data="resend_otp")
    btn_cancel = types.InlineKeyboardButton("❌ Cancel", callback_data="cancel")
    markup.add(btn_resend, btn_cancel)
    return markup

def is_admin(user_id):
    return user_id == ADMIN_ID

@bot.message_handler(commands=['start'])
def cmd_start(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ <b>Unauthorized access.</b>")
        return
    
    db["states"][str(message.from_user.id)] = "idle"
    save_db()
    
    text = """
🤖 <b>Combo Bot - All In One</b>
━━━━━━━━━━━━━━━━━━━━

<b>Available Features:</b>
📱 <b>Add Number</b> - Login accounts with OTP
📡 <b>Stream</b> - Join VC with all accounts
👥 <b>My Accounts</b> - View stored accounts

<b>How to use:</b>
1️⃣ Click <b>Add Number</b>
2️⃣ Send phone number (+91XXXXXXXXXX)
3️⃣ OTP will be sent to that number
4️⃣ Enter OTP - account gets stored
5️⃣ Click <b>Stream</b> and send VC link
6️⃣ All accounts will join the stream

━━━━━━━━━━━━━━━━━━━━
<i>💡 Unlimited accounts supported!</i>
"""
    bot.reply_to(message, text, reply_markup=get_main_menu(), disable_web_page_preview=True)

@bot.message_handler(commands=['help'])
def cmd_help(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ <b>Unauthorized.</b>")
        return
    
    text = """
📚 <b>Help & Instructions</b>
━━━━━━━━━━━━━━━━━━━━

<b>📱 Add Number:</b>
• Click button
• Send phone number with country code
• Example: <code>+919876543210</code>
• OTP will arrive on that number
• Enter OTP to complete login

<b>📡 Stream:</b>
• Click button
• Send voice chat link
• All accounts will join automatically

━━━━━━━━━━━━━━━━━━━━
"""
    bot.reply_to(message, text, disable_web_page_preview=True)

@bot.callback_query_handler(func=lambda call: call.data == "add_number")
def cb_add_number(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ Unauthorized", show_alert=True)
        return
    
    db["states"][str(call.from_user.id)] = "awaiting_number"
    save_db()
    
    bot.edit_message_text(
        "📱 <b>Send your phone number:</b>\n\nFormat: <code>+919876543210</code>\n\nInclude country code.",
        chat_id=call.from_user.id,
        message_id=call.message.message_id,
        reply_markup=get_cancel()
    )
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: db["states"].get(str(m.from_user.id)) == "awaiting_number")
def handle_number(m):
    user_id = m.from_user.id
    phone = m.text.strip()
    
    clean = phone.replace("+", "").replace(" ", "").replace("-", "")
    
    if not clean.isdigit() or len(clean) < 10 or len(clean) > 15:
        bot.reply_to(m, "❌ <b>Invalid number!</b>\n\nSend like: <code>+919876543210</code>", reply_markup=get_cancel())
        return
    
    db["states"][str(user_id)] = "awaiting_otp"
    db["pending"][str(user_id)] = {"phone": clean}
    save_db()
    
    status_msg = bot.reply_to(m, "⏳ <b>Sending OTP...</b>")
    
    def send_otp():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            async def send_code_request():
                client = TelegramClient(StringSession(), API_ID, API_HASH)
                await client.connect()
                
                if not await client.is_user_authorized():
                    result = await client.send_code_request(clean)
                    return client, result.phone_code_hash
                return None, None
            
            client, phone_code_hash = loop.run_until_complete(send_code_request())
            
            active_clients[str(user_id)] = {
                "client": client,
                "phone": clean,
                "code_hash": phone_code_hash,
                "loop": loop,
                "timestamp": time.time()
            }
            
            bot.edit_message_text(
                f"✅ <b>OTP sent to {clean}!</b>\n\n⚠️ <b>OTP 5 minute tak valid hai!</b>\n\nPlease enter the OTP code:",
                chat_id=user_id,
                message_id=status_msg.message_id,
                reply_markup=get_otp_keyboard()
            )
            
        except Exception as e:
            logger.error(f"OTP error: {e}")
            error_msg = str(e)
            
            if "API_ID" in error_msg or "API_HASH" in error_msg:
                error_msg = "❌ API credentials galat hain."
            elif "FLOOD" in error_msg.upper():
                error_msg = "⚠️ Telegram ne block kiya. 24hrs baad try karo."
            elif "PHONE_NUMBER_INVALID" in error_msg.upper():
                error_msg = "❌ Phone number invalid hai. Format: +919876543210"
            
            bot.edit_message_text(
                f"❌ <b>Failed:</b>\n<code>{error_msg}</code>",
                chat_id=user_id,
                message_id=status_msg.message_id,
                reply_markup=get_main_menu()
            )
            db["states"][str(user_id)] = "idle"
            save_db()
    
    threading.Thread(target=send_otp, daemon=True).start()

@bot.callback_query_handler(func=lambda call: call.data == "resend_otp")
def cb_resend_otp(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ Unauthorized", show_alert=True)
        return
    
    user_id = call.from_user.id
    client_data = active_clients.get(str(user_id))
    
    if not client_data:
        bot.answer_callback_query(call.id, "❌ Session expired. Start again.", show_alert=True)
        return
    
    status_msg = bot.edit_message_text(
        "⏳ <b>Resending OTP...</b>",
        chat_id=user_id,
        message_id=call.message.message_id
    )
    
    def resend_otp():
        try:
            client = client_data["client"]
            phone = client_data["phone"]
            loop = client_data["loop"]
            
            async def resend():
                result = await client.send_code_request(phone)
                return result.phone_code_hash
            
            new_code_hash = loop.run_until_complete(resend())
            
            client_data["code_hash"] = new_code_hash
            client_data["timestamp"] = time.time()
            active_clients[str(user_id)] = client_data
            
            bot.edit_message_text(
                f"✅ <b>New OTP sent!</b>\n\nPlease enter the OTP:",
                chat_id=user_id,
                message_id=status_msg.message_id,
                reply_markup=get_otp_keyboard()
            )
        except Exception as e:
            logger.error(f"Resend error: {e}")
            bot.edit_message_text(
                f"❌ <b>Failed:</b>\n<code>{str(e)}</code>",
                chat_id=user_id,
                message_id=status_msg.message_id,
                reply_markup=get_main_menu()
            )
    
    threading.Thread(target=resend_otp, daemon=True).start()
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: db["states"].get(str(m.from_user.id)) == "awaiting_otp")
def handle_otp(m):
    user_id = m.from_user.id
    otp = m.text.strip()
    
    client_data = active_clients.get(str(user_id))
    if not client_data:
        bot.reply_to(m, "❌ <b>Session expired.</b>\n\nClick Add Number again.", reply_markup=get_main_menu())
        db["states"][str(user_id)] = "idle"
        save_db()
        return
    
    status_msg = bot.reply_to(m, "⏳ <b>Verifying OTP...</b>")
    
    def verify_otp():
        try:
            client = client_data["client"]
            phone = client_data["phone"]
            code_hash = client_data["code_hash"]
            loop = client_data["loop"]
            
            async def sign_in_and_save():
                if not await client.is_user_authorized():
                    try:
                        await client.sign_in(
                            phone=phone,
                            code=otp,
                            phone_code_hash=code_hash
                        )
                    except Exception as e:
                        error_str = str(e)
                        if "2FA" in error_str.upper() or "PASSWORD" in error_str.upper():
                            db["states"][str(user_id)] = "awaiting_2fa"
                            save_db()
                            bot.edit_message_text(
                                "🔐 <b>2FA Password Required!</b>\n\nTelegram password enter karo:",
                                chat_id=user_id,
                                message_id=status_msg.message_id,
                                reply_markup=get_cancel()
                            )
                            return None
                        elif "EXPIRED" in error_str.upper():
                            bot.edit_message_text(
                                "❌ <b>OTP expire ho gaya!</b>\n\nResend OTP button dabao.",
                                chat_id=user_id,
                                message_id=status_msg.message_id,
                                reply_markup=get_otp_keyboard()
                            )
                            return None
                        else:
                            raise e
                
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
                db["pending"].pop(str(user_id), None)
                save_db()
                
                active_clients.pop(str(user_id), None)
                await client.disconnect()
                
                total = len(db["accounts"][str(user_id)])
                
                bot.edit_message_text(
                    f"🎉 <b>Account Added!</b>\n\n📱 {phone}\n👤 {me.first_name}\n📊 Total: {total}",
                    chat_id=user_id,
                    message_id=status_msg.message_id,
                    reply_markup=get_main_menu()
                )
                
                return me
            
            loop.run_until_complete(sign_in_and_save())
            
        except Exception as e:
            logger.error(f"Verify error: {e}")
            active_clients.pop(str(user_id), None)
            bot.edit_message_text(
                f"❌ <b>Failed:</b>\n<code>{str(e)}</code>",
                chat_id=user_id,
                message_id=status_msg.message_id,
                reply_markup=get_otp_keyboard()
            )
    
    threading.Thread(target=verify_otp, daemon=True).start()

@bot.message_handler(func=lambda m: db["states"].get(str(m.from_user.id)) == "awaiting_2fa")
def handle_2fa(m):
    user_id = m.from_user.id
    password = m.text.strip()
    
    client_data = active_clients.get(str(user_id))
    if not client_data:
        bot.reply_to(m, "❌ <b>Session expired.</b>", reply_markup=get_main_menu())
        return
    
    status_msg = bot.reply_to(m, "⏳ <b>Verifying Password...</b>")
    
    def verify_2fa():
        try:
            client = client_data["client"]
            phone = client_data["phone"]
            loop = client_data["loop"]
            
            async def complete_2fa():
                await client.sign_in(password=password)
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
                db["pending"].pop(str(user_id), None)
                save_db()
                
                active_clients.pop(str(user_id), None)
                await client.disconnect()
                
                total = len(db["accounts"][str(user_id)])
                
                bot.edit_message_text(
                    f"🎉 <b>Account Added!</b>\n\n📱 {phone}\n👤 {me.first_name}\n📊 Total: {total}",
                    chat_id=user_id,
                    message_id=status_msg.message_id,
                    reply_markup=get_main_menu()
                )
            
            loop.run_until_complete(complete_2fa())
            
        except Exception as e:
            logger.error(f"2FA error: {e}")
            active_clients.pop(str(user_id), None)
            bot.edit_message_text(
                f"❌ <b>Failed:</b>\n<code>{str(e)}</code>",
                chat_id=user_id,
                message_id=status_msg.message_id,
                reply_markup=get_cancel()
            )
    
    threading.Thread(target=verify_2fa, daemon=True).start()

@bot.callback_query_handler(func=lambda call: call.data == "stream")
def cb_stream(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ Unauthorized", show_alert=True)
        return
    
    accounts = db["accounts"].get(str(call.from_user.id), [])
    
    if not accounts:
        bot.answer_callback_query(call.id, "❌ No accounts! Add first.", show_alert=True)
        return
    
    db["states"][str(call.from_user.id)] = "awaiting_stream"
    save_db()
    
    bot.edit_message_text(
        f"📡 <b>Send VC Link:</b>\n\nAccounts: <b>{len(accounts)}</b>",
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
    
    status_msg = bot.reply_to(m, f"🚀 <b>Joining {len(accounts)} accounts...</b>", reply_markup=get_main_menu())
    
    def join_stream():
        success = 0
        failed = 0
        channel = link.rstrip("/").split("/")[-1].split("?")[0]
        
        for i, acc in enumerate(accounts, 1):
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                async def join_vc():
                    client = TelegramClient(StringSession(acc["session"]), API_ID, API_HASH)
                    await client.connect()
                    entity = await client.get_entity(channel)
                    await client(JoinChannelRequest(entity))
                    await asyncio.sleep(0.5)
                    try:
                        me = await client.get_me()
                        await client(JoinGroupCallRequest(
                            call=entity,
                            params=DataJSON(data={}),
                            muted=False,
                            join_as=me
                        ))
                    except Exception as vc_err:
                        logger.warning(f"VC error: {vc_err}")
                    await client.disconnect()
                
                loop.run_until_complete(join_vc())
                success += 1
                
                try:
                    bot.edit_message_text(
                        f"🚀 <b>Joining...</b>\n\n✅ {i}/{len(accounts)}",
                        chat_id=user_id,
                        message_id=status_msg.message_id
                    )
                except:
                    pass
                
            except Exception as e:
                failed += 1
            
            time.sleep(2)
        
        bot.edit_message_text(
            f"✅ <b>Done!</b>\n\n✅ Success: {success}\n❌ Failed: {failed}",
            chat_id=user_id,
            message_id=status_msg.message_id,
            reply_markup=get_main_menu()
        )
    
    threading.Thread(target=join_stream, daemon=True).start()

@bot.callback_query_handler(func=lambda call: call.data == "my_accounts")
def cb_accounts(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔", show_alert=True)
        return
    
    accounts = db["accounts"].get(str(call.from_user.id), [])
    account_list = ""
    
    for i, acc in enumerate(accounts, 1):
        name = acc.get("name", "Unknown")
        account_list += f"\n{i}. <code>{acc['phone']}</code> - {name}"
    
    text = f"👥 <b>Total: {len(accounts)}</b>{account_list}"
    bot.edit_message_text(text, chat_id=call.from_user.id, message_id=call.message.message_id, reply_markup=get_main_menu())
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "help")
def cb_help(call):
    text = "📚 <b>Help:</b>\n\n1️⃣ Add Number\n2️⃣ Stream\n3️⃣ My Accounts"
    bot.edit_message_text(text, chat_id=call.from_user.id, message_id=call.message.message_id, reply_markup=get_main_menu())
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "cancel")
def cb_cancel(call):
    db["states"][str(call.from_user.id)] = "idle"
    active_clients.pop(str(call.from_user.id), None)
    db["pending"].pop(str(call.from_user.id), None)
    save_db()
    bot.edit_message_text("❌ <b>Cancelled.</b>", chat_id=call.from_user.id, message_id=call.message.message_id, reply_markup=get_main_menu())
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
