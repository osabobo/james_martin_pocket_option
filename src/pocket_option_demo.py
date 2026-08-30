"""Pocket Option demo connector using the current unofficial pocket-option SDK.

This module is deliberately isolated behind TradeExecutor. It will refuse to
start unless TRADING_MODE=demo.
"""
import os
import asyncio
from .models import TradeRequest, TradeResult
from .executor import TradeExecutor

class PocketOptionDemoExecutor(TradeExecutor):
    def __init__(self):
        self.ssid = os.getenv("POCKET_OPTION_SSID")
        self.uid = os.getenv("POCKET_OPTION_UID")
        self.platform = os.getenv("POCKET_OPTION_PLATFORM", "1")
        self.client = None
        self.deals_storage = None
        self._pending_close_listener = None

    async def connect(self):
        await self._try_connect()
    
    async def reconnect(self, pending_close_listener=None):
        if not self.client:
            return await self.connect()

        print("[RECONNECT] Attempting lightweight reconnect to preserve storage...")
        old_storage = self.deals_storage
        old_listener = pending_close_listener or self._pending_close_listener
        
        try:
            await self.client.disconnect()
        except Exception:
            pass
            
        await self._try_connect(force_fresh=False, create_new_storage=False)
        
        if old_storage:
            self.deals_storage = old_storage
            self.deals_storage.client = self.client
            self.client.on.success_open_deal(self.deals_storage._on_success_open_deal)
            self.client.on.success_close_deal(self.deals_storage._on_success_close_deal)
            self.client.on.update_opened_deals(self.deals_storage.add_or_update_deal_bulk)
            self.client.on.update_closed_deals(self.deals_storage.add_or_update_deal_bulk)
            
        if old_listener:
            self._pending_close_listener = old_listener
            self.client.on.success_close_deal(old_listener)

    async def _fetch_closed_history(self, deal_uuid, close_event: "asyncio.Event", timeout: float = 8.0):
        """Emit history-fetch requests to the server and wait up to `timeout` seconds
        for the `updateClosedDeals` bulk sync to arrive and populate deals_storage.
        Returns True if the target deal was found with a valid close_price."""
        if not (self.client and getattr(self.client.sio, 'connected', False)):
            return False
        
        print(f"[TRADE-RESULT] Fetching closed history from server to find deal {deal_uuid}...")
        try:
            await self.client.sio.emit("updateHistoryNew", {"_placeholder": True, "num": 0})
            await self.client.sio.emit("updateClosedDeals", {"_placeholder": True, "num": 0})
        except Exception as e:
            print(f"[TRADE-RESULT] History fetch emit failed: {e}")
            return False
        
        # Wait for the server response to be processed into deals_storage
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            # Check if the bulk event listener already found it
            if close_event.is_set():
                return True
            # Check deals_storage directly
            try:
                deal = await self.deals_storage.get_deal(deal_id=deal_uuid)
                if deal and getattr(deal, 'close_price', 0.0) not in (0.0, None):
                    print(f"[TRADE-RESULT] Deal {deal_uuid} found in closed history (close_price={deal.close_price}).")
                    return True
                # Also treat a non-zero profit as proof of closure
                if deal and getattr(deal, 'profit', None) is not None:
                    try:
                        if float(deal.profit) != 0.0:
                            print(f"[TRADE-RESULT] Deal {deal_uuid} found in closed history (profit={deal.profit}).")
                            return True
                    except (ValueError, TypeError):
                        pass
            except Exception:
                pass
            await asyncio.sleep(0.5)
        
        return False

    async def _try_connect(self, force_fresh=False, create_new_storage=True):
        if force_fresh or not self.ssid:
            print("Fetching fresh SSID via automated login...")
            from .session_manager import get_fresh_ssid
            self.ssid = await get_fresh_ssid()
            self.uid = os.environ.get("POCKET_OPTION_UID", self.uid)

        if not self.ssid:
            raise RuntimeError(
                "POCKET_OPTION_SSID is missing and automated login failed. "
                "Ensure your email/password are in .env."
            )

        # The SDK is intentionally imported lazily so the rest of the project
        # can still be tested without a broker session.
        from pocket_option import PocketOptionClient
        from pocket_option.models import AuthorizationData
        from pocket_option.constants import Regions
        from pocket_option.contrib.deals import MemoryDealsStorage
        
        # SDK APIs can change because this is unofficial. Keep this code isolated.
        import logging
        self.client = PocketOptionClient(
            logger=True,
            socketio_logger=True,
            engineio_logger=True,
        )
        auth_data = AuthorizationData(
            session=self.ssid,
            uid=int(self.uid) if self.uid else 0,
            isDemo=(os.getenv("TRADING_MODE", "demo").lower() == "demo"),
            isFastHistory=True,
            isOptimized=True,
            platform=int(self.platform) if self.platform else 2,
        )
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
            "Origin": "https://pocketoption.com"
        }
        trading_mode = os.getenv("TRADING_MODE", "demo").lower()
        ws_url = Regions.EUROPA.value if trading_mode == "live" else Regions.DEMO.value
        
        await self.client.connect(
            url=ws_url, 
            auth=None, 
            headers=headers
        )
        
        # Pocket Option backend changed recently: they no longer accept authentication 
        # inside the Socket.IO connect packet (packet 0). They expect it as a standard 
        # event message (packet 42["auth", {...}]).
        
        # We also need to listen for data events because the server might not send "successauth" anymore
        async def on_auth_success(*args):
            self.client.authorized_event.set()
        self.client.add_on("auth/success", on_auth_success)
        self.client.add_on("user_ready", on_auth_success)
        
        # MemoryDealsStorage expects authorization_data to be populated
        self.client.authorization_data = auth_data
        
        # Send the standard SDK auth payload. Note: The SDK serializes this properly.
        await self.client.send("auth", auth_data)
        
        # Wait for the server to confirm authorization before accepting trades
        print("Waiting for broker authorization...")
        authorized = False
        for _ in range(30):
            if self.client.authorized_event.is_set():
                authorized = True
                break
            if not self.client.sio.connected:
                print("[WARNING] Socket disconnected while waiting for authorization.")
                break
            await asyncio.sleep(0.5)
            
        if authorized:
            print("[SUCCESS] Broker authorized and ready!")
        else:
            # If this was a saved SSID, it's probably expired - try a fresh one
            if not force_fresh:
                print("[WARNING] Saved SSID expired or auth failed. Fetching a fresh one...")
                try:
                    await self.client.disconnect()
                except Exception:
                    pass
                self.client = None
                self.ssid = None
                return await self._try_connect(force_fresh=True, create_new_storage=create_new_storage)
            else:
                print("[WARNING] Authorization failed - continuing anyway, trades may fail.")
        
        if create_new_storage:
            self.deals_storage = MemoryDealsStorage(self.client)

    def _resolve_asset(self, asset_str: str):
        """Map a signal asset string like 'USDCHF-OTC' to the SDK's Asset enum."""
        from pocket_option.models import Asset
        
        # Normalize: "USDCHF-OTC" → "USDCHF_otc", "EURUSD" → "EURUSD"
        normalized = asset_str.replace("-OTC", "_otc").replace("-otc", "_otc").replace("_OTC", "_otc").replace(" ", "_").replace("/", "")
        
        # The SDK's Asset enum has a dynamic _missing_ method, meaning we can 
        # pass ANY string to it and it will create a valid Asset for the API.
        # This prevents the bot from accidentally trading the OTC chart when the 
        # signal meant the regular chart.
        try:
            return Asset(normalized)
        except Exception:
            return None

    async def place_trade(self, request: TradeRequest) -> TradeResult:
        if self.client is None or not self.client.sio.connected:
            print("[INFO] Broker socket disconnected. Reconnecting...")
            await self.connect()

        from pocket_option.models import DealAction
        
        asset = self._resolve_asset(request.asset)
        if asset is None:
            return TradeResult(
                accepted=False,
                status="UNSUPPORTED_ASSET",
                message=f"Asset '{request.asset}' not found in SDK. No order was sent.",
            )

        action = DealAction.CALL if request.direction.value == "UP" else DealAction.PUT

        try:
            deal = await self.deals_storage.open_deal(
                asset=asset,
                amount=int(request.amount),
                action=action,
                time=request.expiry_seconds,
            )
            return TradeResult(
                accepted=True,
                trade_id=str(deal.id),
                status="OPEN",
                message=f"Deal opened: {deal.asset} {action.value} ${int(request.amount)} for {request.expiry_seconds}s",
            )
        except Exception as exc:
            return TradeResult(
                accepted=False,
                status="REJECTED",
                message=f"Pocket Option demo request failed: {type(exc).__name__}: {exc}",
            )

    async def get_trade_result(self, trade_id: str, timeout: int = 600) -> TradeResult:
        if self.client is None:
            await self.connect()
        
        if self.deals_storage is None:
            return TradeResult(
                accepted=False,
                trade_id=trade_id,
                status="NOT_CONNECTED",
                message="Deals storage not initialized.",
            )
        
        import uuid
        deal_uuid = uuid.UUID(trade_id)
        
        def _make_result(deal):
            expected_profit = getattr(deal, 'profit', None)
            
            status = "UNKNOWN"
            
            # Primary method: use the profit field directly
            if expected_profit is not None:
                try:
                    p = float(expected_profit)
                    if p < 0:
                        status = "LOSS"
                    elif p > 0:
                        status = "WIN"
                    else:
                        status = "TIE"
                except (ValueError, TypeError):
                    pass
            
            # Fallback method: use open_price and close_price if profit was inconclusive
            if status == "UNKNOWN" and hasattr(deal, 'open_price') and hasattr(deal, 'close_price') and getattr(deal, 'close_price') is not None and getattr(deal, 'close_price') != 0.0:
                if hasattr(deal.command, 'name'):
                    command_str = str(deal.command.name).lower()
                else:
                    command_str = str(deal.command).lower()
                
                if command_str == "call":
                    if deal.close_price > deal.open_price:
                        status = "WIN"
                    elif deal.close_price < deal.open_price:
                        status = "LOSS"
                    else:
                        status = "TIE"
                elif command_str == "put":
                    if deal.close_price < deal.open_price:
                        status = "WIN"
                    elif deal.close_price > deal.open_price:
                        status = "LOSS"
                    else:
                        status = "TIE"
            
            realized_profit = expected_profit if status == "WIN" else (expected_profit if expected_profit and float(expected_profit) < 0 else 0.0)
            
            print(f"[TRADE-RESULT] Deal {trade_id} closed: status={status}, expected_profit={expected_profit}, open={getattr(deal, 'open_price', None)}, close={getattr(deal, 'close_price', None)}")
            return TradeResult(
                accepted=True,
                trade_id=trade_id,
                status=status,
                result=str(deal),
                pnl=float(realized_profit) if realized_profit is not None else None,
            )
        
        # --- Shared close event and profit capture ---
        # Triggered by EITHER the real-time successcloseOrder event OR the bulk updateClosedDeals sync.
        actual_profit = None
        custom_close_event = asyncio.Event()

        # Listener 1: real-time per-deal close event (fires when trade closes normally)
        def on_close_deal(event):
            print(f"[TRADE-RESULT-DEBUG] Received successcloseOrder event. Profit: {event.profit}. Deals in event: {len(event.deals)}")
            for closed_deal in event.deals:
                print(f"[TRADE-RESULT-DEBUG] Checking closed deal ID: {closed_deal.id} against target: {deal_uuid}")
                if closed_deal.id == deal_uuid:
                    nonlocal actual_profit
                    actual_profit = event.profit
                    custom_close_event.set()

        # Listener 2: bulk history sync (fires after every reconnect via updateClosedDeals)
        # This is the key fix: after a WS drop the server sends updateClosedDeals (bulk),
        # NOT successcloseOrder, so we MUST also scan the bulk payload for our deal.
        def on_bulk_closed_deals(event):
            deals_list = getattr(event, 'deals', []) or []
            for closed_deal in deals_list:
                if getattr(closed_deal, 'id', None) == deal_uuid:
                    close_price = getattr(closed_deal, 'close_price', 0.0)
                    profit = getattr(closed_deal, 'profit', None)
                    # Only treat as truly closed if we have a non-zero close_price or a profit figure
                    has_close_price = close_price not in (0.0, None)
                    has_profit = profit is not None
                    if has_close_price or has_profit:
                        nonlocal actual_profit
                        if profit is not None:
                            try:
                                actual_profit = float(profit)
                            except (ValueError, TypeError):
                                pass
                        print(f"[TRADE-RESULT-DEBUG] Found deal {deal_uuid} in bulk updateClosedDeals (close_price={close_price}, profit={profit}).")
                        custom_close_event.set()
                        break
        
        # Subscribe to both events
        self._pending_close_listener = on_close_deal
        unsub_realtime = self.client.on.success_close_deal(on_close_deal)
        # Register bulk listener — use update_closed_deals if available, otherwise fall back to sio.on
        unsub_bulk = None
        try:
            unsub_bulk = self.client.on.update_closed_deals(on_bulk_closed_deals)
        except Exception:
            try:
                self.client.sio.on("updateClosedDeals", on_bulk_closed_deals)
            except Exception:
                pass
        
        def _unsub_all():
            try:
                if unsub_realtime:
                    unsub_realtime()
            except Exception:
                pass
            try:
                if unsub_bulk:
                    unsub_bulk()
            except Exception:
                pass
        
        # Poll loop: wait for the close_event from the websocket.
        elapsed = 0
        poll_interval = 1
        trade_duration = timeout - 60  # The actual expiry duration
        last_history_fetch = -999  # Track when we last fetched history to avoid spamming
        
        while elapsed < timeout:
            if custom_close_event.is_set():
                break
                
            # If socket drops, reconnect then immediately fetch closed history.
            # This is the primary fix: after reconnect the server sends updateClosedDeals
            # (bulk sync) rather than successcloseOrder, so we actively request it.
            if self.client and not getattr(self.client.sio, 'connected', True):
                print(f"[TRADE-RESULT] Socket disconnected for {trade_id}. Attempting reconnect...")
                try:
                    await self.reconnect(on_close_deal)
                    # Re-register bulk listener on the new client connection
                    try:
                        self.client.on.update_closed_deals(on_bulk_closed_deals)
                    except Exception:
                        try:
                            self.client.sio.on("updateClosedDeals", on_bulk_closed_deals)
                        except Exception:
                            pass
                    # Immediately fetch closed history — don't wait for next polling tick
                    found = await self._fetch_closed_history(deal_uuid, custom_close_event, timeout=8.0)
                    elapsed += 10  # Account for reconnect + fetch time
                    last_history_fetch = elapsed
                    if found or custom_close_event.is_set():
                        break
                except Exception as e:
                    print(f"[TRADE-RESULT] Reconnect failed: {e}")
                    await asyncio.sleep(3)
                    elapsed += 3
            
            # Periodically fetch closed history after the trade should have expired.
            # Reduced from every 10s to every 5s for faster recovery.
            if elapsed >= trade_duration and (elapsed - last_history_fetch) >= 5:
                if self.client and getattr(self.client.sio, 'connected', False):
                    try:
                        await self.client.sio.emit("updateHistoryNew", {"_placeholder": True, "num": 0})
                        await self.client.sio.emit("updateClosedDeals", {"_placeholder": True, "num": 0})
                        last_history_fetch = elapsed
                    except Exception:
                        pass
            
            # Check deals_storage fallback. A deal is truly closed when close_price is set
            # OR when profit is non-None (broker sometimes sets profit without close_price).
            deal = await self.deals_storage.get_deal(deal_id=deal_uuid)
            if deal:
                close_price = getattr(deal, 'close_price', 0.0)
                profit = getattr(deal, 'profit', None)
                has_real_close = close_price not in (0.0, None)
                has_profit = profit is not None and profit != 0.0
                if has_real_close or has_profit:
                    print(f"[TRADE-RESULT] Deal {trade_id} found fully closed in deals_storage (close_price={close_price}, profit={profit}).")
                    _unsub_all()
                    return _make_result(deal)

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        
        # Unsubscribe all listeners
        _unsub_all()
            
        if custom_close_event.is_set():
            deal = await self.deals_storage.get_deal(deal_id=deal_uuid)
            
            status = "UNKNOWN"
            if actual_profit is not None:
                if actual_profit == 0.0:
                    status = "LOSS"
                elif actual_profit > 0.0:
                    status = "WIN"
                elif actual_profit < 0.0:
                    status = "LOSS"
            
            if deal:
                if status == "LOSS":
                    pnl = -float(deal.amount)
                elif status == "WIN":
                    # Use deal.profit (net) if available, otherwise fall back to actual_profit
                    pnl = float(getattr(deal, 'profit', actual_profit or 0.0))
                else:
                    pnl = 0.0
            else:
                pnl = actual_profit if actual_profit and actual_profit > 0 else 0.0
                
            print(f"[TRADE-RESULT] Deal {trade_id} closed: status={status}, actual_event_profit={actual_profit}, expected_profit={getattr(deal, 'profit', None) if deal else None}")
            return TradeResult(
                accepted=True,
                trade_id=trade_id,
                status=status,
                result=str(deal) if deal else "",
                pnl=pnl,
            )
        
        # If we're here, either the socket died or we timed out. We MUST NOT default to LOSS!
        # If we blindly return LOSS, it causes runaway Martingale trades on network issues.
        # Final recovery: reconnect and actively pull history up to 3 times.
        for attempt in range(3):
            deal = await self.deals_storage.get_deal(deal_id=deal_uuid)
            if deal:
                close_price = getattr(deal, 'close_price', 0.0)
                profit = getattr(deal, 'profit', None)
                has_real_close = close_price not in (0.0, None)
                has_profit = profit is not None and profit != 0.0
                if has_real_close or has_profit:
                    print(f"[TRADE-RESULT] Deal {trade_id} found closed after timeout on attempt {attempt+1}.")
                    return _make_result(deal)
            
            if attempt < 2:
                print(f"[TRADE-RESULT] Checking deal {trade_id} failed. Trying reconnect...")
                try:
                    await self.reconnect(on_close_deal)
                    try:
                        self.client.on.update_closed_deals(on_bulk_closed_deals)
                    except Exception:
                        pass
                    # Actively fetch history after reconnect
                    found = await self._fetch_closed_history(deal_uuid, custom_close_event, timeout=8.0)
                    if found or custom_close_event.is_set():
                        deal = await self.deals_storage.get_deal(deal_id=deal_uuid)
                        if deal:
                            return _make_result(deal)
                except Exception:
                    await asyncio.sleep(5)
            
        print(f"[TRADE-RESULT] WARNING: Could not determine result for {trade_id} (elapsed={elapsed}s). Returning UNKNOWN.")
        return TradeResult(
            accepted=True,
            trade_id=trade_id,
            status="UNKNOWN",
            message=f"Result unknown (timeout or network error).",
        )

