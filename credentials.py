import os

if os.path.exists(".env"):
    from dotenv import load_dotenv
    load_dotenv()

BOT_USERNAME = os.getenv('BOT_USERNAME')
BOT_TOKEN = os.getenv('BOT_TOKEN')