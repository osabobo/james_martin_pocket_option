import os
import asyncio
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession

load_dotenv()

async def main():
    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]

    print("Logging in to generate a session string...")
    # Passing an empty StringSession means it won't load from the sqlite file, 
    # forcing a fresh interactive login.
    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.start()
    
    session_str = client.session.save()
    print("\n" + "="*50)
    print("YOUR SESSION STRING IS:")
    print(session_str)
    print("="*50 + "\n")
    print("Copy the long string above and add it to Render as the 'TELEGRAM_SESSION_STRING' environment variable.")
    
    await client.disconnect()

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
