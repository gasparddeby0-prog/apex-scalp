from apex.engine.orchestrator import Orchestrator
from apex.engine.scoring import ScoringEngine
from apex.models import Direction, Signal
from apex.strategies import default_strategies


def test_scoring_passes_with_full_confluence():
    engine = ScoringEngine(default_strategies(), entry_score=7.0, min_aligned=3)
    signals = [
        Signal("A1", Direction.LONG, 8.0),  # price action
        Signal("B1", Direction.LONG, 7.5),  # indicator
        Signal("C1", Direction.LONG, 7.0),  # level
        Signal("D1", Direction.SHORT, 6.0),  # opposing volume signal
    ]
    conf = engine.evaluate(signals)
    assert conf.direction is Direction.LONG
    assert conf.passed
    assert conf.score >= 7.0


def test_scoring_fails_without_price_action():
    engine = ScoringEngine(default_strategies(), entry_score=7.0, min_aligned=3)
    signals = [
        Signal("B1", Direction.LONG, 8.0),
        Signal("B2", Direction.LONG, 8.0),
        Signal("D1", Direction.LONG, 8.0),
    ]
    conf = engine.evaluate(signals)
    assert not conf.passed
    assert any("category A" in r for r in conf.reasons)


def test_scoring_fails_below_min_aligned():
    engine = ScoringEngine(default_strategies(), entry_score=7.0, min_aligned=3)
    signals = [
        Signal("A1", Direction.LONG, 9.0),
        Signal("B1", Direction.LONG, 9.0),
    ]
    conf = engine.evaluate(signals)
    assert not conf.passed
    assert any("aligned" in r for r in conf.reasons)


def test_orchestrator_runs_paper_cycles_without_error(settings):
    orch = Orchestrator(settings, enforce_time_filters=False)
    assert orch.start()
    try:
        for _ in range(30):
            orch.broker.step(5)
            result = orch.run_once(execute=True)
            assert result.account is not None
            assert len(result.plans) == len(settings.symbols)
            for plan in result.plans:
                assert plan.decision in {"EXECUTE", "WAIT", "REJECT"}
                # Any plan that reached execution must have a protective stop.
                if plan.decision == "EXECUTE":
                    assert plan.stop_loss > 0 and plan.volume > 0
        acc = orch.broker.account()
        assert isinstance(acc.balance, float)
    finally:
        orch.stop()


def test_orchestrator_spread_filter_blocks_when_spread_wide(settings):
    # Force a tiny spread limit so every symbol is blocked by the spread filter.
    import dataclasses

    orch = Orchestrator(settings, enforce_time_filters=False)
    orch.start()
    try:
        orch.broker.step(20)
        acc = orch.broker.account()
        # Wrap symbol_info to advertise an impossible spread limit (info is frozen).
        original = orch.broker.symbol_info

        def tight(symbol):
            return dataclasses.replace(original(symbol), spread_limit_pips=0.0)

        orch.broker.symbol_info = tight  # type: ignore[assignment]
        plan, _ = orch.analyse(settings.symbols[0], acc)
        # Even a strong signal cannot EXECUTE when the spread filter trips.
        assert plan.decision in {"WAIT", "REJECT"}
    finally:
        orch.stop()
