"""Trade statistics derived from a sequence of realised P/L values."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class TradeStats:
    trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    expectancy: float = 0.0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    sharpe: float = 0.0
    best_streak: int = 0
    worst_streak: int = 0


def compute_stats(pnls: list[float]) -> TradeStats:
    """Aggregate per-trade P/L into a :class:`TradeStats` summary.

    ``sharpe`` is a simple per-trade Sharpe ratio (mean/stdev of trade returns),
    not annualised - useful as a relative quality signal across runs.
    """
    s = TradeStats()
    if not pnls:
        return s

    s.trades = len(pnls)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    s.wins = len(wins)
    s.losses = len(losses)
    s.win_rate = s.wins / s.trades * 100.0
    s.gross_profit = sum(wins)
    s.gross_loss = abs(sum(losses))
    s.profit_factor = (s.gross_profit / s.gross_loss) if s.gross_loss > 0 else float("inf")
    s.avg_win = (s.gross_profit / s.wins) if s.wins else 0.0
    s.avg_loss = (s.gross_loss / s.losses) if s.losses else 0.0
    s.total_pnl = sum(pnls)
    s.expectancy = s.total_pnl / s.trades

    # Equity-curve max drawdown.
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        equity += p
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    s.max_drawdown = max_dd

    # Per-trade Sharpe.
    mean = s.total_pnl / s.trades
    var = sum((p - mean) ** 2 for p in pnls) / s.trades
    std = math.sqrt(var)
    s.sharpe = (mean / std) if std > 0 else 0.0

    # Win/loss streaks.
    cur = 0
    best = worst = 0
    for p in pnls:
        if p > 0:
            cur = cur + 1 if cur > 0 else 1
        elif p < 0:
            cur = cur - 1 if cur < 0 else -1
        else:
            cur = 0
        best = max(best, cur)
        worst = min(worst, cur)
    s.best_streak = best
    s.worst_streak = abs(worst)
    return s
