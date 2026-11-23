"""Composition root: real settings and the Pub/Sub publisher."""

from functools import partial

from shared.config import env_str
from shared.logging import setup_logging
from shared.pubsub import publish_json

from wa_webhook.app import Settings, create_app

setup_logging()

app = create_app(
    Settings(app_secret=env_str("META_APP_SECRET"), verify_token=env_str("META_VERIFY_TOKEN")),
    publish=partial(publish_json, env_str("WA_INBOUND_TOPIC")),
)
