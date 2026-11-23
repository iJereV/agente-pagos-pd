"""Composition root: wires the Google Cloud adapters. Served by `uvicorn link_web.main:app`."""

import os

from google.cloud import firestore

from .adapters.firebase_identity import FirebaseIdentityVerifier
from .adapters.firestore_store import FirestoreChannelStore
from .adapters.shared_adapters import PubSubPublisher, SharedLinkTokenVerifier
from .app import create_app
from .logging_setup import configure_logging
from .page import IdentityConfig
from .service import LinkService

configure_logging()

_project = os.environ["GOOGLE_CLOUD_PROJECT"]

_service = LinkService(
    link_tokens=SharedLinkTokenVerifier(),
    identities=FirebaseIdentityVerifier(_project),
    store=FirestoreChannelStore(
        firestore.Client(
            project=_project, database=os.environ.get("FIRESTORE_CHANNEL_DB", "channel")
        )
    ),
    publisher=PubSubPublisher(os.environ["WA_INBOUND_TOPIC"]),
)

app = create_app(
    _service,
    IdentityConfig(
        api_key=os.environ["IDENTITY_API_KEY"],
        auth_domain=os.environ["IDENTITY_AUTH_DOMAIN"],
    ),
)
