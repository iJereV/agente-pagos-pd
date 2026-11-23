import pytest
from main_worker_testkit import World, build_world

SIGNER_EMAIL = "sa-main-worker@example-project.iam.gserviceaccount.com"


@pytest.fixture(autouse=True)
def local_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOKEN_SIGNER", "local")
    monkeypatch.setenv("LOCAL_TOKEN_SECRET", "test-secret-not-real-0123456789abcdef")
    monkeypatch.setenv("SIGNER_SA_EMAIL", SIGNER_EMAIL)
    monkeypatch.setenv("TOKEN_ISSUER", SIGNER_EMAIL)


@pytest.fixture
def world() -> World:
    return build_world()
