"""Domain models shared across the engine.

These are plain, framework-free dataclasses / enums so they can be used
identically by the paper broker, the real MT5 broker, strategies, the risk
manager and the dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

import numpy as np


class Timeframe(StrEnum):
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"

    @property
    def minutes(self) -> int:
        return {
            "M1": 1,
            "M5": 5,
            "M15": 15,
            "M30": 30,
            "H1": 60,
            "H4": 240,
        }[self.value]


class Direction(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    NONE = "NONE"

    @property
    def sign(self) -> int:
        return {"LONG": 1, "SHORT": -1, "NONE": 0}[self.value]


class OrderType(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    BUY_LIMIT = "BUY_LIMIT"
    SELL_LIMIT = "SELL_LIMIT"
    BUY_STOP = "BUY_STOP"
    SELL_STOP = "SELL_STOP"


@dataclass(frozen=True)
class Tick:
    symbol: str
    bid: float
    ask: float
    time: datetime

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread(self) -> float:
        return self.ask - self.bid


@dataclass(frozen=True)
class SymbolInfo:
    """Static description of a tradable instrument."""

    name: str
    digits: int
    point: float  # smallest price increment, e.g. 0.00001
    pip: float  # one pip in price terms, e.g. 0.0001 (10 points on 5-digit FX)
    contract_size: float  # units per 1.00 lot, e.g. 100_000 for FX
    volume_min: float = 0.01
    volume_max: float = 100.0
    volume_step: float = 0.01
    spread_limit_pips: float = 3.0  # max acceptable spread for entries

    def price_to_pips(self, price_distance: float) -> float:
        return price_distance / self.pip

    def pips_to_price(self, pips: float) -> float:
        return pips * self.pip


@dataclass
class Candles:
    """Column-oriented OHLCV series for one symbol/timeframe (oldest first)."""

    symbol: str
    timeframe: Timeframe
    time: np.ndarray
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray

    def __len__(self) -> int:
        return int(self.close.shape[0])

    def last(self, n: int = 1) -> Candles:
        return Candles(
            symbol=self.symbol,
            timeframe=self.timeframe,
            time=self.time[-n:],
            open=self.open[-n:],
            high=self.high[-n:],
            low=self.low[-n:],
            close=self.close[-n:],
            volume=self.volume[-n:],
        )


@dataclass(frozen=True)
class Signal:
    """A single strategy's verdict on a symbol/timeframe."""

    strategy_id: str
    direction: Direction
    score: float  # 0..10
    reason: str = ""

    @property
    def is_actionable(self) -> bool:
        return self.direction is not Direction.NONE and self.score > 0.0


@dataclass
class TradePlan:
    """Aggregated decision produced by the scoring engine + risk manager."""

    symbol: str
    direction: Direction
    score: float
    aligned: list[Signal] = field(default_factory=list)
    entry: float = 0.0
    stop_loss: float = 0.0
    take_profits: list[float] = field(default_factory=list)
    volume: float = 0.0
    risk_amount: float = 0.0
    risk_pct: float = 0.0
    decision: str = "REJECT"  # EXECUTE | WAIT | REJECT
    notes: list[str] = field(default_factory=list)

    @property
    def strategy_ids(self) -> list[str]:
        return [s.strategy_id for s in self.aligned]


@dataclass
class Position:
    ticket: int
    symbol: str
    direction: Direction
    volume: float
    entry_price: float
    stop_loss: float
    take_profit: float
    open_time: datetime
    magic: int = 0
    comment: str = ""
    profit: float = 0.0  # unrealised P/L in account currency


@dataclass
class OrderRequest:
    symbol: str
    order_type: OrderType
    volume: float
    price: float
    stop_loss: float
    take_profit: float
    deviation: int = 10
    magic: int = 0
    comment: str = ""


@dataclass
class OrderResult:
    ok: bool
    ticket: int | None = None
    price: float | None = None
    message: str = ""
    retcode: int | None = None


@dataclass
class AccountInfo:
    balance: float
    equity: float
    margin: float
    free_margin: float
    currency: str = "USD"
    connected: bool = True

    @property
    def margin_level_pct(self) -> float:
        if self.margin <= 0:
            return float("inf")
        return self.equity / self.margin * 100.0


def utcnow() -> datetime:
    return datetime.now(tz=UTC)
