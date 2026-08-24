import asyncio
import os
from dotenv import load_dotenv

async def main():
    load_dotenv()
    from src.pocket_option_demo import PocketOptionDemoExecutor
    print("Testing connection...")
    executor = PocketOptionDemoExecutor()
    try:
        await executor.connect()
        print("Test passed! Connection successful.")
    except Exception as e:
        print(f"Test failed! {e}")

if __name__ == "__main__":
    asyncio.run(main())
