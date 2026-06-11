"""Category C - levels & zones strategies."""

from __future__ import annotations

import numpy as np

from apex.data import MarketSnapshot, TimeframeView
from apex.models import Direction, Signal, Timeframe
from apex.strategies.base import Category, Strategy, registry


@registry.register
class SupportResistance(Strategy):
    """C1 - Support / Resistance reaction.

    Swing highs and lows are clustered into horizontal levels. A level tested
    several times that price is currently reacting to generates a signal:
    a bounce off support -> LONG, a rejection at resistance -> SHORT.
    """

    id = "C1"
    name = "Support/Resistance"
    category = Category.LEVEL
    weight = 1.1
    timeframe = Timeframe.M15
    min_bars = 60
    swing_width = 2

    def _evaluate(self, snapshot: MarketSnapshot, view: TimeframeView) -> Signal:
        atr = view.atr(14)[-1]
        if np.isnan(atr) or atr <= 0:
            return self.flat("no atr")

        swings = self._swings(view.high, view.low, self.swing_width)
        if not swings:
            return self.flat("no swings")

        levels = self._cluster(swings, tol=atr * 0.5)
        price = view.close[-1]
        prev = view.close[-2]
        low_ = view.low[-1]
        high = view.high[-1]
        near = atr * 0.6

        best = None
        for level, touches in levels:
            if touches < 2:
                continue
            if abs(price - level) <= near:
                if best is None or touches > best[1]:
                    best = (level, touches)
        if best is None:
            return self.flat("not at level")

        level, touches = best
        score = 5.0 + min(touches, 5) * 0.7

        # Support bounce: low pierced/approached the level, close back above.
        if low_ <= level + near and price > level and price >= prev:
            return self.signal(Direction.LONG, score, f"support x{touches} @ {level:.5f}")
        # Resistance rejection: high reached the level, close back below.
        if high >= level - near and price < level and price <= prev:
            return self.signal(Direction.SHORT, score, f"resistance x{touches} @ {level:.5f}")
        return self.flat("no reaction")

    @staticmethod
    def _swings(high: np.ndarray, low: np.ndarray, width: int) -> list[float]:
        out: list[float] = []
        for i in range(width, len(high) - width):
            hw = high[i - width : i + width + 1]
            lw = low[i - width : i + width + 1]
            if high[i] == hw.max():
                out.append(float(high[i]))
            if low[i] == lw.min():
                out.append(float(low[i]))
        return out

    @staticmethod
    def _cluster(values: list[float], tol: float) -> list[tuple[float, int]]:
        """Greedy 1-D clustering -> list of (centre, count)."""
        clusters: list[list[float]] = []
        for v in sorted(values):
            if clusters and abs(v - np.mean(clusters[-1])) <= tol:
                clusters[-1].append(v)
            else:
                clusters.append([v])
        return [(float(np.mean(c)), len(c)) for c in clusters]
