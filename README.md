# Pocket Signal Agent — Claude Code + MCP + Telegram + Pocket Option DEMO

This update adds an isolated Pocket Option **DEMO** WebSocket connector using the
current unofficial `pocket-option` Python SDK (0.2.8). The package documents
Socket.IO WebSocket access, session authentication, and demo/real order management.

Architecture:
Telegram -> parser -> risk engine -> MCP -> Pocket Option demo connector -> result monitor.

IMPORTANT:
- This connector is unofficial and not affiliated with Pocket Option.
- It uses a browser session/SSID rather than treating `/cabinet` as a REST API.
- Keep `TRADING_MODE=demo`.
- Never paste your SSID/session, password, cookies, or tokens into chat.
- The connector refuses non-demo mode.
- If the installed SDK API differs, it fails closed rather than guessing an order call.

## Setup

1. Install Python 3.13+.
2. Copy `.env.example` to `.env`.
3. Set `TRADING_MODE=demo`.
4. Set `POCKET_EXECUTOR=pocket_demo`.
5. Put your own DEMO session value in `POCKET_OPTION_SSID`.
6. Optionally set `POCKET_OPTION_UID` and `POCKET_OPTION_PLATFORM`.
7. Install:
   `python -m pip install -r requirements.txt`
8. Run tests:
   `pytest -q`
9. Start MCP:
   `python -m src.mcp_server`

The current third-party SDK documentation says a valid session payload can be
obtained from the authenticated browser WebSocket and uses an auth message
starting with `42["auth", ...]`. Use a fresh DEMO session only.

## What this does

The MCP layer can call:
- `system_status`
- `place_demo_trade`
- `get_demo_trade_result`

The demo connector attempts:
- connect to the Pocket Option demo WebSocket
- submit a demo order using the SDK's `buy()` interface
- retrieve the result using `check_win()`

No live execution is included.

## If connection fails

Because this is an unofficial, reverse-engineered interface, endpoints and
authentication can change. The adapter returns an explicit error instead of
falling back to browser clicking or silently sending an order.
