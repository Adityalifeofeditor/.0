# db.py
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGODB_URI, DB_NAME, USERS_COLLECTION, SETTINGS_COLLECTION
from datetime import datetime, timedelta
import asyncio

client = AsyncIOMotorClient(MONGODB_URI)
db = client[DB_NAME]
users = db[USERS_COLLECTION]
settings = db[SETTINGS_COLLECTION]

# === USER OPERATIONS ===
async def get_user(user_id: int, user_data: dict = None):
    user = await users.find_one({"user_id": user_id})
    if not user:
        user = {
            "user_id": user_id,
            "first_name": user_data.get("first_name", "User"),
            "username": user_data.get("username"),
            "points": 50,
            "banned": False,
            "last_bonus_time": None,
            "joined_at": datetime.utcnow()
        }
        await users.insert_one(user)
    return user

async def update_points(user_id: int, amount: int):
    await users.update_one({"user_id": user_id}, {"$inc": {"points": amount}})

async def deduct_point(user_id: int):
    return await users.update_one(
        {"user_id": user_id, "points": {"$gt": 0}},
        {"$inc": {"points": -1}}
    )

async def set_bonus_time(user_id: int):
    await users.update_one(
        {"user_id": user_id},
        {"$set": {"last_bonus_time": datetime.utcnow()}}
    )

async def get_bonus_cooldown(user_id: int):
    user = await users.find_one({"user_id": user_id})
    if not user or not user.get("last_bonus_time"):
        return 0
    last = user["last_bonus_time"]
    next_allowed = last + timedelta(hours=24)
    if datetime.utcnow() < next_allowed:
        return (next_allowed - datetime.utcnow()).seconds
    return 0

async def ban_user(user_id: int):
    await users.update_one({"user_id": user_id}, {"$set": {"banned": True}})

async def unban_user(user_id: int):
    await users.update_one({"user_id": user_id}, {"$set": {"banned": False}})

# === SETTINGS ===
async def get_gemini_key():
    setting = await settings.find_one({"key": "gemini_api_key"})
    return setting["value"] if setting else None

async def set_gemini_key(key: str):
    await settings.replace_one(
        {"key": "gemini_api_key"},
        {"key": "gemini_api_key", "value": key},
        upsert=True
    )

async def get_all_users():
    return await users.find({"banned": False}).to_list(length=None)

async def get_stats():
    total = await users.count_documents({})
    banned = await users.count_documents({"banned": True})
    points = sum([u["points"] async for u in users.find({}, {"points": 1})])
    return total, banned, points
