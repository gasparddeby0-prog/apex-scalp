"""Centralised configuration loaded from environment / .env file.

Secrets (MT5 credentials, Telegram tokens) are only ever read from the
environment - never hard-coded. Paper trading is the safe default.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class TradingMode(StrEnum):
    PAPER = "paper"
    LIVE = "live"


class Settings(BaseSettings):
    """Application settings, populated from environment variables / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    # ── Mode ────────────────────────────────────────────────────────────────
    mode: TradingMode = Field(default=TradingMode.PAPER, alias="APEX_MODE")

    # ── MT5 connection ───────────────────────────────────────────────────────
    mt5_login: int | None = Field(default=None, alias="MT5_LOGIN")
    mt5_password: str | None = Field(default=None, alias="MT5_PASSWORD")
    mt5_server: str | None = Field(default=None, alias="MT5_SERVER")
    mt5_path: str | None = Field(default=None, alias="MT5_PATH")

    # ── Risk ──────────────────────────────────────────────────────────────────
    risk_per_trade_pct: float = Field(default=0.5, alias="APEX_RISK_PER_TRADE_PCT")
    max_daily_risk_pct: float = Field(default=2.0, alias="APEX_MAX_DAILY_RISK_PCT")
    max_weekly_risk_pct: float = Field(default=5.0, alias="APEX_MAX_WEEKLY_RISK_PCT")
    max_open_positions: int = Field(default=3, alias="APEX_MAX_OPEN_POSITIONS")
    paper_balance: float = Field(default=10_000.0, alias="APEX_PAPER_BALANCE")

    # ── Engine ──────────────────────────────────────────────────────────────────
    # NoDecode tells pydantic-settings NOT to JSON-decode this env value, so a
    # plain comma-separated string (APEX_SYMBOLS=EURUSD,GBPUSD,...) is accepted
    # and split by the validator below instead of crashing on json.loads.
    symbols: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "NAS100"],
        alias="APEX_SYMBOLS",
    )
    entry_score: float = Field(default=7.0, alias="APEX_ENTRY_SCORE")
    min_aligned: int = Field(default=3, alias="APEX_MIN_ALIGNED")
    magic: int = Field(default=20240101, alias="APEX_MAGIC")

    # ── Dashboard ────────────────────────────────────────────────────────────────
    dashboard_host: str = Field(default="127.0.0.1", alias="APEX_DASHBOARD_HOST")
    dashboard_port: int = Field(default=8050, alias="APEX_DASHBOARD_PORT")

    # ── Telegram (optional) ─────────────────────────────────────────────────────
    telegram_token: str | None = Field(default=None, alias="TELEGRAM_TOKEN")
    telegram_chat_id: str | None = Field(default=None, alias="TELEGRAM_CHAT_ID")

    @field_validator("symbols", mode="before")
    @classmethod
    def _split_symbols(cls, value: object) -> object:
        """Accept a comma-separated string from the env and turn it into a list.

        Tolerates a plain CSV (``EURUSD,GBPUSD``) as well as a JSON-ish list
        (``["EURUSD","GBPUSD"]``); surrounding brackets/quotes are stripped.
        """
        if isinstance(value, str):
            cleaned = value.strip().strip("[]")
            parts = [p.strip().strip('"').strip("'").upper() for p in cleaned.split(",")]
            return [p for p in parts if p]
        return value

    @property
    def is_live(self) -> bool:
        return self.mode is TradingMode.LIVE


def load_settings() -> Settings:
    """Return a freshly loaded :class:`Settings` instance."""
    return Settings()
