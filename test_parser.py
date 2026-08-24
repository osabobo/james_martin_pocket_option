from src.signal_parser import parse_signal

texts = [
"""EURUSD_otc UP Expires in 1 minute 08:38""",
"""USDCHF-OTC•
Expires in 1 minute (M1)•
09:27:00•
UP (UTC+01)•
Max 2 martingales! 09:26""",
"""James Martin l FREE Signals

📊 FREE Signals 📊
⏰ Time Zone: UTC -3

• USDCHF - CALL 🟩 - 10:25
• Expiration: 5 minutes (M5)
• If you lose, make up to 2 Gale's."""
]

for t in texts:
    print(parse_signal(t))
