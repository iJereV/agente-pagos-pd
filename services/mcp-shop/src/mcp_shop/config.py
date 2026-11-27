"""Settings read from the environment (see docs/contracts.md, "Environment variables")."""

import os
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Literal

type TransferVerifierName = Literal["mercadopago", "simulated"]


@dataclass(frozen=True)
class Settings:
    project: str | None
    location: str
    shop_database: str
    media_bucket: str
    transfer_verifier: TransferVerifierName
    mp_access_token: str | None
    mp_collector_id: str | None
    simulated_transfers_path: Path | None
    order_created_topic: str
    extraction_model: str
    extraction_model_location: str
    welcome_credit_cents: int
    match_window: timedelta
    port: int

    @classmethod
    def from_env(cls) -> "Settings":
        simulated_path = os.environ.get("SIMULATED_TRANSFERS_PATH")
        return cls(
            project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
            shop_database=os.environ.get("FIRESTORE_SHOP_DB", "shop"),
            media_bucket=os.environ["MEDIA_BUCKET"],
            transfer_verifier=_transfer_verifier(
                os.environ.get("TRANSFER_VERIFIER", "mercadopago")
            ),
            mp_access_token=os.environ.get("MP_ACCESS_TOKEN"),
            mp_collector_id=os.environ.get("MP_COLLECTOR_ID"),
            simulated_transfers_path=Path(simulated_path) if simulated_path else None,
            order_created_topic=os.environ["ORDER_CREATED_TOPIC"],
            # Llama 4 runs on the same billing as gpt-oss; Gemini ids (e.g.
            # "gemini-3.5-flash" in "global") need a paid billing account.
            extraction_model=os.environ.get(
                "EXTRACTION_MODEL", "meta/llama-4-maverick-17b-128e-instruct-maas"
            ),
            extraction_model_location=os.environ.get("EXTRACTION_MODEL_LOCATION", "us-east5"),
            welcome_credit_cents=_non_negative(
                "WELCOME_CREDIT_CENTS", os.environ.get("WELCOME_CREDIT_CENTS", "1000")
            ),
            match_window=timedelta(minutes=int(os.environ.get("MATCH_WINDOW_MINUTES", "120"))),
            port=int(os.environ.get("PORT", "8080")),
        )


def _non_negative(name: str, value: str) -> int:
    amount = int(value)
    if amount < 0:
        raise ValueError(f"{name} must not be negative, got {amount}")
    return amount


def _transfer_verifier(value: str) -> TransferVerifierName:
    if value == "mercadopago":
        return "mercadopago"
    if value == "simulated":
        return "simulated"
    raise ValueError(f"TRANSFER_VERIFIER must be mercadopago or simulated, got {value!r}")
