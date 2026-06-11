"""Abstract broker interface shared by the paper and MT5 implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod

from apex.models import (
    AccountInfo,
    Candles,
    OrderRequest,
    OrderResult,
    Position,
    SymbolInfo,
    Tick,
    Timeframe,
)


class Broker(ABC):
    """Everything the engine needs from a trading backend."""

    # ── Lifecycle ────────────────────────────────────────────────────────────
    @abstractmethod
    def connect(self) -> bool:
        """Establish the connection. Returns ``True`` on success."""

    @abstractmethod
    def shutdown(self) -> None:
        """Tear down the connection / release resources."""

    @abstractmethod
    def is_connected(self) -> bool:
        ...

    # ── Account & instruments ─────────────────────────────────────────────────
    @abstractmethod
    def account(self) -> AccountInfo:
        ...

    @abstractmethod
    def symbols(self) -> list[str]:
        """Return the list of available symbol names."""

    @abstractmethod
    def symbol_info(self, symbol: str) -> SymbolInfo:
        ...

    # ── Market data ───────────────────────────────────────────────────────────
    @abstractmethod
    def tick(self, symbol: str) -> Tick:
        ...

    @abstractmethod
    def candles(self, symbol: str, timeframe: Timeframe, count: int) -> Candles:
        """Return the most recent ``count`` candles (oldest first)."""

    # ── Trading ───────────────────────────────────────────────────────────────
    @abstractmethod
    def positions(self) -> list[Position]:
        ...

    @abstractmethod
    def send_order(self, request: OrderRequest) -> OrderResult:
        ...

    @abstractmethod
    def modify_position(
        self, ticket: int, stop_loss: float | None = None, take_profit: float | None = None
    ) -> OrderResult:
        ...

    @abstractmethod
    def close_position(self, ticket: int, volume: float | None = None) -> OrderResult:
        """Close a position fully, or partially if ``volume`` is given."""
