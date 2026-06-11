"""Category D - volume & orderflow strategies."""

from __future__ import annotations

import numpy as np

from apex.data import MarketSnapshot, TimeframeView
from apex.models import Direction, Signal, Timeframe
from apex.strategies.base import Category, Strategy, registry


@registry.register
class VolumeSpike(Strategy):
    """D1 - Volume Spike entry.

    A bar whose volume exceeds twice its 20-period average signals strong
    participation; direction follows the candle's body. The score scales with
    how far the spike exceeds the threshold.
    """

    id = "D1"
    name = "Volume Spike"
    category = Category.VOLUME
    weight = 0.9
    timeframe = Timeframe.M5
    min_bars = 30
    spike_mult = 2.0

    def _evaluate(self, snapshot: MarketSnapshot, view: TimeframeView) -> Signal:
        vol = view.volume[-1]
        vol_avg = view.volume_sma(20)[-1]
        if np.isnan(vol_avg) or vol_avg <= 0:
            return self.flat("no avg volume")

        ratio = vol / vol_avg
        if ratio < self.spike_mult:
            return self.flat(f"volume normal x{ratio:.1f}")

        o, c = view.open[-1], view.close[-1]
        rng = view.high[-1] - view.low[-1]
        if rng <= 0 or c == o:
            return self.flat("no direction")

        # Require the close to be decisively in one half of the bar.
        body_pos = (c - view.low[-1]) / rng
        score = 5.0 + min(ratio - self.spike_mult, 4.0)
        if c > o and body_pos > 0.55:
            return self.signal(Direction.LONG, score, f"bull volume spike x{ratio:.1f}")
        if c < o and body_pos < 0.45:
            return self.signal(Direction.SHORT, score, f"bear volume spike x{ratio:.1f}")
        return self.flat("indecisive spike")
