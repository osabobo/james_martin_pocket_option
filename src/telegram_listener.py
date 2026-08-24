import asyncio
import sys

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import os
from dotenv import load_dotenv
from .signal_parser import parse_signal
from .risk import RiskEngine
from .executor import DemoExecutor
from .config import settings
# Force stdout to UTF-8 to prevent UnicodeEncodeError when printing emojis on Windows
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
from .sheets_logger import log_trade_to_sheets

load_dotenv()

import datetime

def parse_utc_offset(tz_str):
    if not tz_str:
        return datetime.timezone.utc
    tz_str = tz_str.upper().replace('UTC', '').strip()
    if not tz_str:
        return datetime.timezone.utc
    sign = 1 if tz_str.startswith('+') else -1
    tz_str = tz_str.lstrip('+-')
    parts = tz_str.split(':')
    hours = int(parts[0])
    minutes = int(parts[1]) if len(parts) > 1 else 0
    return datetime.timezone(sign * datetime.timedelta(hours=hours, minutes=minutes))

def start_dummy_server():
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    port = int(os.environ.get("PORT", 8080))
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Bot is running!")
        def log_message(self, format, *args):
            pass

    server = HTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"Dummy web server started on port {port} for Render health checks")

async def keep_alive_task():
    url = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("KEEP_ALIVE_URL")
    if not url:
        return
    import aiohttp
    print(f"Starting keep-alive ping loop for {url}")
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                await session.get(url)
                print(f"[KEEP-ALIVE] Pinged {url} successfully to prevent Render sleep")
            except Exception as e:
                print(f"[KEEP-ALIVE] Ping failed: {e}")
            await asyncio.sleep(600)  # Ping every 10 minutes (600 seconds)

async def execute_with_martingale(executor, risk, signal, max_martingale=2, multiplier=2.2):
    request = risk.make_request(signal)
    current_amount = request.amount
    mg_count = 0
    
    # Use signal's max_martingale if provided, but cap it to user's max preference (2).
    # If signal doesn't specify (0), default to the user's preference.
    allowed_mgs = signal.max_martingale if signal.max_martingale > 0 else max_martingale
    allowed_mgs = min(allowed_mgs, max_martingale)
    
    while mg_count <= allowed_mgs:
        print(f"[MARTINGALE] Executing trade (MG step {mg_count}/{allowed_mgs}): {signal.asset} {signal.direction.value} {signal.expiry_seconds}s ${current_amount:.2f}")
        
        # Create a new request for this step with the updated amount
        mg_request = risk.make_request(signal)
        mg_request.amount = current_amount
        
        # Retry logic: if the broker rejects the trade, wait and try again
        result = None
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            result = await executor.place_trade(mg_request)
            if result.accepted and result.trade_id:
                break
            if attempt < max_retries:
                print(f"[MARTINGALE] Trade rejected on attempt {attempt}/{max_retries}. Retrying in 3 seconds...")
                await asyncio.sleep(3)
            else:
                print(f"[MARTINGALE] Trade rejected after {max_retries} attempts. Aborting martingale.")
        
        if mg_count == 0:
            risk.mark_submitted(signal)
            
        print({"event": "demo_trade", "mg_step": mg_count, "signal": signal.model_dump(), "trade": result.model_dump()})
        
        if not result.accepted or not result.trade_id:
            print(f"[MARTINGALE] Trade rejected or missing trade_id. Aborting.")
            await log_trade_to_sheets(signal, "REJECTED", mg_count)
            break
            
        print(f"[MARTINGALE] Waiting for trade {result.trade_id} to finish...")
        # We do NOT manually sleep here because get_trade_result blocks until the broker sends the closing event.
        # Add 30 seconds buffer to the expiry for the network delay
        timeout_seconds = signal.expiry_seconds + 60
        check_result = await executor.get_trade_result(result.trade_id, timeout=timeout_seconds)
        print(f"[MARTINGALE] Result for {result.trade_id}: {check_result.status}")
        
        if check_result.status == "WIN":
            print(f"[MARTINGALE] Trade WON! Celebrating and stopping.")
            await log_trade_to_sheets(signal, "WIN", mg_count)
            break
        elif check_result.status == "LOSS":
            print(f"[MARTINGALE] Trade result: LOSS.")
            if mg_count < allowed_mgs:
                mg_count += 1
                current_amount *= multiplier
                print(f"[MARTINGALE] Initiating Martingale step {mg_count}. New amount: ${current_amount:.2f}")
            else:
                print(f"[MARTINGALE] Max martingales ({allowed_mgs}) reached. Stopping.")
                await log_trade_to_sheets(signal, "LOSS", mg_count)
                break
        else:
            print(f"[MARTINGALE] Trade result is {check_result.status}. Cannot safely proceed with martingale.")
            print("[MARTINGALE] Aborting chain to prevent erroneous trades.")
            await log_trade_to_sheets(signal, check_result.status, mg_count)
            break

async def main():
    if "PORT" in os.environ:
        start_dummy_server()
        asyncio.create_task(keep_alive_task())
    
    from telethon import TelegramClient, events
    from telethon.sessions import StringSession

    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]
    source = os.environ["TELEGRAM_SOURCE"].strip()

    session_str = os.getenv("TELEGRAM_SESSION_STRING", "").strip()
    if session_str:
        client = TelegramClient(StringSession(session_str), api_id, api_hash)
    else:
        client = TelegramClient("telegram_signal_agent", api_id, api_hash)
    
    risk = RiskEngine()
    if os.getenv("POCKET_EXECUTOR", "simulator").lower() == "pocket_demo":
        from .pocket_option_demo import PocketOptionDemoExecutor
        executor = PocketOptionDemoExecutor()
    else:
        executor = DemoExecutor()


    sources = [s.strip() for s in source.split(',')] if source else []
    sources_clean = [s.replace("@", "").lower() for s in sources]

    @client.on(events.NewMessage())
    async def handler(event):
        chat = await event.get_chat()
        chat_username = getattr(chat, 'username', '') or ""
        chat_title = getattr(chat, 'title', '') or ""
        # For private chats (User objects), build a display name from first/last name
        chat_first = getattr(chat, 'first_name', '') or ""
        chat_last = getattr(chat, 'last_name', '') or ""
        chat_display_name = f"{chat_first} {chat_last}".strip()
        chat_id = str(event.chat_id)

        print(f"[DEBUG-ALL] New message from: title='{chat_title}', username='{chat_username}', name='{chat_display_name}', id='{chat_id}'")

        # Bulletproof source matching for multiple sources
        if sources:
            is_match = False
            for src, src_clean in zip(sources, sources_clean):
                if chat_username.lower() == src_clean:
                    is_match = True
                    break
                elif chat_title and src.lower() in chat_title.lower():
                    is_match = True
                    break
                elif chat_display_name and src.lower() in chat_display_name.lower():
                    is_match = True
                    break
                elif chat_id == src:
                    is_match = True
                    break
                elif src_clean in ["me", "self"] and event.is_private and event.out:
                    is_match = True
                    break
            
            if not is_match:
                return

        print(f"[DEBUG] Received message in target chat: {repr(event.raw_text[:50])}...")
        
        signal = parse_signal(event.raw_text or "", event.id)
        if not signal:
            print("[DEBUG] Failed to parse message as a valid signal.")
            return
            
        destination = os.environ.get("FORWARD_DESTINATION")
        if destination:
            try:
                await client.send_message(destination, event.message)
                print(f"[FORWARDER] Successfully forwarded signal to {destination}.")
            except Exception as e:
                print(f"[FORWARDER] Error forwarding message: {e}")
        
        if signal.signal_time:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            parts = list(map(int, signal.signal_time.split(':')))
            sig_hour = parts[0]
            sig_minute = parts[1]
            sig_second = parts[2] if len(parts) > 2 else 0
            
            best_delay = None
            
            # First, check the timezone they explicitly provided
            if signal.timezone:
                tz = parse_utc_offset(signal.timezone)
                now_tz = now_utc.astimezone(tz)
                target_tz = now_tz.replace(hour=sig_hour, minute=sig_minute, second=sig_second, microsecond=0)
                if (target_tz - now_tz).total_seconds() < -43200:
                    target_tz += datetime.timedelta(days=1)
                delay = (target_tz - now_tz).total_seconds()
                
                # If the delay is sensible (between -1 min and 1 hour), trust it
                if -60 <= delay <= 3600:
                    best_delay = delay
            
            # If the provided timezone was broken (e.g. delay is 4 hours or -20 hours),
            # sweep all possible global timezones to find the intended one.
            if best_delay is None:
                valid_delays = []
                for offset_hours in range(-12, 15):
                    tz = datetime.timezone(datetime.timedelta(hours=offset_hours))
                    now_tz = now_utc.astimezone(tz)
                    target_tz = now_tz.replace(hour=sig_hour, minute=sig_minute, second=sig_second, microsecond=0)
                    
                    if (target_tz - now_tz).total_seconds() < -43200:
                        target_tz += datetime.timedelta(days=1)
                    
                    delay = (target_tz - now_tz).total_seconds()
                    
                    # Assume typical signals are for 0 to 30 mins in the future
                    if -60 <= delay <= 1800:
                        valid_delays.append(delay)
                
                if valid_delays:
                    # Pick the smallest positive delay
                    best_delay = min([d for d in valid_delays if d >= 0] or valid_delays)
            
            if best_delay is not None:
                if best_delay > 0:
                    print(f"[SCHEDULE] Signal time heuristically resolved. Waiting {best_delay:.1f} seconds...")
                    await asyncio.sleep(best_delay)
                    print(f"[SCHEDULE] Executing scheduled trade now!")
                else:
                    print(f"[SCHEDULE] Signal is for RIGHT NOW (delay {best_delay:.1f}s). Executing immediately!")
            else:
                print(f"[WARNING] Signal time is unresolvable or too far in the past/future! Rejecting trade.")
                return

        ok, reason = risk.approve(signal)
        if not ok:
            print({"event": "signal_rejected", "reason": reason})
            return
        
        if settings.allow_martingale:
            max_mg = settings.max_martingale_steps
            print(f"[MARTINGALE] Martingale ENABLED for {signal.asset} (expiry={signal.expiry_seconds}s, max_steps={max_mg})")
            asyncio.create_task(execute_with_martingale(executor, risk, signal, max_martingale=max_mg))
        else:
            print(f"[TRADE] Martingale disabled. Placing single trade for {signal.asset}.")
            asyncio.create_task(execute_with_martingale(executor, risk, signal, max_martingale=0))

    await client.start()
    
    # Pre-connect the broker so it fetches the SSID immediately
    if hasattr(executor, "connect"):
        print("Initializing broker connection...")
        for attempt in range(1, 6):
            try:
                await executor.connect()
                break
            except Exception as e:
                print(f"[WARNING] Broker connection attempt {attempt}/5 failed: {e}")
                if attempt < 5:
                    print(f"[WARNING] Retrying in 30 seconds...")
                    await asyncio.sleep(30)
                else:
                    print("[WARNING] Could not connect to broker after 5 attempts. Bot will try to reconnect when a signal arrives.")
        
    print("Telegram listener running in DEMO mode. Waiting for signals...")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
