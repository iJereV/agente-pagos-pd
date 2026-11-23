"""In-memory TransferVerifier for local runs and evals. No provider needed."""

import json
from datetime import datetime
from importlib import resources
from pathlib import Path

from mcp_shop.domain.transfers import IncomingTransfer

PROVIDER = "simulated"


class SimulatedTransferVerifier:
    def __init__(self, transfers: list[IncomingTransfer] | None = None) -> None:
        self._transfers = list(transfers or [])

    def add(self, transfer: IncomingTransfer) -> None:
        self._transfers.append(transfer)

    async def incoming_transfers(self, since: datetime, until: datetime) -> list[IncomingTransfer]:
        return [t for t in self._transfers if since <= t.received_at <= until]

    @classmethod
    def from_fixture(cls, path: Path | None = None) -> "SimulatedTransferVerifier":
        """Load transfers from JSON; defaults to the bundled synthetic fixture."""
        text = (
            path.read_text(encoding="utf-8")
            if path
            else resources.files(__package__)
            .joinpath("fixtures/simulated_transfers.json")
            .read_text(encoding="utf-8")
        )
        return cls([_from_json(item) for item in json.loads(text)])


def _from_json(item: dict[str, object]) -> IncomingTransfer:
    return IncomingTransfer(
        provider=PROVIDER,
        provider_payment_id=str(item["provider_payment_id"]),
        e2e_id=str(item["e2e_id"]) if item.get("e2e_id") else None,
        amount_cents=int(str(item["amount_cents"])),
        received_at=datetime.fromisoformat(str(item["received_at"])),
        payer_cuit=str(item["payer_cuit"]) if item.get("payer_cuit") else None,
    )
