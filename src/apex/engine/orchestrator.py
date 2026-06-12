"""Scan orchestrator: the loop that ties every layer together.

For each symbol it builds a market snapshot, runs all strategies, scores the
confluence, applies eligibility filters, sizes the trade with the risk manager,
and (optionally) executes it. It also manages open positions and enforces the
drawdown kill-switch. Designed so a single ``run_once()`` is fully testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from apex.broker import build_broker
from apex.broker.base import Broker
from apex.config import Settings
from apex.data import MarketData
from apex.engine.scoring import ScoringEngine
from apex.execution import Executor, build_levels
from apex.filters import in_trading_session, is_rollover, news_blackout
from apex.logging_setup import get_logger
from apex.models import AccountInfo, Direction, Signal, Timeframe, TradePlan, utcnow
from apex.risk import DrawdownAction, RiskManager
from apex.strategies import default_strategies

log = get_logger("apex.engine")


@dataclass
class ScanResult:
    timestamp: object
    account: AccountInfo
    plans: list[TradePlan] = field(default_factory=list)
    executed: list[tuple[str, str]] = field(default_factory=list)  # (symbol, message)
    signals: dict[str, list[Signal]] = field(default_factory=dict)

    @property
    def actionable(self) -> list[TradePlan]:
        return [p for p in self.plans if p.decision == "EXECUTE"]


class Orchestrator:
    """Owns the broker, engine components and the scan/manage cycle."""

    def __init__(
        self,
        settings: Settings,
        broker: Broker | None = None,
        enforce_time_filters: bool | None = None,
    ):
        self.settings = settings
        self.broker = broker or build_broker(settings)
        self.data = MarketData(self.broker)
        self.strategies = default_strategies()
        self.scoring = ScoringEngine(
            self.strategies,
            entry_score=settings.entry_score,
            min_aligned=settings.min_aligned,
        )
        self.risk = RiskManager(settings)
        self.executor = Executor(self.broker, magic=settings.magic)
        # Real session/news filters only make sense on live data.
        self.enforce_time_filters = (
            settings.is_live if enforce_time_filters is None else enforce_time_filters
        )
        self.last_scan: ScanResult | None = None
        # How many realised P/L entries we have already fed to the risk manager,
        # so the consecutive-loss size reduction reacts to newly closed trades.
        self._consumed_pnls = 0

    # ── Lifecycle ────────────────────────────────────────────────────────────────
    def start(self) -> bool:
        ok = self.broker.connect()
        if ok:
            acc = self.broker.account()
            self.risk.peak_equity = max(self.risk.peak_equity, acc.equity)
            log.info("Orchestrator started in %s mode | equity=%.2f",
                     self.settings.mode.value.upper(), acc.equity)
        return ok

    def stop(self) -> None:
        self.broker.shutdown()

    # ── Per-symbol analysis ─────────────────────────────────────────────────────
    def analyse(self, symbol: str, account: AccountInfo) -> tuple[TradePlan, list[Signal]]:
        snapshot = self.data.snapshot(symbol)
        signals = [s.evaluate(snapshot) for s in self.strategies]
        conf = self.scoring.evaluate(signals)

        plan = TradePlan(
            symbol=symbol,
            direction=conf.direction,
            score=conf.score,
            aligned=conf.aligned,
        )

        if conf.direction is Direction.NONE or conf.score < self.settings.entry_score:
            plan.decision = "REJECT"
            plan.notes = conf.reasons or ["score below threshold"]
            return plan, signals

        # Eligibility filters.
        block = self._filter_reasons(symbol, snapshot.spread_pips, snapshot.info.spread_limit_pips)
        if not conf.passed:
            block = conf.reasons + block

        # Build SL/TP from ATR on the entry timeframe (M5).
        entry_tf = Timeframe.M5 if snapshot.has(Timeframe.M5) else next(iter(snapshot.frames))
        atr = float(snapshot.tf(entry_tf).atr(14)[-1])
        entry = snapshot.tick.ask if conf.direction is Direction.LONG else snapshot.tick.bid
        levels = build_levels(conf.direction, entry, atr, snapshot.info)

        size = self.risk.position_size(account, snapshot.info, entry, levels.stop_loss)
        plan.entry = round(entry, snapshot.info.digits)
        plan.stop_loss = levels.stop_loss
        plan.take_profits = levels.take_profits
        plan.volume = size.volume
        plan.risk_amount = size.risk_amount
        plan.risk_pct = size.risk_pct
        plan.notes = block + size.notes

        if size.volume <= 0:
            plan.decision = "REJECT"
            plan.notes.append("size resolved to 0")
            return plan, signals

        gate = self.risk.can_open(account, len(self.broker.positions()), size.risk_pct)
        if not gate.allowed:
            plan.decision = "WAIT"
            plan.notes += gate.reasons
            return plan, signals

        plan.decision = "WAIT" if block else "EXECUTE"
        return plan, signals

    def _filter_reasons(self, symbol: str, spread_pips: float, spread_limit: float) -> list[str]:
        reasons: list[str] = []
        if spread_pips > spread_limit:
            reasons.append(f"spread {spread_pips:.1f}p > limit {spread_limit:.1f}p")
        if self.enforce_time_filters:
            now = utcnow()
            if not in_trading_session(now):
                reasons.append("outside London/NY session")
            if is_rollover(now):
                reasons.append("rollover window")
            if news_blackout(symbol, now):
                reasons.append("news blackout")
        return reasons

    # ── Full cycle ────────────────────────────────────────────────────────────────
    def run_once(self, execute: bool = True) -> ScanResult:
        self.risk.roll_periods()
        account = self.broker.account()
        self.risk.update_equity(account)

        # Drawdown kill-switch first.
        action = self.risk.drawdown_action(account)
        if action is DrawdownAction.KILL:
            self._close_all("KILL switch: drawdown >= 10%")

        self._manage_open_positions()

        # Feed freshly-closed trades to the risk manager so the consecutive-loss
        # size reduction (spec: halve size after 3 losses) actually engages.
        self._sync_closed_trades()

        result = ScanResult(timestamp=utcnow(), account=account)
        for symbol in self.settings.symbols:
            try:
                plan, signals = self.analyse(symbol, account)
            except Exception as exc:  # a single bad symbol must not stop the scan
                log.exception("analyse failed for %s: %s", symbol, exc)
                continue
            result.plans.append(plan)
            result.signals[symbol] = signals

            if execute and plan.decision == "EXECUTE" and action is DrawdownAction.NORMAL:
                res = self.executor.open_trade(plan)
                if res.ok:
                    self.risk.commit(plan.risk_pct)
                result.executed.append((symbol, res.message))

        self.last_scan = result
        return result

    def _sync_closed_trades(self) -> None:
        """Register newly-closed trades with the risk manager.

        The broker (paper or live) closes positions on its own when SL/TP is
        touched, so the orchestrator polls the realised-P/L ledger and forwards
        only the new entries. Guarded with ``getattr`` so brokers that do not
        expose a ledger simply skip this step.
        """
        ledger = getattr(self.broker, "realised_pnl", None)
        if ledger is None:
            return
        for pnl in ledger[self._consumed_pnls:]:
            self.risk.register_close(pnl)
        self._consumed_pnls = len(ledger)

    def _manage_open_positions(self) -> None:
        for pos in self.broker.positions():
            try:
                snap = self.data.snapshot(pos.symbol)
                actions = self.executor.manage_position(pos, snap)
                for a in actions:
                    log.info("manage #%d %s: %s", pos.ticket, pos.symbol, a)
            except Exception as exc:  # pragma: no cover - defensive
                log.warning("manage_position failed for %s: %s", pos.symbol, exc)

    def _close_all(self, reason: str) -> None:
        positions = self.broker.positions()
        if positions:
            log.warning("%s - closing %d position(s)", reason, len(positions))
        for pos in positions:
            self.executor.close(pos.ticket)
