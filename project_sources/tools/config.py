
from dotenv import load_dotenv
import os

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")