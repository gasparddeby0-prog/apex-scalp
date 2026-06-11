# APEX-SCALP

A layered, multi-strategy scalping bot for MetaTrader 5, built around a
**broker abstraction** so the exact same engine runs against:

- a built-in **paper / simulation broker** (any OS, no terminal needed) — the default, and
- a real **MetaTrader 5 terminal** (`MetaTrader5` package, Windows only) for live/demo trading.

> **Paper trading is the default.** Going live is a deliberate switch
> (`APEX_MODE=live`) that requires MT5 credentials and a running terminal.
> Nothing here is financial advice, and no strategy is guaranteed to be profitable.
> Validate with a backtest and a forward test on a demo account first.

## Architecture

```
src/apex/
├── config.py            # pydantic-settings, .env, paper/live mode
├── models.py            # Candle/Tick/Signal/Position/Order domain types
├── indicators.py        # pure-NumPy EMA, RSI, ATR, MACD, Bollinger, Stoch, ADX...
├── broker/
│   ├── base.py          # Broker interface (the only thing the engine talks to)
│   ├── paper_broker.py  # deterministic simulation (synthetic price engine)
│   └── mt5_broker.py    # real MetaTrader5 adapter (import-guarded)
├── data.py              # MarketSnapshot: multi-timeframe candles + cached indicators
├── strategies/          # A (price action), B (indicators), C (levels), D (volume)
├── engine/
│   ├── scoring.py       # weighted score + confluence rules
│   └── orchestrator.py  # the scan/manage/execute cycle
├── risk.py              # lot sizing, daily/weekly caps, drawdown kill-switch
├── execution.py         # ATR SL/TP ladder, order submission, break-even/trailing
├── filters.py           # spread / session / rollover / news gating
├── stats.py             # win rate, profit factor, Sharpe, drawdown
├── dashboard/app.py     # Dash + Plotly live dashboard
└── cli.py               # `apex scan | run | dashboard`
```

The decision flow per symbol:

```
MarketSnapshot → [strategies] → signals → ScoringEngine (confluence)
              → RiskManager (sizing + caps) → Executor (SL/TP order)
```

## Quick start

```bash
# 1. Create the environment (Python 3.11)
uv venv --python 3.11
uv pip install -e ".[dev]"

# 2. Configure (optional — sensible defaults work for paper mode)
cp .env.example .env

# 3. Run a single analysis cycle (paper, no orders)
uv run apex scan --warmup 200 --dry-run

# 4. Run a paper-trading simulation for 300 cycles
uv run apex run --cycles 300 --step-bars 5

# 5. Launch the live dashboard (drives the simulation in paper mode)
uv run apex dashboard       # http://127.0.0.1:8050
```

## Configuration

All settings come from environment variables / `.env` (see `.env.example`).
Key ones:

| Variable | Default | Meaning |
|---|---|---|
| `APEX_MODE` | `paper` | `paper` or `live` |
| `APEX_SYMBOLS` | majors + XAU + NAS100 | symbols to scan |
| `APEX_RISK_PER_TRADE_PCT` | `0.5` | risk per trade (% of balance) |
| `APEX_MAX_DAILY_RISK_PCT` | `2.0` | daily committed-risk cap |
| `APEX_MAX_WEEKLY_RISK_PCT` | `5.0` | weekly committed-risk cap |
| `APEX_MAX_OPEN_POSITIONS` | `3` | simultaneous positions |
| `APEX_ENTRY_SCORE` | `7.0` | confluence score needed to enter |
| `APEX_MIN_ALIGNED` | `3` | min strategies pointing the same way |
| `MT5_LOGIN/PASSWORD/SERVER/PATH` | — | live connection (Windows) |

## Risk controls (enforced)

- Fixed-fractional sizing; **every** order carries a stop loss (orders without one are rejected).
- Daily (2%) and weekly (5%) committed-risk caps.
- Drawdown ladder from the equity high-water mark: **5%** halve size, **8%** stop new trades, **10%** kill-switch (close everything).
- Size halved after 3 consecutive losses.
- Spread / session / rollover filters (session+news filters enforced in live mode).

## Going live (Windows)

1. Install the broker package: `pip install -e ".[mt5]"`.
2. Set `APEX_MODE=live` and the `MT5_*` variables in `.env`.
3. Make sure the MT5 terminal is running and logged in.
4. Start with a **demo** account and a tiny risk percentage.

## Tests

```bash
uv run pytest
```

## Status & scope

This release implements the full pipeline end-to-end with a representative set of
6 strategies (A1, A3, B1, B2, C1, D1) spanning all four core categories. The
registry pattern in `strategies/` makes adding the remaining strategies from the
spec a small, isolated change. The economic-calendar / news blackout is a stub
(`filters.news_blackout`) and must be wired to a real data feed before relying on
the news rule live.
