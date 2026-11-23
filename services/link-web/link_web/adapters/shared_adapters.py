"""Adapters over the `shared` library: link token verification and Pub/Sub publishing."""

from typing import Any

from shared.pubsub import publish_json
from shared.tokens import ExpiredToken, InvalidToken, verify_link_token

from ..ports import ExpiredLinkTokenError, InvalidLinkTokenError, LinkTokenClaims


class SharedLinkTokenVerifier:
    def verify(self, token: str) -> LinkTokenClaims:
        try:
            claims = verify_link_token(token)
        except ExpiredToken as error:
            raise ExpiredLinkTokenError(str(error)) from error
        except InvalidToken as error:
            raise InvalidLinkTokenError(str(error)) from error
        return LinkTokenClaims(wa_id=claims.wa_id, jti=claims.jti, purpose=claims.purpose)


class PubSubPublisher:
    def __init__(self, topic: str) -> None:
        self._topic = topic

    def publish(self, payload: dict[str, Any]) -> None:
        publish_json(self._topic, payload)
