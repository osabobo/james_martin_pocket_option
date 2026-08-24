import os
from fastmcp import FastMCP
from .config import settings
from .executor import DemoExecutor
from .models import TradeRequest
from .risk import RiskEngine

mcp = FastMCP("Pocket Signal Agent")
risk = RiskEngine()
demo = DemoExecutor()

def broker():
    # Fail-closed: only the explicitly named demo connector can be selected.
    if os.getenv("POCKET_EXECUTOR", "simulator").lower() == "pocket_demo":
        from .pocket_option_demo import PocketOptionDemoExecutor
        return PocketOptionDemoExecutor()
    return demo

@mcp.tool()
async def system_status() -> dict:
    return {
        "trading_mode": settings.trading_mode,
        "executor": os.getenv("POCKET_EXECUTOR", "simulator"),
        "daily_trades": risk.state.trades,
        "daily_pnl": risk.state.pnl,
        "consecutive_losses": risk.state.consecutive_losses,
    }

@mcp.tool()
async def place_demo_trade(asset: str, direction: str, amount: float, expiry_seconds: int) -> dict:
    """Place a demo-only trade through the selected demo executor."""
    req = TradeRequest(
        asset=asset,
        direction=direction.upper(),
        amount=amount,
        expiry_seconds=expiry_seconds,
    )
    result = await broker().place_trade(req)
    return result.model_dump()

@mcp.tool()
async def get_demo_trade_result(trade_id: str) -> dict:
    """Retrieve a demo trade result; unknown results are never guessed."""
    result = await broker().get_trade_result(trade_id)
    return result.model_dump()

if __name__ == "__main__":
    mcp.run()
