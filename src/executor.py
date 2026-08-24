from abc import ABC, abstractmethod
from .models import TradeRequest, TradeResult

class TradeExecutor(ABC):
    @abstractmethod
    async def place_trade(self, request: TradeRequest) -> TradeResult:
        ...

    @abstractmethod
    async def get_trade_result(self, trade_id: str, timeout=None) -> TradeResult:
        ...

class DemoExecutor(TradeExecutor):
    # Safe placeholder: never contacts a broker.
    def __init__(self):
        self.counter = 0
        self.trades = {}

    async def place_trade(self, request: TradeRequest) -> TradeResult:
        self.counter += 1
        trade_id = f"DEMO-{self.counter:06d}"
        result = TradeResult(
            accepted=True,
            trade_id=trade_id,
            status="SIMULATED",
            message=f"Demo only: {request.asset} {request.direction.value} {request.expiry_seconds}s ${request.amount:.2f}",
        )
        self.trades[trade_id] = result
        return result

    async def get_trade_result(self, trade_id: str, timeout=None) -> TradeResult:
        return self.trades.get(
            trade_id,
            TradeResult(accepted=False, status="UNKNOWN", message="Unknown trade id"),
        )
