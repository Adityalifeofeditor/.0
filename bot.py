# bot.py
from pyrogram import Client, filters, types
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import google.generativeai as genai
from datetime import datetime
import asyncio
import os
import sys

from config import API_ID, API_HASH, BOT_TOKEN, OWNER_ID
from db import *
from handlers.utils import admin_keyboard, is_owner, format_time

app = Client("gemini_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Store user states for interactive input
user_states = {}

# === WELCOME MESSAGE ===
WELCOME_MSG = """
👋 **Welcome to Gemini AI Bot!** 🤖

✨ You're now registered!
🎉 You received **50 welcome points**!

💡 Use `/ask <your question>` to talk with Gemini AI
🔄 Claim **20 free points** daily with `/bonus`

💰 You have: **{points} points**
"""

# === START COMMAND ===
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client: Client, message: Message):
    user = await get_user(message.from_user.id, message.from_user.__dict__)
    points = user["points"]
    await message.reply(WELCOME_MSG.format(points=points), disable_web_page_preview=True)

# === ASK COMMAND ===
@app.on_message(filters.command("ask") & filters.private)
async def ask_cmd(client: Client, message: Message):
    user = await get_user(message.from_user.id)
    if user["banned"]:
        return await message.reply("🚫 You are banned from using this bot.")

    api_key = await get_gemini_key()
    if not api_key:
        return await message.reply("🤖 Gemini API is not configured yet. Contact admin.")

    if len(message.command) > 1:
        query = " ".join(message.command[1:])
    else:
        user_states[message.from_user.id] = "awaiting_ask"
        return await message.reply("💬 Please send your question now:")

    await process_ask(message, query, user)

async def process_ask(message: Message, query: str, user: dict):
    if user["points"] <= 0:
        return await message.reply("❌ Not enough points! Claim bonus with /bonus")

    # Deduct point
    result = await deduct_point(message.from_user.id)
    if not result.modified_count:
        return await message.reply("❌ Failed to deduct point. Try again.")

    thinking = await message.reply("🤔 Thinking...")

    try:
        genai.configure(api_key=await get_gemini_key())
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = await asyncio.to_thread(model.generate_content, query)
        text = response.text[:4000]
        await thinking.edit_text(f"✅ **Gemini Answer:**\n\n{text}\n\n💰 Points left: {user['points']-1}")
    except Exception as e:
        await update_points(message.from_user.id, 1)  # Refund
        await thinking.edit_text(f"❌ Error: {str(e)}")

# Handle text after /ask
@app.on_message(filters.text & filters.private & filters.create(lambda _, __, m: user_states.get(m.from_user.id) == "awaiting_ask"))
async def handle_ask_input(client: Client, message: Message):
    if message.from_user.id in user_states:
        del user_states[message.from_user.id]
    user = await get_user(message.from_user.id)
    await process_ask(message, message.text, user)

# === BONUS ===
@app.on_message(filters.command("bonus"))
async def bonus_cmd(client: Client, message: Message):
    user = await get_user(message.from_user.id)
    if user["banned"]:
        return await message.reply("🚫 You are banned.")

    cooldown = await get_bonus_cooldown(message.from_user.id)
    if cooldown > 0:
        return await message.reply(f"⏳ Wait {format_time(cooldown)} before claiming again!")

    await update_points(message.from_user.id, 20)
    await set_bonus_time(message.from_user.id)
    await message.reply("🎉 **+20 points claimed!** Enjoy!")

# === ADMIN PANEL ===
@app.on_message(filters.command("admin_settings"))
async def admin_panel(client: Client, message: Message):
    if not await is_owner(message.from_user.id):
        return
    await message.reply("🔧 **Admin Panel**", reply_markup=admin_keyboard())

# === CALLBACK HANDLERS ===
@app.on_callback_query()
async def callback_handler(client: Client, query: CallbackQuery):
    data = query.data
    user_id = query.from_user.id

    if not await is_owner(user_id):
        return await query.answer("❌ Owner only!", show_alert=True)

    states = {
        "admin_add_points": ("add_points", "➕ Enter user ID and points (e.g., 12345 50):"),
        "admin_rem_points": ("rem_points", "➖ Enter user ID and points to remove:"),
        "admin_ban": ("ban", "🚫 Enter user ID to ban:"),
        "admin_unban": ("unban", "♻️ Enter user ID to unban:"),
        "admin_set_key": ("set_key", "🔑 Send new Gemini API key:"),
        "admin_banlist": ("banlist", None),
        "admin_back": ("back", None)
    }

    if data == "admin_banlist":
        banned = [u async for u in users.find({"banned": True}, {"user_id": 1, "first_name": 1})]
        if not banned:
            text = "No banned users."
        else:
            text = "\n".join([f"• {u['user_id']} ({u.get('first_name')})" for u in banned])
        await query.message.edit_text(f"📜 **Banned Users**\n\n{text}", reply_markup=admin_keyboard())
        return

    if data == "admin_back":
        await query.message.edit_text("🔧 **Admin Panel**", reply_markup=admin_keyboard())
        return

    action, prompt = states.get(data, (None, None))
    if prompt:
        user_states[user_id] = action
        await query.message.edit_text(prompt)

    await query.answer()

# Handle admin inputs
@app.on_message(filters.text & filters.private & filters.create(lambda _, __, m: m.from_user.id == OWNER_ID and user_states.get(m.from_user.id) in [
    "add_points", "rem_points", "ban", "unban", "set_key"
]))
async def handle_admin_input(client: Client, message: Message):
    state = user_states.get(message.from_user.id)
    text = message.text.strip()

    if state == "set_key":
        await set_gemini_key(text)
        await message.reply("✅ Gemini API key updated!")
    elif state in ["add_points", "rem_points"]:
        try:
            uid, pts = text.split()[:2]
            uid, pts = int(uid), int(pts)
            if state == "add_points":
                await update_points(uid, pts)
                await message.reply(f"✅ Added {pts} points to {uid}")
            else:
                await update_points(uid, -pts)
                await message.reply(f"✅ Removed {pts} points from {uid}")
        except:
            await message.reply("❌ Format: user_id points")
    elif state == "ban":
        await ban_user(int(text))
        await message.reply(f"🚫 Banned {text}")
    elif state == "unban":
        await unban_user(int(text))
        await message.reply(f"♻️ Unbanned {text}")

    user_states.pop(message.from_user.id, None)

# === BROADCAST ===
@app.on_message(filters.command("broadcast"))
async def broadcast_cmd(client: Client, message: Message):
    if not await is_owner(message.from_user.id):
        return
    if len(message.command) > 1:
        text = message.text.split(" ", 1)[1]
    else:
        user_states[message.from_user.id] = "broadcast"
        return await message.reply("📢 Send the message to broadcast:")

    users_list = await get_all_users()
    success = 0
    for user in users_list:
        try:
            await client.send_message(user["user_id"], text)
            success += 1
            await asyncio.sleep(0.1)
        except:
            pass
    await message.reply(f"✅ Broadcast sent to {success} users.")

@app.on_message(filters.text & filters.private & filters.create(lambda _, __, m: user_states.get(m.from_user.id) == "broadcast"))
async def handle_broadcast(client: Client, message: Message):
    if message.from_user.id != OWNER_ID:
        return
    del user_states[message.from_user.id]
    # Re-use the same logic
    await broadcast_cmd(client, message)

# === STATS ===
@app.on_message(filters.command("stats"))
async def stats_cmd(client: Client, message: Message):
    if not await is_owner(message.from_user.id):
        return
    total, banned, points = await get_stats()
    await message.reply(
        f"📊 **Bot Statistics**\n\n"
        f"👥 Total Users: {total}\n"
        f"🚫 Banned: {banned}\n"
        f"💰 Total Points Distributed: {points}\n"
        f"🕐 Server Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )

# === RESTART ===
@app.on_message(filters.command("restart"))
async def restart_cmd(client: Client, message: Message):
    if not await is_owner(message.from_user.id):
        return
    await message.reply("🔄 Restarting bot...")
    os.execv(sys.executable, ['python', 'bot.py'])

print("🤖 Gemini Bot Started!")
app.run()
