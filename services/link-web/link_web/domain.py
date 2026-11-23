"""Linking and re-authentication rules, independent of Firestore and HTTP."""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Purpose(StrEnum):
    LINK = "link"
    REAUTH = "reauth"


class Rejection(StrEnum):
    TOKEN_NOT_FOUND = "token_not_found"
    TOKEN_USED = "token_used"
    TOKEN_EXPIRED = "token_expired"
    TOKEN_MISMATCH = "token_mismatch"
    NUMBER_LINKED_TO_OTHER_ACCOUNT = "number_linked_to_other_account"
    ACCOUNT_LINKED_TO_OTHER_NUMBER = "account_linked_to_other_number"
    NOT_LINKED = "not_linked"
    ACCOUNT_MISMATCH = "account_mismatch"


def token_hash(jti: str) -> str:
    """Document id of `link_tokens`: hex SHA-256 of the token's jti."""
    return hashlib.sha256(jti.encode()).hexdigest()


@dataclass(frozen=True)
class SignInRequest:
    """A verified link token plus a verified Google identity."""

    token_hash: str
    wa_id: str
    purpose: Purpose
    uid: str
    email: str
    now: datetime


@dataclass(frozen=True)
class LinkTokenRecord:
    wa_id: str
    purpose: str
    expires_at: datetime
    used_at: datetime | None


@dataclass(frozen=True)
class ChannelSnapshot:
    """What the store holds for one sign-in, read inside a single transaction."""

    token: LinkTokenRecord | None
    linked_customer_id: str | None  # wa_links/{wa_id}.customer_id
    customer_wa_id: str | None  # customers/{uid}.wa_id


@dataclass(frozen=True)
class Accepted:
    create_link: bool


def decide(snapshot: ChannelSnapshot, request: SignInRequest) -> Accepted | Rejection:
    token = snapshot.token
    if token is None:
        return Rejection.TOKEN_NOT_FOUND
    if token.wa_id != request.wa_id or token.purpose != request.purpose:
        return Rejection.TOKEN_MISMATCH
    if token.used_at is not None:
        return Rejection.TOKEN_USED
    if request.now >= token.expires_at:
        return Rejection.TOKEN_EXPIRED

    if request.purpose is Purpose.REAUTH:
        if snapshot.linked_customer_id is None:
            return Rejection.NOT_LINKED
        if snapshot.linked_customer_id != request.uid:
            return Rejection.ACCOUNT_MISMATCH
        return Accepted(create_link=False)

    if snapshot.linked_customer_id not in (None, request.uid):
        return Rejection.NUMBER_LINKED_TO_OTHER_ACCOUNT
    if snapshot.customer_wa_id not in (None, request.wa_id):
        return Rejection.ACCOUNT_LINKED_TO_OTHER_NUMBER
    return Accepted(create_link=snapshot.linked_customer_id is None)


def new_link_fields(request: SignInRequest) -> dict[str, object]:
    """Fields of the `wa_links/{wa_id}` document created on first link."""
    return {"customer_id": request.uid, "linked_at": request.now}


def customer_fields(request: SignInRequest, accepted: Accepted) -> dict[str, object]:
    """Fields merged into `customers/{uid}` on every accepted sign-in."""
    fields: dict[str, object] = {
        "email": request.email,
        "wa_id": request.wa_id,
        "last_sign_in_at": request.now,
    }
    if accepted.create_link:
        fields["linked_at"] = request.now
    return fields
