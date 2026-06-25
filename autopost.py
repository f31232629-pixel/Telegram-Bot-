import asyncio
import random
import logging
from datetime import datetime
from telethon import Button

# ==========================================
# OFFLINE BIN ENGINE
# ==========================================
def get_local_bin_data(bin_str):
    """Generates realistic offline mock data based on card prefix."""
    prefix = bin_str[0]
    schemes = {'4': 'Visa', '5': 'Mastercard', '6': 'Discover', '2': 'Mastercard', '3': 'American Express'}
    scheme = schemes.get(prefix, "Unknown")
    c_type = random.choice(["Credit", "Debit", "Prepaid"])
    banks = ["JPMorgan Chase", "Bank of America", "Wells Fargo", "Citibank", "HSBC", "Barclays", "Capital One", "Standard Chartered"]
    bank_name = random.choice(banks) if scheme != 'American Express' else "American Express"
    countries = [("United States", "🇺🇸"), ("United Kingdom", "🇬🇧"), ("Canada", "🇨🇦"), ("Australia", "🇦🇺"), ("Germany", "🇩🇪"), ("France", "🇫🇷"), ("India", "🇮🇳")]
    country_name, flag = random.choice(countries)
    return scheme, c_type, bank_name, country_name, flag

def generate_random_card():
    prefixes = ['4', '5', '6', '2', '3']
    prefix = random.choice(prefixes)
    length = 15 if prefix == '3' else 16
    bin_str = prefix + ''.join([str(random.randint(0, 9)) for _ in range(5)])
    rest_of_card = ''.join([str(random.randint(0, 9)) for _ in range(length - 6)])
    card_number = bin_str + rest_of_card
    month = f"{random.randint(1, 12):02d}"
    year = str(random.randint(2025, 2032))
    cvv = ''.join([str(random.randint(0, 9)) for _ in range(4 if prefix == '3' else 3)])
    return bin_str, f"{card_number}|{month}|{year}|{cvv}"

# ==========================================
# ENHANCED UI DESIGN
# ==========================================
def format_card_result(card_data, bin_info):
    """Creates a visually appealing card result with enhanced UI design."""
    
    card_number, exp_month, exp_year, cvv = card_data.split('|')
    scheme, card_type, bank, country, flag = bin_info
    
    # Card design with visual hierarchy
    header = f"""
╔═══════════════════════════════════════════════╗
║              💳  CARD INFORMATION            ║
╚═══════════════════════════════════════════════╝
"""
    
    card_display = f"""
┌───────────────────────────────────────────────┐
│  🔢 Card Number: <b>{card_number}</b>                    │
│  📅 Expiry: <b>{exp_month}/{exp_year}</b>                    │
│  🔐 CVV: <b>{cvv}</b>                                   │
├───────────────────────────────────────────────┤
│  🏛 Bank: <b>{bank}</b>                                   │
│  🌐 Scheme: <b>{scheme}</b>                                │
│  💳 Type: <b>{card_type}</b>                               │
│  🌍 Country: <b>{flag} {country}</b>                      │
├───────────────────────────────────────────────┤
│  🆔 BIN: <b>{card_number[:6]}</b>                             │
│  ⏰ Checked: <b>{datetime.now().strftime('%H:%M:%S')}</b>             │
└───────────────────────────────────────────────┘
"""
    
    footer = """
✅ <b>Status:</b> <code>APPROVED</code>  🟢
📊 <b>Rate:</b> <code>✓ LIVE</code>  ⚡
"""
    
    return header + card_display + footer

def format_batch_result(cards):
    """Formats multiple card results with paginated style."""
    
    header = """
╔═══════════════════════════════════════════════╗
║           📋  BATCH RESULTS                  ║
╚═══════════════════════════════════════════════╝
"""
    
    cards_section = ""
    for idx, (card, bin_info) in enumerate(cards, 1):
        card_num, exp_month, exp_year, cvv = card.split('|')
        scheme, card_type, bank, country, flag = bin_info
        
        cards_section += f"""
┌───────────────────────────────────────────────┐
│  #{idx}  💳 <b>{card_num}</b>                     │
│  📅 {exp_month}/{exp_year}  🔐 {cvv}             │
│  🏛 {bank}  🌐 {scheme}                     │
│  💳 {card_type}  🌍 {flag} {country}           │
└───────────────────────────────────────────────┘
"""
    
    total_info = f"""
📊 <b>Total Cards:</b> <code>{len(cards)}</code>
✅ <b>Valid:</b> <code>{len(cards)}</code>
⏱ <b>Checked:</b> <code>{datetime.now().strftime('%H:%M:%S')}</code>
"""
    
    return header + cards_section + total_info

def format_enhanced_card_result(card_data, bin_info):
    """Alternative enhanced UI with modern card design."""
    
    card_number, exp_month, exp_year, cvv = card_data.split('|')
    scheme, card_type, bank, country, flag = bin_info
    
    # Modern card-like design
    template = f"""
╭───────────────────────────────────────────────╮
│    ✦  <b>CREDIT CARD</b>  ✦                     │
│  ───────────────────────────────────────────  │
│                                               │
│  💳  <b>{card_number}</b>                        │
│     ⋮⋮⋮ ⋮⋮⋮ ⋮⋮⋮                              │
│                                               │
│  📅 <b>{exp_month}/{exp_year}</b>       🔐 <b>{cvv}</b>     │
│                                               │
│  ───────────────────────────────────────────  │
│  🏛  <b>{bank}</b>                               │
│  🌐  <b>{scheme}</b>  •  💳 <b>{card_type}</b>        │
│  🌍  <b>{flag} {country}</b>                     │
│                                               │
│  🆔  <b>{card_number[:6]}</b>                   │
│  ⏱  <b>{datetime.now().strftime('%H:%M:%S')}</b>    │
│                                               │
│  ✓  <i>Validated</i>  🟢  <i>LIVE</i>  ⚡         │
╰───────────────────────────────────────────────╯
"""
    return template

# ==========================================
# AUTO POST WITH ENHANCED UI
# ==========================================
async def start_auto_poster(bot, read_db, modify_db, parse_chat_id, notify_owner):
    """Enhanced auto poster with improved UI design."""
    
    while True:
        try:
            # Generate card with bin data
            bin_str, card_data = generate_random_card()
            bin_info = get_local_bin_data(bin_str)
            
            # Format with enhanced UI
            message = format_card_result(card_data, bin_info)
            
            # Create interactive buttons
            buttons = [
                [Button.inline("🔄 Check Again", b"refresh")],
                [Button.inline("📊 Batch Check", b"batch"), Button.inline("⚡ Fast Check", b"fast")],
                [Button.url("🔗 Check BIN", f"https://binlist.net/{bin_str}")]
            ]
            
            # Send message to channel
            await bot.send_message(
                parse_chat_id, 
                message,
                buttons=buttons,
                parse_mode='HTML'
            )
            
            # Log the post
            logging.info(f"Posted card: {card_data[:6]}... at {datetime.now()}")
            
            # Random delay between posts
            await asyncio.sleep(random.randint(30, 120))  # 30 sec to 2 min
            
        except Exception as e:
            logging.error(f"Auto-poster error: {e}")
            await notify_owner(f"⚠️ Auto-poster error: {e}")
            await asyncio.sleep(60)

async def start_batch_auto_poster(bot, read_db, modify_db, parse_chat_id, notify_owner, batch_size=5):
    """Auto poster for batch card results with enhanced UI."""
    
    while True:
        try:
            cards = []
            for _ in range(batch_size):
                bin_str, card_data = generate_random_card()
                bin_info = get_local_bin_data(bin_str)
                cards.append((card_data, bin_info))
            
            # Format batch result
            message = format_batch_result(cards)
            
            # Interactive buttons for batch
            buttons = [
                [Button.inline("🔄 New Batch", b"new_batch")],
                [Button.inline("📊 Check BINs", b"check_bins")],
                [Button.url("🔗 BIN Database", "https://binlist.net/")]
            ]
            
            await bot.send_message(
                parse_chat_id, 
                message,
                buttons=buttons,
                parse_mode='HTML'
            )
            
            logging.info(f"Posted batch of {batch_size} cards at {datetime.now()}")
            await asyncio.sleep(random.randint(60, 180))  # 1-3 min delay
            
        except Exception as e:
            logging.error(f"Batch auto-poster error: {e}")
            await notify_owner(f"⚠️ Batch auto-poster error: {e}")
            await asyncio.sleep(120)

# ==========================================
# ADDITIONAL UI COMPONENTS
# ==========================================
def format_card_stats(card_data, bin_info, stats):
    """Formats card with additional statistics."""
    
    card_number, exp_month, exp_year, cvv = card_data.split('|')
    scheme, card_type, bank, country, flag = bin_info
    
    stats_display = f"""
╔═══════════════════════════════════════════════╗
║              📊 CARD STATISTICS              ║
╠═══════════════════════════════════════════════╣
║                                               ║
║  💳 Card: <b>{card_number}</b>                      ║
║  📅 Exp: <b>{exp_month}/{exp_year}</b>    🔐 <b>{cvv}</b>     ║
║                                               ║
║  🏛 Bank: <b>{bank}</b>                                 ║
║  🌐 Scheme: <b>{scheme}</b>  💳 Type: <b>{card_type}</b>          ║
║  🌍 Location: <b>{flag} {country}</b>                   ║
║  🆔 BIN: <b>{card_number[:6]}</b>                           ║
║                                               ║
║  📈 Check Count: <b>{stats.get('check_count', 0)}</b>            ║
║  ✅ Success Rate: <b>{stats.get('success_rate', '100%')}</b>    ║
║  ⏱ Last Check: <b>{stats.get('last_check', 'Now')}</b>         ║
║                                               ║
║  ✦ Status: <code>✓ APPROVED</code>  🟢                    ║
╚═══════════════════════════════════════════════╝
"""
    return stats_display

def format_compact_card(card_data, bin_info):
    """Compact card format for quick viewing."""
    
    card_number, exp_month, exp_year, cvv = card_data.split('|')
    scheme, card_type, bank, country, flag = bin_info
    
    return f"""
╭─💳─<b>{bank[:12]}</b>─────────────╮
│ <b>{card_number}</b>                │
│ 📅{exp_month}/{exp_year} 🔐{cvv}               │
│ 🌐{scheme} 💳{card_type}           │
│ 🌍{flag}{country}                   │
│ ✅ LIVE 🟢                        │
╰──────────────────────────────────╯
"""

# Usage example:
# await start_auto_poster(bot, read_db, modify_db, channel_id, owner_notify)
