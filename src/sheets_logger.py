import os
import json
import gspread
from datetime import datetime, timezone
import asyncio

# Superscript mapping for martingale counts
SUPERSCRIPTS = {0: "⁰", 1: "¹", 2: "²", 3: "³", 4: "⁴", 5: "⁵"}

# Currency flag mapping
FLAGS = {
    "USD": "🇺🇸",
    "EUR": "🇪🇺",
    "GBP": "🇬🇧",
    "JPY": "🇯🇵",
    "CHF": "🇨🇭",
    "CAD": "🇨🇦",
    "AUD": "🇦🇺",
    "CNH": "🇨🇳",
    "NZD": "🇳🇿",
}

def format_asset(asset: str) -> str:
    # E.g. "USDCHF_otc" -> "🇺🇸 USD/CHF 🇨🇭 OTC"
    # E.g. "EURUSD" -> "🇪🇺 EUR/USD 🇺🇸"
    upper_asset = asset.upper().replace("_OTC", "").replace("-OTC", "")
    
    if len(upper_asset) == 6:
        base = upper_asset[:3]
        quote = upper_asset[3:]
        base_flag = FLAGS.get(base, "")
        quote_flag = FLAGS.get(quote, "")
        
        formatted = f"{base_flag} {base}/{quote} {quote_flag}".strip()
        if "OTC" in asset.upper():
            formatted += " OTC"
        return formatted
    
    # Fallback
    return asset.replace("_otc", " OTC").replace("-otc", " OTC")

def format_trade_result(signal, status: str, mg_count: int) -> str:
    # Example format: ✅¹ 06:35 • 🇬🇧 GBP/USD 🇺🇸 OTC • Buy
    # or ❌³ 07:20 • 🇺🇸 USD/CAD 🇨🇦 OTC • Sell
    
    if status == "WIN":
        emoji = "✅"
    elif status == "LOSS":
        emoji = "❌"
    else:
        emoji = "⚠️"
        
    superscript = SUPERSCRIPTS.get(mg_count, str(mg_count))
    
    # Use the signal time if available, otherwise current time
    if signal.signal_time:
        time_str = signal.signal_time[:5] # "HH:MM"
    else:
        time_str = datetime.now(timezone.utc).strftime("%H:%M")
        
    asset_str = format_asset(signal.asset)
    direction_str = signal.direction.value.capitalize() # "Up" -> "Up", or maybe we want "Buy"/"Sell"
    
    if direction_str == "Up":
        direction_str = "Buy"
    elif direction_str == "Down":
        direction_str = "Sell"
        
    return f"{emoji}{superscript} {time_str} • {asset_str} • {direction_str}", time_str

def get_session_header(time_str: str) -> str:
    try:
        hour = int(time_str.split(':')[0])
    except Exception:
        hour = 0
        
    if 0 <= hour < 6:
        return "⚽ OVERNIGHT SESSION"
    elif 6 <= hour < 12:
        return "⛅ MORNING SESSION"
    elif 12 <= hour < 18:
        return "☀️ AFTERNOON SESSION"
    else:
        return "🌙 NIGHT SESSION"

def _log_to_sheets_sync(formatted_string: str, time_str: str):
    creds_json_str = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON")
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    
    if sheet_id:
        sheet_id = sheet_id.strip()
    
    if not creds_json_str or not sheet_id:
        print("[SHEETS] Missing GOOGLE_SHEETS_CREDENTIALS_JSON or GOOGLE_SHEET_ID in .env. Skipping Google Sheets logging.")
        return
        
    try:
        creds_dict = json.loads(creds_json_str)
        gc = gspread.service_account_from_dict(creds_dict)
        sh = gc.open_by_key(sheet_id)
        worksheet = sh.sheet1
        
        # Get today's date in format DD/MM/YYYY and Day (e.g. Thu)
        now_utc = datetime.now(timezone.utc)
        today_str = now_utc.strftime("%d/%m/%Y")
        day_str = now_utc.strftime("%a")
        
        # Find the column for today
        header_row = worksheet.row_values(1)
        
        col_index = None
        for i, val in enumerate(header_row):
            if today_str in str(val):
                col_index = i + 1
                break
                
        if col_index is None:
            # Create new column
            col_index = len(header_row) + 1
            worksheet.update_cell(1, col_index, today_str)
            worksheet.update_cell(2, col_index, day_str)
            
        col_values = worksheet.col_values(col_index)
        
        session_header = get_session_header(time_str)
        
        if session_header not in col_values:
            next_row = len(col_values) + 1
            if next_row < 3:
                next_row = 3
            worksheet.update_cell(next_row, col_index, session_header)
            worksheet.update_cell(next_row + 1, col_index, "-----------------------------")
            
            # Refetch to get updated length
            col_values = worksheet.col_values(col_index)
            
        # Find the first empty row in that column
        next_row = len(col_values) + 1
        if next_row < 3:
            next_row = 3
        
        # Write the formatted string
        worksheet.update_cell(next_row, col_index, formatted_string)
        print(f"[SHEETS] Successfully logged trade to Google Sheets: {formatted_string}")
        
    except Exception as e:
        print(f"[SHEETS] Failed to log to Google Sheets: {e}")

async def log_trade_to_sheets(signal, status: str, mg_count: int):
    """
    Logs the trade result to Google Sheets asynchronously to avoid blocking the main thread.
    """
    formatted_string, time_str = format_trade_result(signal, status, mg_count)
    # Run the synchronous gspread network calls in a thread pool
    await asyncio.to_thread(_log_to_sheets_sync, formatted_string, time_str)
