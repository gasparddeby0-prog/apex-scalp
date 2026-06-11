"""Strategy base class, category enum and a simple registry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum

from apex.data import MarketSnapshot, TimeframeView
from apex.models import Direction, Signal, Timeframe


class Category(StrEnum):
    PRICE_ACTION = "A"  # price action
    INDICATOR = "B"  # technical indicators
    LEVEL = "C"  # levels & zones
    VOLUME = "D"  # volume & orderflow
    ADVANCED = "E"  # advanced / multi-timeframe


class Strategy(ABC):
    """Base class for all signal generators.

    Subclasses set the class attributes and implement :meth:`evaluate`.
    """

    id: str = "X0"
    name: str = "unnamed"
    category: Category = Category.INDICATOR
    weight: float = 1.0
    timeframe: Timeframe = Timeframe.M5
    min_bars: int = 50

    def evaluate(self, snapshot: MarketSnapshot) -> Signal:
        """Return a :class:`Signal`; never raises on insufficient data."""
        if not snapshot.has(self.timeframe):
            return self.flat("no data")
        view = snapshot.tf(self.timeframe)
        if len(view) < self.min_bars:
            return self.flat("warming up")
        try:
            return self._evaluate(snapshot, view)
        except Exception as exc:  # defensive: a broken strategy must not halt the scan
            return self.flat(f"error: {exc}")

    @abstractmethod
    def _evaluate(self, snapshot: MarketSnapshot, view: TimeframeView) -> Signal:
        ...

    # Helpers -------------------------------------------------------------------
    def flat(self, reason: str = "") -> Signal:
        return Signal(strategy_id=self.id, direction=Direction.NONE, score=0.0, reason=reason)

    def signal(self, direction: Direction, score: float, reason: str = "") -> Signal:
        return Signal(
            strategy_id=self.id,
            direction=direction,
            score=max(0.0, min(10.0, score)),
            reason=reason,
        )


class StrategyRegistry:
    """Maps strategy id -> Strategy class for discovery / extension."""

    def __init__(self) -> None:
        self._classes: dict[str, type[Strategy]] = {}

    def register(self, cls: type[Strategy]) -> type[Strategy]:
        self._classes[cls.id] = cls
        return cls

    def get(self, strategy_id: str) -> type[Strategy] | None:
        return self._classes.get(strategy_id)

    def all(self) -> dict[str, type[Strategy]]:
        return dict(self._classes)


registry = StrategyRegistry()
