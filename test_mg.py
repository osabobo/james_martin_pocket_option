import asyncio
import os
import datetime
from dotenv import load_dotenv
load_dotenv()
from src.pocket_option_demo import PocketOptionDemoExecutor
from src.risk import RiskEngine
from src.telegram_listener import execute_with_martingale
from src.models import Signal, Direction

async def main():
    risk = RiskEngine()
    executor = PocketOptionDemoExecutor()
    await executor.connect()
    
    signal = Signal(
        provider="TEST",
        asset="EURUSD",
        direction=Direction.UP,
        expiry_seconds=60,
        signal_time="12:00",
        timezone="UTC",
        max_martingale=0,
        received_at=datetime.datetime.now(datetime.timezone.utc)
    )
    
    await execute_with_martingale(executor, risk, signal, max_martingale=0)

asyncio.run(main())
