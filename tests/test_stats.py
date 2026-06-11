from apex.stats import compute_stats


def test_empty():
    s = compute_stats([])
    assert s.trades == 0
    assert s.total_pnl == 0.0


def test_basic_metrics():
    pnls = [100.0, -50.0, 200.0, -100.0, 50.0]
    s = compute_stats(pnls)
    assert s.trades == 5
    assert s.wins == 3
    assert s.losses == 2
    assert abs(s.win_rate - 60.0) < 1e-9
    assert abs(s.gross_profit - 350.0) < 1e-9
    assert abs(s.gross_loss - 150.0) < 1e-9
    assert abs(s.profit_factor - (350.0 / 150.0)) < 1e-9
    assert abs(s.total_pnl - 200.0) < 1e-9


def test_max_drawdown_and_streaks():
    pnls = [100.0, 100.0, -300.0, 50.0, 50.0]
    s = compute_stats(pnls)
    # Equity peaks at 200, drops to -100 -> drawdown 300.
    assert abs(s.max_drawdown - 300.0) < 1e-9
    assert s.best_streak == 2
    assert s.worst_streak == 1
