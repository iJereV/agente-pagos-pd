"""Use case: prove a payment from the caller's last receipt and credit it."""

import hashlib
import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from mcp_shop.application.access import linked_customer
from mcp_shop.application.ids import utc_now
from mcp_shop.application.outcomes import Credited, Rejected
from mcp_shop.domain.identity import Caller
from mcp_shop.domain.ledger import Ledger
from mcp_shop.domain.matching import Matched, NeedsReview, NotFound, match_receipt
from mcp_shop.domain.payments import ManualReview, PaymentAlreadyRecorded, RecordedPayment
from mcp_shop.domain.receipts import RawReceipt, parse_receipt
from mcp_shop.ports.receipts import (
    ExtractionUnavailable,
    ReceiptExtractor,
    ReceiptNotFound,
    ReceiptStore,
)
from mcp_shop.ports.repository import ShopRepository
from mcp_shop.ports.transfers import TransferVerifier

logger = logging.getLogger(__name__)

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
    welcome_credit_cents: int
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

        try:
            raw = await self.extractor.extract(receipt_file)
        except ExtractionUnavailable:
            logger.warning("receipt extraction unavailable", exc_info=True)
            return Rejected(status="temporarily_unavailable")
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
        # Set by the last (committed) run of `apply`; a retried transaction runs it again.
        welcome_granted = 0

        def apply(ledger: Ledger) -> RecordedPayment:
            nonlocal welcome_granted
            ledger.grant_welcome_credit(self.welcome_credit_cents, now)
            welcome_granted = ledger.welcome_credit_granted_now_cents
            # The credited amount is always the provider's, never the receipt's.
            ledger.credit_payment(transfer.payment_key, transfer.amount_cents, now)
            return RecordedPayment(
                transfer=transfer,
                customer_id=customer_id,
                match_method=matched.method,
                receipt_ref=receipt_ref,
                created_at=now,
                balance_cents=ledger.balance_cents,
            )

        try:
            payment = await self.repository.record_payment(customer_id, transfer.payment_key, apply)
        except PaymentAlreadyRecorded:
            return Rejected(status="already_used")
        return Credited(
            amount_cents=transfer.amount_cents,
            balance_cents=payment.balance_cents,
            welcome_credit_cents=welcome_granted,
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
