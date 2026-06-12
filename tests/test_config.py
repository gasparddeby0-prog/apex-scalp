"""Regression tests for settings parsing.

Guards the bug where a comma-separated ``APEX_SYMBOLS`` in a .env file made
pydantic-settings try to JSON-decode it and crash with a SettingsError.
"""

from apex.config import Settings, TradingMode


def test_symbols_default_without_env():
    s = Settings(_env_file=None)
    assert s.symbols == ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "NAS100"]
    assert s.mode is TradingMode.PAPER


def test_symbols_csv_from_env_var(monkeypatch):
    monkeypatch.setenv("APEX_SYMBOLS", "eurusd, gbpusd ,xauusd")
    s = Settings(_env_file=None)
    assert s.symbols == ["EURUSD", "GBPUSD", "XAUUSD"]


def test_symbols_json_style_from_env_var(monkeypatch):
    monkeypatch.setenv("APEX_SYMBOLS", '["EURUSD","GBPUSD"]')
    s = Settings(_env_file=None)
    assert s.symbols == ["EURUSD", "GBPUSD"]


def test_symbols_csv_from_dotenv_file(tmp_path, monkeypatch):
    # The exact path that used to crash: CSV symbols read from a .env file.
    monkeypatch.delenv("APEX_SYMBOLS", raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "APEX_MODE=paper\n"
        "APEX_SYMBOLS=EURUSD,GBPUSD,USDJPY,XAUUSD,NAS100\n"
        "MT5_LOGIN=108249043\n",
        encoding="utf-8",
    )
    s = Settings(_env_file=str(env))
    assert s.symbols == ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "NAS100"]
    assert s.mt5_login == 108249043
    assert s.mode is TradingMode.PAPER


def test_mode_from_env_var(monkeypatch):
    monkeypatch.setenv("APEX_MODE", "live")
    s = Settings(_env_file=None)
    assert s.mode is TradingMode.LIVE
    assert s.is_live
