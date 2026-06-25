import asyncio
import json
import os
import logging
import uuid
import random
import aiohttp
from datetime import datetime, timedelta
from typing import Callable, Dict, Any, Awaitable, List
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.filters import Command, CommandStart
from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

# ==========================================
# 1. CONFIGURATION
# ==========================================
BOT_TOKEN = "8962210629:AAFhB5oNooreoJRhIuG7Frc9kqRxpQ2NWHA"
OWNER_ID = 8570832903
OWNER_USERNAME = "@theaadikoder"
EXECUTIVE_NAME = "Aditya Thakur"
PLATFORM_NAME = "TheAdiCoder Premium Network"
USE_PYTHONANYWHERE_PROXY = False

# ==========================================
# 2. DATABASE ENGINE (all collections)
# ==========================================
db_lock = asyncio.Lock()
FILES = {
    "users.json": {},
    "stocks.json": [],
    "channels.json": [],
    "groups.json": [],
    "logs.json": [],
    "settings.json": {
        "auto_post_enabled": False,
        "auto_post_channels": [],          # list of channel IDs
        "auto_post_interval": 300,
        "daily_limit": 50,
        "daily_post_count": 0,
        "last_post_date": "1970-01-01",
        "last_post_timestamp": 0,
        "post_template": "premium",
        "show_bin_info": True,
        "show_timestamp": True,
        "rotation_index": 0,
        "post_types": ["card", "quote", "announcement"],
        "scheduled_posts": []
    },
    "reports.json": [],
    "feedback.json": [],
    "referrals.json": {},
    "transactions.json": [],
    "leaderboard.json": {}
}

def init_db():
    for filename, default_data in FILES.items():
        if not os.path.exists(filename):
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(default_data, f, indent=4)
        else:
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    if json.load(f) is None:
                        raise json.JSONDecodeError("Null DB", "", 0)
            except json.JSONDecodeError:
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(default_data, f, indent=4)

async def read_db(filename: str):
    async with db_lock:
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f) or FILES.get(filename).copy()
        except:
            return FILES.get(filename).copy()

async def modify_db(filename: str, modifier_func: Callable):
    async with db_lock:
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f) or FILES.get(filename).copy()
        except:
            data = FILES.get(filename).copy()
        updated_data = modifier_func(data)
        if updated_data is not None:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(updated_data, f, indent=4)
            return updated_data
        return None

async def log_action(action: str, user_id: int, details: str = ""):
    def add_log(logs):
        logs.append({
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "action": action,
            "user_id": user_id,
            "details": details
        })
        return logs
    await modify_db("logs.json", add_log)

async def notify_owner(bot: Bot, message: str):
    try:
        await bot.send_message(chat_id=OWNER_ID, text=message, parse_mode="HTML")
    except:
        pass

async def ensure_user_registered(user_id: int, username: str, bot: Bot = None):
    uid_str = str(user_id)
    is_new = [False]
    safe_username = str(username).replace("_", "\\_") if username else "Unknown"

    def register_user(users):
        if uid_str not in users:
            users[uid_str] = {
                "username": safe_username,
                "role": "owner" if user_id == OWNER_ID else "user",
                "banned": False,
                "join_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "redeem_count": 0,
                "total_checks": 0,
                "last_active": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "referral_code": str(uuid.uuid4())[:8],
                "referred_by": None,
                "referral_earnings": 0
            }
            is_new[0] = True
        else:
            if user_id == OWNER_ID:
                users[uid_str]["role"], users[uid_str]["banned"] = "owner", False
            if "join_date" not in users[uid_str]:
                users[uid_str]["join_date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if "referral_code" not in users[uid_str]:
                users[uid_str]["referral_code"] = str(uuid.uuid4())[:8]
            users[uid_str]["last_active"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return users

    await modify_db("users.json", register_user)
    if is_new[0] and bot and user_id != OWNER_ID:
        await notify_owner(bot, f"🔔 **New User**\n👤 ID: `{user_id}`\n👤 Username: @{safe_username}")
    return is_new[0]

def parse_chat_id(cid: str):
    cid_str = str(cid).strip()
    if "t.me/" in cid_str:
        cid_str = "@" + cid_str.split("t.me/")[-1].split("/")[0]
    try:
        return int(cid_str)
    except ValueError:
        if not cid_str.startswith("@") and not cid_str.startswith("-100"):
            cid_str = "@" + cid_str
        return cid_str

# ==========================================
# 3. SECURITY MIDDLEWARE
# ==========================================
class ForceJoinMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user_id = event.from_user.id
        bot: Bot = data['bot']
        await ensure_user_registered(user_id, event.from_user.username, bot)
        users = await read_db("users.json")
        if users.get(str(user_id), {}).get("banned", False):
            if isinstance(event, Message):
                await event.answer("🚫 <b>Access Revoked</b>\nYou have been banned.", parse_mode="HTML")
            elif isinstance(event, CallbackQuery):
                await event.answer("🚫 Access Revoked", show_alert=True)
            return
        role = users.get(str(user_id), {}).get("role", "user")
        if user_id == OWNER_ID or role == "admin":
            return await handler(event, data)
        channels = await read_db("channels.json")
        not_joined = []
        for ch in channels:
            try:
                member = await bot.get_chat_member(parse_chat_id(ch['channel_id']), user_id)
                if member.status in ['left', 'kicked', 'banned']:
                    not_joined.append(ch['link'])
            except TelegramBadRequest:
                pass
        if not_joined:
            text = "🛑 <b>Verification Required</b>\n\n> Join our channels to continue:\n"
            for link in not_joined:
                text += f"\n🔗 {link}"
            text += "\n\n<i>After joining, click Verify.</i>"
            markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Verify Access", callback_data="verify_join")]
            ])
            if isinstance(event, Message):
                await event.answer(text, disable_web_page_preview=True, reply_markup=markup, parse_mode="HTML")
            elif isinstance(event, CallbackQuery):
                await event.message.answer(text, disable_web_page_preview=True, reply_markup=markup, parse_mode="HTML")
                await event.answer("Verification required!", show_alert=True)
            return
        return await handler(event, data)

dp = Dispatcher()
dp.message.middleware(ForceJoinMiddleware())
dp.callback_query.middleware(ForceJoinMiddleware())

# ==========================================
# 4. CARD ENGINE (enhanced realistic data)
# ==========================================
def get_local_bin_data(bin_str):
    prefix = bin_str[0]
    schemes = {
        '4': ('Visa', '💳'),
        '5': ('Mastercard', '💳'),
        '6': ('Discover', '💳'),
        '2': ('Mastercard', '💳'),
        '3': ('American Express', '💎')
    }
    scheme, scheme_icon = schemes.get(prefix, ("Unknown", "❓"))
    c_type = random.choice(["Credit", "Debit", "Prepaid"])
    banks = [
        "JPMorgan Chase", "Bank of America", "Wells Fargo",
        "Citibank", "HSBC", "Barclays", "Capital One",
        "Standard Chartered", "Deutsche Bank", "BNP Paribas",
        "Royal Bank of Canada", "Commonwealth Bank"
    ]
    bank_name = random.choice(banks) if scheme != 'American Express' else "American Express"
    countries = [
        ("United States", "🇺🇸"), ("United Kingdom", "🇬🇧"),
        ("Canada", "🇨🇦"), ("Australia", "🇦🇺"),
        ("Germany", "🇩🇪"), ("France", "🇫🇷"),
        ("India", "🇮🇳"), ("Japan", "🇯🇵"),
        ("Brazil", "🇧🇷"), ("UAE", "🇦🇪"), ("Singapore", "🇸🇬")
    ]
    country_name, flag = random.choice(countries)
    level = random.choice(["Classic", "Gold", "Platinum", "World", "Black", "Titanium"])
    return scheme, c_type, bank_name, country_name, flag, level, scheme_icon

def generate_random_card():
    prefixes = ['4', '5', '6', '2', '3']
    prefix = random.choice(prefixes)
    length = 15 if prefix == '3' else 16
    bin_str = prefix + ''.join([str(random.randint(0, 9)) for _ in range(5)])
    rest = ''.join([str(random.randint(0, 9)) for _ in range(length - 6)])
    card_number = bin_str + rest
    if prefix == '3':
        formatted = f"{card_number[:4]} {card_number[4:10]} {card_number[10:15]}"
    else:
        formatted = f"{card_number[:4]} {card_number[4:8]} {card_number[8:12]} {card_number[12:16]}"
    month = f"{random.randint(1, 12):02d}"
    year = str(random.randint(2025, 2035))
    cvv = ''.join([str(random.randint(0, 9)) for _ in range(4 if prefix == '3' else 3)])
    return bin_str, card_number, formatted, month, year, cvv

# ==========================================
# 5. BEAUTIFUL CARD TEMPLATES
# ==========================================
def format_enhanced_card(card_data, bin_info, template="premium", show_timestamp=True):
    bin_str, card_number, formatted, month, year, cvv = card_data
    scheme, c_type, bank_name, country_name, flag, level, scheme_icon = bin_info
    timestamp = f"⏱ {datetime.now().strftime('%H:%M:%S')}" if show_timestamp else ""

    if template == "premium":
        return f"""╔═══════════════════════════════════════════════════╗
║              💎 {scheme_icon} {scheme} {level}              ║
╠═══════════════════════════════════════════════════╣
║                                                   ║
║  💳  <b>{formatted}</b>                          ║
║                                                   ║
║  📅  <b>{month}/{year}</b>              🔐  <b>{cvv}</b>        ║
║                                                   ║
║  ───────────────────────────────────────────────  ║
║                                                   ║
║  🏛  <b>{bank_name}</b>                            ║
║  🌐  <b>{scheme}</b>  •  💳  <b>{c_type}</b>          ║
║  🌍  <b>{flag} {country_name}</b>                   ║
║  📊  <b>{level}</b> Level                          ║
║                                                   ║
║  🆔  <b>{bin_str}</b>                               ║
║  {timestamp}                                    ║
║                                                   ║
║  ✅  <code>✓ APPROVED</code>  🟢  <code>LIVE</code>  ⚡   ║
╚═══════════════════════════════════════════════════╝"""
    elif template == "compact":
        return f"""┌─ 💎 {scheme} {level} ────────────────┐
│ <b>{formatted}</b>           │
│ 📅{month}/{year} 🔐{cvv}             │
│ 🏛{bank_name[:15]}           │
│ 🌐{scheme} 💳{c_type}        │
│ 🌍{flag}{country_name}               │
│ ✅ LIVE 🟢 {timestamp}      │
└─────────────────────────────────────┘"""
    elif template == "minimal":
        return f"""<b>💳 {scheme} {level}</b>
<code>{formatted}</code>
📅 {month}/{year}  🔐 {cvv}
🏛 {bank_name}  🌍 {flag}
✅ LIVE 🟢
{timestamp}"""
    else:  # default
        return f"""🔹 <b>💳 CARD</b> 🔹
━━━━━━━━━━━━━━━━━━━━━━━━━
<code>{formatted}</code>
📅 {month}/{year}  🔐 {cvv}
━━━━━━━━━━━━━━━━━━━━━━━━━
🏛 {bank_name}
🌐 {scheme} • 💳 {c_type}
🌍 {flag} {country_name}
📊 {level}
🆔 {bin_str}
{timestamp}
✅ APPROVED 🟢 LIVE ⚡
━━━━━━━━━━━━━━━━━━━━━━━━━"""

def format_batch_result(cards_data, title="📋 BATCH RESULTS"):
    header = f"""╔═══════════════════════════════════════════════════╗
║              {title}                    ║
╠═══════════════════════════════════════════════════╣"""
    cards_section = ""
    for idx, (card_data, bin_info) in enumerate(cards_data, 1):
        bin_str, card_number, formatted, month, year, cvv = card_data
        scheme, c_type, bank_name, country_name, flag, level, scheme_icon = bin_info
        cards_section += f"""
┌─ #{idx} ──────────────────────────────────────┐
│ 💳 <code>{formatted}</code>                    │
│ 📅 {month}/{year}  🔐 {cvv}                    │
│ 🏛 {bank_name[:20]}  🌍 {flag}              │
│ 🌐 {scheme}  💳 {c_type}  📊 {level}          │
└─────────────────────────────────────────────┘"""
    footer = f"""
╠═══════════════════════════════════════════════════╣
║  📊 Total: <code>{len(cards_data)}</code>  ✅ Valid: <code>{len(cards_data)}</code>  ⚡ LIVE  ║
╚═══════════════════════════════════════════════════╝"""
    return header + cards_section + footer

# ==========================================
# 6. PANELS (User, Admin, Owner)
# ==========================================
def get_user_dashboard_kb(role: str, user_id: int):
    kb = [
        [InlineKeyboardButton(text="🎁 Redeem Center", callback_data="user_redeem_center")],
        [InlineKeyboardButton(text="👤 My Profile", callback_data="user_profile"),
         InlineKeyboardButton(text="📊 Stats", callback_data="user_stats")],
        [InlineKeyboardButton(text="📢 Official Links", callback_data="user_links"),
         InlineKeyboardButton(text="💬 Support", callback_data="user_support")],
        [InlineKeyboardButton(text="🔍 Check Card", callback_data="user_check_card")],
        [InlineKeyboardButton(text="🏆 Leaderboard", callback_data="user_leaderboard")],
        [InlineKeyboardButton(text="🔗 Referral", callback_data="user_referral")]
    ]
    if user_id == OWNER_ID:
        kb.append([InlineKeyboardButton(text="👑 Owner Panel", callback_data="panel_owner")])
    elif role == "admin":
        kb.append([InlineKeyboardButton(text="🛡️ Admin Panel", callback_data="panel_admin")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Analytics", callback_data="admin_stats"),
         InlineKeyboardButton(text="📦 Stock", callback_data="admin_stock")],
        [InlineKeyboardButton(text="👥 Users", callback_data="admin_users"),
         InlineKeyboardButton(text="📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="📁 Export", callback_data="admin_export"),
         InlineKeyboardButton(text="📝 Reports", callback_data="admin_reports")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="user_home")]
    ])

def get_owner_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 Auto-Post Manager", callback_data="owner_autopost")],
        [InlineKeyboardButton(text="📊 Analytics", callback_data="admin_stats"),
         InlineKeyboardButton(text="📦 Stock", callback_data="admin_stock")],
        [InlineKeyboardButton(text="👥 Users", callback_data="admin_users"),
         InlineKeyboardButton(text="📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🛡️ Admins", callback_data="owner_admins"),
         InlineKeyboardButton(text="📁 Export", callback_data="admin_export")],
        [InlineKeyboardButton(text="🎨 Templates", callback_data="owner_templates"),
         InlineKeyboardButton(text="📝 Reports", callback_data="admin_reports")],
        [InlineKeyboardButton(text="⏰ Scheduled Posts", callback_data="owner_schedule")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="user_home")]
    ])

# ==========================================
# 7. START & HOME
# ==========================================
@dp.message(CommandStart())
async def start_cmd(message: Message):
    # referral handling
    args = message.text.split()
    if len(args) > 1:
        ref_code = args[1]
        def process_ref(users):
            uid = str(message.from_user.id)
            if uid in users and not users[uid].get("referred_by"):
                for uid2, data in users.items():
                    if data.get("referral_code") == ref_code and uid2 != uid:
                        users[uid]["referred_by"] = uid2
                        users[uid2]["referral_earnings"] = users[uid2].get("referral_earnings", 0) + 1
                        break
            return users
        await modify_db("users.json", process_ref)

    users = await read_db("users.json")
    role = users.get(str(message.from_user.id), {}).get("role", "user")
    text = f"""✦ <b>Welcome to {PLATFORM_NAME}</b> ✦

> 🛡️ <b>Secured by:</b> {OWNER_USERNAME}
> ⚡ <b>Status:</b> 🟢 Online
> 📊 <b>Version:</b> 3.0 Enterprise

<b>Select an option:</b>"""
    await message.answer(text, reply_markup=get_user_dashboard_kb(role, message.from_user.id), parse_mode="HTML")

@dp.callback_query(F.data == "verify_join")
async def verify_join(call: CallbackQuery):
    await call.answer("Verifying...", show_alert=False)
    await call.message.delete()

@dp.callback_query(F.data == "user_home")
async def user_home(call: CallbackQuery):
    users = await read_db("users.json")
    role = users.get(str(call.from_user.id), {}).get("role", "user")
    text = f"✦ <b>{PLATFORM_NAME}</b> ✦\n\n> 🛡️ Managed by {OWNER_USERNAME}\n\n<b>Dashboard:</b>"
    await call.message.edit_text(text, reply_markup=get_user_dashboard_kb(role, call.from_user.id), parse_mode="HTML")

# ==========================================
# 8. USER FEATURES
# ==========================================
@dp.callback_query(F.data == "user_profile")
async def user_profile(call: CallbackQuery):
    users = await read_db("users.json")
    u = users.get(str(call.from_user.id), {})
    text = f"""👤 <b>Profile</b>

<b>ID:</b> <code>{call.from_user.id}</code>
<b>Username:</b> @{u.get('username', 'N/A')}
<b>Role:</b> <code>{u.get('role', 'user').upper()}</code>
<b>Joined:</b> <code>{u.get('join_date', 'Unknown')}</code>
<b>Redeemed:</b> <code>{u.get('redeem_count', 0)}</code>
<b>Checks:</b> <code>{u.get('total_checks', 0)}</code>
<b>Referral Code:</b> <code>{u.get('referral_code', 'N/A')}</code>
<b>Referred By:</b> <code>{u.get('referred_by', 'None')}</code>
<b>Earnings:</b> <code>{u.get('referral_earnings', 0)}</code>"""
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="user_profile")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="user_home")]
    ]), parse_mode="HTML")

@dp.callback_query(F.data == "user_stats")
async def user_stats(call: CallbackQuery):
    users = await read_db("users.json")
    stocks = await read_db("stocks.json")
    total = len(users)
    active = sum(1 for u in users.values() if not u.get("banned", False))
    available = len([s for s in stocks if not s.get("redeemed")])
    redeemed = len([s for s in stocks if s.get("redeemed")])
    text = f"""📊 <b>Platform Stats</b>

👥 Users: {total:,}
🟢 Active: {active:,}
📦 Available: {available:,}
🎟️ Redeemed: {redeemed:,}
⚡ Uptime: 99.9%
📈 Version: 3.0"""
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="user_stats")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="user_home")]
    ]), parse_mode="HTML")

@dp.callback_query(F.data == "user_links")
async def user_links(call: CallbackQuery):
    channels = await read_db("channels.json")
    text = "📢 <b>Official Channels</b>\n\n"
    if channels:
        for ch in channels:
            text += f"🔹 {ch['link']}\n"
    else:
        text += "> No channels configured."
    await call.message.edit_text(text, disable_web_page_preview=True, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back", callback_data="user_home")]
    ]), parse_mode="HTML")

@dp.callback_query(F.data == "user_support")
async def user_support(call: CallbackQuery):
    text = f"""💬 <b>Support</b>

Contact:
<b>Owner:</b> {OWNER_USERNAME}
<b>Response:</b> <24h

Send feedback via /feedback [message]"""
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back", callback_data="user_home")]
    ]), parse_mode="HTML")

@dp.callback_query(F.data == "user_check_card")
async def user_check_card(call: CallbackQuery):
    text = """🔍 <b>Card Checker</b>

Usage:
<code>/check [card]</code>

Examples:
<code>/check 4111111111111111</code>
<code>/check 411111</code>
<code>/check 411111|12|25|123</code>"""
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back", callback_data="user_home")]
    ]), parse_mode="HTML")

@dp.message(Command("check"))
async def check_card(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.answer("⚠️ <b>Usage:</b> <code>/check [card]</code>", parse_mode="HTML")
    query = args[1].strip()
    if len(query) < 6:
        return await message.answer("❌ <b>Invalid</b> – must be at least 6 digits.", parse_mode="HTML")
    bin_str = query[:6]
    if len(query) >= 16:
        parts = query.replace("|", " ").split()
        if len(parts) >= 4:
            card_num = parts[0]
            month = parts[1]
            year = parts[2]
            cvv = parts[3]
        else:
            card_num = query[:16]
            month = f"{random.randint(1,12):02d}"
            year = str(random.randint(2025,2035))
            cvv = ''.join([str(random.randint(0,9)) for _ in range(3)])
    else:
        card_num = bin_str + ''.join([str(random.randint(0,9)) for _ in range(10)])
        month = f"{random.randint(1,12):02d}"
        year = str(random.randint(2025,2035))
        cvv = ''.join([str(random.randint(0,9)) for _ in range(3)])
    if len(card_num) == 16:
        formatted = f"{card_num[:4]} {card_num[4:8]} {card_num[8:12]} {card_num[12:16]}"
    elif len(card_num) == 15:
        formatted = f"{card_num[:4]} {card_num[4:10]} {card_num[10:15]}"
    else:
        formatted = card_num
    bin_info = get_local_bin_data(bin_str)
    card_data = (bin_str, card_num, formatted, month, year, cvv)
    def inc_check(users):
        uid = str(message.from_user.id)
        if uid in users:
            users[uid]["total_checks"] = users[uid].get("total_checks", 0) + 1
        return users
    await modify_db("users.json", inc_check)
    result = format_enhanced_card(card_data, bin_info, "premium", True)
    await message.answer(result, parse_mode="HTML")

@dp.callback_query(F.data == "user_leaderboard")
async def user_leaderboard(call: CallbackQuery):
    users = await read_db("users.json")
    sorted_users = sorted(users.items(), key=lambda x: x[1].get("redeem_count", 0), reverse=True)[:10]
    text = "🏆 <b>Leaderboard</b>\n\n"
    for idx, (uid, data) in enumerate(sorted_users, 1):
        username = data.get("username", "Unknown")
        redeem = data.get("redeem_count", 0)
        checks = data.get("total_checks", 0)
        text += f"{idx}. @{username} – 🎁 {redeem} | 🔍 {checks}\n"
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back", callback_data="user_home")]
    ]), parse_mode="HTML")

@dp.callback_query(F.data == "user_referral")
async def user_referral(call: CallbackQuery):
    users = await read_db("users.json")
    uid = str(call.from_user.id)
    code = users.get(uid, {}).get("referral_code", "N/A")
    earnings = users.get(uid, {}).get("referral_earnings", 0)
    bot_username = (await call.bot.get_me()).username
    text = f"""🔗 <b>Referral</b>

Your code: <code>{code}</code>
Link: <code>https://t.me/{bot_username}?start={code}</code>

You referred <b>{earnings}</b> users.
Rewards for each new user!"""
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back", callback_data="user_home")]
    ]), parse_mode="HTML")

# ==========================================
# 9. REDEEM CENTER (with expiry)
# ==========================================
redeem_cooldowns = {}

@dp.callback_query(F.data == "user_redeem_center")
async def redeem_center(call: CallbackQuery):
    stocks = await read_db("stocks.json")
    now = datetime.now()
    valid = [s for s in stocks if not s.get("redeemed") and (not s.get("expiry") or datetime.fromisoformat(s["expiry"]) > now)]
    cats = {}
    for s in valid:
        cat = s["category"].upper()
        cats[cat] = cats.get(cat, 0) + 1
    text = "🎁 <b>Redeem Center</b>\n\n> Select category:\n"
    if not cats:
        text = "🎁 <b>Redeem Center</b>\n\n❌ No stock available."
    kb = []
    for cat, count in cats.items():
        kb.append([InlineKeyboardButton(text=f"{cat} ({count})", callback_data=f"ui_redeem_{cat}")])
    kb.append([InlineKeyboardButton(text="🔄 Refresh", callback_data="user_redeem_center")])
    kb.append([InlineKeyboardButton(text="🔙 Back", callback_data="user_home")])
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

@dp.callback_query(F.data.startswith("ui_redeem_"))
async def process_redeem(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    now = datetime.now()
    if user_id in redeem_cooldowns and redeem_cooldowns[user_id] > now:
        return await call.answer("⏳ Rate limited – wait 3s", show_alert=True)
    redeem_cooldowns[user_id] = now + timedelta(seconds=3)
    category = call.data.replace("ui_redeem_", "")
    found = [None]
    def redeem(stocks):
        for s in stocks:
            if s["category"].upper() == category.upper() and not s.get("redeemed"):
                if s.get("expiry") and datetime.fromisoformat(s["expiry"]) < datetime.now():
                    continue
                s["redeemed"] = True
                s["redeemed_by"] = user_id
                s["redeemed_at"] = datetime.now().isoformat()
                found[0] = s
                break
        return stocks
    await modify_db("stocks.json", redeem)
    if not found[0]:
        return await call.answer(f"❌ {category} out of stock!", show_alert=True)
    def inc(users):
        uid = str(user_id)
        if uid in users:
            users[uid]["redeem_count"] = users[uid].get("redeem_count", 0) + 1
        return users
    await modify_db("users.json", inc)
    await log_action("redeem", user_id, f"{category}: {found[0]['item']}")
    try:
        await bot.send_message(user_id, f"✅ <b>Redeemed</b>\n\nCategory: {found[0]['category']}\nItem: <code>{found[0]['item']}</code>", parse_mode="HTML")
        await call.answer("✅ Sent to DMs!", show_alert=True)
    except:
        await call.answer("❌ Start bot first to receive DMs.", show_alert=True)
    await redeem_center(call)

@dp.message(Command("redeem"))
async def redeem_cmd(message: Message):
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("⚠️ /redeem [category]", parse_mode="HTML")
    category = args[1]
    user_id = message.from_user.id
    now = datetime.now()
    if user_id in redeem_cooldowns and redeem_cooldowns[user_id] > now:
        return await message.answer("⏳ Rate limit – wait 3s.", parse_mode="HTML")
    redeem_cooldowns[user_id] = now + timedelta(seconds=3)
    found = [None]
    def redeem(stocks):
        for s in stocks:
            if s["category"].lower() == category.lower() and not s.get("redeemed"):
                if s.get("expiry") and datetime.fromisoformat(s["expiry"]) < datetime.now():
                    continue
                s["redeemed"] = True
                s["redeemed_by"] = user_id
                s["redeemed_at"] = datetime.now().isoformat()
                found[0] = s
                break
        return stocks
    await modify_db("stocks.json", redeem)
    if not found[0]:
        return await message.answer(f"❌ {category} out of stock.", parse_mode="HTML")
    def inc(users):
        uid = str(user_id)
        if uid in users:
            users[uid]["redeem_count"] = users[uid].get("redeem_count", 0) + 1
        return users
    await modify_db("users.json", inc)
    await log_action("cmd_redeem", user_id, f"{category}: {found[0]['item']}")
    await message.answer(f"✅ <b>Redeemed</b>\n\nCategory: {found[0]['category']}\nItem: <code>{found[0]['item']}</code>", parse_mode="HTML")

# ==========================================
# 10. ADMIN/OWNER COMMANDS
# ==========================================
@dp.message(Command("addstock"))
async def addstock(message: Message):
    users = await read_db("users.json")
    if users.get(str(message.from_user.id), {}).get("role") not in ["admin", "owner"]:
        return
    args = message.text.split(maxsplit=3)
    if len(args) < 3:
        return await message.answer("⚠️ /addstock [category] [item] [expiry_optional]", parse_mode="HTML")
    category = args[1]
    item = args[2]
    expiry = args[3] if len(args) > 3 else None
    def insert(stocks):
        stocks.append({
            "id": str(uuid.uuid4()),
            "category": category,
            "item": item,
            "redeemed": False,
            "redeemed_by": None,
            "added_at": datetime.now().isoformat(),
            "expiry": expiry
        })
        return stocks
    await modify_db("stocks.json", insert)
    await message.answer(f"✅ Added to {category}.", parse_mode="HTML")

@dp.message(Command("bulkstock"))
async def bulkstock(message: Message):
    users = await read_db("users.json")
    if users.get(str(message.from_user.id), {}).get("role") not in ["admin", "owner"]:
        return
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        return await message.answer("⚠️ /bulkstock [category] [item1|item2|...]", parse_mode="HTML")
    category = args[1]
    items = args[2].split("|")
    def insert(stocks):
        for item in items:
            stocks.append({
                "id": str(uuid.uuid4()),
                "category": category,
                "item": item.strip(),
                "redeemed": False,
                "redeemed_by": None,
                "added_at": datetime.now().isoformat(),
                "expiry": None
            })
        return stocks
    await modify_db("stocks.json", insert)
    await message.answer(f"✅ Added {len(items)} items to {category}.", parse_mode="HTML")

@dp.message(Command("addchannel"))
async def addchannel(message: Message):
    users = await read_db("users.json")
    if users.get(str(message.from_user.id), {}).get("role") not in ["admin", "owner"]:
        return
    args = message.text.split()
    if len(args) < 3:
        return await message.answer("⚠️ /addchannel [id] [link]", parse_mode="HTML")
    def append(channels):
        channels.append({"channel_id": args[1], "link": args[2]})
        return channels
    await modify_db("channels.json", append)
    await message.answer(f"✅ Channel added: {args[1]}", parse_mode="HTML")

@dp.message(Command("removechannel"))
async def removechannel(message: Message):
    users = await read_db("users.json")
    if users.get(str(message.from_user.id), {}).get("role") not in ["admin", "owner"]:
        return
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("⚠️ /removechannel [id]", parse_mode="HTML")
    def remove(channels):
        return [ch for ch in channels if str(ch["channel_id"]) != args[1]]
    await modify_db("channels.json", remove)
    await message.answer(f"🗑️ Removed channel {args[1]}", parse_mode="HTML")

@dp.message(Command("ban"))
async def ban_user(message: Message):
    users = await read_db("users.json")
    if users.get(str(message.from_user.id), {}).get("role") not in ["admin", "owner"]:
        return
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("⚠️ /ban [user_id]", parse_mode="HTML")
    def ban(users):
        if args[1] in users:
            users[args[1]]["banned"] = True
        return users
    await modify_db("users.json", ban)
    await message.answer(f"🔨 Banned {args[1]}", parse_mode="HTML")

@dp.message(Command("unban"))
async def unban_user(message: Message):
    users = await read_db("users.json")
    if users.get(str(message.from_user.id), {}).get("role") not in ["admin", "owner"]:
        return
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("⚠️ /unban [user_id]", parse_mode="HTML")
    def unban(users):
        if args[1] in users:
            users[args[1]]["banned"] = False
        return users
    await modify_db("users.json", unban)
    await message.answer(f"🕊️ Unbanned {args[1]}", parse_mode="HTML")

@dp.message(Command("addadmin"))
async def addadmin(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("⚠️ /addadmin [user_id]", parse_mode="HTML")
    def promote(users):
        if args[1] in users:
            users[args[1]]["role"] = "admin"
        return users
    await modify_db("users.json", promote)
    await message.answer(f"✅ Admin added: {args[1]}", parse_mode="HTML")

@dp.message(Command("removeadmin"))
async def removeadmin(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("⚠️ /removeadmin [user_id]", parse_mode="HTML")
    def demote(users):
        if args[1] in users:
            users[args[1]]["role"] = "user"
        return users
    await modify_db("users.json", demote)
    await message.answer(f"⬇️ Admin removed: {args[1]}", parse_mode="HTML")

# ==========================================
# 11. ADMIN PANEL CALLBACKS
# ==========================================
@dp.callback_query(F.data == "panel_admin")
async def panel_admin(call: CallbackQuery):
    users = await read_db("users.json")
    if users.get(str(call.from_user.id), {}).get("role") not in ["admin", "owner"]:
        return await call.answer("Forbidden", show_alert=True)
    await call.message.edit_text("🛡️ <b>Admin Panel</b>", reply_markup=get_admin_keyboard(), parse_mode="HTML")

@dp.callback_query(F.data == "panel_owner")
async def panel_owner(call: CallbackQuery):
    if call.from_user.id != OWNER_ID:
        return await call.answer("Forbidden", show_alert=True)
    await call.message.edit_text("👑 <b>Owner Panel</b>", reply_markup=get_owner_keyboard(), parse_mode="HTML")

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(call: CallbackQuery):
    users = await read_db("users.json")
    stocks = await read_db("stocks.json")
    logs = await read_db("logs.json")
    total = len(users)
    banned = sum(1 for u in users.values() if u.get("banned"))
    admins = sum(1 for u in users.values() if u.get("role") in ["admin", "owner"])
    available = len([s for s in stocks if not s.get("redeemed")])
    redeemed = len([s for s in stocks if s.get("redeemed")])
    today_logs = sum(1 for l in logs if l.get("timestamp", "").startswith(datetime.now().strftime("%Y-%m-%d")))
    text = f"""📊 <b>Analytics</b>

👥 Users: {total:,}
🚫 Banned: {banned:,}
🛡️ Admins: {admins:,}
📦 Available: {available:,}
🎟️ Redeemed: {redeemed:,}
📝 Today's Logs: {today_logs:,}
⚡ Uptime: 99.9%"""
    back = "panel_owner" if call.from_user.id == OWNER_ID else "panel_admin"
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🔙 Back", callback_data=back)]
    ]), parse_mode="HTML")

@dp.callback_query(F.data == "admin_stock")
async def admin_stock(call: CallbackQuery):
    stocks = await read_db("stocks.json")
    valid = [s for s in stocks if not s.get("redeemed")]
    text = f"📦 <b>Stock</b>\n\nTotal: {len(valid)} available\n\n"
    cats = {}
    for s in valid:
        cat = s["category"].upper()
        cats[cat] = cats.get(cat, 0) + 1
    for cat, count in cats.items():
        text += f"• {cat}: {count}\n"
    back = "panel_owner" if call.from_user.id == OWNER_ID else "panel_admin"
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="admin_stock")],
        [InlineKeyboardButton(text="🔙 Back", callback_data=back)]
    ]), parse_mode="HTML")

@dp.callback_query(F.data == "admin_users")
async def admin_users(call: CallbackQuery):
    text = """👥 <b>User Management</b>

Commands:
/ban [user_id]
/unban [user_id]
/addadmin [user_id]
/removeadmin [user_id]

Export via Export panel."""
    back = "panel_owner" if call.from_user.id == OWNER_ID else "panel_admin"
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back", callback_data=back)]
    ]), parse_mode="HTML")

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(call: CallbackQuery):
    text = """📢 <b>Broadcast</b>

Reply to a message with /broadcast to forward.
Or use /broadcast [text]"""
    back = "panel_owner" if call.from_user.id == OWNER_ID else "panel_admin"
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back", callback_data=back)]
    ]), parse_mode="HTML")

@dp.message(Command("broadcast"))
async def broadcast_cmd(message: Message, bot: Bot):
    users = await read_db("users.json")
    if users.get(str(message.from_user.id), {}).get("role") not in ["admin", "owner"]:
        return
    if message.reply_to_message:
        text = message.reply_to_message.text or message.reply_to_message.caption
        if not text:
            return await message.answer("Cannot broadcast non-text media.")
    else:
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            return await message.answer("⚠️ /broadcast [message] or reply to a message.")
        text = args[1]
    count = 0
    for uid in users:
        try:
            await bot.send_message(int(uid), f"📢 <b>Broadcast</b>\n\n{text}", parse_mode="HTML")
            count += 1
        except:
            pass
    await message.answer(f"✅ Sent to {count} users.", parse_mode="HTML")
    await log_action("broadcast", message.from_user.id, f"Sent to {count} users")

@dp.callback_query(F.data == "admin_export")
async def admin_export(call: CallbackQuery):
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 Users", callback_data="export_users"),
         InlineKeyboardButton(text="📄 Admins", callback_data="export_admins")],
        [InlineKeyboardButton(text="📄 Channels", callback_data="export_channels"),
         InlineKeyboardButton(text="📄 Groups", callback_data="export_groups")],
        [InlineKeyboardButton(text="📈 Logs", callback_data="export_logs")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="panel_admin" if call.from_user.id != OWNER_ID else "panel_owner")]
    ])
    await call.message.edit_text("📁 <b>Export</b>", reply_markup=markup, parse_mode="HTML")

@dp.callback_query(F.data.startswith("export_"))
async def export_data(call: CallbackQuery):
    action = call.data.replace("export_", "")
    content = ""
    filename = f"{action}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
    if action == "users":
        users = await read_db("users.json")
        content = "=== USERS ===\n\n"
        for uid, data in users.items():
            content += f"ID: {uid} | @{data.get('username')} | {data.get('role')} | Banned: {data.get('banned')} | Redeems: {data.get('redeem_count')}\n"
    elif action == "admins":
        users = await read_db("users.json")
        content = "=== ADMINS ===\n\n"
        for uid, data in users.items():
            if data.get("role") in ["admin", "owner"]:
                content += f"ID: {uid} | @{data.get('username')} | {data.get('role')}\n"
    elif action == "channels":
        channels = await read_db("channels.json")
        content = "=== CHANNELS ===\n\n"
        for ch in channels:
            content += f"ID: {ch['channel_id']} | Link: {ch['link']}\n"
    elif action == "groups":
        groups = await read_db("groups.json")
        content = "=== GROUPS ===\n\n"
        for g in groups:
            content += f"ID: {g['group_id']}\n"
    elif action == "logs":
        logs = await read_db("logs.json")
        content = "=== LOGS ===\n\n"
        for log in logs[-500:]:
            content += f"{log['timestamp']} | {log['action']} | {log['user_id']} | {log['details']}\n"
    if not content:
        content = "No data."
    await call.message.answer_document(document=BufferedInputFile(content.encode('utf-8'), filename=filename), caption=f"✅ Export: {filename}")

@dp.callback_query(F.data == "admin_reports")
async def admin_reports(call: CallbackQuery):
    reports = await read_db("reports.json")
    text = f"📝 <b>Reports</b>\nTotal: {len(reports)}\n\n"
    for r in reports[-5:]:
        text += f"• {r.get('timestamp')} | {r.get('user_id')} | {r.get('issue')[:50]}\n"
    back = "panel_owner" if call.from_user.id == OWNER_ID else "panel_admin"
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="admin_reports")],
        [InlineKeyboardButton(text="🔙 Back", callback_data=back)]
    ]), parse_mode="HTML")

@dp.message(Command("feedback"))
async def feedback(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.answer("⚠️ /feedback [your message]", parse_mode="HTML")
    def add_fb(fb):
        fb.append({
            "user_id": message.from_user.id,
            "message": args[1],
            "timestamp": datetime.now().isoformat()
        })
        return fb
    await modify_db("feedback.json", add_fb)
    await message.answer("✅ Feedback received.", parse_mode="HTML")
    await notify_owner(message.bot, f"💬 Feedback from {message.from_user.id}: {args[1]}")

# ==========================================
# 12. ADVANCED AUTO-POST MANAGER (OWNER ONLY)
# ==========================================
@dp.callback_query(F.data == "owner_autopost")
async def owner_autopost(call: CallbackQuery):
    if call.from_user.id != OWNER_ID:
        return
    settings = await read_db("settings.json")
    interval = settings.get('auto_post_interval', 300)
    if interval >= 3600:
        interval_display = f"{int(interval/3600)}h"
    else:
        interval_display = f"{int(interval/60)}m"
    status = "🟢 RUNNING" if settings.get('auto_post_enabled') else "🔴 STOPPED"
    channels = settings.get('auto_post_channels', [])
    ch_str = ", ".join(channels) if channels else "None"
    template = settings.get('post_template', 'premium').upper()
    daily = settings.get('daily_limit', 50)
    posted = settings.get('daily_post_count', 0)
    text = f"""🤖 <b>Auto-Post Engine</b>

Status: {status}
Channels: {ch_str}
Interval: {interval_display}
Template: {template}
Daily Limit: {daily} (posted {posted} today)

⚙️ Controls:"""
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Start", callback_data="ap_start"),
         InlineKeyboardButton(text="⏸️ Stop", callback_data="ap_stop"),
         InlineKeyboardButton(text="🔄 Restart", callback_data="ap_restart")],
        [InlineKeyboardButton(text="⏱️ Interval", callback_data="ap_set_time"),
         InlineKeyboardButton(text="📊 Limit", callback_data="ap_set_limit")],
        [InlineKeyboardButton(text="📺 Add Channel", callback_data="ap_add_channel"),
         InlineKeyboardButton(text="🗑️ Remove Channel", callback_data="ap_remove_channel")],
        [InlineKeyboardButton(text="🎨 Template", callback_data="ap_template")],
        [InlineKeyboardButton(text="🛠️ Test Post", callback_data="ap_testpost")],
        [InlineKeyboardButton(text="⏰ Scheduled Posts", callback_data="owner_schedule")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="panel_owner")]
    ])
    await call.message.edit_text(text, reply_markup=markup, parse_mode="HTML")

@dp.callback_query(F.data.in_(["ap_start", "ap_stop", "ap_restart"]))
async def ap_control(call: CallbackQuery):
    if call.from_user.id != OWNER_ID:
        return
    action = call.data
    def toggle(s):
        if action == "ap_start":
            s["auto_post_enabled"] = True
        elif action == "ap_stop":
            s["auto_post_enabled"] = False
        elif action == "ap_restart":
            s["auto_post_enabled"] = True
            s["daily_post_count"] = 0
            s["last_post_timestamp"] = 0
        return s
    await modify_db("settings.json", toggle)
    await call.answer(f"✅ {action.replace('ap_','').capitalize()}ed", show_alert=False)
    await owner_autopost(call)

@dp.callback_query(F.data == "ap_set_time")
async def ap_set_time(call: CallbackQuery):
    if call.from_user.id != OWNER_ID:
        return
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="5 min", callback_data="ap_time_5m"),
         InlineKeyboardButton(text="10 min", callback_data="ap_time_10m"),
         InlineKeyboardButton(text="15 min", callback_data="ap_time_15m")],
        [InlineKeyboardButton(text="30 min", callback_data="ap_time_30m"),
         InlineKeyboardButton(text="1 hr", callback_data="ap_time_1h"),
         InlineKeyboardButton(text="2 hr", callback_data="ap_time_2h")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="owner_autopost")]
    ])
    await call.message.edit_text("⏱️ <b>Set Interval</b>", reply_markup=markup, parse_mode="HTML")

@dp.callback_query(F.data.startswith("ap_time_"))
async def ap_time_set(call: CallbackQuery):
    if call.from_user.id != OWNER_ID:
        return
    val = call.data.replace("ap_time_", "")
    if val.endswith("m"):
        sec = int(val.replace("m","")) * 60
    elif val.endswith("h"):
        sec = int(val.replace("h","")) * 3600
    else:
        sec = 300
    def update(s):
        s["auto_post_interval"] = sec
        return s
    await modify_db("settings.json", update)
    await call.answer(f"Interval set to {val}", show_alert=True)
    await owner_autopost(call)

@dp.callback_query(F.data == "ap_set_limit")
async def ap_set_limit(call: CallbackQuery):
    if call.from_user.id != OWNER_ID:
        return
    limits = [10, 25, 50, 100, 200, 500]
    kb = []
    for i in range(0, len(limits), 3):
        row = [InlineKeyboardButton(str(limits[i+j]), callback_data=f"aplim_{limits[i+j]}") for j in range(3) if i+j < len(limits)]
        kb.append(row)
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="owner_autopost")])
    await call.message.edit_text("📊 <b>Daily Limit</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

@dp.callback_query(F.data.startswith("aplim_"))
async def ap_limit_set(call: CallbackQuery):
    if call.from_user.id != OWNER_ID:
        return
    limit = int(call.data.replace("aplim_", ""))
    def update(s):
        s["daily_limit"] = limit
        return s
    await modify_db("settings.json", update)
    await call.answer(f"Limit set to {limit}", show_alert=True)
    await owner_autopost(call)

@dp.callback_query(F.data == "ap_add_channel")
async def ap_add_channel(call: CallbackQuery):
    if call.from_user.id != OWNER_ID:
        return
    await call.message.edit_text("📺 <b>Add Channel</b>\n\nSend the channel ID or @username.\nUse: /addautochannel [id]")
    await call.answer("Use /addautochannel command.", show_alert=False)

@dp.message(Command("addautochannel"))
async def add_auto_channel(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("⚠️ /addautochannel [channel_id]", parse_mode="HTML")
    ch = args[1]
    def add_ch(s):
        if "auto_post_channels" not in s:
            s["auto_post_channels"] = []
        if ch not in s["auto_post_channels"]:
            s["auto_post_channels"].append(ch)
        return s
    await modify_db("settings.json", add_ch)
    await message.answer(f"✅ Added channel {ch}", parse_mode="HTML")

@dp.callback_query(F.data == "ap_remove_channel")
async def ap_remove_channel(call: CallbackQuery):
    if call.from_user.id != OWNER_ID:
        return
    settings = await read_db("settings.json")
    channels = settings.get("auto_post_channels", [])
    if not channels:
        return await call.answer("No channels added.", show_alert=True)
    kb = []
    for ch in channels:
        kb.append([InlineKeyboardButton(ch, callback_data=f"ap_rem_{ch}")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="owner_autopost")])
    await call.message.edit_text("🗑️ <b>Select channel to remove</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

@dp.callback_query(F.data.startswith("ap_rem_"))
async def ap_remove_channel_exec(call: CallbackQuery):
    if call.from_user.id != OWNER_ID:
        return
    ch = call.data.replace("ap_rem_", "")
    def remove(s):
        if "auto_post_channels" in s:
            s["auto_post_channels"] = [c for c in s["auto_post_channels"] if c != ch]
        return s
    await modify_db("settings.json", remove)
    await call.answer(f"Removed {ch}", show_alert=True)
    await owner_autopost(call)

@dp.callback_query(F.data == "ap_template")
async def ap_template(call: CallbackQuery):
    if call.from_user.id != OWNER_ID:
        return
    settings = await read_db("settings.json")
    current = settings.get('post_template', 'premium')
    templates = ["premium", "compact", "minimal", "default"]
    kb = []
    for t in templates:
        label = f"{'✅ ' if t == current else ''}{t.upper()}"
        kb.append([InlineKeyboardButton(label, callback_data=f"ap_temp_{t}")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="owner_autopost")])
    await call.message.edit_text("🎨 <b>Template</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

@dp.callback_query(F.data.startswith("ap_temp_"))
async def ap_temp_set(call: CallbackQuery):
    if call.from_user.id != OWNER_ID:
        return
    t = call.data.replace("ap_temp_", "")
    def update(s):
        s["post_template"] = t
        return s
    await modify_db("settings.json", update)
    await call.answer(f"Template set to {t}", show_alert=True)
    await owner_autopost(call)

@dp.callback_query(F.data == "ap_testpost")
async def ap_testpost(call: CallbackQuery, bot: Bot):
    if call.from_user.id != OWNER_ID:
        return
    settings = await read_db("settings.json")
    channels = settings.get("auto_post_channels", [])
    if not channels:
        return await call.answer("No channels added.", show_alert=True)
    await call.message.edit_text("🔄 Testing post on all channels...", parse_mode="HTML")
    template = settings.get('post_template', 'premium')
    bin_str, card_number, formatted, month, year, cvv = generate_random_card()
    bin_info = get_local_bin_data(bin_str)
    card_data = (bin_str, card_number, formatted, month, year, cvv)
    result = format_enhanced_card(card_data, bin_info, template, True)
    success = 0
    for ch in channels:
        try:
            target = parse_chat_id(ch)
            await bot.send_message(target, result, parse_mode="HTML")
            success += 1
        except Exception as e:
            pass
    await call.message.edit_text(f"✅ Test sent to {success}/{len(channels)} channels.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🔙 Back", callback_data="owner_autopost")]
    ]), parse_mode="HTML")

@dp.callback_query(F.data == "owner_schedule")
async def owner_schedule(call: CallbackQuery):
    if call.from_user.id != OWNER_ID:
        return
    await call.message.edit_text("⏰ <b>Scheduled Posts</b>\n\nUse /schedule [HH:MM] [message]")
    # Implementation via command below

@dp.message(Command("schedule"))
async def schedule_post(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        return await message.answer("⚠️ /schedule [HH:MM] [message]", parse_mode="HTML")
    time_str = args[1]
    content = args[2]
    try:
        hour, minute = map(int, time_str.split(":"))
        scheduled_time = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
        if scheduled_time < datetime.now():
            scheduled_time += timedelta(days=1)
        def add_sched(s):
            if "scheduled_posts" not in s:
                s["scheduled_posts"] = []
            s["scheduled_posts"].append({
                "time": scheduled_time.isoformat(),
                "content": content,
                "type": "custom"
            })
            return s
        await modify_db("settings.json", add_sched)
        await message.answer(f"✅ Scheduled for {scheduled_time.strftime('%Y-%m-%d %H:%M')}", parse_mode="HTML")
    except:
        await message.answer("❌ Invalid time format. Use HH:MM", parse_mode="HTML")

# ==========================================
# 13. BACKGROUND TASKS: AUTO-POST & SCHEDULED CHECKER
# ==========================================
async def auto_post_task(bot: Bot):
    await asyncio.sleep(10)
    logging.info("🤖 Auto-Post Task Started")
    while True:
        try:
            await asyncio.sleep(5)
            settings = await read_db("settings.json")
            if not settings.get("auto_post_enabled", False):
                continue
            channels = settings.get("auto_post_channels", [])
            if not channels:
                continue
            interval = settings.get("auto_post_interval", 300)
            daily_limit = settings.get("daily_limit", 50)
            last_ts = settings.get("last_post_timestamp", 0)
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            if settings.get("last_post_date") != today:
                def reset_day(s):
                    s["last_post_date"] = today
                    s["daily_post_count"] = 0
                    return s
                settings = await modify_db("settings.json", reset_day)
            if settings.get("daily_post_count", 0) >= daily_limit:
                continue
            if (now.timestamp() - last_ts) < interval:
                continue

            # Select content type randomly
            content_type = random.choice(settings.get("post_types", ["card"]))
            if content_type == "card":
                bin_str, card_number, formatted, month, year, cvv = generate_random_card()
                bin_info = get_local_bin_data(bin_str)
                card_data = (bin_str, card_number, formatted, month, year, cvv)
                template = settings.get('post_template', 'premium')
                message_text = format_enhanced_card(card_data, bin_info, template, True)
            elif content_type == "quote":
                quotes = ["Success is not final.", "The best way to predict the future is to create it.", "Stay hungry, stay foolish.", "Innovation distinguishes between a leader and a follower."]
                message_text = f"📝 <b>Quote of the day</b>\n\n\"{random.choice(quotes)}\""
            else:  # announcement
                announcements = ["New stock added!", "Stay tuned for updates.", "We are growing!"]
                message_text = f"📢 <b>Announcement</b>\n\n{random.choice(announcements)}"

            # Rotate channels
            rotation_index = settings.get("rotation_index", 0)
            channel = channels[rotation_index % len(channels)]
            rotation_index += 1
            def update_rot(s):
                s["rotation_index"] = rotation_index
                return s
            await modify_db("settings.json", update_rot)

            try:
                target = parse_chat_id(channel)
                await bot.send_message(target, message_text, parse_mode="HTML")
                logging.info(f"✅ Auto-posted to {channel}")
                def update_stats(s):
                    s["daily_post_count"] = s.get("daily_post_count", 0) + 1
                    s["last_post_timestamp"] = datetime.now().timestamp()
                    return s
                await modify_db("settings.json", update_stats)
            except Exception as e:
                logging.error(f"❌ Auto-post failed: {e}")
        except Exception as e:
            logging.error(f"⚠️ Auto-post loop error: {e}")
            await asyncio.sleep(30)

async def scheduled_post_checker(bot: Bot):
    while True:
        await asyncio.sleep(30)
        try:
            settings = await read_db("settings.json")
            scheduled = settings.get("scheduled_posts", [])
            now = datetime.now()
            remaining = []
            for s in scheduled:
                t = datetime.fromisoformat(s["time"])
                if t <= now:
                    channels = settings.get("auto_post_channels", [])
                    for ch in channels:
                        try:
                            target = parse_chat_id(ch)
                            await bot.send_message(target, s["content"], parse_mode="HTML")
                        except:
                            pass
                else:
                    remaining.append(s)
            if len(remaining) != len(scheduled):
                def update_sched(s):
                    s["scheduled_posts"] = remaining
                    return s
                await modify_db("settings.json", update_sched)
        except Exception as e:
            logging.error(f"Scheduled post error: {e}")

# ==========================================
# 14. KEEP-ALIVE SERVER
# ==========================================
async def handle_ping(request):
    return web.Response(text="Bot is running 🚀")

async def run_dummy_server():
    if USE_PYTHONANYWHERE_PROXY:
        return
    try:
        app = web.Application()
        app.router.add_get('/', handle_ping)
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.environ.get("PORT", 8080))
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        logging.info(f"🌐 Web server on port {port}")
    except Exception as e:
        logging.error(f"Server error: {e}")

# ==========================================
# 15. MAIN
# ==========================================
class PythonAnywhereSession(AiohttpSession):
    async def create_session(self) -> aiohttp.ClientSession:
        return aiohttp.ClientSession(trust_env=True)

async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    init_db()
    logging.info("✅ Database initialized")
    await ensure_user_registered(OWNER_ID, OWNER_USERNAME.replace("@", ""), None)

    if USE_PYTHONANYWHERE_PROXY:
        os.environ["http_proxy"] = "http://proxy.server:3128"
        os.environ["https_proxy"] = "http://proxy.server:3128"
        session = PythonAnywhereSession()
    else:
        session = AiohttpSession()

    bot = Bot(token=BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode="HTML"))

    asyncio.create_task(run_dummy_server())
    asyncio.create_task(auto_post_task(bot))
    asyncio.create_task(scheduled_post_checker(bot))

    await notify_owner(bot, "🟢 <b>Bot Online</b>")
    print(f"🚀 Bot started. Owner: {OWNER_USERNAME}")

    while True:
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            await dp.start_polling(bot)
        except Exception as e:
            logging.error(f"Polling error: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped.")
