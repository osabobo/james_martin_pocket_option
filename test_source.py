import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def main():
    from telethon import TelegramClient, events

    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]
    source = os.environ.get("TELEGRAM_SOURCE")

    print(f"Testing connection for source: '{source}'")
    
    # This will prompt for phone number and OTP on first run
    client = TelegramClient("telegram_signal_agent", api_id, api_hash)
    await client.start()

    print("Successfully connected to Telegram!")

    print("Listening for new messages... (Press Ctrl+C to exit).")
    
    source_clean = source.replace("@", "").lower() if source else ""

    @client.on(events.NewMessage())
    async def handler(event):
        chat = await event.get_chat()
        chat_username = getattr(chat, 'username', '') or ""
        chat_title = getattr(chat, 'title', '') or ""
        chat_id = str(event.chat_id)

        print(f"[DEBUG-ALL] Received message from chat_username='{chat_username}', chat_title='{chat_title}', chat_id='{chat_id}'")
        print(f"[DEBUG-ALL] Raw text: {event.raw_text[:20]}...")
        
        # Bulletproof source matching
        if source_clean:
            is_match = False
            if chat_username.lower() == source_clean:
                is_match = True
            elif chat_title.lower() == source.lower():
                is_match = True
            elif chat_id == source:
                is_match = True
            elif source_clean in ["me", "self"] and event.is_private and event.out:
                is_match = True
            
            if not is_match:
                print(f"[DEBUG-ALL] Message ignored. {chat_username.lower()} != {source_clean}")
                return

        print(f"[MESSAGE] Received a new message in {chat_title or chat_username or chat_id}!")
        print(f"Text: {event.raw_text}")

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
