"""Incoming transfers as reported by the payment provider (the source of truth)."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class IncomingTransfer:
    provider: str
    provider_payment_id: str
    e2e_id: str | None
    """COELSA id for bank transfers, provider UUID for wallet-to-wallet transfers."""
    amount_cents: int
    received_at: datetime
    payer_cuit: str | None

    @property
    def payment_key(self) -> str:
        """Document id under `payments/`. One receipt can never claim a transfer twice."""
        return self.e2e_id or f"{self.provider}-{self.provider_payment_id}"

    def summary(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "provider_payment_id": self.provider_payment_id,
            "e2e_id": self.e2e_id,
            "amount_cents": self.amount_cents,
            "received_at": self.received_at.isoformat(),
            "payer_cuit": self.payer_cuit,
        }
