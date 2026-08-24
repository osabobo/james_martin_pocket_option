from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

class Direction(str, Enum):
    UP = "UP"
    DOWN = "DOWN"

class Signal(BaseModel):
    provider: str | None = None
    asset: str
    direction: Direction
    expiry_seconds: int = Field(gt=0, le=3600)
    signal_time: str | None = None
    timezone: str | None = None
    max_martingale: int = Field(default=0, ge=0, le=2)
    telegram_message_id: str | None = None
    received_at: datetime

class TradeRequest(BaseModel):
    asset: str
    direction: Direction
    amount: float = Field(gt=0)
    expiry_seconds: int = Field(gt=0, le=3600)

class TradeResult(BaseModel):
    accepted: bool
    trade_id: str | None = None
    status: str
    result: str | None = None
    pnl: float | None = None
    message: str | None = None
