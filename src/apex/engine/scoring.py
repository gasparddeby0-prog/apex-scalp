"""Signal scoring and confluence rules.

Combines the individual strategy signals for a symbol into a single weighted
verdict, then applies the confluence gate from the spec:

* a weighted score >= the configured entry threshold,
* at least ``min_aligned`` strategies pointing the same way,
* at least one category-A (price-action) strategy,
* at least one category-B (indicator) or category-C (level) strategy.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from apex.models import Direction, Signal
from apex.strategies.base import Category, Strategy


@dataclass
class Confluence:
    """Outcome of combining all strategy signals for one symbol."""

    direction: Direction
    score: float
    aligned: list[Signal] = field(default_factory=list)
    passed: bool = False
    reasons: list[str] = field(default_factory=list)
    categories: set[str] = field(default_factory=set)

    @property
    def strategy_ids(self) -> list[str]:
        return [s.strategy_id for s in self.aligned]


class ScoringEngine:
    """Turns a list of :class:`Signal` into a :class:`Confluence` verdict."""

    def __init__(
        self,
        strategies: list[Strategy],
        entry_score: float = 7.0,
        min_aligned: int = 3,
    ):
        self.entry_score = entry_score
        self.min_aligned = min_aligned
        self._meta: dict[str, tuple[Category, float]] = {
            s.id: (s.category, s.weight) for s in strategies
        }

    def evaluate(self, signals: list[Signal]) -> Confluence:
        actionable = [s for s in signals if s.is_actionable]
        if not actionable:
            return Confluence(Direction.NONE, 0.0, reasons=["no actionable signals"])

        long_side = [s for s in actionable if s.direction is Direction.LONG]
        short_side = [s for s in actionable if s.direction is Direction.SHORT]

        long_score = self._weighted(long_side)
        short_score = self._weighted(short_side)

        # Choose the dominant side by weighted score, then by support count.
        if (long_score, len(long_side)) >= (short_score, len(short_side)):
            direction, aligned, score = Direction.LONG, long_side, long_score
        else:
            direction, aligned, score = Direction.SHORT, short_side, short_score

        categories = {self._meta.get(s.strategy_id, (Category.INDICATOR, 0))[0].value
                      for s in aligned}

        reasons: list[str] = []
        if score < self.entry_score:
            reasons.append(f"score {score:.1f} < {self.entry_score:.1f}")
        if len(aligned) < self.min_aligned:
            reasons.append(f"only {len(aligned)} aligned (<{self.min_aligned})")
        if Category.PRICE_ACTION.value not in categories:
            reasons.append("missing category A (price action)")
        if not ({Category.INDICATOR.value, Category.LEVEL.value} & categories):
            reasons.append("missing category B or C")

        passed = not reasons
        return Confluence(
            direction=direction if passed or score >= self.entry_score else direction,
            score=round(score, 2),
            aligned=sorted(aligned, key=lambda s: s.score, reverse=True),
            passed=passed,
            reasons=reasons,
            categories=categories,
        )

    def _weighted(self, signals: list[Signal]) -> float:
        if not signals:
            return 0.0
        num = 0.0
        den = 0.0
        for s in signals:
            _, weight = self._meta.get(s.strategy_id, (Category.INDICATOR, 1.0))
            num += s.score * weight
            den += weight
        return num / den if den > 0 else 0.0
