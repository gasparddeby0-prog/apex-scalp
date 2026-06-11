"""Execution layer.

Translates an approved :class:`~apex.models.TradePlan` into a broker order with
a protective stop and take-profit, retrying on transient failures. Also derives
the ATR-based SL/TP ladder and manages open positions (break-even at +1R,
ATR trailing stop) per the spec.

Every market order carries a stop loss: opening a position without one is
explicitly forbidden and is rejected here as a safety net.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from apex.broker.base import Broker
from apex.data import MarketSnapshot
from apex.logging_setup import get_logger
from apex.models import (
    Direction,
    OrderRequest,
    OrderResult,
    OrderType,
    Position,
    SymbolInfo,
    TradePlan,
)

log = get_logger("apex.execution")

# Risk:reward multiples for the three take-profits and the share of the
# position closed at each (sums to 1.0).
TP_RR = (1.5, 2.5, 4.0)
TP_SHARE = (0.5, 0.3, 0.2)


@dataclass
class TradeLevels:
    stop_loss: float
    take_profits: list[float]
    stop_distance: float


def build_levels(
    direction: Direction,
    entry: float,
    atr: float,
    info: SymbolInfo,
    atr_mult: float = 1.5,
    min_pips: float = 10.0,
) -> TradeLevels:
    """ATR(14)*1.5 stop (min 10 pips) and the 1:1.5 / 1:2.5 / 1:4 TP ladder."""
    min_dist = info.pips_to_price(min_pips)
    stop_distance = max(atr * atr_mult, min_dist)
    sign = direction.sign
    stop_loss = entry - sign * stop_distance
    take_profits = [entry + sign * stop_distance * rr for rr in TP_RR]
    return TradeLevels(
        stop_loss=round(stop_loss, info.digits),
        take_profits=[round(tp, info.digits) for tp in take_profits],
        stop_distance=stop_distance,
    )


class Executor:
    """Sends and manages orders through a :class:`Broker`."""

    def __init__(self, broker: Broker, magic: int = 20240101, max_retries: int = 2):
        self.broker = broker
        self.magic = magic
        self.max_retries = max_retries

    def open_trade(self, plan: TradePlan) -> OrderResult:
        if plan.direction is Direction.NONE:
            return OrderResult(ok=False, message="no direction")
        if plan.stop_loss <= 0:
            return OrderResult(ok=False, message="refused: no stop loss")
        if plan.volume <= 0:
            return OrderResult(ok=False, message="refused: zero volume")

        order_type = OrderType.BUY if plan.direction is Direction.LONG else OrderType.SELL
        tick = self.broker.tick(plan.symbol)
        price = tick.ask if plan.direction is Direction.LONG else tick.bid
        tp1 = plan.take_profits[0] if plan.take_profits else 0.0

        comment = f"APEX|{'+'.join(plan.strategy_ids)}|{plan.score:.1f}"[:31]
        request = OrderRequest(
            symbol=plan.symbol,
            order_type=order_type,
            volume=plan.volume,
            price=price,
            stop_loss=plan.stop_loss,
            take_profit=tp1,
            deviation=self._deviation(plan.symbol),
            magic=self.magic,
            comment=comment,
        )

        result = OrderResult(ok=False, message="not attempted")
        for attempt in range(1, self.max_retries + 2):
            result = self.broker.send_order(request)
            if result.ok:
                if attempt > 1:
                    log.info("order succeeded on attempt %d", attempt)
                return result
            log.warning("order attempt %d failed: %s", attempt, result.message)
            if attempt <= self.max_retries:
                time.sleep(0.2)
                refreshed = self.broker.tick(plan.symbol)
                request.price = refreshed.ask if plan.direction is Direction.LONG else refreshed.bid
        return result

    def close(self, ticket: int, volume: float | None = None) -> OrderResult:
        return self.broker.close_position(ticket, volume)

    # ── Position management ──────────────────────────────────────────────────────
    def manage_position(self, pos: Position, snapshot: MarketSnapshot) -> list[str]:
        """Apply break-even (+1R) and ATR trailing; returns a list of actions taken."""
        actions: list[str] = []
        info = snapshot.info
        if snapshot.has(self.broker_timeframe_fallback(snapshot)):
            atr_view = snapshot.tf(self.broker_timeframe_fallback(snapshot))
            atr = float(atr_view.atr(14)[-1])
        else:
            return actions

        price = snapshot.tick.mid
        sign = pos.direction.sign
        risk = abs(pos.entry_price - pos.stop_loss)
        if risk <= 0:
            return actions

        in_profit = (price - pos.entry_price) * sign
        # Break-even once price has moved +1R.
        if in_profit >= risk and (pos.stop_loss - pos.entry_price) * sign < 0:
            be = round(pos.entry_price, info.digits)
            res = self.broker.modify_position(pos.ticket, stop_loss=be)
            if res.ok:
                actions.append(f"break-even SL->{be}")

        # ATR trailing once in profit.
        if atr and in_profit >= risk:
            trail = round(price - sign * atr * 0.8, info.digits)
            improves = (trail - pos.stop_loss) * sign > 0
            if improves:
                res = self.broker.modify_position(pos.ticket, stop_loss=trail)
                if res.ok:
                    actions.append(f"trail SL->{trail}")
        return actions

    @staticmethod
    def broker_timeframe_fallback(snapshot: MarketSnapshot):
        # Prefer M5 for ATR-based management, fall back to whatever exists.
        from apex.models import Timeframe

        for tf in (Timeframe.M5, Timeframe.M15, Timeframe.M1):
            if snapshot.has(tf):
                return tf
        return next(iter(snapshot.frames))

    @staticmethod
    def _deviation(symbol: str) -> int:
        # Indices tolerate more slippage than FX.
        return 50 if symbol.upper() in {"NAS100", "US30", "SPX500"} else 10
