"""Turn and link tokens: short-lived JWTs signed as the main-worker service account.

Production (``TOKEN_SIGNER=iam``): RS256 through IAM Credentials ``signJwt``, so no
private key is ever stored. Verifiers fetch the service account's public JWKS.
Local development and tests (``TOKEN_SIGNER=local``): HS256 with ``LOCAL_TOKEN_SECRET``.
"""

import json
import os
import time
import uuid
from dataclasses import dataclass
from functools import cache
from typing import Any, Protocol

import jwt

TURN_AUDIENCE = "mcp-shop"
LINK_AUDIENCE = "link-web"
TURN_TOKEN_TTL_SECONDS = 120
LINK_TOKEN_TTL_SECONDS = 600
LINK_PURPOSES = frozenset({"link", "reauth"})

_JWKS_URL = "https://www.googleapis.com/service_accounts/v1/jwk/{email}"
_CLOCK_SKEW_SECONDS = 5
_LOCAL_ISSUER = "local-signer"


class InvalidToken(Exception):
    """The token is malformed, forged, expired or meant for another audience."""


class ExpiredToken(InvalidToken):
    """The token verified but its ``exp`` has passed."""


@dataclass(frozen=True)
class TurnClaims:
    customer_id: str | None
    wa_id: str
    auth_fresh: bool
    last_receipt_ref: str | None


@dataclass(frozen=True)
class LinkClaims:
    wa_id: str
    jti: str
    purpose: str


class TokenSigner(Protocol):
    """Signs a claim set. Implementations stamp their own ``iss`` claim."""

    def sign(self, claims: dict) -> str: ...


class IamSigner:
    """Signs through IAM Credentials ``signJwt`` as ``service_account_email``."""

    def __init__(self, service_account_email: str) -> None:
        from google.cloud import iam_credentials_v1

        self._email = service_account_email
        self._name = f"projects/-/serviceAccounts/{service_account_email}"
        self._client = iam_credentials_v1.IAMCredentialsClient()

    def sign(self, claims: dict) -> str:
        payload = json.dumps({**claims, "iss": self._email})
        return self._client.sign_jwt(name=self._name, payload=payload).signed_jwt


class LocalSigner:
    """HS256 signer for local development and tests."""

    def __init__(self, secret: str, issuer: str = _LOCAL_ISSUER) -> None:
        self._secret = secret
        self._issuer = issuer

    def sign(self, claims: dict) -> str:
        return jwt.encode({**claims, "iss": self._issuer}, self._secret, algorithm="HS256")


def make_signer() -> TokenSigner:
    """Build the signer selected by ``TOKEN_SIGNER`` (``iam`` by default)."""
    if _local_mode():
        issuer = os.environ.get("SIGNER_SA_EMAIL") or _LOCAL_ISSUER
        return LocalSigner(_local_secret(), issuer)
    return IamSigner(os.environ["SIGNER_SA_EMAIL"])


def issue_turn_token(
    signer: TokenSigner,
    *,
    customer_id: str | None,
    wa_id: str,
    auth_fresh: bool,
    last_receipt_ref: str | None,
) -> str:
    now = int(time.time())
    return signer.sign(
        {
            "aud": TURN_AUDIENCE,
            "sub": customer_id or "",
            "wa_id": wa_id,
            "auth_fresh": auth_fresh,
            "last_receipt_ref": last_receipt_ref,
            "iat": now,
            "exp": now + TURN_TOKEN_TTL_SECONDS,
        }
    )


def issue_link_token(signer: TokenSigner, *, wa_id: str, purpose: str) -> tuple[str, str]:
    """Return ``(token, jti)``. The caller stores ``sha256(jti)`` for single use."""
    if purpose not in LINK_PURPOSES:
        raise ValueError(f"unknown link token purpose: {purpose}")
    now = int(time.time())
    jti = str(uuid.uuid4())
    token = signer.sign(
        {
            "aud": LINK_AUDIENCE,
            "wa_id": wa_id,
            "jti": jti,
            "purpose": purpose,
            "iat": now,
            "exp": now + LINK_TOKEN_TTL_SECONDS,
        }
    )
    return token, jti


def verify_turn_token(token: str) -> TurnClaims:
    claims = _decode(token, TURN_AUDIENCE, required=("sub", "wa_id", "auth_fresh"))
    receipt_ref = claims.get("last_receipt_ref")
    return TurnClaims(
        customer_id=claims["sub"] or None,
        wa_id=_require_str(claims, "wa_id"),
        auth_fresh=claims["auth_fresh"] is True,
        last_receipt_ref=receipt_ref if isinstance(receipt_ref, str) else None,
    )


def verify_link_token(token: str) -> LinkClaims:
    claims = _decode(token, LINK_AUDIENCE, required=("wa_id", "jti", "purpose"))
    purpose = _require_str(claims, "purpose")
    if purpose not in LINK_PURPOSES:
        raise InvalidToken("unknown purpose")
    return LinkClaims(
        wa_id=_require_str(claims, "wa_id"), jti=_require_str(claims, "jti"), purpose=purpose
    )


def _decode(token: str, audience: str, *, required: tuple[str, ...]) -> dict[str, Any]:
    issuer = _expected_issuer()
    try:
        key, algorithm = _verification_key(token, issuer)
        return jwt.decode(
            token,
            key,
            algorithms=[algorithm],
            audience=audience,
            issuer=issuer,
            leeway=_CLOCK_SKEW_SECONDS,
            options={"require": ["iss", "aud", "iat", "exp", *required]},
        )
    except jwt.PyJWKClientConnectionError:
        raise  # JWKS endpoint unreachable: transient, not a bad token.
    except jwt.ExpiredSignatureError as exc:
        raise ExpiredToken(str(exc)) from exc
    except jwt.PyJWTError as exc:
        raise InvalidToken(str(exc)) from exc


def _verification_key(token: str, issuer: str) -> tuple[Any, str]:
    if _local_mode():
        return _local_secret(), "HS256"
    return _jwks_client(issuer).get_signing_key_from_jwt(token).key, "RS256"


@cache
def _jwks_client(issuer: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(_JWKS_URL.format(email=issuer), cache_keys=True)


def _expected_issuer() -> str:
    if _local_mode():
        return os.environ.get("TOKEN_ISSUER") or _LOCAL_ISSUER
    return os.environ["TOKEN_ISSUER"]


def _local_mode() -> bool:
    return os.environ.get("TOKEN_SIGNER", "iam") == "local"


def _local_secret() -> str:
    secret = os.environ.get("LOCAL_TOKEN_SECRET")
    if not secret:
        raise RuntimeError("LOCAL_TOKEN_SECRET is required when TOKEN_SIGNER=local")
    return secret


def _require_str(claims: dict[str, Any], name: str) -> str:
    value = claims.get(name)
    if not isinstance(value, str) or not value:
        raise InvalidToken(f"claim {name} must be a non-empty string")
    return value
