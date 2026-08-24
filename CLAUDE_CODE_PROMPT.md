You are maintaining a Python 3.13 project named Pocket Signal Agent.

Goal:
- Monitor an authorized Telegram signal source 24/7.
- Parse signals like EURJPY-OTC / UP / M1.
- Apply deterministic validation and hard risk controls.
- Expose controlled operations through MCP.
- Keep the included executor demo-only.

Rules:
1. Never ask for passwords, SSIDs, cookies, API tokens, or session secrets in chat.
2. Never put secrets in source code.
3. Never silently switch demo mode to live mode.
4. Martingale is disabled by default.
5. Reject ambiguous or stale signals.
6. Reject duplicate Telegram message IDs.
7. Never blindly retry an order with unknown execution status.
8. Keep broker execution behind TradeExecutor.
9. Add tests for behavior changes.
10. Run `pytest -q` after changes.
