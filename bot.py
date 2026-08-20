import os
import json
import asyncio
import logging
import threading
import time
from datetime import datetime
from telebot import TeleBot, types
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.phone import JoinGroupCallRequest
from telethon.tl.types import DataJSON

# ==========================================
# CONFIGURATION
# ==========================================
BOT_TOKEN = "8920720185:AAF2sj4Rl_5XY3-Ohhc1X60G0yLYMBjSAIc"
ADMIN_ID = 7374203179

# Your Telegram API credentials
API_ID = 35055508
API_HASH = "e5b9b02c6a3e789158d243fd2a0e24b4"

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot initialize
bot = TeleBot(BOT_TOKEN, threaded=True, parse_mode="HTML")

# ==========================================
# DATABASE
# ==========================================
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

# ==========================================
# KEYBOARDS
# ==========================================
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

def is_admin(user_id):
    return user_id == ADMIN_ID

# ==========================================
# COMMANDS
# ==========================================
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
    logger.info(f"Welcome sent to {message.from_user.first_name}")

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

# ==========================================
# ADD NUMBER SYSTEM
# ==========================================
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
            
            client = TelegramClient(StringSession(), API_ID, API_HASH)
            client.connect()
            
            result = client.send_code_request(clean)
            
            active_clients[str(user_id)] = {
                "client": client,
                "phone": clean,
                "code_hash": result.phone_code_hash
            }
            
            bot.edit_message_text(
                f"✅ <b>OTP sent to {clean}!</b>\n\nPlease enter the OTP code:",
                chat_id=user_id,
                message_id=status_msg.message_id,
                reply_markup=get_cancel()
            )
        except Exception as e:
            logger.error(f"OTP error: {e}")
            bot.edit_message_text(
                f"❌ <b>Failed to send OTP:</b>\n<code>{str(e)}</code>",
                chat_id=user_id,
                message_id=status_msg.message_id,
                reply_markup=get_main_menu()
            )
            db["states"][str(user_id)] = "idle"
            save_db()
    
    threading.Thread(target=send_otp, daemon=True).start()

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
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            client = client_data["client"]
            phone = client_data["phone"]
            code_hash = client_data["code_hash"]
            
            client.sign_in(phone=phone, code=otp, phone_code_hash=code_hash)
            
            session_string = client.session.save()
            me = client.get_me()
            
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
            active_clients.pop(str(user_id), None)
            db["pending"].pop(str(user_id), None)
            save_db()
            
            total = len(db["accounts"][str(user_id)])
            
            bot.edit_message_text(
                f"🎉 <b>Account Added Successfully!</b>\n━━━━━━━━━━━━━━━━━━━━\n\n📱 <b>Phone:</b> <code>{phone}</code>\n👤 <b>Name:</b> {me.first_name}\n📊 <b>Total Accounts:</b> {total}",
                chat_id=user_id,
                message_id=status_msg.message_id,
                reply_markup=get_main_menu()
            )
        except Exception as e:
            logger.error(f"Verify error: {e}")
            bot.edit_message_text(
                f"❌ <b>OTP verification failed:</b>\n<code>{str(e)}</code>",
                chat_id=user_id,
                message_id=status_msg.message_id,
                reply_markup=get_cancel()
            )
    
    threading.Thread(target=verify_otp, daemon=True).start()

# ==========================================
# STREAM SYSTEM
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data == "stream")
def cb_stream(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ Unauthorized", show_alert=True)
        return
    
    accounts = db["accounts"].get(str(call.from_user.id), [])
    
    if not accounts:
        bot.answer_callback_query(call.id, "❌ No accounts! Add numbers first.", show_alert=True)
        return
    
    db["states"][str(call.from_user.id)] = "awaiting_stream"
    save_db()
    
    bot.edit_message_text(
        f"📡 <b>Send Voice Chat Link:</b>\n\nAccounts ready: <b>{len(accounts)}</b>\n\nExample: <code>https://t.me/channelname</code>",
        chat_id=call.from_user.id,
        message_id=call.message.message_id,
        reply_markup=get_cancel()
    )
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: db["states"].get(str(m.from_user.id)) == "awaiting_stream")
def handle_stream(m):
    user_id = m.from_user.id
    link = m.text.strip()
    
    if "t.me" not in link and "telegram" not in link:
        bot.reply_to(m, "❌ <b>Invalid link!</b>\n\nSend a Telegram channel/group link.", reply_markup=get_cancel())
        return
    
    db["states"][str(user_id)] = "idle"
    save_db()
    
    accounts = db["accounts"].get(str(user_id), [])
    
    status_msg = bot.reply_to(m, f"🚀 <b>Stream Join Started!</b>\n━━━━━━━━━━━━━━━━━━━━\n\n📊 Accounts: {len(accounts)}\n🔗 Link: {link}\n\n<i>Joining all accounts...</i>", reply_markup=get_main_menu())
    
    def join_stream():
        success = 0
        failed = 0
        
        channel = link.rstrip("/").split("/")[-1].split("?")[0]
        
        for i, acc in enumerate(accounts, 1):
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                client = TelegramClient(StringSession(acc["session"]), API_ID, API_HASH)
                client.connect()
                
                entity = client.get_entity(channel)
                
                client(JoinChannelRequest(entity))
                time.sleep(0.5)
                
                try:
                    client(JoinGroupCallRequest(
                        call=entity,
                        params=DataJSON(data={}),
                        muted=False,
                        join_as=client.get_me()
                    ))
                except Exception as vc_err:
                    logger.warning(f"VC join error for {acc['phone']}: {vc_err}")
                
                client.disconnect()
                success += 1
                
                try:
                    bot.edit_message_text(
                        f"🚀 <b>Joining Accounts...</b>\n━━━━━━━━━━━━━━━━━━━━\n\n✅ Done: {i}/{len(accounts)}\n👤 Current: {acc['phone']}",
                        chat_id=user_id,
                        message_id=status_msg.message_id,
                        reply_markup=get_main_menu()
                    )
                except:
                    pass
                
            except Exception as e:
                logger.error(f"Failed {acc['phone']}: {e}")
                failed += 1
            
            time.sleep(2)
        
        bot.edit_message_text(
            f"✅ <b>Stream Join Complete!</b>\n━━━━━━━━━━━━━━━━━━━━\n\n📊 Total: {len(accounts)}\n✅ Success: {success}\n❌ Failed: {failed}",
            chat_id=user_id,
            message_id=status_msg.message_id,
            reply_markup=get_main_menu()
        )
    
    threading.Thread(target=join_stream, daemon=True).start()

# ==========================================
# MY ACCOUNTS
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data == "my_accounts")
def cb_accounts(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ Unauthorized", show_alert=True)
        return
    
    accounts = db["accounts"].get(str(call.from_user.id), [])
    account_list = ""
    
    for i, acc in enumerate(accounts, 1):
        name = acc.get("name", "Unknown")
        account_list += f"\n{i}. <code>{acc['phone']}</code> - {name}"
    
    text = f"""
👥 <b>My Accounts</b>
━━━━━━━━━━━━━━━━━━━━

<b>Total:</b> {len(accounts)}
{account_list if account_list else "\n<i>No accounts added yet.</i>"}

━━━━━━━━━━━━━━━━━━━━
"""
    bot.edit_message_text(
        text,
        chat_id=call.from_user.id,
        message_id=call.message.message_id,
        reply_markup=get_main_menu()
    )
    bot.answer_callback_query(call.id)

# ==========================================
# HELP CALLBACK
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data == "help")
def cb_help(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ Unauthorized", show_alert=True)
        return
    
    text = """
📚 <b>How To Use</b>
━━━━━━━━━━━━━━━━━━━━

1️⃣ <b>Add Number:</b>
   Click → Send number → Get OTP → Enter OTP

2️⃣ <b>Stream:</b>
   Click → Send VC link → Bot joins all accounts

3️⃣ <b>My Accounts:</b>
   View all stored accounts

━━━━━━━━━━━━━━━━━━━━
"""
    bot.edit_message_text(
        text,
        chat_id=call.from_user.id,
        message_id=call.message.message_id,
        reply_markup=get_main_menu()
    )
    bot.answer_callback_query(call.id)

# ==========================================
# CANCEL
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data == "cancel")
def cb_cancel(call):
    db["states"][str(call.from_user.id)] = "idle"
    active_clients.pop(str(call.from_user.id), None)
    db["pending"].pop(str(call.from_user.id), None)
    save_db()
    
    bot.edit_message_text(
        "❌ <b>Operation cancelled.</b>",
        chat_id=call.from_user.id,
        message_id=call.message.message_id,
        reply_markup=get_main_menu()
    )
    bot.answer_callback_query(call.id)

# ==========================================
# MAIN
# ==========================================
def main():
    print("""
╔════════════════════════════════════╗
║     COMBO BOT STARTING...          ║
╚════════════════════════════════════╝
    """)
    
    logger.info("Combo Bot starting...")
    
    try:
        bot_info = bot.get_me()
        logger.info(f"Logged in as @{bot_info.username}")
        logger.info(f"Admin: {ADMIN_ID}")
        logger.info("Bot is now polling for updates...")
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        logger.critical(f"Critical error: {e}")

if __name__ == "__main__":
    main()