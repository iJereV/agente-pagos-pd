import pytest
from fastapi.testclient import TestClient
from link_fakes import (
    JTI,
    NOW,
    OTHER_UID,
    WA_ID,
    FakeChannelStore,
    FakeIdentities,
    FakeLinkTokens,
    FakePublisher,
    google_identity,
)
from link_web.app import create_app
from link_web.page import IdentityConfig
from link_web.ports import LinkTokenClaims
from link_web.service import LinkService


@pytest.fixture
def store() -> FakeChannelStore:
    return FakeChannelStore()


@pytest.fixture
def publisher() -> FakePublisher:
    return FakePublisher()


@pytest.fixture
def make_client(store):
    def build(publisher: FakePublisher) -> TestClient:
        service = LinkService(
            link_tokens=FakeLinkTokens(
                {
                    "link-token": LinkTokenClaims(wa_id=WA_ID, jti=JTI, purpose="link"),
                    "reauth-token": LinkTokenClaims(wa_id=WA_ID, jti=JTI, purpose="reauth"),
                }
            ),
            identities=FakeIdentities(
                {
                    "google-id": google_identity(),
                    "other-google-id": google_identity(OTHER_UID),
                    "password-id": google_identity(sign_in_provider="password"),
                }
            ),
            store=store,
            publisher=publisher,
            clock=lambda: NOW,
            new_event_id=lambda: "evt-1",
        )
        return TestClient(
            create_app(service, IdentityConfig("public-api-key", "demo.firebaseapp.com"))
        )

    return build


@pytest.fixture
def client(make_client, publisher) -> TestClient:
    return make_client(publisher)
