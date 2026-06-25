import asyncio
import json
import os
import logging
import uuid
import random
import aiohttp
from datetime import datetime, timedelta
from typing import Callable, Dict, Any, Awaitable
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.filters import Command, CommandStart
from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

# ==========================================
# 1. CONFIGURATION & EXECUTIVE INFO
# ==========================================
BOT_TOKEN = "8962210629:AAFhB5oNooreoJRhIuG7Frc9kqRxpQ2NWHA"
OWNER_ID = 8570832903
OWNER_USERNAME = "@theaadikoder"
EXECUTIVE_NAME = "Aditya Thakur"
PLATFORM_NAME = "TheAdiCoder Premium Network"
USE_PYTHONANYWHERE_PROXY = False

redeem_cooldowns = {}
bg_tasks = set()

# ==========================================
# 2. ENHANCED DATABASE ENGINE
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
        "auto_post_channel": None,
        "auto_post_interval": 300,
        "daily_limit": 50,
        "daily_post_count": 0,
        "last_post_date": "1970-01-01",
        "last_post_timestamp": 0,
        "post_template": "premium",
        "show_bin_info": True,
        "show_timestamp": True
    },
    "reports.json": [],
    "feedback.json": []
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
        await bot.send_message(chat_id=OWNER_ID, text=message)
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
                "last_active": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            is_new[0] = True
        else:
            if user_id == OWNER_ID: 
                users[uid_str]["role"], users[uid_str]["banned"] = "owner", False
            if "join_date" not in users[uid_str]: 
                users[uid_str]["join_date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if "redeem_count" not in users[uid_str]: 
                users[uid_str]["redeem_count"] = 0
            if "total_checks" not in users[uid_str]:
                users[uid_str]["total_checks"] = 0
            users[uid_str]["last_active"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return users

    await modify_db("users.json", register_user)
    if is_new[0] and bot and user_id != OWNER_ID: 
        await notify_owner(bot, f"🔔 **System Alert**\n\n👤 **New User:** `{user_id}` (@{safe_username})")
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
# 3. ENHANCED SECURITY MIDDLEWARE
# ==========================================
class ForceJoinMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]], event: Message, data: Dict[str, Any]) -> Any:
        user_id = event.from_user.id
        bot: Bot = data['bot']
        await ensure_user_registered(user_id, event.from_user.username, bot)
        users = await read_db("users.json")

        if users.get(str(user_id), {}).get("banned", False):
            if isinstance(event, Message): 
                await event.answer("🚫 **Access Revoked**\n\nYou have been banned from using this bot.")
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
            text = "🛑 **Verification Required**\n\n> To maintain platform security, you must join our verified channels:\n"
            for link in not_joined: 
                text += f"\n🔗 {link}"
            text += "\n\n⚠️ *After joining, click the button below to verify.*"
            markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Verify Access", callback_data="verify_join")]
            ])
            if isinstance(event, Message): 
                await event.answer(text, disable_web_page_preview=True, reply_markup=markup)
            elif isinstance(event, CallbackQuery):
                await event.message.answer(text, disable_web_page_preview=True, reply_markup=markup)
                await event.answer("Verification required!", show_alert=True)
            return
        return await handler(event, data)

dp = Dispatcher()
dp.message.middleware(ForceJoinMiddleware())
dp.callback_query.middleware(ForceJoinMiddleware())

# ==========================================
# 4. ENHANCED UI - BEAUTIFUL CARD DESIGN
# ==========================================
def get_local_bin_data(bin_str):
    """Enhanced BIN data with more realistic info"""
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
        "Standard Chartered", "Deutsche Bank", "BNP Paribas"
    ]
    bank_name = random.choice(banks) if scheme != 'American Express' else "American Express"
    countries = [
        ("United States", "🇺🇸"), ("United Kingdom", "🇬🇧"), 
        ("Canada", "🇨🇦"), ("Australia", "🇦🇺"), 
        ("Germany", "🇩🇪"), ("France", "🇫🇷"), 
        ("India", "🇮🇳"), ("Japan", "🇯🇵"),
        ("Brazil", "🇧🇷"), ("UAE", "🇦🇪")
    ]
    country_name, flag = random.choice(countries)
    level = random.choice(["Classic", "Gold", "Platinum", "World", "Black"])
    return scheme, c_type, bank_name, country_name, flag, level, scheme_icon

def generate_random_card():
    prefixes = ['4', '5', '6', '2', '3']
    prefix = random.choice(prefixes)
    length = 15 if prefix == '3' else 16
    bin_str = prefix + ''.join([str(random.randint(0, 9)) for _ in range(5)])
    rest_of_card = ''.join([str(random.randint(0, 9)) for _ in range(length - 6)])
    card_number = bin_str + rest_of_card
    # Format with spaces for better readability
    if prefix == '3':
        formatted = f"{card_number[:4]} {card_number[4:10]} {card_number[10:15]}"
    else:
        formatted = f"{card_number[:4]} {card_number[4:8]} {card_number[8:12]} {card_number[12:16]}"
    month = f"{random.randint(1, 12):02d}"
    year = str(random.randint(2025, 2035))
    cvv = ''.join([str(random.randint(0, 9)) for _ in range(4 if prefix == '3' else 3)])
    return bin_str, card_number, formatted, month, year, cvv

def format_enhanced_card(card_data, bin_info, template="premium", show_timestamp=True):
    """Create stunning card output with multiple templates"""
    bin_str, card_number, formatted, month, year, cvv = card_data
    scheme, c_type, bank_name, country_name, flag, level, scheme_icon = bin_info
    
    timestamp = f"⏱ {datetime.now().strftime('%H:%M:%S')}" if show_timestamp else ""
    
    if template == "premium":
        return f"""
╔═══════════════════════════════════════════════════╗
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
╚═══════════════════════════════════════════════════╝
"""

    elif template == "compact":
        return f"""
┌─ 💎 {scheme} {level} ────────────────┐
│ <b>{formatted}</b>           │
│ 📅{month}/{year} 🔐{cvv}             │
│ 🏛{bank_name[:15]}           │
│ 🌐{scheme} 💳{c_type}        │
│ 🌍{flag}{country_name}               │
│ ✅ LIVE 🟢 {timestamp}      │
└─────────────────────────────────────┘
"""

    elif template == "minimal":
        return f"""
<b>💳 {scheme} {level}</b>
<code>{formatted}</code>
📅 {month}/{year}  🔐 {cvv}
🏛 {bank_name}  🌍 {flag}
✅ LIVE 🟢
{timestamp}
"""

    else:  # default
        return f"""
🔹 <b>💳 CARD INFORMATION</b> 🔹
━━━━━━━━━━━━━━━━━━━━━━━━━
<code>{formatted}</code>
📅 {month}/{year}  🔐 {cvv}
━━━━━━━━━━━━━━━━━━━━━━━━━
🏛 {bank_name}
🌐 {scheme} • 💳 {c_type}
🌍 {flag} {country_name}
📊 {level} Level
🆔 {bin_str}
{timestamp}
✅ APPROVED 🟢 LIVE ⚡
━━━━━━━━━━━━━━━━━━━━━━━━━
"""

def format_batch_result(cards_data, title="📋 BATCH RESULTS"):
    """Format multiple cards in a beautiful batch view"""
    header = f"""
╔═══════════════════════════════════════════════════╗
║              {title}                    ║
╠═══════════════════════════════════════════════════╣
"""
    
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
└─────────────────────────────────────────────┘
"""
    
    footer = f"""
╠═══════════════════════════════════════════════════╣
║  📊 Total: <code>{len(cards_data)}</code>  ✅ Valid: <code>{len(cards_data)}</code>  ⚡ LIVE  ║
╚═══════════════════════════════════════════════════╝
"""
    return header + cards_section + footer

# ==========================================
# 5. ENHANCED PANELS
# ==========================================
def get_user_dashboard_kb(role: str, user_id: int):
    kb = [
        [InlineKeyboardButton(text="🎁 Redeem Center", callback_data="user_redeem_center")],
        [InlineKeyboardButton(text="👤 My Profile", callback_data="user_profile"), 
         InlineKeyboardButton(text="📊 Statistics", callback_data="user_stats")],
        [InlineKeyboardButton(text="📢 Official Links", callback_data="user_links"), 
         InlineKeyboardButton(text="💬 Support", callback_data="user_support")],
        [InlineKeyboardButton(text="🔍 Check Card", callback_data="user_check_card")]
    ]
    if user_id == OWNER_ID: 
        kb.append([InlineKeyboardButton(text="👑 Enter Owner Panel", callback_data="panel_owner")])
    elif role == "admin": 
        kb.append([InlineKeyboardButton(text="🛡️ Enter Admin Panel", callback_data="panel_admin")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Analytics", callback_data="admin_stats"), 
         InlineKeyboardButton(text="📦 Manage Stock", callback_data="admin_stock")],
        [InlineKeyboardButton(text="👥 Manage Users", callback_data="admin_users"), 
         InlineKeyboardButton(text="📢 Broadcast Hub", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="📁 Database Export", callback_data="admin_export"),
         InlineKeyboardButton(text="📝 Reports", callback_data="admin_reports")],
        [InlineKeyboardButton(text="🔙 Back to User Panel", callback_data="user_home")]
    ])

def get_owner_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 Auto-Post Manager", callback_data="owner_autopost")],
        [InlineKeyboardButton(text="📊 Analytics", callback_data="admin_stats"), 
         InlineKeyboardButton(text="📦 Manage Stock", callback_data="admin_stock")],
        [InlineKeyboardButton(text="👥 Manage Users", callback_data="admin_users"), 
         InlineKeyboardButton(text="📢 Broadcast Hub", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🛡️ Admin Controls", callback_data="owner_admins"), 
         InlineKeyboardButton(text="📁 Export DB", callback_data="admin_export")],
        [InlineKeyboardButton(text="🎨 Template Manager", callback_data="owner_templates"),
         InlineKeyboardButton(text="📝 Reports", callback_data="admin_reports")],
        [InlineKeyboardButton(text="🔙 Back to User Panel", callback_data="user_home")]
    ])

# ==========================================
# 6. ENHANCED USER FEATURES
# ==========================================
@dp.message(CommandStart())
async def start_cmd(message: Message):
    users = await read_db("users.json")
    role = users.get(str(message.from_user.id), {}).get("role", "user")
    text = f"""✦ **Welcome to {PLATFORM_NAME}** ✦

> 🛡️ <b>Secured & Managed by:</b> {OWNER_USERNAME}
> ⚡ <b>System Status:</b> 🟢 Online & Optimized
> 📊 <b>Platform:</b> Premium Enterprise Edition

<b>Select an option below to access your dashboard:</b>"""
    await message.answer(text, reply_markup=get_user_dashboard_kb(role, message.from_user.id))

@dp.callback_query(F.data == "user_check_card")
async def user_check_card(call: CallbackQuery):
    text = """🔍 <b>Card Checker</b>

Enter a card number or BIN to check:

<b>Examples:</b>
• <code>4111111111111111</code>
• <code>411111</code>
• <code>4111111111111111|12|25|123</code>

<i>Use the command:</i> <code>/check [card]</code>"""
    
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back", callback_data="user_home")]
    ]))

@dp.message(Command("check"))
async def check_card_cmd(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.answer("⚠️ <b>Usage:</b> <code>/check [card_number or bin]</code>")
    
    query = args[1].strip()
    
    # Generate mock card info based on query
    if len(query) >= 6:
        bin_str = query[:6]
        if len(query) >= 16:
            # Full card
            card_parts = query.replace("|", " ").split()
            if len(card_parts) >= 4:
                card_num = card_parts[0]
                month = card_parts[1] if len(card_parts) > 1 else f"{random.randint(1, 12):02d}"
                year = card_parts[2] if len(card_parts) > 2 else str(random.randint(2025, 2035))
                cvv = card_parts[3] if len(card_parts) > 3 else ''.join([str(random.randint(0, 9)) for _ in range(3)])
            else:
                card_num = query[:16]
                month = f"{random.randint(1, 12):02d}"
                year = str(random.randint(2025, 2035))
                cvv = ''.join([str(random.randint(0, 9)) for _ in range(3)])
        else:
            card_num = bin_str + ''.join([str(random.randint(0, 9)) for _ in range(10)])
            month = f"{random.randint(1, 12):02d}"
            year = str(random.randint(2025, 2035))
            cvv = ''.join([str(random.randint(0, 9)) for _ in range(3)])
    else:
        return await message.answer("❌ <b>Invalid format.</b> Please provide a valid card number or BIN.")
    
    # Format card number
    if len(card_num) == 16:
        formatted = f"{card_num[:4]} {card_num[4:8]} {card_num[8:12]} {card_num[12:16]}"
    elif len(card_num) == 15:
        formatted = f"{card_num[:4]} {card_num[4:10]} {card_num[10:15]}"
    else:
        formatted = card_num
    
    bin_info = get_local_bin_data(bin_str)
    card_data = (bin_str, card_num, formatted, month, year, cvv)
    
    # Check if user exists and increment check count
    def update_user(users):
        uid = str(message.from_user.id)
        if uid in users:
            users[uid]["total_checks"] = users[uid].get("total_checks", 0) + 1
        return users
    await modify_db("users.json", update_user)
    
    result = format_enhanced_card(card_data, bin_info, "premium", True)
    await message.answer(result, parse_mode="HTML")

@dp.callback_query(F.data == "user_profile")
async def user_profile(call: CallbackQuery):
    users = await read_db("users.json")
    user_data = users.get(str(call.from_user.id), {})
    text = f"""👤 <b>User Profile Dashboard</b>

<b>ID:</b> <code>{call.from_user.id}</code>
<b>Username:</b> @{user_data.get('username', 'N/A')}
<b>Role Level:</b> <code>{str(user_data.get('role', 'user')).upper()}</code>
<b>Account Created:</b> <code>{user_data.get('join_date', 'Unknown')}</code>
<b>Items Redeemed:</b> <code>{user_data.get('redeem_count', 0)}</code>
<b>Total Checks:</b> <code>{user_data.get('total_checks', 0)}</code>
<b>Last Active:</b> <code>{user_data.get('last_active', 'Unknown')}</code>"""
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="user_profile")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="user_home")]
    ]))

@dp.callback_query(F.data == "user_stats")
async def user_public_stats(call: CallbackQuery):
    users = await read_db("users.json")
    stocks = await read_db("stocks.json")
    available_stocks = [s for s in stocks if not s.get("redeemed")]
    total_users = len(users)
    active_users = sum(1 for u in users.values() if u.get("role") in ["admin", "owner"] or not u.get("banned", False))
    
    text = f"""📊 <b>Platform Metrics</b>

<b>📈 User Statistics:</b>
• Total Users: <code>{total_users:,}</code>
• Active Users: <code>{active_users:,}</code>
• Admins: <code>{sum(1 for u in users.values() if u.get('role') in ['admin', 'owner'])}</code>

<b>📦 Stock Statistics:</b>
• Available Items: <code>{len(available_stocks):,}</code>
• Total Redeemed: <code>{len([s for s in stocks if s.get('redeemed')]):,}</code>

<b>⚡ System Status:</b>
• Uptime: <code>99.9%</code>
• Architecture: <code>Premium SaaS Engine</code>
• Version: <code>3.0.0</code>"""
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="user_stats")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="user_home")]
    ]))

# ==========================================
# 7. ENHANCED AUTO-POST MANAGER
# ==========================================
@dp.callback_query(F.data == "owner_autopost")
async def owner_autopost_menu(call: CallbackQuery):
    if call.from_user.id != OWNER_ID: return
    settings = await read_db("settings.json")

    interval_sec = settings.get('auto_post_interval', 300)
    if interval_sec >= 3600 and interval_sec % 3600 == 0: 
        interval_display = f"{int(interval_sec/3600)} Hour(s)"
    else: 
        interval_display = f"{int(interval_sec/60)} Minute(s)"

    status_icon = "🟢 RUNNING" if settings.get('auto_post_enabled') else "🔴 STOPPED"
    template = settings.get('post_template', 'premium').upper()

    text = f"""🤖 <b>Enterprise Auto-Post Engine</b>

<b>Engine Status:</b> <code>{status_icon}</code>
<b>Target Channel:</b> <code>{settings.get('auto_post_channel', 'Not Set')}</code>
<b>Post Interval:</b> <code>{interval_display}</code>
<b>Daily Limit:</b> <code>{settings.get('daily_limit', 50)} Posts/Day</code>
<b>Posted Today:</b> <code>{settings.get('daily_post_count', 0)}</code>
<b>Template:</b> <code>{template}</code>

⚙️ <b>Engine Controls:</b>"""

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Start", callback_data="ap_start"),
         InlineKeyboardButton(text="⏸️ Stop", callback_data="ap_stop"),
         InlineKeyboardButton(text="🔄 Restart", callback_data="ap_restart")],
        [InlineKeyboardButton(text="⏱️ Set Interval", callback_data="ap_set_time"),
         InlineKeyboardButton(text="📊 Set Limit", callback_data="ap_set_limit")],
        [InlineKeyboardButton(text="📺 Setup Channel", callback_data="ap_set_channel"),
         InlineKeyboardButton(text="🛠️ Force Test", callback_data="ap_testpost")],
        [InlineKeyboardButton(text="🎨 Change Template", callback_data="ap_template")],
        [InlineKeyboardButton(text="🔙 Back to Owner Panel", callback_data="panel_owner")]
    ])
    await call.message.edit_text(text, reply_markup=markup, parse_mode="HTML")

@dp.callback_query(F.data == "ap_template")
async def ap_template_menu(call: CallbackQuery):
    if call.from_user.id != OWNER_ID: return
    settings = await read_db("settings.json")
    current = settings.get('post_template', 'premium')
    
    text = f"""🎨 <b>Post Template Manager</b>

<b>Current Template:</b> <code>{current.upper()}</code>

<b>Available Templates:</b>
• <code>premium</code> - Full featured design
• <code>compact</code> - Compact view
• <code>minimal</code> - Clean minimal design
• <code>default</code> - Standard design

Select a template below:"""
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ {t.upper()}" if t == current else t.upper(), callback_data=f"ap_template_set_{t}") 
         for t in ["premium", "compact"]],
        [InlineKeyboardButton(text=f"✅ {t.upper()}" if t == current else t.upper(), callback_data=f"ap_template_set_{t}") 
         for t in ["minimal", "default"]],
        [InlineKeyboardButton(text="🔙 Back", callback_data="owner_autopost")]
    ])
    await call.message.edit_text(text, reply_markup=markup, parse_mode="HTML")

@dp.callback_query(F.data.startswith("ap_template_set_"))
async def ap_template_set(call: CallbackQuery):
    if call.from_user.id != OWNER_ID: return
    template = call.data.replace("ap_template_set_", "")
    
    def update_template(s):
        s["post_template"] = template
        return s
    await modify_db("settings.json", update_template)
    await call.answer(f"✅ Template set to {template.upper()}!", show_alert=True)
    await owner_autopost_menu(call)

@dp.callback_query(F.data == "ap_testpost")
async def ap_testpost_cb(call: CallbackQuery, bot: Bot):
    if call.from_user.id != OWNER_ID: return
    settings = await read_db("settings.json")
    channel_id = settings.get("auto_post_channel")

    if not channel_id or channel_id == "None":
        return await call.message.edit_text(
            "❌ <b>No Channel Set:</b> Please set a channel first via <code>📺 Setup Channel</code>.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Back", callback_data="owner_autopost")]
            ]),
            parse_mode="HTML"
        )

    await call.message.edit_text(f"🔄 <b>Testing Auto-Post...</b>\nSending a test card to <code>{channel_id}</code>", parse_mode="HTML")

    try:
        bin_str, card_number, formatted, month, year, cvv = generate_random_card()
        bin_info = get_local_bin_data(bin_str)
        card_data = (bin_str, card_number, formatted, month, year, cvv)
        template = settings.get('post_template', 'premium')
        
        # Enhanced test post with beautiful UI
        result = format_enhanced_card(card_data, bin_info, template, True)
        test_header = "🛠 <b>[TEST POST]</b> 🛠\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        full_message = test_header + result

        target_chat = parse_chat_id(channel_id)
        await bot.send_message(chat_id=target_chat, text=full_message, parse_mode="HTML")
        
        # Add interactive buttons to test post
        buttons = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Refresh Card", callback_data="ap_testpost")],
            [InlineKeyboardButton(text="📊 Check BIN", url=f"https://binlist.net/{bin_str}")]
        ])
        await bot.send_message(
            chat_id=target_chat,
            text="✅ <b>Interactive Card Checker</b>\n\nClick below to check this card or refresh for a new one:",
            reply_markup=buttons,
            parse_mode="HTML"
        )
        
        await call.message.edit_text(
            "✅ <b>Test Successful!</b>\nThe message was successfully posted to your channel.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Back to Manager", callback_data="owner_autopost")]
            ]),
            parse_mode="HTML"
        )
    except TelegramBadRequest as e:
        await call.message.edit_text(
            f"❌ <b>Test Failed!</b>\n\n<b>Telegram Error:</b> <code>{e}</code>\n\n<i>Make sure the bot is an ADMIN in the channel and the ID is correct.</i>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Back", callback_data="owner_autopost")]
            ]),
            parse_mode="HTML"
        )
    except Exception as e:
        await call.message.edit_text(
            f"❌ <b>Test Failed!</b>\n\n<b>System Error:</b> <code>{e}</code>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Back", callback_data="owner_autopost")]
            ]),
            parse_mode="HTML"
        )

# ==========================================
# 8. ENHANCED AUTO-POST TASK
# ==========================================
async def auto_post_task(bot: Bot):
    await asyncio.sleep(5)
    logging.info("⚙️ Enhanced Auto-Post Task Started...")

    while True:
        try:
            await asyncio.sleep(5)
            settings = await read_db("settings.json")

            if not settings.get("auto_post_enabled", False):
                continue

            channel_id = settings.get("auto_post_channel")
            interval = settings.get("auto_post_interval", 300)
            daily_limit = settings.get("daily_limit", 50)
            last_ts = settings.get("last_post_timestamp", 0)

            if not channel_id or channel_id == "None": 
                continue

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

            # Generate beautiful card
            bin_str, card_number, formatted, month, year, cvv = generate_random_card()
            bin_info = get_local_bin_data(bin_str)
            card_data = (bin_str, card_number, formatted, month, year, cvv)
            template = settings.get('post_template', 'premium')
            
            result = format_enhanced_card(card_data, bin_info, template, True)

            # Add interactive buttons to posted card
            buttons = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Next Card", callback_data="ap_next")],
                [InlineKeyboardButton(text="📊 Check BIN", url=f"https://binlist.net/{bin_str}")],
                [InlineKeyboardButton(text="📩 Report Issue", callback_data="ap_report")]
            ])

            try:
                target_chat = parse_chat_id(channel_id)
                await bot.send_message(chat_id=target_chat, text=result, reply_markup=buttons, parse_mode="HTML")
                logging.info(f"✅ Auto-posted enhanced card {bin_str}")

                def update_post_stats(s):
                    s["daily_post_count"] = s.get("daily_post_count", 0) + 1
                    s["last_post_timestamp"] = datetime.now().timestamp()
                    return s
                await modify_db("settings.json", update_post_stats)

            except Exception as e:
                err_msg = str(e)
                logging.error(f"❌ Failed to post: {err_msg}")
                def turn_off_engine(s):
                    s["auto_post_enabled"] = False
                    return s
                await modify_db("settings.json", turn_off_engine)
                await notify_owner(bot, f"⚠️ <b>Auto-Post Engine Stopped!</b>\n\nBot couldn't post to the channel.\n<b>Reason:</b> <code>{err_msg}</code>\n\n<i>Engine has been turned OFF. Please fix the issue and turn it ON from the Owner Panel.</i>")

        except Exception as e:
            logging.error(f"⚠️ Loop Error: {e}")
            await asyncio.sleep(10)

@dp.callback_query(F.data == "ap_next")
async def ap_next_callback(call: CallbackQuery):
    """Handle 'Next Card' button clicks from posted messages"""
    await call.answer("🔄 Generating next card...", show_alert=False)
    try:
        bin_str, card_number, formatted, month, year, cvv = generate_random_card()
        bin_info = get_local_bin_data(bin_str)
        card_data = (bin_str, card_number, formatted, month, year, cvv)
        settings = await read_db("settings.json")
        template = settings.get('post_template', 'premium')
        result = format_enhanced_card(card_data, bin_info, template, True)
        
        buttons = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Next Card", callback_data="ap_next")],
            [InlineKeyboardButton(text="📊 Check BIN", url=f"https://binlist.net/{bin_str}")],
            [InlineKeyboardButton(text="📩 Report Issue", callback_data="ap_report")]
        ])
        
        await call.message.edit_text(result, reply_markup=buttons, parse_mode="HTML")
    except Exception as e:
        await call.answer(f"Error: {e}", show_alert=True)

@dp.callback_query(F.data == "ap_report")
async def ap_report_callback(call: CallbackQuery):
    """Handle report button clicks"""
    await call.answer("📩 Report feature coming soon!", show_alert=True)

# ==========================================
# 9. ADMIN REPORTS FEATURE
# ==========================================
@dp.callback_query(F.data == "admin_reports")
async def admin_reports(call: CallbackQuery):
    if call.from_user.id != OWNER_ID:
        users = await read_db("users.json")
        if users.get(str(call.from_user.id), {}).get("role") != "admin":
            return await call.answer("Forbidden", show_alert=True)
    
    reports = await read_db("reports.json")
    text = f"""📝 <b>Reports Dashboard</b>

<b>Total Reports:</b> <code>{len(reports)}</code>
<b>Pending:</b> <code>{sum(1 for r in reports if not r.get('resolved', False))}</code>
<b>Resolved:</b> <code>{sum(1 for r in reports if r.get('resolved', False))}</code>

📋 <b>Recent Reports:</b>"""
    
    for report in reports[-5:]:
        text += f"\n\n🔹 <b>ID:</b> <code>{report.get('id', 'N/A')}</code>"
        text += f"\n👤 <b>User:</b> <code>{report.get('user_id', 'N/A')}</code>"
        text += f"\n📝 <b>Issue:</b> {report.get('issue', 'N/A')}"
        text += f"\n⏱ <b>Time:</b> {report.get('timestamp', 'N/A')}"
        text += f"\n📊 <b>Status:</b> {'✅ Resolved' if report.get('resolved') else '⏳ Pending'}"
    
    back_btn = "panel_owner" if call.from_user.id == OWNER_ID else "panel_admin"
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="admin_reports")],
        [InlineKeyboardButton(text="🔙 Back", callback_data=back_btn)]
    ]), parse_mode="HTML")

# ==========================================
# 10. KEEP-ALIVE WEB SERVER
# ==========================================
async def handle_ping(request):
    return web.Response(text="Bot is awake and running 24/7! 🚀")

async def run_dummy_server():
    if USE_PYTHONANYWHERE_PROXY: return
    try:
        app = web.Application()
        app.router.add_get('/', handle_ping)
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.environ.get("PORT", 8080))
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        logging.info(f"🌐 Keep-alive web server running on port {port}")
    except Exception as e: 
        logging.error(f"🌐 Dummy Server Skipped: {e}")

# ==========================================
# 11. ENGINE IGNITION
# ==========================================
class PythonAnywhereSession(AiohttpSession):
    async def create_session(self) -> aiohttp.ClientSession:
        return aiohttp.ClientSession(trust_env=True)

async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    init_db()
    logging.info("✅ Database Multi-Node Architecture Initialized")

    await ensure_user_registered(OWNER_ID, OWNER_USERNAME.replace("@", ""), None)

    if USE_PYTHONANYWHERE_PROXY:
        os.environ["http_proxy"] = "http://proxy.server:3128"
        os.environ["https_proxy"] = "http://proxy.server:3128"
        os.environ["HTTP_PROXY"] = "http://proxy.server:3128"
        os.environ["HTTPS_PROXY"] = "http://proxy.server:3128"
        session = PythonAnywhereSession()
        print("🔄 Connecting via PythonAnywhere Proxy...")
    else:
        session = AiohttpSession()
        print("🔄 Connecting directly (Render/VPS mode)...")

    bot = Bot(token=BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode="HTML"))

    # Background Tasks
    asyncio.create_task(run_dummy_server())
    asyncio.create_task(auto_post_task(bot))

    print(f"🚀 Premium Enterprise Engine Online! Executive Access: {OWNER_USERNAME}")
    await notify_owner(bot, "🟢 <b>System Online:</b> Platform Reboot Successful.")

    while True:
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            await dp.start_polling(bot)
        except Exception as e:
            logging.error(f"⚠️ Network Error: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Manual Termination Sequence Initiated.")
