from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import ApplicationBuilder, CallbackContext, CommandHandler

from credentials import BOT_TOKEN


async def launch_web_ui(update: Update, context: CallbackContext) -> None:
    greeting_message = (
        "👋 Hello there! Welcome to SaveIt Parser!\n\n"
        "I'm here to help you extract content from web pages. "
        "Just send me a URL, and I'll do the magic for you. 🪄✨"
    )

    keyboard = [
        [InlineKeyboardButton("Launch SaveIt Parser", web_app=WebAppInfo(url="https://mini-bookmark-telegram-toms-projects-04b11994.vercel.app/"))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.effective_chat.send_message(greeting_message, reply_markup=reply_markup)

if __name__ == "__main__":
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler('start', launch_web_ui))

    application.run_polling()
