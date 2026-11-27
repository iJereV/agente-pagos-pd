import pytest
from mcp_shop.config import Settings

REQUIRED = {"MEDIA_BUCKET": "media", "ORDER_CREATED_TOPIC": "order-created"}


def test_extraction_model_is_served_from_global_by_default(monkeypatch):
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    monkeypatch.delenv("EXTRACTION_MODEL", raising=False)
    monkeypatch.delenv("EXTRACTION_MODEL_LOCATION", raising=False)

    settings = Settings.from_env()

    assert settings.extraction_model == "gemini-3.5-flash"
    assert settings.extraction_model_location == "global"
    assert settings.location == "us-central1"


def test_extraction_model_location_is_configurable(monkeypatch):
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("EXTRACTION_MODEL_LOCATION", "us-east5")

    assert Settings.from_env().extraction_model_location == "us-east5"


def test_welcome_credit_defaults_to_ten_pesos(monkeypatch):
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("WELCOME_CREDIT_CENTS", raising=False)

    assert Settings.from_env().welcome_credit_cents == 1000


def test_negative_welcome_credit_is_refused(monkeypatch):
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("WELCOME_CREDIT_CENTS", "-1")

    with pytest.raises(ValueError, match="WELCOME_CREDIT_CENTS"):
        Settings.from_env()
