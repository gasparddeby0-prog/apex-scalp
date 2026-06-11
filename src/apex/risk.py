"""Risk management.

Implements the inviolable rules from the spec:

* fixed fractional risk per trade (default 0.5% of capital),
* daily (2%) and weekly (5%) committed-risk caps,
* a maximum number of simultaneous positions,
* a drawdown ladder - reduce size at 5%, halt new trades at 8%,
  kill-switch (close everything) at 10% measured from the equity high-water mark,
* size reduction after consecutive losses.

Lot sizing assumes a margin proxy consistent with the paper broker (1% of
notional). Adjust ``margin_rate`` to match your broker's leverage when live.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from apex.config import Settings
from apex.models import AccountInfo, SymbolInfo, utcnow


class DrawdownAction(StrEnum):
    NORMAL = "NORMAL"
    REDUCE = "REDUCE"  # DD >= 5%  -> halve size
    HALT = "HALT"  # DD >= 8%  -> no new trades
    KILL = "KILL"  # DD >= 10% -> close everything


@dataclass
class SizeResult:
    volume: float
    risk_amount: float
    risk_pct: float
    stop_distance: float
    multiplier: float
    notes: list[str] = field(default_factory=list)


@dataclass
class RiskDecision:
    allowed: bool
    reasons: list[str] = field(default_factory=list)


class RiskManager:
    """Stateful per-session risk controller."""

    def __init__(self, settings: Settings, margin_rate: float = 0.01):
        self.s = settings
        self.margin_rate = margin_rate
        self.peak_equity: float = float(settings.paper_balance)
        self.daily_risk_used: float = 0.0
        self.weekly_risk_used: float = 0.0
        self.consecutive_losses: int = 0
        self._day: int = -1
        self._week: int = -1

    # ── Period bookkeeping ─────────────────────────────────────────────────────
    def roll_periods(self, now: datetime | None = None) -> None:
        now = now or utcnow()
        day = now.timetuple().tm_yday
        week = int(now.strftime("%V"))
        if day != self._day:
            self._day = day
            self.daily_risk_used = 0.0
        if week != self._week:
            self._week = week
            self.weekly_risk_used = 0.0

    def update_equity(self, account: AccountInfo) -> None:
        self.peak_equity = max(self.peak_equity, account.equity)

    def register_close(self, pnl: float) -> None:
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

    # ── Drawdown ladder ─────────────────────────────────────────────────────────
    def drawdown_pct(self, account: AccountInfo) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, (self.peak_equity - account.equity) / self.peak_equity * 100.0)

    def drawdown_action(self, account: AccountInfo) -> DrawdownAction:
        dd = self.drawdown_pct(account)
        if dd >= 10.0:
            return DrawdownAction.KILL
        if dd >= 8.0:
            return DrawdownAction.HALT
        if dd >= 5.0:
            return DrawdownAction.REDUCE
        return DrawdownAction.NORMAL

    def size_multiplier(self, account: AccountInfo) -> float:
        mult = 1.0
        if self.drawdown_action(account) is DrawdownAction.REDUCE:
            mult = min(mult, 0.5)
        if self.consecutive_losses >= 3:
            mult = min(mult, 0.5)
        return mult

    # ── Lot sizing ──────────────────────────────────────────────────────────────
    def position_size(
        self,
        account: AccountInfo,
        info: SymbolInfo,
        entry: float,
        stop: float,
    ) -> SizeResult:
        notes: list[str] = []
        stop_distance = abs(entry - stop)
        if stop_distance <= 0:
            return SizeResult(0.0, 0.0, 0.0, 0.0, 0.0, ["invalid stop distance"])

        mult = self.size_multiplier(account)
        risk_pct = self.s.risk_per_trade_pct * mult
        risk_amount = account.balance * (risk_pct / 100.0)

        # Loss per 1.0 lot if the stop is hit (quote currency ~ account currency).
        loss_per_lot = stop_distance * info.contract_size
        if loss_per_lot <= 0:
            return SizeResult(0.0, 0.0, 0.0, stop_distance, mult, ["zero loss per lot"])

        raw_volume = risk_amount / loss_per_lot

        # Cap: no more than 5% of capital as margin on a single symbol.
        margin_per_lot = entry * info.contract_size * self.margin_rate
        if margin_per_lot > 0:
            max_by_margin = (account.balance * 0.05) / margin_per_lot
            if raw_volume > max_by_margin:
                raw_volume = max_by_margin
                notes.append("capped at 5% margin/symbol")

        volume = self._round_step(raw_volume, info)
        if volume < info.volume_min:
            notes.append(f"below volume_min ({info.volume_min}); not tradable at this risk")
            volume = 0.0

        realised_risk = volume * loss_per_lot
        realised_pct = (realised_risk / account.balance * 100.0) if account.balance > 0 else 0.0
        return SizeResult(
            volume=volume,
            risk_amount=round(realised_risk, 2),
            risk_pct=round(realised_pct, 3),
            stop_distance=stop_distance,
            multiplier=mult,
            notes=notes,
        )

    @staticmethod
    def _round_step(volume: float, info: SymbolInfo) -> float:
        if info.volume_step <= 0:
            return round(volume, 2)
        # Add a small epsilon before flooring to avoid binary float artefacts
        # (e.g. 0.25 / 0.01 == 24.9999... which would floor to 24).
        steps = math.floor(volume / info.volume_step + 1e-9)
        vol = steps * info.volume_step
        vol = min(vol, info.volume_max)
        return round(vol, 2)

    # ── Pre-trade gate ────────────────────────────────────────────────────────────
    def can_open(
        self,
        account: AccountInfo,
        open_positions: int,
        plan_risk_pct: float,
    ) -> RiskDecision:
        reasons: list[str] = []
        action = self.drawdown_action(account)
        if action in (DrawdownAction.HALT, DrawdownAction.KILL):
            reasons.append(f"drawdown {self.drawdown_pct(account):.1f}% -> {action.value}")
        if open_positions >= self.s.max_open_positions:
            reasons.append(f"max open positions reached ({self.s.max_open_positions})")
        if self.daily_risk_used + plan_risk_pct > self.s.max_daily_risk_pct + 1e-9:
            reasons.append(
                f"daily risk cap: {self.daily_risk_used:.2f}+{plan_risk_pct:.2f} "
                f">{self.s.max_daily_risk_pct:.2f}%"
            )
        if self.weekly_risk_used + plan_risk_pct > self.s.max_weekly_risk_pct + 1e-9:
            reasons.append(
                f"weekly risk cap: {self.weekly_risk_used:.2f}+{plan_risk_pct:.2f} "
                f">{self.s.max_weekly_risk_pct:.2f}%"
            )
        if account.margin_level_pct < 150.0:
            reasons.append(f"margin level {account.margin_level_pct:.0f}% < 150%")
        return RiskDecision(allowed=not reasons, reasons=reasons)

    def commit(self, plan_risk_pct: float) -> None:
        """Record committed risk once a trade is actually opened."""
        self.daily_risk_used += plan_risk_pct
        self.weekly_risk_used += plan_risk_pct
