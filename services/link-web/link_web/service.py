"""Sign-in completion use case: verify both tokens, bind or re-check, notify main-worker."""

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum

from .domain import Purpose, Rejection, SignInRequest, token_hash
from .ports import (
    ChannelStore,
    EventPublisher,
    ExpiredLinkTokenError,
    IdentityVerifier,
    InvalidIdentityError,
    InvalidLinkTokenError,
    LinkTokenVerifier,
)

logger = logging.getLogger(__name__)

GOOGLE_PROVIDER = "google.com"


class Failure(StrEnum):
    INVALID_LINK = "invalid_link"
    INVALID_IDENTITY = "invalid_identity"
    GOOGLE_ACCOUNT_REQUIRED = "google_account_required"


class SignInError(Exception):
    def __init__(self, code: Failure | Rejection) -> None:
        super().__init__(code.value)
        self.code = code


class LinkService:
    def __init__(
        self,
        *,
        link_tokens: LinkTokenVerifier,
        identities: IdentityVerifier,
        store: ChannelStore,
        publisher: EventPublisher,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        new_event_id: Callable[[], str] = lambda: str(uuid.uuid4()),
    ) -> None:
        self._link_tokens = link_tokens
        self._identities = identities
        self._store = store
        self._publisher = publisher
        self._clock = clock
        self._new_event_id = new_event_id

    def complete(self, link_token: str, id_token: str) -> Purpose:
        """Returns the completed purpose or raises SignInError."""
        try:
            claims = self._link_tokens.verify(link_token)
            purpose = Purpose(claims.purpose)
        except ExpiredLinkTokenError as error:
            raise SignInError(Rejection.TOKEN_EXPIRED) from error
        except (InvalidLinkTokenError, ValueError) as error:
            raise SignInError(Failure.INVALID_LINK) from error

        # Verify the Google identity before touching the single-use token, so a failed
        # sign-in does not burn the customer's link.
        try:
            identity = self._identities.verify(id_token)
        except InvalidIdentityError as error:
            raise SignInError(Failure.INVALID_IDENTITY) from error
        if (
            identity.sign_in_provider != GOOGLE_PROVIDER
            or not identity.email
            or not identity.email_verified
        ):
            raise SignInError(Failure.GOOGLE_ACCOUNT_REQUIRED)

        now = self._clock()
        decision = self._store.apply_sign_in(
            SignInRequest(
                token_hash=token_hash(claims.jti),
                wa_id=claims.wa_id,
                purpose=purpose,
                uid=identity.uid,
                email=identity.email,
                now=now,
            )
        )
        if isinstance(decision, Rejection):
            logger.warning(
                "sign-in rejected", extra={"reason": decision.value, "purpose": purpose.value}
            )
            raise SignInError(decision)

        self._notify(claims.wa_id, identity.uid, now)
        logger.info("sign-in completed", extra={"purpose": purpose.value})
        return purpose

    def _notify(self, wa_id: str, uid: str, now: datetime) -> None:
        event = {
            "type": "system_event",
            "event": "sign_in_completed",
            "event_id": self._new_event_id(),
            "wa_id": wa_id,
            "timestamp": now.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "data": {"customer_id": uid},
        }
        try:
            self._publisher.publish(event)
        except Exception:
            # The binding is committed and the token is spent; the customer's next
            # WhatsApp message already sees the fresh sign-in, so only log the miss.
            logger.exception("sign_in_completed publish failed")
