import random

import pytest
from image_fakes import NOW, FakeImageModel, FakeMediaStore, FakePublisher
from image_generator.service import OrderImageService


@pytest.fixture
def image_model() -> FakeImageModel:
    return FakeImageModel()


@pytest.fixture
def store() -> FakeMediaStore:
    return FakeMediaStore()


@pytest.fixture
def publisher() -> FakePublisher:
    return FakePublisher()


@pytest.fixture
def make_service(image_model, publisher):
    def build(store: FakeMediaStore, daily_cap: int = 200) -> OrderImageService:
        return OrderImageService(
            image_model=image_model,
            store=store,
            publisher=publisher,
            daily_cap=daily_cap,
            rng=random.Random(7),
            clock=lambda: NOW,
        )

    return build
