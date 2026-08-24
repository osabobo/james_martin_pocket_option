import asyncio
import os
import datetime
from dotenv import load_dotenv
load_dotenv()
from src.pocket_option_demo import PocketOptionDemoExecutor
from src.risk import RiskEngine
from src.models import Signal, Direction

async def main():
    executor = PocketOptionDemoExecutor()
    await executor.connect()
    
    # Place a 5-second trade manually
    request = RiskEngine().make_request(Signal(
        provider="TEST",
        asset="EURUSD",
        direction=Direction.UP,
        expiry_seconds=60,
        signal_time="12:00",
        timezone="UTC",
        max_martingale=0,
        received_at=datetime.datetime.now(datetime.timezone.utc)
    ))
    
    result = await executor.place_trade(request)
    print(f"Placed trade: {result}")
    
    import uuid
    deal_id = uuid.UUID(result.trade_id)
    
    deal_open = await executor.deals_storage.get_deal(deal_id=deal_id)
    print(f"OPEN DEAL STATE:")
    print(f"  close_timestamp: {deal_open.close_timestamp}")
    print(f"  close_time: {deal_open.close_time}")
    print(f"  close_price: {deal_open.close_price}")
    print(f"  profit: {deal_open.profit}")
    
    print("Waiting 65 seconds for trade to close...")
    await asyncio.sleep(65)
    
    deal_closed = await executor.deals_storage.get_deal(deal_id=deal_id)
    print(f"CLOSED DEAL STATE:")
    print(f"  close_timestamp: {deal_closed.close_timestamp}")
    print(f"  close_time: {deal_closed.close_time}")
    print(f"  close_price: {deal_closed.close_price}")
    print(f"  profit: {deal_closed.profit}")

asyncio.run(main())
