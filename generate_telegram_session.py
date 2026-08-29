"""
Generate a Telegram StringSession for use on Render (or any server).
"""
import asyncio
import sys
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = 32530747
API_HASH = "4cc5c923e19a0ab2c30068afc006a43c"
PHONE = "+2348027605209"

async def main():
    print("=" * 60)
    print("  Telegram Session String Generator for Render")
    print("=" * 60)
    print()
    
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    
    # Send the code request
    result = await client.send_code_request(PHONE)
    
    print("A verification code has been sent to your Telegram.")
    print("Please enter the code: ", end="", flush=True)
    code = input().strip()
    
    try:
        await client.sign_in(PHONE, code, phone_code_hash=result.phone_code_hash)
    except Exception as e:
        if "Two-steps verification" in str(e) or "2FA" in str(e) or "password" in str(type(e).__name__.lower()):
            print("2FA is enabled. Please enter your password: ", end="", flush=True)
            password = input().strip()
            await client.sign_in(password=password)
        else:
            raise
    
    session_string = client.session.save()
    
    print()
    print("=" * 60)
    print("  SUCCESS! Copy the string below to Render.")
    print("=" * 60)
    print()
    print(session_string)
    print()
    print("=" * 60)
    
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
