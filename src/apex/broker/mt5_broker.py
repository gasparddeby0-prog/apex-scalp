"""Thin wrapper over the real ``MetaTrader5`` package.

This module is import-safe everywhere: the ``MetaTrader5`` dependency is only
imported inside :meth:`MT5Broker.connect`, so the rest of the codebase (and the
test-suite) runs on Linux/macOS without it installed. Run live only on Windows
with a running MT5 terminal and ``pip install MetaTrader5``.
"""

from __future__ import annotations

from datetime import UTC, datetime

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
)

log = get_logger("apex.broker.mt5")


class MT5Broker:
    """Adapter mapping our domain models onto the MetaTrader5 API."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._mt5 = None  # populated on connect()
        self._tf_map: dict[Timeframe, int] = {}
        self._order_type_map: dict[OrderType, int] = {}

    # ── Lifecycle ────────────────────────────────────────────────────────────
    def connect(self) -> bool:
        try:
            import MetaTrader5 as mt5  # noqa: N813  (deferred, Windows-only)
        except ImportError as exc:  # pragma: no cover - depends on platform
            raise RuntimeError(
                "The 'MetaTrader5' package is required for live mode. "
                "Install it on Windows with: pip install MetaTrader5"
            ) from exc

        self._mt5 = mt5
        self._tf_map = {
            Timeframe.M1: mt5.TIMEFRAME_M1,
            Timeframe.M5: mt5.TIMEFRAME_M5,
            Timeframe.M15: mt5.TIMEFRAME_M15,
            Timeframe.M30: mt5.TIMEFRAME_M30,
            Timeframe.H1: mt5.TIMEFRAME_H1,
            Timeframe.H4: mt5.TIMEFRAME_H4,
        }
        self._order_type_map = {
            OrderType.BUY: mt5.ORDER_TYPE_BUY,
            OrderType.SELL: mt5.ORDER_TYPE_SELL,
            OrderType.BUY_LIMIT: mt5.ORDER_TYPE_BUY_LIMIT,
            OrderType.SELL_LIMIT: mt5.ORDER_TYPE_SELL_LIMIT,
            OrderType.BUY_STOP: mt5.ORDER_TYPE_BUY_STOP,
            OrderType.SELL_STOP: mt5.ORDER_TYPE_SELL_STOP,
        }

        kwargs: dict = {}
        if self.settings.mt5_path:
            kwargs["path"] = self.settings.mt5_path
        if self.settings.mt5_login:
            kwargs["login"] = int(self.settings.mt5_login)
        if self.settings.mt5_password:
            kwargs["password"] = self.settings.mt5_password
        if self.settings.mt5_server:
            kwargs["server"] = self.settings.mt5_server

        if not mt5.initialize(**kwargs):
            err = mt5.last_error()
            log.error("mt5.initialize failed: %s", err)
            return False
        info = mt5.terminal_info()
        log.info("MT5 connected: %s", getattr(info, "name", "terminal"))
        return bool(info and info.connected)

    def shutdown(self) -> None:
        if self._mt5 is not None:
            self._mt5.shutdown()

    def is_connected(self) -> bool:
        if self._mt5 is None:
            return False
        info = self._mt5.terminal_info()
        return bool(info and info.connected)

    # ── Account & instruments ──────────────────────────────────────────────────
    def account(self) -> AccountInfo:
        a = self._mt5.account_info()
        if a is None:
            return AccountInfo(0, 0, 0, 0, connected=False)
        return AccountInfo(
            balance=a.balance,
            equity=a.equity,
            margin=a.margin,
            free_margin=a.margin_free,
            currency=a.currency,
            connected=True,
        )

    def symbols(self) -> list[str]:
        syms = self._mt5.symbols_get()
        return [s.name for s in syms] if syms else []

    def symbol_info(self, symbol: str) -> SymbolInfo:
        s = self._mt5.symbol_info(symbol)
        if s is None:
            raise ValueError(f"unknown symbol {symbol}")
        if not s.visible:
            self._mt5.symbol_select(symbol, True)
            s = self._mt5.symbol_info(symbol)
        # On 5/3-digit FX a pip is 10 points; otherwise treat point as pip.
        pip = s.point * 10 if s.digits in (3, 5) else s.point
        return SymbolInfo(
            name=s.name,
            digits=s.digits,
            point=s.point,
            pip=pip,
            contract_size=s.trade_contract_size,
            volume_min=s.volume_min,
            volume_max=s.volume_max,
            volume_step=s.volume_step,
            spread_limit_pips=max((s.spread or 0) * s.point / pip * 2, 1.0),
        )

    # ── Market data ─────────────────────────────────────────────────────────────
    def tick(self, symbol: str) -> Tick:
        t = self._mt5.symbol_info_tick(symbol)
        return Tick(
            symbol=symbol,
            bid=t.bid,
            ask=t.ask,
            time=datetime.fromtimestamp(t.time, tz=UTC),
        )

    def candles(self, symbol: str, timeframe: Timeframe, count: int) -> Candles:
        rates = self._mt5.copy_rates_from_pos(symbol, self._tf_map[timeframe], 0, count)
        if rates is None or len(rates) == 0:
            empty = np.array([])
            return Candles(symbol, timeframe, empty, empty, empty, empty, empty, empty)
        times = np.array(
            [datetime.fromtimestamp(r["time"], tz=UTC) for r in rates]
        )
        return Candles(
            symbol=symbol,
            timeframe=timeframe,
            time=times,
            open=np.asarray(rates["open"], dtype=float),
            high=np.asarray(rates["high"], dtype=float),
            low=np.asarray(rates["low"], dtype=float),
            close=np.asarray(rates["close"], dtype=float),
            volume=np.asarray(rates["tick_volume"], dtype=float),
        )

    # ── Trading ───────────────────────────────────────────────────────────────
    def positions(self) -> list[Position]:
        raw = self._mt5.positions_get()
        if not raw:
            return []
        out = []
        for p in raw:
            out.append(
                Position(
                    ticket=p.ticket,
                    symbol=p.symbol,
                    direction=Direction.LONG if p.type == self._mt5.POSITION_TYPE_BUY else Direction.SHORT,
                    volume=p.volume,
                    entry_price=p.price_open,
                    stop_loss=p.sl,
                    take_profit=p.tp,
                    open_time=datetime.fromtimestamp(p.time, tz=UTC),
                    magic=p.magic,
                    comment=p.comment,
                    profit=p.profit,
                )
            )
        return out

    def send_order(self, request: OrderRequest) -> OrderResult:
        mt5 = self._mt5
        is_pending = request.order_type not in (OrderType.BUY, OrderType.SELL)
        action = mt5.TRADE_ACTION_PENDING if is_pending else mt5.TRADE_ACTION_DEAL
        req = {
            "action": action,
            "symbol": request.symbol,
            "volume": float(request.volume),
            "type": self._order_type_map[request.order_type],
            "price": float(request.price),
            "sl": float(request.stop_loss),
            "tp": float(request.take_profit),
            "deviation": int(request.deviation),
            "magic": int(request.magic),
            "comment": request.comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(req)
        if result is None:
            return OrderResult(ok=False, message=f"order_send returned None: {mt5.last_error()}")
        ok = result.retcode == mt5.TRADE_RETCODE_DONE
        return OrderResult(
            ok=ok,
            ticket=getattr(result, "order", None),
            price=getattr(result, "price", None),
            message=result.comment,
            retcode=result.retcode,
        )

    def modify_position(
        self, ticket: int, stop_loss: float | None = None, take_profit: float | None = None
    ) -> OrderResult:
        mt5 = self._mt5
        pos = next((p for p in self.positions() if p.ticket == ticket), None)
        if pos is None:
            return OrderResult(ok=False, message=f"no position {ticket}")
        req = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": pos.symbol,
            "position": ticket,
            "sl": float(stop_loss if stop_loss is not None else pos.stop_loss),
            "tp": float(take_profit if take_profit is not None else pos.take_profit),
        }
        result = mt5.order_send(req)
        ok = result is not None and result.retcode == mt5.TRADE_RETCODE_DONE
        return OrderResult(ok=ok, ticket=ticket, message=getattr(result, "comment", "no result"))

    def close_position(self, ticket: int, volume: float | None = None) -> OrderResult:
        mt5 = self._mt5
        pos = next((p for p in self.positions() if p.ticket == ticket), None)
        if pos is None:
            return OrderResult(ok=False, message=f"no position {ticket}")
        close_type = (
            mt5.ORDER_TYPE_SELL if pos.direction is Direction.LONG else mt5.ORDER_TYPE_BUY
        )
        tick = mt5.symbol_info_tick(pos.symbol)
        price = tick.bid if pos.direction is Direction.LONG else tick.ask
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "position": ticket,
            "volume": float(volume if volume is not None else pos.volume),
            "type": close_type,
            "price": float(price),
            "deviation": 10,
            "magic": pos.magic,
            "comment": "APEX|close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(req)
        ok = result is not None and result.retcode == mt5.TRADE_RETCODE_DONE
        return OrderResult(ok=ok, ticket=ticket, message=getattr(result, "comment", "no result"))
