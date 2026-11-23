"""IdentityVerifier for Identity Platform (Firebase-compatible) ID tokens."""

import google.auth.transport.requests
from google.auth.exceptions import GoogleAuthError
from google.oauth2 import id_token

from ..ports import InvalidIdentityError, VerifiedIdentity


class FirebaseIdentityVerifier:
    def __init__(self, project_id: str) -> None:
        self._project_id = project_id
        self._request = google.auth.transport.requests.Request()

    def verify(self, token: str) -> VerifiedIdentity:
        try:
            # Checks signature, expiry, audience (project id) and issuer.
            claims = id_token.verify_firebase_token(token, self._request, audience=self._project_id)
        except (ValueError, GoogleAuthError) as error:
            raise InvalidIdentityError(str(error)) from error
        return VerifiedIdentity(
            uid=claims["sub"],
            email=claims.get("email"),
            email_verified=bool(claims.get("email_verified")),
            sign_in_provider=claims.get("firebase", {}).get("sign_in_provider"),
        )
