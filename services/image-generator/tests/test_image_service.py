import pytest
from image_fakes import RacingMediaStore, order_payload
from image_generator.models import OrderCreated
from image_generator.service import CounterContentionError, Outcome

ORDER = OrderCreated.model_validate(order_payload())
COUNTER = "orders/_counters/2026-11-23.json"
MANIFEST = "orders/ord_TEST001/manifest.json"
IMAGES = [f"orders/ord_TEST001/{n}.png" for n in (1, 2, 3)]


def test_generates_images_manifest_and_order_ready(make_service, store, image_model, publisher):
    outcome = make_service(store).handle(ORDER)

    assert outcome is Outcome.GENERATED
    assert all(path in store.objects for path in IMAGES)
    manifest = store.read_json(MANIFEST)
    assert manifest["order_id"] == "ord_TEST001"
    assert manifest["images"] == IMAGES
    assert manifest["model"] == "fake-image-model"
    assert manifest["created_at"] == "2026-11-23T15:15:02Z"
    assert [v["animal"] for v in manifest["variants"]] == ["dog", "dog", "capybara"]
    assert [v["prompt"] for v in manifest["variants"]] == image_model.prompts
    assert store.read_json(COUNTER) == {"images": 3}
    assert publisher.published == [
        {
            "type": "order_ready",
            "order_id": "ord_TEST001",
            "customer_id": "uid-synthetic-1",
            "wa_id": "5490000000001",
            "images": IMAGES,
            "ready_at": "2026-11-23T15:15:02Z",
        }
    ]


def test_redelivery_republishes_without_generating_again(
    make_service, store, image_model, publisher
):
    service = make_service(store)
    service.handle(ORDER)
    prompts_after_first_run = list(image_model.prompts)

    outcome = service.handle(ORDER)

    assert outcome is Outcome.ALREADY_GENERATED
    assert image_model.prompts == prompts_after_first_run
    assert store.read_json(COUNTER) == {"images": 3}
    assert len(publisher.published) == 2
    assert publisher.published[0] == publisher.published[1]


def test_over_daily_cap_skips_generation(make_service, store, image_model, publisher):
    store.write_json(COUNTER, {"images": 198})

    outcome = make_service(store, daily_cap=200).handle(ORDER)

    assert outcome is Outcome.OVER_DAILY_CAP
    assert image_model.prompts == []
    assert publisher.published == []
    assert store.read_json(MANIFEST) is None
    assert store.read_json(COUNTER) == {"images": 198}


def test_order_that_exactly_reaches_the_cap_is_generated(make_service, store):
    store.write_json(COUNTER, {"images": 197})

    assert make_service(store, daily_cap=200).handle(ORDER) is Outcome.GENERATED
    assert store.read_json(COUNTER) == {"images": 200}


def test_counter_retries_when_another_writer_wins_the_race(make_service):
    store = RacingMediaStore(races=2)

    assert make_service(store).handle(ORDER) is Outcome.GENERATED
    # Two concurrent increments of 1 plus our 3 images.
    assert store.read_json(COUNTER) == {"images": 5}


def test_counter_gives_up_after_persistent_contention(make_service):
    with pytest.raises(CounterContentionError):
        make_service(RacingMediaStore(races=100)).handle(ORDER)
