"""Use case: prove a payment from the caller's last receipt and credit it."""

import hashlib
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from mcp_shop.application.access import linked_customer
from mcp_shop.application.ids import utc_now
from mcp_shop.application.outcomes import AllocatedAmount, Credited, Rejected
from mcp_shop.domain.identity import Caller
from mcp_shop.domain.ledger import Ledger
from mcp_shop.domain.matching import Matched, NeedsReview, NotFound, match_receipt
from mcp_shop.domain.payments import ManualReview, PaymentAlreadyRecorded, RecordedPayment
from mcp_shop.domain.receipts import RawReceipt, parse_receipt
from mcp_shop.ports.receipts import ReceiptExtractor, ReceiptNotFound, ReceiptStore
from mcp_shop.ports.repository import ShopRepository
from mcp_shop.ports.transfers import TransferVerifier

RECEIPTS_PREFIX = "receipts/"
SEARCH_LOOKBACK = timedelta(days=2)
"""How far before the receipt time (or now) the provider is searched."""


@dataclass(frozen=True)
class VerifyReceipt:
    repository: ShopRepository
    receipts: ReceiptStore
    extractor: ReceiptExtractor
    transfers: TransferVerifier
    match_window: timedelta
    clock: Callable[[], datetime] = utc_now

    async def __call__(self, caller: Caller) -> Credited | Rejected:
        customer_id = linked_customer(caller)
        if isinstance(customer_id, Rejected):
            return customer_id
        receipt_ref = caller.last_receipt_ref
        if not receipt_ref or not receipt_ref.startswith(RECEIPTS_PREFIX):
            return Rejected(status="no_receipt")
        try:
            receipt_file = await self.receipts.read(receipt_ref)
        except ReceiptNotFound:
            return Rejected(status="no_receipt")

        raw = await self.extractor.extract(receipt_file)
        if not raw.is_receipt:
            return Rejected(status="not_a_receipt")
        parsed = parse_receipt(raw)

        now = self.clock()
        candidates = await self.transfers.incoming_transfers(
            since=(parsed.sent_at or now) - SEARCH_LOOKBACK, until=now
        )
        match match_receipt(parsed, candidates, self.match_window):
            case Matched() as matched:
                return await self._record(customer_id, receipt_ref, matched, now)
            case NeedsReview() as review:
                await self._send_to_review(customer_id, receipt_ref, raw, review, now)
                return Rejected(status="manual_review")
            case NotFound():
                return Rejected(status="not_found_yet")

    async def _record(
        self, customer_id: str, receipt_ref: str, matched: Matched, now: datetime
    ) -> Credited | Rejected:
        transfer = matched.transfer

        def apply(ledger: Ledger) -> RecordedPayment:
            # The credited amount is always the provider's, never the receipt's.
            result = ledger.apply_payment(transfer.amount_cents)
            return RecordedPayment(
                transfer=transfer,
                customer_id=customer_id,
                match_method=matched.method,
                allocations=result.allocations,
                receipt_ref=receipt_ref,
                created_at=now,
                credit_balance_cents=ledger.credit_balance_cents,
                debt_cents=ledger.debt_cents,
            )

        try:
            payment = await self.repository.record_payment(customer_id, transfer.payment_key, apply)
        except PaymentAlreadyRecorded:
            return Rejected(status="already_used")
        return Credited(
            amount_cents=transfer.amount_cents,
            allocations=[
                AllocatedAmount(order_id=a.order_id, amount_cents=a.amount_cents)
                for a in payment.allocations
            ],
            credit_balance_cents=payment.credit_balance_cents,
            debt_cents=payment.debt_cents,
        )

    async def _send_to_review(
        self,
        customer_id: str,
        receipt_ref: str,
        raw: RawReceipt,
        review: NeedsReview,
        now: datetime,
    ) -> None:
        await self.repository.save_manual_review(
            ManualReview(
                # One review per receipt: asking again does not pile up duplicates.
                review_id=hashlib.sha256(receipt_ref.encode()).hexdigest()[:32],
                customer_id=customer_id,
                receipt_ref=receipt_ref,
                reason=review.reason,
                extracted=asdict(raw),
                candidates=review.candidates,
                created_at=now,
            )
        )
