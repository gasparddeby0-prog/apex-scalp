"""In-memory paper-trading broker.

A self-contained simulation that requires no external terminal and runs on any
OS. It maintains synthetic M1 price paths (a seeded geometric random walk per
symbol), aggregates them to any timeframe, fills market orders, and marks open
positions to market - closing them when SL/TP is touched. This is the default
backend and what the test-suite and Linux sandbox use.
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np

from apex.config import Settings
from apex.logging_setup import get_logger
from apex.models import (
    AccountInfo,
    Candles,
    Direction,
    OrderRequest,
    OrderResult,
    OrderType,
    Position,
    SymbolInfo,
    Tick,
    Timeframe,
    utcnow,
)

log = get_logger("apex.broker.paper")

# Reasonable static specs + simulation parameters for common instruments.
# (start price, annualised-ish vol per bar, spread in price, SymbolInfo)
_SPECS: dict[str, dict] = {
    "EURUSD": {"price": 1.0850, "vol": 0.00035, "spread": 0.00012,
               "info": dict(digits=5, point=1e-5, pip=1e-4, contract_size=100_000, spread_limit_pips=1.5)},
    "GBPUSD": {"price": 1.2700, "vol": 0.00045, "spread": 0.00018,
               "info": dict(digits=5, point=1e-5, pip=1e-4, contract_size=100_000, spread_limit_pips=2.0)},
    "USDJPY": {"price": 156.20, "vol": 0.045, "spread": 0.018,
               "info": dict(digits=3, point=1e-3, pip=1e-2, contract_size=100_000, spread_limit_pips=2.0)},
    "USDCHF": {"price": 0.9050, "vol": 0.00035, "spread": 0.00016,
               "info": dict(digits=5, point=1e-5, pip=1e-4, contract_size=100_000, spread_limit_pips=2.0)},
    "AUDUSD": {"price": 0.6650, "vol": 0.00035, "spread": 0.00016,
               "info": dict(digits=5, point=1e-5, pip=1e-4, contract_size=100_000, spread_limit_pips=2.0)},
    "XAUUSD": {"price": 2350.0, "vol": 1.8, "spread": 0.25,
               "info": dict(digits=2, point=1e-2, pip=1e-1, contract_size=100, spread_limit_pips=25.0)},
    "NAS100": {"price": 18500.0, "vol": 12.0, "spread": 1.0,
               "info": dict(digits=1, point=1e-1, pip=1.0, contract_size=1, spread_limit_pips=3.0)},
    "US30": {"price": 39000.0, "vol": 20.0, "spread": 2.0,
             "info": dict(digits=1, point=1e-1, pip=1.0, contract_size=1, spread_limit_pips=4.0)},
    "BTCUSD": {"price": 67000.0, "vol": 120.0, "spread": 8.0,
               "info": dict(digits=2, point=1e-2, pip=1.0, contract_size=1, spread_limit_pips=50.0)},
}

_DEFAULT_SPEC = {"price": 100.0, "vol": 0.1, "spread": 0.02,
                 "info": dict(digits=3, point=1e-3, pip=1e-2, contract_size=100_000, spread_limit_pips=3.0)}

_PREFILL_BARS = 1500


class PaperBroker:
    """A deterministic, dependency-free trading simulator."""

    def __init__(self, settings: Settings, seed: int = 42):
        self.settings = settings
        self._rng = np.random.default_rng(seed)
        self._connected = False
        self._balance = float(settings.paper_balance)
        self._symbols = list(settings.symbols)
        self._m1: dict[str, Candles] = {}
        self._positions: dict[int, Position] = {}
        self._next_ticket = 1
        self._closed_pnl: list[float] = []

    # ── Lifecycle ────────────────────────────────────────────────────────────
    def connect(self) -> bool:
        for sym in self._symbols:
            self._m1[sym] = self._generate_history(sym, _PREFILL_BARS)
        self._connected = True
        log.info("PaperBroker connected | balance=%.2f | symbols=%s",
                 self._balance, ",".join(self._symbols))
        return True

    def shutdown(self) -> None:
        self._connected = False
        log.info("PaperBroker shutdown")

    def is_connected(self) -> bool:
        return self._connected

    # ── Account & instruments ──────────────────────────────────────────────────
    def account(self) -> AccountInfo:
        floating = sum(self._unrealised(p) for p in self._positions.values())
        equity = self._balance + floating
        used_margin = sum(self._margin(p) for p in self._positions.values())
        return AccountInfo(
            balance=round(self._balance, 2),
            equity=round(equity, 2),
            margin=round(used_margin, 2),
            free_margin=round(equity - used_margin, 2),
            currency="USD",
            connected=self._connected,
        )

    def symbols(self) -> list[str]:
        return list(self._symbols)

    def symbol_info(self, symbol: str) -> SymbolInfo:
        spec = _SPECS.get(symbol, _DEFAULT_SPEC)["info"]
        return SymbolInfo(name=symbol, **spec)

    # ── Market data ─────────────────────────────────────────────────────────────
    def tick(self, symbol: str) -> Tick:
        self._ensure(symbol)
        m1 = self._m1[symbol]
        mid = float(m1.close[-1])
        spread = _SPECS.get(symbol, _DEFAULT_SPEC)["spread"]
        return Tick(symbol=symbol, bid=mid - spread / 2, ask=mid + spread / 2, time=utcnow())

    def candles(self, symbol: str, timeframe: Timeframe, count: int) -> Candles:
        self._ensure(symbol)
        m1 = self._m1[symbol]
        if timeframe is Timeframe.M1:
            return m1.last(count)
        return self._resample(m1, timeframe).last(count)

    # ── Trading ───────────────────────────────────────────────────────────────
    def positions(self) -> list[Position]:
        out = []
        for p in self._positions.values():
            p.profit = round(self._unrealised(p), 2)
            out.append(p)
        return out

    def send_order(self, request: OrderRequest) -> OrderResult:
        if not self._connected:
            return OrderResult(ok=False, message="not connected")
        self._ensure(request.symbol)
        tick = self.tick(request.symbol)

        if request.order_type in (OrderType.BUY, OrderType.SELL):
            fill = tick.ask if request.order_type is OrderType.BUY else tick.bid
            direction = Direction.LONG if request.order_type is OrderType.BUY else Direction.SHORT
        else:
            # Pending orders are filled immediately at their requested price for
            # the purpose of this simulation (kept simple, deterministic).
            fill = request.price
            direction = (
                Direction.LONG
                if request.order_type in (OrderType.BUY_LIMIT, OrderType.BUY_STOP)
                else Direction.SHORT
            )

        ticket = self._next_ticket
        self._next_ticket += 1
        pos = Position(
            ticket=ticket,
            symbol=request.symbol,
            direction=direction,
            volume=request.volume,
            entry_price=fill,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
            open_time=utcnow(),
            magic=request.magic,
            comment=request.comment,
        )
        self._positions[ticket] = pos
        log.info("FILL #%d %s %s %.2f @ %.5f SL=%.5f TP=%.5f [%s]",
                 ticket, direction.value, request.symbol, request.volume, fill,
                 request.stop_loss, request.take_profit, request.comment)
        return OrderResult(ok=True, ticket=ticket, price=fill, message="filled", retcode=10009)

    def modify_position(
        self, ticket: int, stop_loss: float | None = None, take_profit: float | None = None
    ) -> OrderResult:
        pos = self._positions.get(ticket)
        if not pos:
            return OrderResult(ok=False, message=f"no position {ticket}")
        if stop_loss is not None:
            pos.stop_loss = stop_loss
        if take_profit is not None:
            pos.take_profit = take_profit
        return OrderResult(ok=True, ticket=ticket, message="modified")

    def close_position(self, ticket: int, volume: float | None = None) -> OrderResult:
        pos = self._positions.get(ticket)
        if not pos:
            return OrderResult(ok=False, message=f"no position {ticket}")
        close_vol = pos.volume if volume is None else min(volume, pos.volume)
        tick = self.tick(pos.symbol)
        exit_price = tick.bid if pos.direction is Direction.LONG else tick.ask
        realised = self._pnl(pos, exit_price, close_vol)
        self._balance += realised
        self._closed_pnl.append(realised)

        if close_vol >= pos.volume - 1e-9:
            del self._positions[ticket]
        else:
            pos.volume = round(pos.volume - close_vol, 2)
        log.info("CLOSE #%d %s vol=%.2f @ %.5f pnl=%.2f",
                 ticket, pos.symbol, close_vol, exit_price, realised)
        return OrderResult(ok=True, ticket=ticket, price=exit_price, message="closed")

    # ── Simulation control ──────────────────────────────────────────────────────
    def step(self, bars: int = 1) -> None:
        """Advance the simulation by ``bars`` M1 candles and process SL/TP."""
        for _ in range(bars):
            for sym in self._symbols:
                self._append_bar(sym)
            self._process_sl_tp()

    @property
    def realised_pnl(self) -> list[float]:
        return list(self._closed_pnl)

    # ── Internals ────────────────────────────────────────────────────────────────
    def _ensure(self, symbol: str) -> None:
        if symbol not in self._m1:
            if symbol not in self._symbols:
                self._symbols.append(symbol)
            self._m1[symbol] = self._generate_history(symbol, _PREFILL_BARS)

    def _generate_history(self, symbol: str, bars: int) -> Candles:
        spec = _SPECS.get(symbol, _DEFAULT_SPEC)
        start_price = spec["price"]
        vol = spec["vol"]
        end = utcnow().replace(second=0, microsecond=0)
        times = np.array([end - timedelta(minutes=bars - 1 - i) for i in range(bars)])

        # Random-walk closes with mild mean-reversion to keep prices sane.
        steps = self._rng.normal(0.0, vol, size=bars)
        closes = np.empty(bars)
        closes[0] = start_price
        for i in range(1, bars):
            drift = -0.002 * (closes[i - 1] - start_price)
            closes[i] = max(closes[i - 1] + steps[i] + drift, spec["spread"])

        opens = np.empty(bars)
        opens[0] = start_price
        opens[1:] = closes[:-1]
        wick = np.abs(self._rng.normal(0.0, vol * 0.6, size=bars))
        highs = np.maximum(opens, closes) + wick
        lows = np.minimum(opens, closes) - wick
        base_vol = self._rng.integers(500, 1500, size=bars).astype(float)
        volumes = base_vol * (1.0 + 3.0 * (wick / (vol + 1e-12)) * 0.1)

        return Candles(
            symbol=symbol,
            timeframe=Timeframe.M1,
            time=times,
            open=opens,
            high=highs,
            low=lows,
            close=closes,
            volume=volumes,
        )

    def _append_bar(self, symbol: str) -> None:
        spec = _SPECS.get(symbol, _DEFAULT_SPEC)
        m1 = self._m1[symbol]
        prev_close = float(m1.close[-1])
        vol = spec["vol"]
        drift = -0.002 * (prev_close - spec["price"])
        new_close = max(prev_close + float(self._rng.normal(0.0, vol)) + drift, spec["spread"])
        new_open = prev_close
        wick = abs(float(self._rng.normal(0.0, vol * 0.6)))
        new_high = max(new_open, new_close) + wick
        new_low = min(new_open, new_close) - wick
        new_time = m1.time[-1] + timedelta(minutes=1)
        new_volume = float(self._rng.integers(500, 1500))

        m1.time = np.append(m1.time, new_time)
        m1.open = np.append(m1.open, new_open)
        m1.high = np.append(m1.high, new_high)
        m1.low = np.append(m1.low, new_low)
        m1.close = np.append(m1.close, new_close)
        m1.volume = np.append(m1.volume, new_volume)

    def _process_sl_tp(self) -> None:
        for ticket in list(self._positions):
            pos = self._positions[ticket]
            candle = self._m1[pos.symbol]
            hi, lo = float(candle.high[-1]), float(candle.low[-1])
            hit_sl = (pos.direction is Direction.LONG and lo <= pos.stop_loss) or (
                pos.direction is Direction.SHORT and hi >= pos.stop_loss
            )
            hit_tp = (pos.direction is Direction.LONG and hi >= pos.take_profit) or (
                pos.direction is Direction.SHORT and lo <= pos.take_profit
            )
            if pos.stop_loss > 0 and hit_sl:
                self._settle(ticket, pos.stop_loss, "SL")
            elif pos.take_profit > 0 and hit_tp:
                self._settle(ticket, pos.take_profit, "TP")

    def _settle(self, ticket: int, price: float, reason: str) -> None:
        pos = self._positions.pop(ticket)
        realised = self._pnl(pos, price, pos.volume)
        self._balance += realised
        self._closed_pnl.append(realised)
        log.info("%s hit #%d %s @ %.5f pnl=%.2f", reason, ticket, pos.symbol, price, realised)

    def _pnl(self, pos: Position, exit_price: float, volume: float) -> float:
        info = self.symbol_info(pos.symbol)
        diff = (exit_price - pos.entry_price) * pos.direction.sign
        return diff * volume * info.contract_size

    def _unrealised(self, pos: Position) -> float:
        tick = self.tick(pos.symbol)
        price = tick.bid if pos.direction is Direction.LONG else tick.ask
        return self._pnl(pos, price, pos.volume)

    def _margin(self, pos: Position) -> float:
        info = self.symbol_info(pos.symbol)
        # Flat 1% notional margin proxy (no leverage modelling in the sim).
        return pos.entry_price * pos.volume * info.contract_size * 0.01

    @staticmethod
    def _resample(m1: Candles, tf: Timeframe) -> Candles:
        factor = tf.minutes
        n = len(m1)
        usable = (n // factor) * factor
        if usable == 0:
            return m1.last(0)
        start = n - usable
        idx = np.arange(start, n).reshape(-1, factor)

        o = m1.open[idx[:, 0]]
        c = m1.close[idx[:, -1]]
        h = np.array([m1.high[row].max() for row in idx])
        low_ = np.array([m1.low[row].min() for row in idx])
        v = np.array([m1.volume[row].sum() for row in idx])
        t = m1.time[idx[:, 0]]
        return Candles(symbol=m1.symbol, timeframe=tf, time=t, open=o, high=h, low=low_,
                       close=c, volume=v)
