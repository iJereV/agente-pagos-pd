from datetime import UTC, datetime, timedelta
from typing import Any

from link_web.domain import (
    Accepted,
    ChannelSnapshot,
    LinkTokenRecord,
    Rejection,
    SignInRequest,
    customer_fields,
    decide,
    new_link_fields,
    token_hash,
)
from link_web.ports import (
    ExpiredLinkTokenError,
    InvalidIdentityError,
    InvalidLinkTokenError,
    LinkTokenClaims,
    VerifiedIdentity,
)

NOW = datetime(2026, 11, 23, 15, 20, tzinfo=UTC)
WA_ID = "5490000000001"
JTI = "jti-synthetic-1"
UID = "uid-synthetic-1"
OTHER_UID = "uid-synthetic-2"
EMAIL = "cliente@example.com"


class FakeLinkTokens:
    """Maps opaque test tokens to claims; anything else is invalid."""

    def __init__(self, tokens: dict[str, LinkTokenClaims]) -> None:
        self._tokens = tokens

    def verify(self, token: str) -> LinkTokenClaims:
        if token == "expired-link-token":
            raise ExpiredLinkTokenError("token expired")
        if token not in self._tokens:
            raise InvalidLinkTokenError("bad token")
        return self._tokens[token]


class FakeIdentities:
    def __init__(self, identities: dict[str, VerifiedIdentity]) -> None:
        self._identities = identities

    def verify(self, id_token: str) -> VerifiedIdentity:
        if id_token not in self._identities:
            raise InvalidIdentityError("bad id token")
        return self._identities[id_token]


class FakeChannelStore:
    """In-memory `channel` database applying the same domain decision and writes."""

    def __init__(self) -> None:
        self.link_tokens: dict[str, dict[str, Any]] = {}
        self.wa_links: dict[str, dict[str, Any]] = {}
        self.customers: dict[str, dict[str, Any]] = {}

    def add_token(
        self, jti: str, purpose: str, *, expires_in: timedelta = timedelta(minutes=10)
    ) -> None:
        self.link_tokens[token_hash(jti)] = {
            "wa_id": WA_ID,
            "purpose": purpose,
            "expires_at": NOW + expires_in,
            "used_at": None,
        }

    def apply_sign_in(self, request: SignInRequest) -> Accepted | Rejection:
        token = self.link_tokens.get(request.token_hash)
        link = self.wa_links.get(request.wa_id)
        customer = self.customers.get(request.uid)
        decision = decide(
            ChannelSnapshot(
                token=LinkTokenRecord(**token) if token else None,
                linked_customer_id=link["customer_id"] if link else None,
                customer_wa_id=customer["wa_id"] if customer else None,
            ),
            request,
        )
        if isinstance(decision, Rejection):
            return decision
        token["used_at"] = request.now
        if decision.create_link:
            self.wa_links[request.wa_id] = new_link_fields(request)
        self.customers.setdefault(request.uid, {}).update(customer_fields(request, decision))
        return decision


class FakePublisher:
    def __init__(self, fail: bool = False) -> None:
        self.published: list[dict[str, Any]] = []
        self._fail = fail

    def publish(self, payload: dict[str, Any]) -> None:
        if self._fail:
            raise RuntimeError("pubsub down")
        self.published.append(payload)


def google_identity(uid: str = UID, **overrides: Any) -> VerifiedIdentity:
    fields = {"uid": uid, "email": EMAIL, "email_verified": True, "sign_in_provider": "google.com"}
    return VerifiedIdentity(**(fields | overrides))
