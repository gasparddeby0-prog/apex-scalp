"""Command-line entrypoint: ``apex <command>``.

Commands
--------
scan        Run a single analysis cycle and print the result (no execution).
run         Run N paper-trading cycles, advancing the simulation each step.
dashboard   Launch the live web dashboard (drives the simulation in paper mode).

Live trading (``APEX_MODE=live``) requires the MetaTrader5 package and a running
terminal on Windows; paper mode is the default everywhere else.
"""

from __future__ import annotations

import argparse
import logging
import time

from apex import __version__
from apex.broker.paper_broker import PaperBroker
from apex.config import TradingMode, load_settings
from apex.engine.orchestrator import Orchestrator, ScanResult
from apex.logging_setup import configure_logging, get_logger
from apex.stats import compute_stats

log = get_logger("apex.cli")


def _format_scan(result: ScanResult) -> str:
    """Render a scan in the spec's output format."""
    ts = result.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [f"[SCAN] Analyse de {len(result.plans)} symboles | {ts}"]
    interesting = [p for p in result.plans if p.score > 0 or p.decision != "REJECT"]
    if not interesting:
        lines.append("  (aucun signal actionnable ce cycle)")
    for p in sorted(interesting, key=lambda x: x.score, reverse=True):
        lines.append(f"[SIGNAL] {p.symbol} {p.direction.value} | Score: {p.score:.1f}/10")
        lines.append(f"  -> Strategies: {{{', '.join(p.strategy_ids) or '-'}}}")
        if p.entry:
            tps = ", ".join(f"{tp:.5f}" for tp in p.take_profits)
            lines.append(f"  -> Entree: {p.entry:.5f} | SL: {p.stop_loss:.5f} | TP: {tps}")
            lines.append(f"  -> Lots: {p.volume:.2f} | Risque: {p.risk_amount:.2f} "
                         f"({p.risk_pct:.2f}%)")
        if p.notes:
            lines.append(f"  -> Notes: {'; '.join(p.notes)}")
        lines.append(f"  -> Decision: {p.decision}")
    for symbol, message in result.executed:
        lines.append(f"[ORDER] {symbol} -> {message}")
    acc = result.account
    lines.append(f"[DASHBOARD] Balance: {acc.balance:.2f} | Equity: {acc.equity:.2f}")
    return "\n".join(lines)


def _build_orchestrator(args) -> Orchestrator:
    settings = load_settings()
    if getattr(args, "symbols", None):
        settings.symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if getattr(args, "mode", None):
        settings.mode = TradingMode(args.mode)
    log.info("Active mode: %s", settings.mode.value.upper())
    orch = Orchestrator(settings)
    try:
        connected = orch.start()
    except RuntimeError as exc:
        # e.g. the MetaTrader5 package is not installed in live mode.
        raise SystemExit(str(exc)) from exc
    if not connected:
        if settings.is_live:
            raise SystemExit(
                "Failed to connect to MetaTrader 5. Make sure the MT5 terminal is "
                "installed, OPEN and logged in, and that MT5_LOGIN / MT5_PASSWORD / "
                "MT5_SERVER / MT5_PATH in your .env are correct."
            )
        raise SystemExit("Failed to connect broker. Check your configuration.")
    return orch


def cmd_scan(args) -> None:
    orch = _build_orchestrator(args)
    try:
        if isinstance(orch.broker, PaperBroker) and args.warmup:
            orch.broker.step(args.warmup)
        result = orch.run_once(execute=not args.dry_run)
        print(_format_scan(result))
    finally:
        orch.stop()


def cmd_run(args) -> None:
    orch = _build_orchestrator(args)
    try:
        for i in range(args.cycles):
            if isinstance(orch.broker, PaperBroker):
                orch.broker.step(args.step_bars)
            result = orch.run_once(execute=True)
            if args.verbose or result.executed:
                print(f"\n--- cycle {i + 1}/{args.cycles} ---")
                print(_format_scan(result))
            if args.delay > 0:
                time.sleep(args.delay)

        pnls = getattr(orch.broker, "realised_pnl", [])
        stats = compute_stats(pnls)
        acc = orch.broker.account()
        print("\n========== RESUME ==========")
        print(f"Cycles            : {args.cycles}")
        print(f"Trades closed     : {stats.trades}")
        print(f"Win rate          : {stats.win_rate:.1f}%")
        pf = "inf" if stats.profit_factor == float("inf") else f"{stats.profit_factor:.2f}"
        print(f"Profit factor     : {pf}")
        print(f"Total realised PnL: {stats.total_pnl:.2f}")
        print(f"Per-trade Sharpe  : {stats.sharpe:.2f}")
        print(f"Max drawdown      : {stats.max_drawdown:.2f}")
        print(f"Final balance     : {acc.balance:.2f} | equity: {acc.equity:.2f}")
    finally:
        orch.stop()


def cmd_dashboard(args) -> None:
    from apex.dashboard import run_dashboard

    orch = _build_orchestrator(args)
    s = orch.settings
    host = args.host or s.dashboard_host
    port = args.port or s.dashboard_port
    if isinstance(orch.broker, PaperBroker) and args.warmup:
        orch.broker.step(args.warmup)
    log.info("Dashboard at http://%s:%d", host, port)
    if host in ("0.0.0.0", "::"):
        log.info("Bound to all interfaces - reachable from other hosts on the network.")
    try:
        run_dashboard(
            orch,
            host=host,
            port=port,
            debug=args.debug,
            step_bars=args.step_bars,
            refresh_ms=args.interval,
            chart_symbol=args.chart_symbol,
        )
    finally:
        orch.stop()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="apex", description="APEX-SCALP multi-strategy bot")
    p.add_argument("--version", action="version", version=f"apex {__version__}")
    p.add_argument("--symbols", help="override symbols, comma-separated")
    p.add_argument("--mode", choices=["paper", "live"], default=None,
                   help="override APEX_MODE (paper or live). Robust against .env issues.")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("scan", help="run a single analysis cycle")
    s.add_argument("--warmup", type=int, default=0, help="advance paper sim N bars first")
    s.add_argument("--dry-run", action="store_true", help="analyse only, never send orders")
    s.set_defaults(func=cmd_scan)

    r = sub.add_parser("run", help="run N paper-trading cycles")
    r.add_argument("--cycles", type=int, default=200)
    r.add_argument("--step-bars", type=int, default=5, help="M1 bars to advance per cycle")
    r.add_argument("--delay", type=float, default=0.0, help="seconds between cycles")
    r.add_argument("--verbose", action="store_true")
    r.set_defaults(func=cmd_run)

    d = sub.add_parser("dashboard", help="launch the web dashboard")
    d.add_argument("--debug", action="store_true")
    d.add_argument("--host", default=None,
                   help="bind address (default from config; use 0.0.0.0 to expose on the network)")
    d.add_argument("--port", type=int, default=None, help="bind port (default from config)")
    d.add_argument("--warmup", type=int, default=0,
                   help="advance paper sim N bars before serving")
    d.add_argument("--step-bars", type=int, default=5,
                   help="M1 bars to advance per refresh (paper mode)")
    d.add_argument("--interval", type=int, default=1000,
                   help="dashboard refresh interval in milliseconds")
    d.add_argument("--chart-symbol", default=None,
                   help="symbol shown in the candlestick chart (default: first configured)")
    d.set_defaults(func=cmd_dashboard)
    return p


def main(argv: list[str] | None = None) -> None:
    configure_logging(logging.INFO)
    args = build_parser().parse_args(argv)
    settings = load_settings()
    mode = TradingMode(args.mode) if getattr(args, "mode", None) else settings.mode
    if mode is TradingMode.LIVE:
        log.warning("LIVE MODE ENABLED - real orders may be sent to MT5.")
    args.func(args)


if __name__ == "__main__":
    main()
