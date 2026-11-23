"""Composition root: wires the real adapters into the use cases."""

from fastapi import FastAPI
from google.cloud import firestore, storage
from shared.config import env_str
from shared.logging import setup_logging
from shared.tokens import make_signer

from main_worker.adapters.agent_runtime import VertexAgentRuntime
from main_worker.adapters.firestore_store import FirestoreChannelStore
from main_worker.adapters.gcs_media import GcsMediaStore
from main_worker.adapters.whatsapp import GraphWhatsApp
from main_worker.api import create_app
from main_worker.application import utc_now
from main_worker.application.conversation import Conversation
from main_worker.application.deliveries import OrderDeliveries
from main_worker.application.inbound import InboundHandler
from main_worker.domain.policy import Policy


def build_app() -> FastAPI:
    project = env_str("GOOGLE_CLOUD_PROJECT")
    location = env_str("GOOGLE_CLOUD_LOCATION", "us-central1")
    policy = Policy.from_env()

    store = FirestoreChannelStore(
        firestore.AsyncClient(project=project, database=env_str("FIRESTORE_CHANNEL_DB", "channel"))
    )
    media = GcsMediaStore(storage.Client(project=project), env_str("MEDIA_BUCKET"))
    whatsapp = GraphWhatsApp(
        access_token=env_str("META_ACCESS_TOKEN"),
        phone_number_id=env_str("WA_PHONE_NUMBER_ID"),
        graph_version=env_str("META_GRAPH_VERSION", "v21.0"),
    )
    agent = VertexAgentRuntime(
        resource_name=env_str("AGENT_RESOURCE_NAME"), project=project, location=location
    )

    conversation = Conversation(
        store=store, agent=agent, signer=make_signer(), policy=policy, clock=utc_now
    )
    deliveries = OrderDeliveries(
        store=store,
        whatsapp=whatsapp,
        media=media,
        conversation=conversation,
        policy=policy,
        clock=utc_now,
    )
    inbound = InboundHandler(
        store=store,
        whatsapp=whatsapp,
        media=media,
        conversation=conversation,
        deliveries=deliveries,
        clock=utc_now,
    )
    return create_app(inbound, deliveries)


setup_logging()
app = build_app()
