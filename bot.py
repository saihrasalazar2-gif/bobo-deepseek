import os
import random
import asyncio
import time
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)
from telegram.error import TelegramError
from telegram.request import HTTPXRequest

# ==========================================
# 1. CONFIG
# ==========================================
BOT_TOKEN = "8645466073:AAGho0HHg9yPwMpKNDtG-5GW1uH5NwMfAYo"
OWNER_ID = 9071386675
CHANNEL_USERNAME = "@nafaelmain1"
CHANNEL_LINK = "https://t.me/nafaelmain1"

DATABASE_FILE = "database.txt"
WAIT_COUNTRY, WAIT_AMOUNT, WAIT_RANGE = range(3)

ACTIVE_SESSIONS = {}
GLOBAL_USED_COMBOS = set() # Wipes on restart

# ==========================================
# 2. UI
# ==========================================
def get_main_menu(uid):
    kb = [[InlineKeyboardButton("⚡ Generate Combos", callback_data="menu_gen")]]
    if uid == OWNER_ID:
        kb.append([InlineKeyboardButton("👑 Admin Panel", callback_data="menu_admin")])
    return InlineKeyboardMarkup(kb)

def get_admin_menu():
    return InlineKeyboardMarkup([[InlineKeyboardButton("↩ Back", callback_data="menu_home")]])

def get_join_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Join Channel", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ Verify", callback_data="verify_join")]
    ])

def create_progress_bar(current, total):
    bar_length = 15
    filled = int(bar_length * current // total) if total > 0 else 0
    bar = "█" * filled + "░" * (bar_length - filled)
    percent = (current / total) * 100 if total > 0 else 0
    return f"[{bar}] {percent:.1f}%"

# ==========================================
# 3. LOGIC & GENERATION
# ==========================================
async def check_joined(user_id, bot):
    if user_id == OWNER_ID: return True
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except TelegramError:
        return False

def load_file(filename):
    if not os.path.exists(filename):
        return []
    with open(filename, "r", encoding="utf-8") as file:
        return [line.strip() for line in file if line.strip()]

def generate_moonton(amount, start_num, end_num, session_id, progress_callback, loop):
    global GLOBAL_USED_COMBOS
    
    lines = load_file(DATABASE_FILE)
    if not lines:
        return None, "database.txt missing."

    generated = []
    random.shuffle(lines)
    
    suffixes = [""]
    if start_num is not None and end_num is not None:
        suffixes = [f"{i:02d}" if i < 100 else str(i) for i in range(start_num, end_num + 1)]
    
    update_interval = max(50, amount // 20)
    count = 0

    while count < amount:
        if ACTIVE_SESSIONS.get(session_id, {}).get("cancelled"):
            return None, "Cancelled"
        
        found = False
        for raw_line in lines:
            if count >= amount: break
            
            try:
                parts = raw_line.split(",")
                if len(parts) < 4: continue
                
                name = parts[3].strip()
                if not name or not name.isalpha(): continue
                
                # FORCE CAPITAL FIRST LETTER
                name = name.capitalize()
                
                suffix = random.choice(suffixes)
                combo_string = f"{name}{suffix}"
                
                final_combo = f"{combo_string}:{combo_string}"
                
                if final_combo in GLOBAL_USED_COMBOS:
                    continue
                    
                GLOBAL_USED_COMBOS.add(final_combo)
                generated.append(final_combo)
                count += 1
                found = True
                
                if count % update_interval == 0 and count < amount:
                    asyncio.run_coroutine_threadsafe(progress_callback(count, amount), loop)
                    
            except Exception:
                continue
                
        if not found:
            break

    if not generated:
        return None, "No unique combos left. The whole database is used up."
        
    return generated, "Success"

def save_output(generated):
    if not generated: return None
    os.makedirs("results", exist_ok=True)
    filename = f"results/upass_{int(time.time())}.txt"
    with open(filename, "w", encoding="utf-8") as file:
        file.write("\n".join(generated))
        file.write("\n")
    return filename

# ==========================================
# 4. HANDLERS
# ==========================================
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await check_joined(uid, ctx.bot):
        await update.message.reply_text(f"⚠️ <b>Join Channel First</b>", reply_markup=get_join_keyboard(), parse_mode="HTML")
        return ConversationHandler.END
    await update.message.reply_text(f"👋 <b>Welcome!</b>\nSelect an option:", reply_markup=get_main_menu(uid), parse_mode="HTML")
    return ConversationHandler.END

async def menu_router(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = update.effective_user.id

    if data == "menu_home":
        await query.edit_message_text("👋 <b>Welcome!</b>", reply_markup=get_main_menu(uid), parse_mode="HTML")
    elif data == "menu_admin" and uid == OWNER_ID:
        await query.edit_message_text("👑 <b>Admin</b>", reply_markup=get_admin_menu(), parse_mode="HTML")
    elif data == "menu_gen":
        await query.edit_message_text("🔢 <b>How many lines?</b>\nSend a number (Max: 10,000).", parse_mode="HTML")
        return WAIT_AMOUNT

async def verify_join(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if await check_joined(uid, ctx.bot):
        await query.message.edit_text("✅ <b>Verified!</b>", reply_markup=get_main_menu(uid), parse_mode="HTML")
    else:
        await query.message.edit_text("❌ <b>Not joined.</b>", reply_markup=get_join_keyboard(), parse_mode="HTML")

async def amount_received(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    try:
        amount = int(update.message.text.strip())
        if amount <= 0: raise ValueError
        if uid != OWNER_ID and amount > 10000:
            await update.message.reply_text("❌ Max 10,000 for users.")
            return WAIT_AMOUNT
    except ValueError:
        await update.message.reply_text("❌ Invalid number.")
        return WAIT_AMOUNT

    ctx.user_data["amount"] = amount
    await update.message.reply_text(
        "🔢 <b>Number Range</b>\n\n"
        "Send a range like <code>1-99</code> to add a number to the username.\n"
        "Or tap /skip to generate <code>Name:Name</code> with no numbers.", 
        parse_mode="HTML"
    )
    return WAIT_RANGE

async def skip_range(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["range"] = (None, None)
    return await start_generation(update, ctx)

async def range_received(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() in ["skip", "/skip"]:
        ctx.user_data["range"] = (None, None)
        return await start_generation(update, ctx)

    try:
        s, e = text.split("-")
        s, e = int(s), int(e)
        if s < 0 or e < s or e > 999: raise ValueError
        ctx.user_data["range"] = (s, e)
    except ValueError:
        await update.message.reply_text("❌ Invalid range. Use <code>1-99</code> or /skip.", parse_mode="HTML")
        return WAIT_RANGE

    return await start_generation(update, ctx)

async def start_generation(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    amount = ctx.user_data.get("amount")
    start_num, end_num = ctx.user_data.get("range", (None, None))
    
    msg = await update.message.reply_text("⏳ <b>Starting...</b>", parse_mode="HTML")
    session_id = f"{uid}_{int(datetime.now().timestamp())}"
    ACTIVE_SESSIONS[session_id] = {"cancelled": False}

    loop = asyncio.get_event_loop()
    
    async def update_progress(current, total):
        bar = create_progress_bar(current, total)
        try:
            await msg.edit_text(
                text=f"⏳ <b>Generating...</b>\n\n"
                     f"📦 <b>Progress:</b> {current:,} / {total:,}\n"
                     f"<code>{bar}</code>",
                parse_mode="HTML"
            )
        except Exception:
            pass # Ignore telegram rate limits

    generated, result = await loop.run_in_executor(
        None, lambda: generate_moonton(amount, start_num, end_num, session_id, update_progress, loop)
    )
    ACTIVE_SESSIONS.pop(session_id, None)

    if not generated:
        await msg.edit_text(f"❌ {result}")
    else:
        file = save_output(generated)
        doc = open(file, "rb")
        await ctx.bot.send_document(
            chat_id=uid, document=doc, filename=os.path.basename(file),
            caption=f"✅ <b>Generated {len(generated):,} combos.</b>\nZero duplicates.",
            parse_mode="HTML"
        )
        doc.close()
        await msg.delete()
        if os.path.exists(file): os.remove(file)

    return ConversationHandler.END

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ <b>Cancelled.</b>", reply_markup=get_main_menu(update.effective_user.id), parse_mode="HTML")
    return ConversationHandler.END

# ==========================================
# 5. MAIN
# ==========================================
def main():
    req = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)
    app = Application.builder().token(BOT_TOKEN).request(req).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CallbackQueryHandler(menu_router, pattern="^menu_"),
        ],
        states={
            WAIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, amount_received)],
            WAIT_RANGE: [
                CommandHandler("skip", skip_range),
                MessageHandler(filters.TEXT & ~filters.COMMAND, range_received)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(verify_join, pattern="^verify_join$"))

    print("Bot running.")
    app.run_polling(drop_pending_updates=True, close_loop=False)

if __name__ == "__main__":
    main()