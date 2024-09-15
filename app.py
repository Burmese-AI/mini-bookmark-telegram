from telegram import Update
from telegram.ext import ApplicationBuilder, CallbackContext, CommandHandler

from credentials import BOT_TOKEN


async def launch_web_ui(update: Update, context: CallbackContext) -> None:
    await update.effective_chat.send_message("Let's do this!")

if __name__ == "__main__":
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler('start', launch_web_ui))

    application.run_polling()
