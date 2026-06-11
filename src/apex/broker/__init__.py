"""Broker abstraction layer.

The engine only ever talks to the :class:`~apex.broker.base.Broker` interface.
Two implementations are provided:

* :class:`~apex.broker.paper_broker.PaperBroker` - a self-contained simulation
  that runs on any OS (used for development, tests, and paper trading).
* :class:`~apex.broker.mt5_broker.MT5Broker` - a thin wrapper over the real
  ``MetaTrader5`` package (Windows only, requires a running terminal).
"""

from apex.broker.base import Broker
from apex.broker.paper_broker import PaperBroker

__all__ = ["Broker", "PaperBroker", "build_broker"]


def build_broker(settings) -> Broker:  # type: ignore[no-untyped-def]
    """Factory: return the broker that matches the configured trading mode.

    Importing :class:`MT5Broker` is deferred so the ``MetaTrader5`` package is
    only required when actually running live.
    """
    from apex.config import TradingMode

    if settings.mode is TradingMode.LIVE:
        from apex.broker.mt5_broker import MT5Broker

        return MT5Broker(settings)
    return PaperBroker(settings)
