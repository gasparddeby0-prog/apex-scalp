"""Strategy library.

Each strategy is a small, self-contained unit that inspects a
:class:`~apex.data.MarketSnapshot` and returns a :class:`~apex.models.Signal`
with a direction and a 0..10 conviction score. The scoring engine combines
them; strategies never place orders themselves.

This initial release ships a representative subset spanning all four
categories from the spec (A price-action, B indicators, C levels, D volume).
The registry pattern makes adding the remaining strategies a one-liner.
"""

from apex.strategies.base import Category, Strategy, StrategyRegistry, registry
from apex.strategies.levels import SupportResistance
from apex.strategies.price_action import EngulfingPattern, PinBarReversal
from apex.strategies.technical import EmaCross, RsiDivergence
from apex.strategies.volume import VolumeSpike


def default_strategies() -> list[Strategy]:
    """Instantiate the built-in strategy set (order is irrelevant)."""
    return [
        PinBarReversal(),
        EngulfingPattern(),
        EmaCross(),
        RsiDivergence(),
        SupportResistance(),
        VolumeSpike(),
    ]


__all__ = [
    "Category",
    "Strategy",
    "StrategyRegistry",
    "registry",
    "default_strategies",
    "PinBarReversal",
    "EngulfingPattern",
    "EmaCross",
    "RsiDivergence",
    "SupportResistance",
    "VolumeSpike",
]
