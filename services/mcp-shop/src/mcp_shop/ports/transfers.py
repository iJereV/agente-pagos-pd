"""Port to the payment provider that received the transfers."""

from datetime import datetime
from typing import Protocol

from mcp_shop.domain.transfers import IncomingTransfer


class TransferVerifier(Protocol):
    async def incoming_transfers(self, since: datetime, until: datetime) -> list[IncomingTransfer]:
        """Transfers received by the shop account between two UTC instants."""
        ...
