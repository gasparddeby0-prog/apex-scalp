import numpy as np

from apex import indicators as ta


def test_sma_basic():
    x = np.array([1, 2, 3, 4, 5], dtype=float)
    out = ta.sma(x, 3)
    assert np.isnan(out[0]) and np.isnan(out[1])
    assert out[2] == 2.0
    assert out[4] == 4.0


def test_ema_tracks_constant_series():
    x = np.full(50, 5.0)
    out = ta.ema(x, 10)
    assert np.isclose(out[-1], 5.0)


def test_rsi_bounds_and_uptrend():
    # Strictly increasing series -> RSI should be very high (near 100).
    x = np.linspace(1, 100, 100)
    out = ta.rsi(x, 14)
    valid = out[~np.isnan(out)]
    assert valid.min() >= 0.0 and valid.max() <= 100.0
    assert out[-1] > 90.0


def test_rsi_downtrend_low():
    x = np.linspace(100, 1, 100)
    out = ta.rsi(x, 14)
    assert out[-1] < 10.0


def test_atr_positive():
    rng = np.random.default_rng(0)
    close = np.cumsum(rng.normal(0, 1, 200)) + 100
    high = close + np.abs(rng.normal(0, 0.5, 200))
    low = close - np.abs(rng.normal(0, 0.5, 200))
    out = ta.atr(high, low, close, 14)
    valid = out[~np.isnan(out)]
    assert (valid > 0).all()


def test_macd_shapes():
    x = np.cumsum(np.random.default_rng(1).normal(0, 1, 100)) + 50
    macd_line, signal, hist = ta.macd(x)
    assert macd_line.shape == x.shape == signal.shape == hist.shape


def test_bollinger_order():
    x = np.cumsum(np.random.default_rng(2).normal(0, 1, 100)) + 50
    upper, mid, lower = ta.bollinger(x, 20, 2.0)
    i = -1
    assert upper[i] >= mid[i] >= lower[i]


def test_stochastic_bounds():
    rng = np.random.default_rng(3)
    close = np.cumsum(rng.normal(0, 1, 100)) + 50
    high = close + 1
    low = close - 1
    k, d = ta.stochastic(high, low, close)
    kv = k[~np.isnan(k)]
    assert kv.min() >= 0.0 and kv.max() <= 100.0


def test_adx_nonnegative():
    rng = np.random.default_rng(4)
    close = np.cumsum(rng.normal(0, 1, 200)) + 100
    high = close + np.abs(rng.normal(0, 0.5, 200))
    low = close - np.abs(rng.normal(0, 0.5, 200))
    adx, plus_di, minus_di = ta.adx(high, low, close, 14)
    av = adx[~np.isnan(adx)]
    assert (av >= 0).all() and (av <= 100).all()
