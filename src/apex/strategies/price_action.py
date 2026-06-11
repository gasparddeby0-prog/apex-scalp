"""Category A - price-action strategies."""

from __future__ import annotations

import numpy as np

from apex.data import MarketSnapshot, TimeframeView
from apex.models import Direction, Signal, Timeframe
from apex.strategies.base import Category, Strategy, registry


@registry.register
class PinBarReversal(Strategy):
    """A1 - Pin Bar Reversal.

    A rejection candle whose wick is at least twice the body signals a reversal
    in the direction opposite the wick. Score scales with the wick/body ratio
    and how decisively price closed away from the rejected extreme.
    """

    id = "A1"
    name = "Pin Bar Reversal"
    category = Category.PRICE_ACTION
    weight = 1.2
    timeframe = Timeframe.M5
    min_bars = 20

    def _evaluate(self, snapshot: MarketSnapshot, view: TimeframeView) -> Signal:
        o, h, low_, c = view.open[-1], view.high[-1], view.low[-1], view.close[-1]
        rng = h - low_
        if rng <= 0:
            return self.flat("flat candle")
        body = abs(c - o)
        upper = h - max(o, c)
        lower = min(o, c) - low_
        body = max(body, rng * 1e-3)  # avoid div-by-zero on doji

        # Bullish pin: long lower wick, close in the upper third.
        if lower >= 2 * body and lower > upper and (c - low_) / rng > 0.6:
            ratio = lower / body
            score = 5.5 + min(ratio, 6.0) * 0.55
            return self.signal(Direction.LONG, score, f"bull pin wick/body={ratio:.1f}")

        # Bearish pin: long upper wick, close in the lower third.
        if upper >= 2 * body and upper > lower and (h - c) / rng > 0.6:
            ratio = upper / body
            score = 5.5 + min(ratio, 6.0) * 0.55
            return self.signal(Direction.SHORT, score, f"bear pin wick/body={ratio:.1f}")

        return self.flat("no pin")


@registry.register
class EngulfingPattern(Strategy):
    """A3 - Engulfing Pattern with volume confirmation.

    The current candle's body fully engulfs the previous opposite-coloured
    body. Volume above its 20-period average adds conviction.
    """

    id = "A3"
    name = "Engulfing Pattern"
    category = Category.PRICE_ACTION
    weight = 1.1
    timeframe = Timeframe.M5
    min_bars = 25

    def _evaluate(self, snapshot: MarketSnapshot, view: TimeframeView) -> Signal:
        o0, c0 = view.open[-2], view.close[-2]
        o1, c1 = view.open[-1], view.close[-1]
        vol = view.volume[-1]
        vol_avg = view.volume_sma(20)[-1]
        vol_boost = 1.0 if (np.isnan(vol_avg) or vol_avg == 0) else min(vol / vol_avg, 3.0)

        prev_bear = c0 < o0
        prev_bull = c0 > o0
        curr_bull = c1 > o1
        curr_bear = c1 < o1

        # Bullish engulfing.
        if prev_bear and curr_bull and c1 >= o0 and o1 <= c0:
            cur_body = c1 - o1
            prev_body = o0 - c0
            strength = cur_body / prev_body if prev_body > 0 else 1.0
            score = 5.0 + min(strength, 3.0) + (vol_boost - 1.0)
            return self.signal(Direction.LONG, score, f"bull engulf x{strength:.1f} vol{vol_boost:.1f}")

        # Bearish engulfing.
        if prev_bull and curr_bear and c1 <= o0 and o1 >= c0:
            cur_body = o1 - c1
            prev_body = c0 - o0
            strength = cur_body / prev_body if prev_body > 0 else 1.0
            score = 5.0 + min(strength, 3.0) + (vol_boost - 1.0)
            return self.signal(Direction.SHORT, score, f"bear engulf x{strength:.1f} vol{vol_boost:.1f}")

        return self.flat("no engulfing")
