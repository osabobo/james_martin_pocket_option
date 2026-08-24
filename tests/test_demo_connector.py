import os
import pytest

def test_demo_connector_rejects_live(monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "live")
    monkeypatch.setenv("POCKET_OPTION_SSID", "dummy")
    from src.pocket_option_demo import PocketOptionDemoExecutor
    with pytest.raises(RuntimeError):
        PocketOptionDemoExecutor()
