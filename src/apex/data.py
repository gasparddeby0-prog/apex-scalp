"""Market data layer.

Strategies should never touch the broker directly. Instead the orchestrator
builds a :class:`MarketSnapshot` per symbol - a multi-timeframe bundle of
candles plus an indicator cache - and hands it to every strategy. Indicators
are computed lazily and memoised so that, e.g., several strategies asking for
``ema(20)`` on M5 only pay the cost once.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from apex import indicators as ta
from apex.broker.base import Broker
from apex.models import Candles, SymbolInfo, Tick, Timeframe

# Timeframes pulled for every snapshot and how many bars of history to load.
DEFAULT_TIMEFRAMES: tuple[Timeframe, ...] = (
    Timeframe.H4,
    Timeframe.H1,
    Timeframe.M15,
    Timeframe.M5,
    Timeframe.M1,
)
DEFAULT_BARS = 300


@dataclass
class TimeframeView:
    """Candles for a single timeframe plus a per-indicator memo cache."""

    candles: Candles
    _cache: dict = field(default_factory=dict, repr=False)

    def __len__(self) -> int:
        return len(self.candles)

    # Convenience accessors -----------------------------------------------------
    @property
    def close(self) -> np.ndarray:
        return self.candles.close

    @property
    def high(self) -> np.ndarray:
        return self.candles.high

    @property
    def low(self) -> np.ndarray:
        return self.candles.low

    @property
    def open(self) -> np.ndarray:
        return self.candles.open

    @property
    def volume(self) -> np.ndarray:
        return self.candles.volume

    def _memo(self, key: tuple, fn):
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]

    # Memoised indicators -------------------------------------------------------
    def ema(self, period: int) -> np.ndarray:
        return self._memo(("ema", period), lambda: ta.ema(self.close, period))

    def sma(self, period: int) -> np.ndarray:
        return self._memo(("sma", period), lambda: ta.sma(self.close, period))

    def rsi(self, period: int = 14) -> np.ndarray:
        return self._memo(("rsi", period), lambda: ta.rsi(self.close, period))

    def atr(self, period: int = 14) -> np.ndarray:
        return self._memo(("atr", period), lambda: ta.atr(self.high, self.low, self.close, period))

    def macd(self, fast: int = 12, slow: int = 26, signal: int = 9):
        return self._memo(("macd", fast, slow, signal),
                          lambda: ta.macd(self.close, fast, slow, signal))

    def bollinger(self, period: int = 20, num_std: float = 2.0):
        return self._memo(("bb", period, num_std),
                          lambda: ta.bollinger(self.close, period, num_std))

    def stochastic(self, k: int = 14, d: int = 3):
        return self._memo(("stoch", k, d),
                          lambda: ta.stochastic(self.high, self.low, self.close, k, d))

    def adx(self, period: int = 14):
        return self._memo(("adx", period),
                          lambda: ta.adx(self.high, self.low, self.close, period))

    def volume_sma(self, period: int = 20) -> np.ndarray:
        return self._memo(("vsma", period), lambda: ta.sma(self.volume, period))

    def zscore(self, period: int = 50) -> np.ndarray:
        return self._memo(("z", period), lambda: ta.zscore(self.close, period))


@dataclass
class MarketSnapshot:
    """Everything a strategy needs about one symbol at one instant."""

    symbol: str
    info: SymbolInfo
    tick: Tick
    frames: dict[Timeframe, TimeframeView]

    def tf(self, timeframe: Timeframe) -> TimeframeView:
        return self.frames[timeframe]

    def has(self, timeframe: Timeframe) -> bool:
        return timeframe in self.frames and len(self.frames[timeframe]) > 0

    @property
    def spread_pips(self) -> float:
        return self.info.price_to_pips(self.tick.spread)


class MarketData:
    """Builds :class:`MarketSnapshot` objects from a broker."""

    def __init__(
        self,
        broker: Broker,
        timeframes: tuple[Timeframe, ...] = DEFAULT_TIMEFRAMES,
        bars: int = DEFAULT_BARS,
    ):
        self.broker = broker
        self.timeframes = timeframes
        self.bars = bars

    def snapshot(self, symbol: str) -> MarketSnapshot:
        info = self.broker.symbol_info(symbol)
        tick = self.broker.tick(symbol)
        frames: dict[Timeframe, TimeframeView] = {}
        for timeframe in self.timeframes:
            candles = self.broker.candles(symbol, timeframe, self.bars)
            if len(candles) > 0:
                frames[timeframe] = TimeframeView(candles=candles)
        return MarketSnapshot(symbol=symbol, info=info, tick=tick, frames=frames)
