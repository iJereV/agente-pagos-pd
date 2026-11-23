"""Receipt-to-transfer matching. Exact rules only: near misses go to a human."""

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum

from mcp_shop.domain.receipts import ParsedReceipt, normalize_id
from mcp_shop.domain.transfers import IncomingTransfer


class MatchMethod(StrEnum):
    COELSA_ID = "coelsa_id"
    AMOUNT_CUIT_WINDOW = "amount_cuit_window"


class ReviewReason(StrEnum):
    AMOUNT_MISMATCH = "amount_mismatch"
    COELSA_MISMATCH = "coelsa_mismatch"
    NEAR_COELSA_ID = "near_coelsa_id"
    MULTIPLE_CANDIDATES = "multiple_candidates"
    UNREADABLE_RECEIPT = "unreadable_receipt"


@dataclass(frozen=True)
class Matched:
    transfer: IncomingTransfer
    method: MatchMethod


@dataclass(frozen=True)
class NeedsReview:
    reason: ReviewReason
    candidates: tuple[IncomingTransfer, ...]


@dataclass(frozen=True)
class NotFound:
    pass


type MatchDecision = Matched | NeedsReview | NotFound


def match_receipt(
    receipt: ParsedReceipt, transfers: list[IncomingTransfer], window: timedelta
) -> MatchDecision:
    """Decide which incoming transfer a receipt proves, if any.

    Receipt with a COELSA id (only that id can match it):
    1. exact id and exact amount match; exact id with another amount is reviewed;
    2. an id that is only near another one (O/0, one character) is reviewed;
    3. no such id but same-amount transfers in the window are reviewed (`coelsa_mismatch`);
       otherwise the transfer has not arrived yet.

    Receipt without a COELSA id: exact amount, compatible origin CUIT and sent within
    `window` (UTC). Exactly one candidate matches; several are reviewed; none is not found yet.
    """
    if receipt.amount_cents is None:
        return NeedsReview(ReviewReason.UNREADABLE_RECEIPT, ())
    if receipt.coelsa_id:
        return _match_by_coelsa_id(receipt, transfers, window)
    return _match_by_amount_cuit_window(receipt, transfers, window)


def is_near_id(a: str, b: str) -> bool:
    """True when two different ids differ only by O/0 confusion or by one character."""
    a, b = normalize_id(a), normalize_id(b)
    if a == b:
        return False
    return a.replace("O", "0") == b.replace("O", "0") or _within_one_edit(a, b)


def _match_by_coelsa_id(
    receipt: ParsedReceipt, transfers: list[IncomingTransfer], window: timedelta
) -> MatchDecision:
    coelsa_id = receipt.coelsa_id or ""
    with_id = [t for t in transfers if t.e2e_id]
    exact = [t for t in with_id if normalize_id(t.e2e_id or "") == coelsa_id]
    if exact:
        transfer = exact[0]
        if transfer.amount_cents == receipt.amount_cents:
            return Matched(transfer, MatchMethod.COELSA_ID)
        return NeedsReview(ReviewReason.AMOUNT_MISMATCH, (transfer,))
    near = tuple(t for t in with_id if is_near_id(t.e2e_id or "", coelsa_id))
    if near:
        return NeedsReview(ReviewReason.NEAR_COELSA_ID, near)
    same_amount = tuple(
        t
        for t in transfers
        if t.amount_cents == receipt.amount_cents and _in_window(receipt, t, window)
    )
    if same_amount:
        return NeedsReview(ReviewReason.COELSA_MISMATCH, same_amount)
    return NotFound()


def _match_by_amount_cuit_window(
    receipt: ParsedReceipt, transfers: list[IncomingTransfer], window: timedelta
) -> MatchDecision:
    if receipt.sent_at is None:
        return NotFound()
    candidates = tuple(
        t
        for t in transfers
        if t.amount_cents == receipt.amount_cents
        and _in_window(receipt, t, window)
        and _cuit_compatible(receipt.origin_cuit, t.payer_cuit)
    )
    if len(candidates) == 1:
        return Matched(candidates[0], MatchMethod.AMOUNT_CUIT_WINDOW)
    if candidates:
        return NeedsReview(ReviewReason.MULTIPLE_CANDIDATES, candidates)
    return NotFound()


def _in_window(receipt: ParsedReceipt, transfer: IncomingTransfer, window: timedelta) -> bool:
    """Without a printed time, every transfer the provider search returned is in range."""
    return receipt.sent_at is None or abs(transfer.received_at - receipt.sent_at) <= window


def _cuit_compatible(receipt_cuit: str | None, payer_cuit: str | None) -> bool:
    """CUITs are compared only when both sides carry one (the provider may omit it)."""
    return receipt_cuit is None or payer_cuit is None or receipt_cuit == payer_cuit


def _within_one_edit(a: str, b: str) -> bool:
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b, strict=True)) == 1
    shorter, longer = sorted((a, b), key=len)
    return any(longer[:i] + longer[i + 1 :] == shorter for i in range(len(longer)))
