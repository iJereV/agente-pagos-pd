import time

import jwt
import pytest
from shared.tokens import (
    ExpiredToken,
    InvalidToken,
    LinkClaims,
    LocalSigner,
    TurnClaims,
    issue_link_token,
    issue_turn_token,
    make_signer,
    verify_link_token,
    verify_turn_token,
)

SECRET = "test-secret-not-real-0123456789abcdef"
ISSUER = "sa-main-worker@example-project.iam.gserviceaccount.com"
WA_ID = "5490000000001"


@pytest.fixture(autouse=True)
def local_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOKEN_SIGNER", "local")
    monkeypatch.setenv("LOCAL_TOKEN_SECRET", SECRET)
    monkeypatch.setenv("SIGNER_SA_EMAIL", ISSUER)
    monkeypatch.setenv("TOKEN_ISSUER", ISSUER)


def test_turn_token_round_trip_for_linked_customer() -> None:
    token = issue_turn_token(
        make_signer(),
        customer_id="uid-123",
        wa_id=WA_ID,
        auth_fresh=True,
        last_receipt_ref="receipts/uid-123/wamid.TEST1.jpg",
    )

    assert verify_turn_token(token) == TurnClaims(
        customer_id="uid-123",
        wa_id=WA_ID,
        auth_fresh=True,
        last_receipt_ref="receipts/uid-123/wamid.TEST1.jpg",
    )


def test_turn_token_for_unlinked_number_has_empty_subject() -> None:
    token = issue_turn_token(
        make_signer(), customer_id=None, wa_id=WA_ID, auth_fresh=False, last_receipt_ref=None
    )

    assert jwt.decode(token, options={"verify_signature": False})["sub"] == ""
    assert verify_turn_token(token) == TurnClaims(None, WA_ID, False, None)


def test_turn_token_lifetime_is_two_minutes() -> None:
    token = issue_turn_token(
        make_signer(), customer_id=None, wa_id=WA_ID, auth_fresh=False, last_receipt_ref=None
    )
    claims = jwt.decode(token, options={"verify_signature": False})

    assert claims["exp"] - claims["iat"] == 120
    assert claims["iss"] == ISSUER
    assert claims["aud"] == "mcp-shop"


def test_link_token_round_trip() -> None:
    token, jti = issue_link_token(make_signer(), wa_id=WA_ID, purpose="reauth")

    assert verify_link_token(token) == LinkClaims(wa_id=WA_ID, jti=jti, purpose="reauth")


def test_link_token_rejects_unknown_purpose() -> None:
    with pytest.raises(ValueError):
        issue_link_token(make_signer(), wa_id=WA_ID, purpose="admin")


def test_expired_token_is_rejected() -> None:
    past = int(time.time()) - 600
    token = LocalSigner(SECRET, ISSUER).sign(
        {
            "aud": "mcp-shop",
            "sub": "",
            "wa_id": WA_ID,
            "auth_fresh": False,
            "last_receipt_ref": None,
            "iat": past,
            "exp": past + 120,
        }
    )

    with pytest.raises(ExpiredToken):
        verify_turn_token(token)


def test_link_token_is_not_accepted_as_turn_token() -> None:
    token, _ = issue_link_token(make_signer(), wa_id=WA_ID, purpose="link")

    with pytest.raises(InvalidToken):
        verify_turn_token(token)


def test_wrong_issuer_is_rejected() -> None:
    token = issue_turn_token(
        LocalSigner(SECRET, "someone-else@example.com"),
        customer_id="uid-123",
        wa_id=WA_ID,
        auth_fresh=True,
        last_receipt_ref=None,
    )

    with pytest.raises(InvalidToken):
        verify_turn_token(token)


def test_forged_signature_is_rejected() -> None:
    token = issue_turn_token(
        LocalSigner("another-secret-also-not-real-0123", ISSUER),
        customer_id="uid-123",
        wa_id=WA_ID,
        auth_fresh=True,
        last_receipt_ref=None,
    )

    with pytest.raises(InvalidToken):
        verify_turn_token(token)


def test_garbage_is_rejected() -> None:
    with pytest.raises(InvalidToken):
        verify_link_token("not-a-jwt")
