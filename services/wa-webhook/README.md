# wa-webhook

Public Cloud Run service that receives WhatsApp Cloud API webhooks. It checks Meta's signature, publishes one `customer_message` per WhatsApp message on `wa-inbound` and answers 200. No business logic, no database and no Meta access token: duplicates and everything else are handled downstream by `main-worker`.

Message format: [docs/contracts.md](../../docs/contracts.md#wa-inbound).

## Endpoints

| Method | Path | Behaviour |
|---|---|---|
| `GET` | `/webhook` | Meta verification. Echoes `hub.challenge` when `hub.mode=subscribe` and `hub.verify_token` matches; otherwise 403. |
| `POST` | `/webhook` | Verifies `X-Hub-Signature-256` (HMAC-SHA256 of the raw body, constant-time compare; 401 on mismatch). Publishes each `entry[].changes[].value.messages[]` item; ignores `statuses`. 500 if publishing fails, so Meta retries. |

## Environment

| Variable | Notes |
|---|---|
| `META_APP_SECRET` | Secret. HMAC key for the signature. |
| `META_VERIFY_TOKEN` | Secret. Token for the verification `GET`. |
| `WA_INBOUND_TOPIC` | Topic id (or full path) to publish to. |
| `GOOGLE_CLOUD_PROJECT` | Project used to build the topic path. |

## Run and test

```sh
uv run pytest services/wa-webhook
docker build -f services/wa-webhook/Dockerfile .
```
