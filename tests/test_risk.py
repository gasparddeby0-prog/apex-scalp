from apex.models import AccountInfo, SymbolInfo
from apex.risk import DrawdownAction, RiskManager


def _acc(balance=10_000.0, equity=None):
    equity = balance if equity is None else equity
    return AccountInfo(balance=balance, equity=equity, margin=0.0, free_margin=equity)


def test_position_size_respects_risk_fraction(settings):
    rm = RiskManager(settings)
    info = SymbolInfo(name="EURUSD", digits=5, point=1e-5, pip=1e-4, contract_size=100_000)
    acc = _acc()
    # 0.5% of 10_000 = 50 risk; stop 20 pips = 0.0020 price; loss/lot = 0.0020*100000 = 200.
    # volume ~ 50/200 = 0.25 lots.
    res = rm.position_size(acc, info, entry=1.1000, stop=1.0980)
    assert abs(res.volume - 0.25) < 1e-9
    assert res.risk_pct <= settings.risk_per_trade_pct + 1e-6


def test_position_size_zero_when_stop_invalid(settings):
    rm = RiskManager(settings)
    info = SymbolInfo(name="EURUSD", digits=5, point=1e-5, pip=1e-4, contract_size=100_000)
    res = rm.position_size(_acc(), info, entry=1.1, stop=1.1)
    assert res.volume == 0.0


def test_drawdown_ladder(settings):
    rm = RiskManager(settings)
    rm.peak_equity = 10_000.0
    assert rm.drawdown_action(_acc(equity=9_600.0)) is DrawdownAction.NORMAL  # 4%
    assert rm.drawdown_action(_acc(equity=9_490.0)) is DrawdownAction.REDUCE  # 5.1%
    assert rm.drawdown_action(_acc(equity=9_150.0)) is DrawdownAction.HALT  # 8.5%
    assert rm.drawdown_action(_acc(equity=8_900.0)) is DrawdownAction.KILL  # 11%


def test_size_multiplier_after_losses(settings):
    rm = RiskManager(settings)
    rm.peak_equity = 10_000.0
    acc = _acc()
    assert rm.size_multiplier(acc) == 1.0
    rm.register_close(-10)
    rm.register_close(-10)
    rm.register_close(-10)
    assert rm.size_multiplier(acc) == 0.5
    rm.register_close(+5)
    assert rm.size_multiplier(acc) == 1.0


def test_daily_cap_blocks(settings):
    rm = RiskManager(settings)
    rm.roll_periods()
    acc = _acc()
    # Commit risk up to the daily cap.
    rm.commit(settings.max_daily_risk_pct)
    decision = rm.can_open(acc, open_positions=0, plan_risk_pct=0.5)
    assert not decision.allowed
    assert any("daily risk" in r for r in decision.reasons)


def test_max_positions_blocks(settings):
    rm = RiskManager(settings)
    rm.roll_periods()
    decision = rm.can_open(_acc(), open_positions=settings.max_open_positions, plan_risk_pct=0.1)
    assert not decision.allowed
