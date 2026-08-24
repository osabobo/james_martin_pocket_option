from dataclasses import dataclass, field
from datetime import date
from .config import settings
from .models import Signal, TradeRequest

@dataclass
class RiskState:
    day: date = field(default_factory=date.today)
    trades: int = 0
    pnl: float = 0.0
    consecutive_losses: int = 0
    seen_message_ids: set[str] = field(default_factory=set)

class RiskEngine:
    def __init__(self):
        self.state = RiskState()

    def approve(self, signal: Signal) -> tuple[bool, str]:
        if signal.telegram_message_id and signal.telegram_message_id in self.state.seen_message_ids:
            return False, "duplicate_signal"
        if self.state.pnl <= -abs(settings.max_daily_loss):
            return False, "daily_loss_limit"
        if self.state.consecutive_losses >= settings.max_consecutive_losses:
            return False, "consecutive_loss_limit"
        return True, "approved"

    def make_request(self, signal: Signal) -> TradeRequest:
        return TradeRequest(
            asset=signal.asset,
            direction=signal.direction,
            amount=settings.fixed_stake,
            expiry_seconds=signal.expiry_seconds,
        )

    def mark_submitted(self, signal: Signal):
        self.state.trades += 1
        if signal.telegram_message_id:
            self.state.seen_message_ids.add(signal.telegram_message_id)
