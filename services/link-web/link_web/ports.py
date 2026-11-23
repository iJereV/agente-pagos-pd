"""Driven ports. Adapters live in `link_web.adapters`; tests use in-memory fakes."""

from dataclasses import dataclass
from typing import Any, Protocol

from .domain import Accepted, Rejection, SignInRequest


class InvalidLinkTokenError(Exception):
    """Bad signature, audience, issuer or expiry of the link token."""


class ExpiredLinkTokenError(InvalidLinkTokenError):
    """The link token is authentic but past its expiry."""


class InvalidIdentityError(Exception):
    """The Identity Platform ID token did not verify."""


@dataclass(frozen=True)
class LinkTokenClaims:
    wa_id: str
    jti: str
    purpose: str


@dataclass(frozen=True)
class VerifiedIdentity:
    uid: str
    email: str | None
    email_verified: bool
    sign_in_provider: str | None


class LinkTokenVerifier(Protocol):
    def verify(self, token: str) -> LinkTokenClaims:
        """Raises InvalidLinkTokenError."""
        ...


class IdentityVerifier(Protocol):
    def verify(self, id_token: str) -> VerifiedIdentity:
        """Raises InvalidIdentityError."""
        ...


class ChannelStore(Protocol):
    def apply_sign_in(self, request: SignInRequest) -> Accepted | Rejection:
        """Atomically reads the snapshot, applies `domain.decide` and, when accepted,
        marks the token used, creates the link if needed and stamps the customer."""
        ...


class EventPublisher(Protocol):
    def publish(self, payload: dict[str, Any]) -> None: ...
