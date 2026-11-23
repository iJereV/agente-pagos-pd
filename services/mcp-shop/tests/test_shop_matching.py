from datetime import timedelta

import pytest
from mcp_shop.domain.matching import (
    Matched,
    MatchMethod,
    NeedsReview,
    NotFound,
    ReviewReason,
    is_near_id,
    match_receipt,
)
from mcp_shop.domain.receipts import ParsedReceipt
from shop_fakes import NOW, PAYER_CUIT, transfer

WINDOW = timedelta(minutes=120)
COELSA = "SYNTHCOELSA00000000000001"


def receipt(
    coelsa_id: str | None = COELSA,
    amount: int | None = 500,
    minutes_ago: int = 12,
    cuit: str | None = PAYER_CUIT,
) -> ParsedReceipt:
    return ParsedReceipt(
        coelsa_id=coelsa_id,
        amount_cents=amount,
        sent_at=NOW - timedelta(minutes=minutes_ago),
        origin_cuit=cuit,
    )


def test_exact_coelsa_id_and_amount_matches():
    target = transfer(e2e_id=COELSA)
    decision = match_receipt(receipt(), [transfer(e2e_id="OTHER", amount=500), target], WINDOW)
    assert decision == Matched(target, MatchMethod.COELSA_ID)


def test_exact_coelsa_id_matches_even_outside_the_window():
    target = transfer(e2e_id=COELSA, received_at=NOW - timedelta(days=1))
    assert match_receipt(receipt(), [target], WINDOW) == Matched(target, MatchMethod.COELSA_ID)


def test_exact_coelsa_id_with_another_amount_goes_to_review():
    target = transfer(e2e_id=COELSA, amount=400)
    decision = match_receipt(receipt(), [target], WINDOW)
    assert decision == NeedsReview(ReviewReason.AMOUNT_MISMATCH, (target,))


def test_o_versus_zero_is_never_auto_matched():
    near = transfer(e2e_id="SYNTHC0ELSA00000000000001")
    decision = match_receipt(receipt(), [near], WINDOW)
    assert decision == NeedsReview(ReviewReason.NEAR_COELSA_ID, (near,))


def test_one_character_off_goes_to_review():
    near = transfer(e2e_id="SYNTHCOELSA00000000000007")
    assert match_receipt(receipt(), [near], WINDOW) == NeedsReview(
        ReviewReason.NEAR_COELSA_ID, (near,)
    )


def test_receipt_without_coelsa_id_matches_one_candidate_by_amount_cuit_and_window():
    target = transfer(e2e_id="UNRELATED-ID-1234567890")
    decision = match_receipt(receipt(coelsa_id=None), [target], WINDOW)
    assert decision == Matched(target, MatchMethod.AMOUNT_CUIT_WINDOW)


def test_fallback_accepts_a_provider_without_payer_cuit():
    target = transfer(e2e_id=None, payer_cuit=None)
    assert match_receipt(receipt(coelsa_id=None), [target], WINDOW) == Matched(
        target, MatchMethod.AMOUNT_CUIT_WINDOW
    )


def test_fallback_rejects_a_different_cuit():
    other = transfer(payer_cuit="27000000002")
    assert match_receipt(receipt(coelsa_id=None), [other], WINDOW) == NotFound()


def test_fallback_rejects_transfers_outside_the_window():
    late = transfer(received_at=NOW + timedelta(hours=3))
    assert match_receipt(receipt(coelsa_id=None), [late], WINDOW) == NotFound()


def test_several_fallback_candidates_go_to_review():
    first = transfer(e2e_id="A1", payment_id="sim-1")
    second = transfer(e2e_id="B2", payment_id="sim-2", received_at=NOW - timedelta(minutes=40))
    decision = match_receipt(receipt(coelsa_id=None), [first, second], WINDOW)
    assert decision == NeedsReview(ReviewReason.MULTIPLE_CANDIDATES, (first, second))


def test_nothing_matching_is_not_found_yet():
    assert match_receipt(receipt(), [transfer(e2e_id="ZZZ", amount=100)], WINDOW) == NotFound()


def test_unreadable_amount_goes_to_review():
    assert match_receipt(receipt(amount=None), [transfer()], WINDOW) == NeedsReview(
        ReviewReason.UNREADABLE_RECEIPT, ()
    )


def test_receipt_without_time_cannot_use_the_window_fallback():
    undated = ParsedReceipt(coelsa_id=None, amount_cents=500, sent_at=None, origin_cuit=None)
    assert match_receipt(undated, [transfer()], WINDOW) == NotFound()


@pytest.mark.parametrize(
    ("a", "b", "near"),
    [
        ("ABC0", "ABCO", True),
        ("ABCD", "ABCE", True),
        ("ABCD", "ABCDE", True),
        ("ABCD", "ACD", True),
        ("ABCD", "AD", False),
        ("ABCD", "ABXY", False),
        ("ABCD", "abcd", False),
    ],
)
def test_near_id_definition(a, b, near):
    assert is_near_id(a, b) is near


def test_receipt_with_coelsa_id_never_falls_back_to_amount_matching():
    lookalike = transfer(e2e_id="UNRELATED-ID-1234567890")
    decision = match_receipt(receipt(), [lookalike], WINDOW)
    assert decision == NeedsReview(ReviewReason.COELSA_MISMATCH, (lookalike,))


def test_coelsa_mismatch_lists_every_same_amount_transfer_in_the_window():
    first = transfer(e2e_id="UNRELATED-A", payment_id="sim-1")
    second = transfer(e2e_id=None, payment_id="sim-2", payer_cuit="27000000002")
    outside = transfer(e2e_id="UNRELATED-B", received_at=NOW - timedelta(hours=5))
    decision = match_receipt(receipt(), [first, second, outside], WINDOW)
    assert decision == NeedsReview(ReviewReason.COELSA_MISMATCH, (first, second))


def test_receipt_with_coelsa_id_and_no_same_amount_transfer_is_not_found_yet():
    outside = transfer(e2e_id="UNRELATED-B", received_at=NOW - timedelta(hours=5))
    assert match_receipt(receipt(), [outside], WINDOW) == NotFound()
