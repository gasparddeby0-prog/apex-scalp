import pytest

from apex.config import Settings, TradingMode


@pytest.fixture
def settings() -> Settings:
    """Deterministic paper-mode settings for tests (ignores any local .env)."""
    return Settings(
        _env_file=None,
        mode=TradingMode.PAPER,
        symbols=["EURUSD", "XAUUSD"],
        paper_balance=10_000.0,
        entry_score=7.0,
        min_aligned=3,
    )
