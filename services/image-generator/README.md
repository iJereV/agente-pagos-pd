# image-generator

Private Cloud Run service. Pub/Sub pushes `order-created` events here; it draws random
variants in code, generates one image per ordered unit with a Gemini image model on
Vertex AI, stores the images and a manifest in the media bucket, and publishes
`order-ready`. It has no database access and no WhatsApp dependency.

Payload shapes, object paths and environment variables are defined in
[docs/contracts.md](../../docs/contracts.md).

## Endpoint

| Method | Path | Caller | Behaviour |
|---|---|---|---|
| `POST` | `/pubsub/order-created` | Pub/Sub push (`sa-pubsub-push`) | `200 {"status": "generated" \| "already_generated" \| "over_daily_cap"}`; `400` for a malformed envelope or payload (dead-lettered, never retried into success); `5xx` on model or storage failures so Pub/Sub redelivers. |

## Behaviour

- **Idempotent per order.** If `orders/{order_id}/manifest.json` exists, nothing is
  generated; `order_ready` is published again so a publish lost after the manifest
  write still reaches main-worker (which is idempotent per order).
- **Daily cap.** `orders/_counters/{YYYY-MM-DD}.json` (UTC day) counts images. It is
  updated with GCS generation preconditions (`if_generation_match`, `0` = create only),
  retrying on conflicts. An order that would exceed `DAILY_GENERATION_CAP` is logged and
  acknowledged without generating.
- **Variants.** `image_generator/variants.py` holds placeholder lists (setting, time of
  day, art style, funny twist) and the prompt template. Each image gets its own draw;
  the chosen variants and prompts are written to the manifest.
- **Write order.** Images, then `manifest.json`, then `order_ready`.

## Layout

```
image_generator/
  models.py        event payloads (pydantic) and the order_ready builder
  variants.py      variant data and drawing
  ports.py         ImageModel, MediaStore, EventPublisher
  service.py       use case: idempotency, daily cap, generation
  app.py           FastAPI push endpoint (driving adapter)
  main.py          composition root
  adapters/        Cloud Storage, google-genai (Vertex AI), shared.pubsub
```

## Environment

`GOOGLE_CLOUD_PROJECT`, `MEDIA_BUCKET`, `ORDER_READY_TOPIC`,
`IMAGE_MODEL` (default `gemini-3.1-flash-lite-image`), `IMAGE_MODEL_LOCATION` (default
`global`), `DAILY_GENERATION_CAP` (default `200`), `PORT` (default `8080`).

The google-genai client is created with `vertexai=True` and
`location=IMAGE_MODEL_LOCATION`, independent of the region the service runs in
(`GOOGLE_CLOUD_LOCATION`): the image model is served from the `global` endpoint.
`gemini-2.5-flash-image` still works through `IMAGE_MODEL` until its retirement
(2027-03-15).

## Run and test

```sh
uv run --package image-generator pytest services/image-generator/tests
docker build -f services/image-generator/Dockerfile .
```
