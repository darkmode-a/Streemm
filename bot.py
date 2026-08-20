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
from telethon.errors import SessionPasswordNeededError
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

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

bot = TeleBot(BOT_TOKEN, threaded=True, parse_mode="HTML")

DATABASE_FILE = "combo_database.json"

def load_db():
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, 'r') as f:
            return json.load(f)
    return {"accounts": {}, "states": {}}

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
    return future.result(timeout=60)

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
    bot.reply_to(
        message,
        "🤖 <b>Combo Bot</b>\n\n📱 Add Number\n📡 Stream\n👥 My Accounts",
        reply_markup=get_main_menu()
    )

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
                f"✅ <b>OTP sent to {phone}!</b>\n\nEnter OTP code:",
                chat_id=user_id,
                message_id=status_msg.message_id,
                reply_markup=get_cancel()
            )
        except Exception as e:
            logger.error(f"OTP error: {e}")
            bot.edit_message_text(
                f"❌ Failed: {str(e)}",
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
        bot.reply_to(m, "❌ Session expired. Start again.", reply_markup=get_main_menu())
        db["states"][str(user_id)] = "idle"
        save_db()
        return
    
    status_msg = bot.reply_to(m, "⏳ <b>Verifying OTP...</b>")
    
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
                bot.edit_message_text(
                    "🔐 <b>2FA Password Required!</b>\n\nEnter password:",
                    chat_id=user_id,
                    message_id=status_msg.message_id,
                    reply_markup=get_cancel()
                )
                return None
            
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
                f"🎉 <b>Account Added!</b>\n\n📱 {phone}\n👤 {me.first_name}\n📊 Total: {total}",
                chat_id=user_id,
                message_id=status_msg.message_id,
                reply_markup=get_main_menu()
            )
            return me
        
        try:
            run_async(_verify())
        except Exception as e:
            logger.error(f"Verify error: {e}")
            bot.edit_message_text(
                f"❌ Failed: {str(e)}",
                chat_id=user_id,
                message_id=status_msg.message_id,
                reply_markup=get_cancel()
            )
    
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
                f"🎉 <b>Account Added!</b>\n\n📱 {client_data['phone']}\n👤 {me.first_name}",
                chat_id=user_id,
                message_id=status_msg.message_id,
                reply_markup=get_main_menu()
            )
        
        try:
            run_async(_2fa())
        except Exception as e:
            logger.error(f"2FA error: {e}")
            bot.edit_message_text(
                f"❌ Failed: {str(e)}",
                chat_id=user_id,
                message_id=status_msg.message_id,
                reply_markup=get_cancel()
            )
    
    threading.Thread(target=verify_2fa, daemon=True).start()

# ========== STREAM SYSTEM (FINAL) ==========

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
        f"📡 <b>Send VC Link:</b>\n\nAccounts: {len(accounts)}",
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
        
        for i, acc in enumerate(accounts, 1):
            async def _join_vc():
                from telethon import functions as tl_functions
                
                client = TelegramClient(StringSession(acc["session"]), API_ID, API_HASH)
                await client.connect()
                
                try:
                    me = await client.get_me()
                    
                    username = link.split("/")[-1].split("?")[0].replace("@", "")
                    entity = await client.get_entity(username)
                    
                    # Channel join (zaroori)
                    try:
                        await client(JoinChannelRequest(entity))
                        await asyncio.sleep(2)
                    except:
                        pass
                    
                    # Get full channel - sahi call object ke liye
                    full_channel = await client(tl_functions.channels.GetFullChannelRequest(entity))
                    
                    if full_channel and full_channel.full_chat and full_channel.full_chat.call:
                        call_obj = full_channel.full_chat.call
                        
                        # VC JOIN - data string ke saath
                        await client(tl_functions.phone.JoinGroupCallRequest(
                            call=call_obj,
                            params=DataJSON(data="{}"),
                            muted=False,
                            join_as=me
                        ))
                        await client.disconnect()
                        return True
                    else:
                        logger.warning(f"No active call for {username}")
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
            except Exception as e:
                logger.error(f"Failed {acc['phone']}: {e}")
                failed += 1
            
            try:
                bot.edit_message_text(
                    f"🚀 <b>Processing...</b>\n\n✅ Success: {success}\n❌ Failed: {failed}",
                    chat_id=user_id,
                    message_id=status_msg.message_id
                )
            except:
                pass
            
            time.sleep(3)
        
        bot.edit_message_text(
            f"✅ <b>Complete!</b>\n\n✅ Success: {success}\n❌ Failed: {failed}",
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
        account_list += f"\n{i}. {acc['phone']} - {acc.get('name', 'Unknown')}"
    bot.edit_message_text(
        f"👥 Total: {len(accounts)}{account_list}",
        chat_id=call.from_user.id,
        message_id=call.message.message_id,
        reply_markup=get_main_menu()
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "help")
def cb_help(call):
    bot.edit_message_text("📚 Help: Add Number, Stream, My Accounts", chat_id=call.from_user.id, message_id=call.message.message_id, reply_markup=get_main_menu())
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "cancel")
def cb_cancel(call):
    db["states"][str(call.from_user.id)] = "idle"
    client_data = active_clients.pop(str(call.from_user.id), None)
    if client_data:
        try:
            asyncio.run_coroutine_threadsafe(client_data["client"].disconnect(), telethon_loop)
        except:
            pass
    save_db()
    bot.edit_message_text("❌ Cancelled.", chat_id=call.from_user.id, message_id=call.message.message_id, reply_markup=get_main_menu())
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
