"""Recorded payments and manual reviews."""

from dataclasses import dataclass
from datetime import datetime

from mcp_shop.domain.matching import MatchMethod, ReviewReason
from mcp_shop.domain.transfers import IncomingTransfer


class PaymentAlreadyRecorded(Exception):
    """The transfer was already claimed by an earlier receipt."""


@dataclass(frozen=True)
class RecordedPayment:
    transfer: IncomingTransfer
    customer_id: str
    match_method: MatchMethod
    receipt_ref: str
    created_at: datetime
    balance_cents: int
    """Balance right after the payment was credited."""


@dataclass(frozen=True)
class ManualReview:
    review_id: str
    customer_id: str
    receipt_ref: str
    reason: ReviewReason
    extracted: dict[str, object]
    candidates: tuple[IncomingTransfer, ...]
    created_at: datetime
