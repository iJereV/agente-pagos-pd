"""Order image generation use case: idempotent per order, bounded by a global daily cap."""

import logging
import random
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum

from .models import OrderCreated, order_ready_event, to_iso
from .ports import EventPublisher, ImageModel, MediaStore
from .variants import draw_variants

logger = logging.getLogger(__name__)

COUNTER_WRITE_ATTEMPTS = 5


class Outcome(StrEnum):
    GENERATED = "generated"
    ALREADY_GENERATED = "already_generated"
    OVER_DAILY_CAP = "over_daily_cap"


class CounterContentionError(RuntimeError):
    """The daily counter kept changing under us; Pub/Sub will redeliver the event."""


def manifest_path(order_id: str) -> str:
    return f"orders/{order_id}/manifest.json"


def image_path(order_id: str, number: int) -> str:
    return f"orders/{order_id}/{number}.png"


def counter_path(day: datetime) -> str:
    return f"orders/_counters/{day.astimezone(UTC):%Y-%m-%d}.json"


class OrderImageService:
    def __init__(
        self,
        *,
        image_model: ImageModel,
        store: MediaStore,
        publisher: EventPublisher,
        daily_cap: int,
        rng: random.Random,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._image_model = image_model
        self._store = store
        self._publisher = publisher
        self._daily_cap = daily_cap
        self._rng = rng
        self._clock = clock

    def handle(self, order: OrderCreated) -> Outcome:
        existing = self._store.read_json(manifest_path(order.order_id))
        if existing is not None:
            # Re-publish so a publish lost after the manifest write still reaches main-worker.
            self._publish_ready(order, existing["images"])
            return Outcome.ALREADY_GENERATED

        animals = order.animals_per_image()
        if not self._reserve_daily_quota(len(animals)):
            logger.warning(
                "daily generation cap reached, order skipped",
                extra={"order_id": order.order_id, "images": len(animals), "cap": self._daily_cap},
            )
            return Outcome.OVER_DAILY_CAP

        variants = draw_variants(animals, self._rng)
        images: list[str] = []
        for number, variant in enumerate(variants, start=1):
            path = image_path(order.order_id, number)
            self._store.write_bytes(
                path, self._image_model.generate_png(variant.prompt), "image/png"
            )
            images.append(path)

        self._store.write_json(
            manifest_path(order.order_id),
            {
                "order_id": order.order_id,
                "images": images,
                "variants": [variant.as_manifest_entry() for variant in variants],
                "model": self._image_model.name,
                "created_at": to_iso(self._clock()),
            },
        )
        self._publish_ready(order, images)
        logger.info(
            "order images generated", extra={"order_id": order.order_id, "images": len(images)}
        )
        return Outcome.GENERATED

    def _reserve_daily_quota(self, count: int) -> bool:
        """Adds `count` to today's counter with optimistic concurrency (GCS generations).

        A failed generation after the reservation still counts against the cap: the cap
        is a cost guard, so over-counting is the safe direction.
        """
        path = counter_path(self._clock())
        for _ in range(COUNTER_WRITE_ATTEMPTS):
            counter, generation = self._store.read_json_versioned(path)
            used = counter["images"] if counter else 0
            if used + count > self._daily_cap:
                return False
            if self._store.write_json_if_generation(path, {"images": used + count}, generation):
                return True
        raise CounterContentionError(path)

    def _publish_ready(self, order: OrderCreated, images: list[str]) -> None:
        self._publisher.publish(order_ready_event(order, images, self._clock()))
