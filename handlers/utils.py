# handlers/utils.py
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import OWNER_ID
from datetime import datetime

def admin_keyboard():
    buttons = [
        [InlineKeyboardButton("➕ Add Points", callback_data="admin_add_points"),
         InlineKeyboardButton("➖ Remove Points", callback_data="admin_rem_points")],
        [InlineKeyboardButton("🚫 Ban User", callback_data="admin_ban"),
         InlineKeyboardButton("♻️ Unban User", callback_data="admin_unban")],
        [InlineKeyboardButton("🔑 Set Gemini Key", callback_data="admin_set_key"),
         InlineKeyboardButton("📜 Ban List", callback_data="admin_banlist")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_back")]
    ]
    return InlineKeyboardMarkup(buttons)

async def is_owner(user_id: int):
    return user_id == OWNER_ID

def format_time(seconds: int):
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours}h {minutes}m {secs}s" if hours else f"{minutes}m {secs}s"
