"""Technical indicators implemented in pure NumPy.

Every function takes 1-D ``float`` arrays (oldest value first) and returns
arrays of the same length, with leading ``NaN`` for the warm-up period. No
TA-Lib / external C dependency is required, so the package installs anywhere.

The implementations follow the conventional definitions used by most charting
platforms (Wilder's smoothing for RSI/ATR/ADX, exponential MACD, etc.).
"""

from __future__ import annotations

import numpy as np

ArrayLike = np.ndarray


def _as_float(x: ArrayLike) -> np.ndarray:
    arr = np.asarray(x, dtype=float)
    if arr.ndim != 1:
        raise ValueError("indicator inputs must be 1-D arrays")
    return arr


def sma(values: ArrayLike, period: int) -> np.ndarray:
    """Simple moving average."""
    v = _as_float(values)
    out = np.full_like(v, np.nan)
    if period <= 0 or len(v) < period:
        return out
    cumsum = np.cumsum(np.insert(v, 0, 0.0))
    out[period - 1 :] = (cumsum[period:] - cumsum[:-period]) / period
    return out


def ema(values: ArrayLike, period: int) -> np.ndarray:
    """Exponential moving average (seeded with the first value)."""
    v = _as_float(values)
    out = np.full_like(v, np.nan)
    if period <= 0 or len(v) == 0:
        return out
    alpha = 2.0 / (period + 1.0)
    out[0] = v[0]
    for i in range(1, len(v)):
        out[i] = alpha * v[i] + (1.0 - alpha) * out[i - 1]
    return out


def wilder_smooth(values: ArrayLike, period: int) -> np.ndarray:
    """Wilder's smoothing (RMA), used by RSI/ATR/ADX."""
    v = _as_float(values)
    out = np.full_like(v, np.nan)
    if period <= 0 or len(v) < period:
        return out
    out[period - 1] = np.mean(v[:period])
    for i in range(period, len(v)):
        out[i] = (out[i - 1] * (period - 1) + v[i]) / period
    return out


def rsi(close: ArrayLike, period: int = 14) -> np.ndarray:
    """Relative Strength Index (Wilder)."""
    c = _as_float(close)
    out = np.full_like(c, np.nan)
    if len(c) <= period:
        return out
    delta = np.diff(c, prepend=c[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = wilder_smooth(gain, period)
    avg_loss = wilder_smooth(loss, period)
    rs = np.divide(
        avg_gain,
        avg_loss,
        out=np.full_like(avg_gain, np.nan),
        where=avg_loss > 0,
    )
    out = 100.0 - (100.0 / (1.0 + rs))
    # When average loss is zero the asset only gained -> RSI 100.
    out[(avg_loss == 0) & ~np.isnan(avg_gain)] = 100.0
    return out


def true_range(high: ArrayLike, low: ArrayLike, close: ArrayLike) -> np.ndarray:
    h, low_, c = _as_float(high), _as_float(low), _as_float(close)
    prev_close = np.roll(c, 1)
    prev_close[0] = c[0]
    tr = np.maximum.reduce(
        [h - low_, np.abs(h - prev_close), np.abs(low_ - prev_close)]
    )
    return tr


def atr(high: ArrayLike, low: ArrayLike, close: ArrayLike, period: int = 14) -> np.ndarray:
    """Average True Range (Wilder)."""
    tr = true_range(high, low, close)
    return wilder_smooth(tr, period)


def macd(
    close: ArrayLike,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """MACD line, signal line, histogram."""
    c = _as_float(close)
    macd_line = ema(c, fast) - ema(c, slow)
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def bollinger(
    close: ArrayLike, period: int = 20, num_std: float = 2.0
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bollinger Bands -> (upper, middle, lower)."""
    c = _as_float(close)
    middle = sma(c, period)
    std = _rolling_std(c, period)
    upper = middle + num_std * std
    lower = middle - num_std * std
    return upper, middle, lower


def _rolling_std(values: ArrayLike, period: int) -> np.ndarray:
    v = _as_float(values)
    out = np.full_like(v, np.nan)
    if period <= 0 or len(v) < period:
        return out
    for i in range(period - 1, len(v)):
        out[i] = np.std(v[i - period + 1 : i + 1])
    return out


def stochastic(
    high: ArrayLike,
    low: ArrayLike,
    close: ArrayLike,
    k_period: int = 14,
    d_period: int = 3,
) -> tuple[np.ndarray, np.ndarray]:
    """Stochastic oscillator -> (%K, %D)."""
    h, low_, c = _as_float(high), _as_float(low), _as_float(close)
    k = np.full_like(c, np.nan)
    for i in range(k_period - 1, len(c)):
        window_high = np.max(h[i - k_period + 1 : i + 1])
        window_low = np.min(low_[i - k_period + 1 : i + 1])
        rng = window_high - window_low
        k[i] = 100.0 * (c[i] - window_low) / rng if rng > 0 else 50.0
    d = sma(k, d_period)
    return k, d


def adx(
    high: ArrayLike,
    low: ArrayLike,
    close: ArrayLike,
    period: int = 14,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Average Directional Index -> (ADX, +DI, -DI)."""
    h, low_, c = _as_float(high), _as_float(low), _as_float(close)
    n = len(c)
    if n < 2:
        nan = np.full(n, np.nan)
        return nan, nan.copy(), nan.copy()
    up_move = h[1:] - h[:-1]
    down_move = low_[:-1] - low_[1:]
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    plus_dm = np.insert(plus_dm, 0, 0.0)
    minus_dm = np.insert(minus_dm, 0, 0.0)
    tr = true_range(h, low_, c)

    atr_ = wilder_smooth(tr, period)
    plus_di = 100.0 * _safe_div(wilder_smooth(plus_dm, period), atr_)
    minus_di = 100.0 * _safe_div(wilder_smooth(minus_dm, period), atr_)
    dx = 100.0 * _safe_div(np.abs(plus_di - minus_di), (plus_di + minus_di))
    adx_ = wilder_smooth(np.nan_to_num(dx, nan=0.0), period)
    # Re-mask the warm-up region that nan_to_num filled with zeros.
    adx_[: 2 * period] = np.nan
    return adx_, plus_di, minus_di


def _safe_div(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.divide(a, b, out=np.full_like(a, np.nan), where=(b != 0) & ~np.isnan(b))


def zscore(values: ArrayLike, period: int = 50) -> np.ndarray:
    """Rolling z-score of the latest value within the window."""
    v = _as_float(values)
    out = np.full_like(v, np.nan)
    mean = sma(v, period)
    std = _rolling_std(v, period)
    mask = (~np.isnan(std)) & (std > 0)
    out[mask] = (v[mask] - mean[mask]) / std[mask]
    return out
