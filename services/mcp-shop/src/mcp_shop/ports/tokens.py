"""Port that turns the `X-Turn-Token` header into a trusted caller."""

from typing import Protocol

from mcp_shop.domain.identity import Caller


class InvalidTurnToken(Exception):
    pass


class TokenVerifier(Protocol):
    async def verify(self, token: str) -> Caller:
        """Raises `InvalidTurnToken` on a bad signature, audience, issuer or expiry."""
        ...
