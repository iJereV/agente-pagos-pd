"""TransferVerifier backed by Mercado Pago's payment search.

Facts from an empirical spike on the shop account:
- Bank transfers into the CVU: `operation_type=account_fund`, `payment_method_id=cvu`.
- Wallet-to-wallet transfers: `operation_type=money_transfer`.
- Loan disbursements also show up as `account_fund` with `payment_method_id=consumer_credits`.
- The search also returns payments the account made, so `collector_id` must be the shop.
- `transaction_details.transaction_id` is the COELSA id (bank) or a UUID (wallet).
"""

from datetime import UTC, datetime
from typing import Any

import httpx

from mcp_shop.domain.money import decimal_to_cents
from mcp_shop.domain.receipts import normalize_cuit
from mcp_shop.domain.transfers import IncomingTransfer

SEARCH_URL = "https://api.mercadopago.com/v1/payments/search"
PAGE_SIZE = 100
MAX_PAGES = 10
PROVIDER = "mercadopago"


class MercadoPagoTransferVerifier:
    def __init__(self, http: httpx.AsyncClient, access_token: str, collector_id: str) -> None:
        self._http = http
        self._headers = {"Authorization": f"Bearer {access_token}"}
        self._collector_id = str(collector_id)

    async def incoming_transfers(self, since: datetime, until: datetime) -> list[IncomingTransfer]:
        transfers: list[IncomingTransfer] = []
        for page in range(MAX_PAGES):
            results, total = await self._search_page(since, until, offset=page * PAGE_SIZE)
            transfers.extend(
                t for p in results if (t := to_incoming_transfer(p, self._collector_id))
            )
            if (page + 1) * PAGE_SIZE >= total or not results:
                break
        return transfers

    async def _search_page(
        self, since: datetime, until: datetime, *, offset: int
    ) -> tuple[list[dict[str, Any]], int]:
        response = await self._http.get(
            SEARCH_URL,
            headers=self._headers,
            params={
                "sort": "date_created",
                "criteria": "desc",
                "range": "date_created",
                "begin_date": _iso(since),
                "end_date": _iso(until),
                "collector.id": self._collector_id,
                "limit": PAGE_SIZE,
                "offset": offset,
            },
        )
        response.raise_for_status()
        body = response.json()
        return body.get("results", []), int(body.get("paging", {}).get("total", 0))


def to_incoming_transfer(payment: dict[str, Any], collector_id: str) -> IncomingTransfer | None:
    """Map one search result to an incoming transfer, or `None` if it is not one."""
    if not _is_incoming_transfer(payment, collector_id):
        return None
    details = payment.get("transaction_details") or {}
    interaction = (payment.get("point_of_interaction") or {}).get("transaction_data") or {}
    identification = (payment.get("payer") or {}).get("identification") or {}
    return IncomingTransfer(
        provider=PROVIDER,
        provider_payment_id=str(payment["id"]),
        e2e_id=details.get("transaction_id") or interaction.get("e2e_id"),
        amount_cents=decimal_to_cents(payment["transaction_amount"]),
        received_at=datetime.fromisoformat(payment["date_created"]).astimezone(UTC),
        payer_cuit=normalize_cuit(identification.get("number")),
    )


def _is_incoming_transfer(payment: dict[str, Any], collector_id: str) -> bool:
    if str(payment.get("collector_id")) != collector_id or payment.get("status") != "approved":
        return False
    operation = payment.get("operation_type")
    method = payment.get("payment_method_id")
    if method == "consumer_credits":
        return False
    return (operation == "account_fund" and method == "cvu") or operation == "money_transfer"


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
