from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    trading_mode: str = os.getenv("TRADING_MODE", "demo").lower()
    fixed_stake: float = float(os.getenv("FIXED_STAKE", "1"))
    max_daily_trades: int = int(os.getenv("MAX_DAILY_TRADES", "20"))
    max_daily_loss: float = float(os.getenv("MAX_DAILY_LOSS", "10"))
    max_consecutive_losses: int = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "3"))
    max_signal_age_seconds: int = int(os.getenv("MAX_SIGNAL_AGE_SECONDS", "30"))
    allow_martingale: bool = os.getenv("ALLOW_MARTINGALE", "false").lower() == "true"
    max_martingale_steps: int = int(os.getenv("MAX_MARTINGALE_STEPS", "2"))

settings = Settings()

if settings.trading_mode != "demo":
    raise RuntimeError("This scaffold is demo-only.")
