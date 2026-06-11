"""Category B - technical-indicator strategies."""

from __future__ import annotations

import numpy as np

from apex.data import MarketSnapshot, TimeframeView
from apex.models import Direction, Signal, Timeframe
from apex.strategies.base import Category, Strategy, registry


@registry.register
class EmaCross(Strategy):
    """B1 - EMA 5/20 cross with volume confirmation.

    A fresh cross of the fast EMA through the slow EMA on the latest bar, in
    the direction of the cross. Wider separation and above-average volume raise
    the score.
    """

    id = "B1"
    name = "EMA Cross 5/20"
    category = Category.INDICATOR
    weight = 1.0
    timeframe = Timeframe.M5
    min_bars = 40

    def _evaluate(self, snapshot: MarketSnapshot, view: TimeframeView) -> Signal:
        fast = view.ema(5)
        slow = view.ema(20)
        if np.isnan(fast[-2]) or np.isnan(slow[-2]):
            return self.flat("warming up")

        crossed_up = fast[-2] <= slow[-2] and fast[-1] > slow[-1]
        crossed_dn = fast[-2] >= slow[-2] and fast[-1] < slow[-1]
        if not (crossed_up or crossed_dn):
            return self.flat("no cross")

        sep = abs(fast[-1] - slow[-1])
        atr = view.atr(14)[-1]
        norm = sep / atr if atr and not np.isnan(atr) and atr > 0 else 0.0

        vol = view.volume[-1]
        vol_avg = view.volume_sma(20)[-1]
        vol_boost = 0.0 if (np.isnan(vol_avg) or vol_avg == 0) else min(vol / vol_avg - 1.0, 2.0)

        score = 6.0 + min(norm * 4.0, 2.5) + max(vol_boost, 0.0)
        direction = Direction.LONG if crossed_up else Direction.SHORT
        return self.signal(direction, score, f"ema cross norm={norm:.2f}")


@registry.register
class RsiDivergence(Strategy):
    """B2 - RSI(14) divergence against price.

    Bullish: price prints a lower low while RSI prints a higher low.
    Bearish: price prints a higher high while RSI prints a lower high.
    Pivots are located as local extrema within a lookback window.
    """

    id = "B2"
    name = "RSI Divergence"
    category = Category.INDICATOR
    weight = 1.15
    timeframe = Timeframe.M5
    min_bars = 60
    lookback = 40

    def _evaluate(self, snapshot: MarketSnapshot, view: TimeframeView) -> Signal:
        rsi = view.rsi(14)
        close = view.close
        n = len(close)
        lb = min(self.lookback, n)
        lows = self._pivots(view.low[-lb:], rsi[-lb:], find_min=True)
        highs = self._pivots(view.high[-lb:], rsi[-lb:], find_min=False)

        # Bullish divergence on the two most recent swing lows.
        if len(lows) >= 2:
            (p_prev, r_prev), (p_last, r_last) = lows[-2], lows[-1]
            if p_last < p_prev and r_last > r_prev and r_prev < 40:
                strength = (r_last - r_prev)
                score = 6.0 + min(strength / 5.0, 3.0)
                return self.signal(Direction.LONG, score, f"bull div RSI {r_prev:.0f}->{r_last:.0f}")

        # Bearish divergence on the two most recent swing highs.
        if len(highs) >= 2:
            (p_prev, r_prev), (p_last, r_last) = highs[-2], highs[-1]
            if p_last > p_prev and r_last < r_prev and r_prev > 60:
                strength = (r_prev - r_last)
                score = 6.0 + min(strength / 5.0, 3.0)
                return self.signal(Direction.SHORT, score, f"bear div RSI {r_prev:.0f}->{r_last:.0f}")

        return self.flat("no divergence")

    @staticmethod
    def _pivots(price: np.ndarray, rsi: np.ndarray, find_min: bool, width: int = 2):
        """Return (price, rsi) pairs at local extrema."""
        out: list[tuple[float, float]] = []
        for i in range(width, len(price) - width):
            window = price[i - width : i + width + 1]
            if np.isnan(rsi[i]):
                continue
            if find_min and price[i] == window.min():
                out.append((float(price[i]), float(rsi[i])))
            elif not find_min and price[i] == window.max():
                out.append((float(price[i]), float(rsi[i])))
        return out
