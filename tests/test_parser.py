from src.signal_parser import parse_signal
from src.models import Direction

MESSAGE = '''Trader X - Free Signals
• EURJPY-OTC
• Expires in 1 minute (M1)
• 09:21:00
• UP  (UTC-03)
• Max 2 martingale!
Don't know how to trade? Click here
'''

def test_parse_example():
    s = parse_signal(MESSAGE, 36)
    assert s is not None
    assert s.asset == "EURJPY-OTC"
    assert s.direction == Direction.UP
    assert s.expiry_seconds == 60
    assert s.max_martingale == 2
    assert s.telegram_message_id == "36"

def test_ignore_ad():
    assert parse_signal("Click here to open the Brokerage https://binolla.com/demo") is None
