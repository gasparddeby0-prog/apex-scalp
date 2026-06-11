import numpy as np

from apex.data import MarketSnapshot, TimeframeView
from apex.models import Candles, Direction, SymbolInfo, Tick, Timeframe, utcnow
from apex.strategies import (
    EmaCross,
    EngulfingPattern,
    PinBarReversal,
    VolumeSpike,
    default_strategies,
)


def _snapshot(o, h, low_, c, v) -> MarketSnapshot:
    o, h, low_, c, v = (np.asarray(x, dtype=float) for x in (o, h, low_, c, v))
    t = np.array([utcnow() for _ in range(len(c))])
    candles = Candles("T", Timeframe.M5, t, o, h, low_, c, v)
    view = TimeframeView(candles)
    info = SymbolInfo(name="T", digits=5, point=1e-5, pip=1e-4, contract_size=100_000)
    tick = Tick("T", bid=c[-1] - 5e-5, ask=c[-1] + 5e-5, time=utcnow())
    frames = {tf: view for tf in (Timeframe.H4, Timeframe.H1, Timeframe.M15,
                                  Timeframe.M5, Timeframe.M1)}
    return MarketSnapshot(symbol="T", info=info, tick=tick, frames=frames)


def test_pin_bar_bullish():
    n = 25
    o = [100.0] * n
    c = [100.02] * n
    h = [100.05] * n
    low_ = [99.97] * n
    v = [1000.0] * n
    # Final bar: long lower wick, close near the top -> bullish pin.
    o[-1], c[-1], h[-1], low_[-1] = 100.0, 100.05, 100.10, 99.00
    sig = PinBarReversal().evaluate(_snapshot(o, h, low_, c, v))
    assert sig.direction is Direction.LONG
    assert sig.score > 5.0


def test_engulfing_bullish():
    n = 30
    o = [100.0] * n
    c = [100.0] * n
    h = [100.2] * n
    low_ = [99.8] * n
    v = [1000.0] * n
    # prev bearish, current bullish engulfing.
    o[-2], c[-2] = 100.2, 99.8
    o[-1], c[-1] = 99.7, 100.3
    h[-1], low_[-1] = 100.35, 99.65
    sig = EngulfingPattern().evaluate(_snapshot(o, h, low_, c, v))
    assert sig.direction is Direction.LONG


def test_ema_cross_up():
    n = 45
    c = [100.0] * n
    c[-1] = 101.0  # sharp move on the last bar forces a fast/slow up-cross
    o = c.copy()
    h = [x + 0.05 for x in c]
    low_ = [x - 0.05 for x in c]
    v = [1000.0] * n
    sig = EmaCross().evaluate(_snapshot(o, h, low_, c, v))
    assert sig.direction is Direction.LONG


def test_ema_cross_down():
    n = 45
    c = [100.0] * n
    c[-1] = 99.0
    o = c.copy()
    h = [x + 0.05 for x in c]
    low_ = [x - 0.05 for x in c]
    v = [1000.0] * n
    sig = EmaCross().evaluate(_snapshot(o, h, low_, c, v))
    assert sig.direction is Direction.SHORT


def test_volume_spike_long():
    n = 30
    o = [100.0] * n
    c = [100.0] * n
    h = [100.1] * n
    low_ = [99.9] * n
    v = [1000.0] * n
    # Big bullish bar on huge volume.
    o[-1], c[-1], h[-1], low_[-1], v[-1] = 100.0, 100.5, 100.5, 100.0, 6000.0
    sig = VolumeSpike().evaluate(_snapshot(o, h, low_, c, v))
    assert sig.direction is Direction.LONG


def test_all_strategies_return_signal_without_error():
    # A flat market should yield non-actionable signals, never exceptions.
    n = 80
    flat = [100.0] * n
    snap = _snapshot(flat, [x + 0.01 for x in flat], [x - 0.01 for x in flat],
                     flat, [1000.0] * n)
    for strat in default_strategies():
        sig = strat.evaluate(snap)
        assert sig.strategy_id == strat.id
        assert 0.0 <= sig.score <= 10.0
