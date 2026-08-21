import os
import json
import asyncio
import logging
import threading
import time
import re
import random
from datetime import datetime
from telebot import TeleBot, types
from telethon import TelegramClient, functions as tl_functions
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from telethon.tl.functions.channels import JoinChannelRequest
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

# ==========================================
# 🧠 ACCOUNT BRAIN SYSTEM
# ==========================================

class AccountBrain:
    """Har account ko alag human-like behavior deta hai"""
    
    def __init__(self, account):
        self.account = account
        self.behavior = random.choice(["normal", "fast", "slow", "careful", "aggressive", "stealth"])
        self.mood = random.choice(["fresh", "tired", "excited", "neutral"])
    
    def get_connect_delay(self):
        """Connection se pehle kitna wait kare"""
        if self.behavior == "normal":
            return random.uniform(2, 5)
        elif self.behavior == "fast":
            return random.uniform(0.5, 2)
        elif self.behavior == "slow":
            return random.uniform(5, 10)
        elif self.behavior == "careful":
            return random.uniform(4, 7)
        elif self.behavior == "aggressive":
            return random.uniform(1, 3)
        else:
            return random.uniform(3, 8)
    
    def get_join_strategy(self):
        """Alag-alag join strategies"""
        strategies = ["direct", "wait_retry", "stealth_muted", "channel_then_vc"]
        weights = [0.3, 0.3, 0.2, 0.2]
        return random.choices(strategies, weights=weights)[0]
    
    def get_retry_count(self):
        """Kitni baar retry kare"""
        if self.behavior == "aggressive":
            return 5
        elif self.behavior == "careful":
            return 2
        elif self.behavior == "stealth":
            return 3
        else:
            return random.randint(2, 4)
    
    def get_retry_delay(self):
        """Retry ke beech kitna wait kare"""
        return random.uniform(2, 6)
    
    def is_muted(self):
        """Account muted join kare ya nahi"""
        if self.behavior == "stealth":
            return True
        return random.choice([True, False])

# ==========================================
# KEYBOARDS
# ==========================================

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

# ==========================================
# COMMANDS
# ==========================================

@bot.message_handler(commands=['start'])
def cmd_start(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ Unauthorized")
        return
    db["states"][str(message.from_user.id)] = "idle"
    save_db()
    
    text = (
        "🤖 <b>Combo Bot - Advanced Brain</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "📱 <b>Add Number:</b> Login accounts\n"
        "📡 <b>Stream:</b> Smart VC Join\n"
        "👥 <b>My Accounts:</b> View accounts\n\n"
        "<i>🧠 Har account alag human-like behave karega!</i>"
    )
    bot.reply_to(message, text, reply_markup=get_main_menu())

# ==========================================
# ADD NUMBER SYSTEM
# ==========================================

@bot.callback_query_handler(func=lambda call: call.data == "add_number")
def cb_add_number(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔", show_alert=True)
        return
    db["states"][str(call.from_user.id)] = "awaiting_number"
    save_db()
    bot.edit_message_text(
        "📱 <b>Send phone number:</b>\n\nFormat: <code>+919876543210</code>",
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
        bot.reply_to(m, "❌ Invalid number", reply_markup=get_cancel())
        return
    
    db["states"][str(user_id)] = "awaiting_otp"
    save_db()
    
    status_msg = bot.reply_to(m, "⏳ <b>Sending OTP...</b>")
    
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
            bot.edit_message_text(
                f"✅ <b>OTP sent!</b>\n\nEnter OTP:",
                chat_id=user_id,
                message_id=status_msg.message_id,
                reply_markup=get_cancel()
            )
        except Exception as e:
            bot.edit_message_text(f"❌ Failed: {str(e)}", chat_id=user_id, message_id=status_msg.message_id, reply_markup=get_main_menu())
            db["states"][str(user_id)] = "idle"
            save_db()
    
    threading.Thread(target=send_otp, daemon=True).start()

@bot.message_handler(func=lambda m: db["states"].get(str(m.from_user.id)) == "awaiting_otp")
def handle_otp(m):
    user_id = m.from_user.id
    raw_text = m.text.strip()
    
    digits_found = re.findall(r'\d+', raw_text)
    if not digits_found:
        bot.reply_to(m, "❌ OTP nahi mila!", reply_markup=get_cancel())
        return
    
    otp = "".join(digits_found)
    
    client_data = active_clients.get(str(user_id))
    if not client_data:
        bot.reply_to(m, "❌ Session expired.", reply_markup=get_main_menu())
        return
    
    status_msg = bot.reply_to(m, f"⏳ <b>Verifying OTP...</b>")
    
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
                bot.edit_message_text("🔐 <b>2FA Password:</b>", chat_id=user_id, message_id=status_msg.message_id, reply_markup=get_cancel())
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
                f"🎉 <b>Account Added!</b>\n\n📱 +{phone}\n👤 {me.first_name}\n📊 Total: {total}",
                chat_id=user_id,
                message_id=status_msg.message_id,
                reply_markup=get_main_menu()
            )
        
        try:
            run_async(_verify())
        except Exception as e:
            bot.edit_message_text(f"❌ Failed: {str(e)}", chat_id=user_id, message_id=status_msg.message_id, reply_markup=get_cancel())
    
    threading.Thread(target=verify_otp, daemon=True).start()

@bot.message_handler(func=lambda m: db["states"].get(str(m.from_user.id)) == "awaiting_2fa")
def handle_2fa(m):
    user_id = m.from_user.id
    password = m.text.strip()
    
    client_data = active_clients.get(str(user_id))
    if not client_data:
        bot.reply_to(m, "❌ Session expired.", reply_markup=get_main_menu())
        return
    
    status_msg = bot.reply_to(m, "⏳ <b>Verifying...</b>")
    
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
                f"🎉 <b>Account Added!</b>\n\n📱 +{client_data['phone']}\n👤 {me.first_name}",
                chat_id=user_id,
                message_id=status_msg.message_id,
                reply_markup=get_main_menu()
            )
        
        try:
            run_async(_2fa())
        except Exception as e:
            bot.edit_message_text(f"❌ Failed: {str(e)}", chat_id=user_id, message_id=status_msg.message_id, reply_markup=get_cancel())
    
    threading.Thread(target=verify_2fa, daemon=True).start()

# ==========================================
# 🧠 SMART STREAM SYSTEM (ADVANCED BRAIN)
# ==========================================

@bot.callback_query_handler(func=lambda call: call.data == "stream")
def cb_stream(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔", show_alert=True)
        return
    accounts = db["accounts"].get(str(call.from_user.id), [])
    if not accounts:
        bot.answer_callback_query(call.id, "❌ No accounts!", show_alert=True)
        return
    db["states"][str(call.from_user.id)] = "awaiting_stream"
    save_db()
    bot.edit_message_text(
        f"📡 <b>Send VC/Livestream Link:</b>\n\n🧠 Active Accounts: {len(accounts)}\n\n<i>Har account alag human-like strategy se join karega!</i>",
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
    
    status_msg = bot.reply_to(m, f"🧠 <b>Brain Active!</b>\n\nProcessing {len(accounts)} accounts...", reply_markup=get_main_menu())
    
    # Username nikaalo
    clean_link = link.split("?")[0].rstrip("/")
    parts = [p for p in clean_link.split("/") if p and p not in ["https:", "http:", "t.me", "telegram.dog"]]
    username = parts[0].replace("@", "").strip() if parts else ""
    
    if not username:
        bot.edit_message_text("❌ Invalid link!", chat_id=user_id, message_id=status_msg.message_id, reply_markup=get_main_menu())
        return
    
    def join_stream():
        success = 0
        failed = 0
        
        for i, acc in enumerate(accounts, 1):
            # Har account ke liye alag brain
            brain = AccountBrain(acc)
            strategy = brain.get_join_strategy()
            
            async def _smart_join():
                client = TelegramClient(StringSession(acc["session"]), API_ID, API_HASH)
                
                # Human-like connection delay
                await asyncio.sleep(brain.get_connect_delay())
                await client.connect()
                
                try:
                    me = await client.get_me()
                    entity = await client.get_entity(username)
                    
                    # Get full channel info
                    full_channel = await client(tl_functions.channels.GetFullChannelRequest(entity))
                    
                    if not full_channel or not full_channel.full_chat or not full_channel.full_chat.call:
                        await client.disconnect()
                        return False
                    
                    call_obj = full_channel.full_chat.call
                    muted = brain.is_muted()
                    
                    # STRATEGY: DIRECT
                    if strategy == "direct":
                        try:
                            await client(tl_functions.phone.JoinGroupCallRequest(
                                call=call_obj,
                                params=DataJSON(data="{}"),
                                muted=muted,
                                join_as=me
                            ))
                            await client.disconnect()
                            return True
                        except Exception as e:
                            if "SSRC" in str(e).upper():
                                await asyncio.sleep(brain.get_retry_delay())
                                await client(tl_functions.phone.JoinGroupCallRequest(
                                    call=call_obj,
                                    params=DataJSON(data="{}"),
                                    muted=muted,
                                    join_as=me
                                ))
                                await client.disconnect()
                                return True
                            raise e
                    
                    # STRATEGY: WAIT RETRY
                    elif strategy == "wait_retry":
                        for attempt in range(brain.get_retry_count()):
                            try:
                                await client(tl_functions.phone.JoinGroupCallRequest(
                                    call=call_obj,
                                    params=DataJSON(data="{}"),
                                    muted=muted,
                                    join_as=me
                                ))
                                await client.disconnect()
                                return True
                            except Exception as e:
                                if "SSRC" in str(e).upper() or "RETRY" in str(e).upper():
                                    await asyncio.sleep(brain.get_retry_delay())
                                    continue
                                else:
                                    raise e
                        await client.disconnect()
                        return False
                    
                    # STRATEGY: CHANNEL THEN VC
                    elif strategy == "channel_then_vc":
                        try:
                            await client(JoinChannelRequest(entity))
                            await asyncio.sleep(random.uniform(1, 3))
                        except:
                            pass
                        
                        await client(tl_functions.phone.JoinGroupCallRequest(
                            call=call_obj,
                            params=DataJSON(data="{}"),
                            muted=muted,
                            join_as=me
                        ))
                        await client.disconnect()
                        return True
                    
                    # DEFAULT: STEALTH MUTED
                    else:
                        await client(tl_functions.phone.JoinGroupCallRequest(
                            call=call_obj,
                            params=DataJSON(data="{}"),
                            muted=True,
                            join_as=me
                        ))
                        await client.disconnect()
                        return True
                    
                except Exception as e:
                    logger.error(f"Smart join failed for {acc['phone']} [{brain.behavior}/{strategy}]: {e}")
                    try:
                        await client.disconnect()
                    except:
                        pass
                    return False
            
            try:
                joined = run_async(_smart_join())
                if joined:
                    success += 1
                else:
                    failed += 1
            except:
                failed += 1
            
            try:
                bot.edit_message_text(
                    f"🧠 <b>Brain Processing...</b>\n\n"
                    f"Target: <code>@{username}</code>\n"
                    f"Account: {i}/{len(accounts)}\n"
                    f"Behavior: <code>{brain.behavior}</code>\n"
                    f"Strategy: <code>{strategy}</code>\n\n"
                    f"✅ Success: {success}\n"
                    f"❌ Failed: {failed}",
                    chat_id=user_id,
                    message_id=status_msg.message_id
                )
            except:
                pass
            
            time.sleep(random.uniform(1, 3))
        
        bot.edit_message_text(
            f"✅ <b>Process Complete!</b>\n\n"
            f"Target: <code>@{username}</code>\n"
            f"✅ Success: {success}\n"
            f"❌ Failed: {failed}\n\n"
            f"<i>🧠 Brain ne {len(accounts)} accounts process kiye!</i>",
            chat_id=user_id,
            message_id=status_msg.message_id,
            reply_markup=get_main_menu()
        )
    
    threading.Thread(target=join_stream, daemon=True).start()

# ==========================================
# OTHER HANDLERS
# ==========================================

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
    text = (
        "📚 <b>Bot Instructions:</b>\n\n"
        "1️⃣ <b>Add Number</b> - Login accounts\n"
        "2️⃣ <b>Stream</b> - Send VC link\n"
        "3️⃣ Bot har account ko alag brain se join karega!\n\n"
        "<i>🧠 Advanced Human-Like System</i>"
    )
    bot.edit_message_text(text, chat_id=call.from_user.id, message_id=call.message.message_id, reply_markup=get_main_menu())
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "cancel")
def cb_cancel(call):
    db["states"][str(call.from_user.id)] = "idle"
    active_clients.pop(str(call.from_user.id), None)
    save_db()
    bot.edit_message_text("❌ Cancelled.", chat_id=call.from_user.id, message_id=call.message.message_id, reply_markup=get_main_menu())
    bot.answer_callback_query(call.id)

# ==========================================
# MAIN
# ==========================================

def run_bot():
    logger.info("Combo Bot with Brain starting...")
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
