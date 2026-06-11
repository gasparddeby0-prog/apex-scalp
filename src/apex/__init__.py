"""APEX-SCALP: a layered, multi-strategy MT5 scalping bot.

The package is intentionally broker-agnostic: the same engine drives a
:class:`~apex.broker.paper_broker.PaperBroker` (simulation, any OS) and a
:class:`~apex.broker.mt5_broker.MT5Broker` (real terminal, Windows only).
Paper trading is the default mode.
"""

__version__ = "0.1.0"
