# main.py
import os
import asyncio
import logging
import aiohttp
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME")
PRIVATE_CHANNEL_ID = int(os.getenv("PRIVATE_CHANNEL_ID"))
REQUIRED_CHANNELS = os.getenv("REQUIRED_CHANNELS", "").split(",")
GPLINKS_API_KEY = os.getenv("GPLINKS_API_KEY")
SHRINKEARN_API_KEY = os.getenv("SHRINKEARN_API_KEY")
SHORTENER_ROTATE = os.getenv("SHORTENER_ROTATE", "GP,SE").split(",")
VERIFY_TOKEN_TTL = int(os.getenv("VERIFY_TOKEN_TTL_SECONDS", "900"))
DELIVERY_DELETE_AFTER = int(os.getenv("DELIVERY_DELETE_AFTER_SECONDS", "1800"))
OWNER_ID = int(os.getenv("OWNER_ID"))

MOVIES = {}   # {code: file_id}
PENDING_TOKENS = {}  # {token: {"code": code, "expires": datetime}}

# -------- Shortener API -------- #
async def short_link(url: str) -> str:
    choice = SHORTENER_ROTATE[0] if SHORTENER_ROTATE else "GP"
    if choice == "GP":
        api = f"https://gplinks.in/api?api={GPLINKS_API_KEY}&url={url}"
    else:
        api = f"https://shrinkearn.com/api?api={SHRINKEARN_API_KEY}&url={url}"

    async with aiohttp.ClientSession() as session:
        async with session.get(api) as resp:
            data = await resp.json()
            SHORTENER_ROTATE.append(SHORTENER_ROTATE.pop(0))  # rotate
            return data.get("shortenedUrl", url)

# -------- Join Check -------- #
async def is_user_joined(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    for channel in REQUIRED_CHANNELS:
        try:
            member = await context.bot.get_chat_member(channel.strip(), user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        except:
            return False
    return True

# -------- Commands -------- #
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if args:
        token = args[0]
        token_data = PENDING_TOKENS.get(token)
        if token_data and token_data["expires"] > datetime.now():
            code = token_data["code"]
            file_id = MOVIES.get(code)
            if file_id:
                msg = await update.message.reply_video(
                    video=file_id,
                    protect_content=True
                )
                # auto delete after DELIVERY_DELETE_AFTER
                await asyncio.sleep(DELIVERY_DELETE_AFTER)
                try:
                    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg.message_id)
                except:
                    pass
            del PENDING_TOKENS[token]
        else:
            await update.message.reply_text("⚠ Token expired or invalid.")
    else:
        await update.message.reply_text("👋 Welcome! Use /movie <code> to request a movie.")

async def add_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /add <code>")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a movie file with this command.")
        return
    code = context.args[0]
    file_id = (update.message.reply_to_message.video or update.message.reply_to_message.document).file_id
    MOVIES[code] = file_id
    await update.message.reply_text(f"✅ Movie added with code: {code}")

async def movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /movie <code>")
        return
    code = context.args[0]
    if code not in MOVIES:
        await update.message.reply_text("❌ Movie not found.")
        return
    user_id = update.effective_user.id
    if not await is_user_joined(user_id, context):
        buttons = [[InlineKeyboardButton("📢 Join Channels", url=f"https://t.me/{REQUIRED_CHANNELS[0].strip('@')}")]]
        await update.message.reply_text("🔒 Please join all required channels to continue.", reply_markup=InlineKeyboardMarkup(buttons))
        return
    token = os.urandom(4).hex()
    PENDING_TOKENS[token] = {"code": code, "expires": datetime.now() + timedelta(seconds=VERIFY_TOKEN_TTL)}
    short_url = await short_link(f"https://t.me/{BOT_USERNAME}?start={token}")
    await update.message.reply_text(f"🔗 Click here to verify: {short_url}")

# -------- Main -------- #
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("add", add_movie))
app.add_handler(CommandHandler("movie", movie))

if __name__ == "__main__":
    logger.info("Bot starting...")
    app.run_polling()
