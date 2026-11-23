# main-worker

Private Cloud Run service; only the Pub/Sub push service account can invoke it. It turns each WhatsApp message or event into one agent turn on Agent Runtime and relays the agent's plain-text reply. It is the only holder of the Meta access token and the only signer of turn and link tokens.

Contracts (messages, tokens, Firestore layout, session state): [docs/contracts.md](../../docs/contracts.md).

## Endpoints

| Method | Path | Subscription | Behaviour |
|---|---|---|---|
| `POST` | `/pubsub/wa-inbound` | `wa-inbound` | `customer_message` and `system_event`. |
| `POST` | `/pubsub/order-ready` | `order-ready` | Delivers an order: agent text plus images, or a template outside the 24 h window. |

Acknowledgement policy: 204 on success and on permanent errors (malformed message, 4xx from Meta), which are logged; 503/500 on transient or unexpected errors so Pub/Sub retries and eventually dead-letters.

## Flow of a customer message

1. Claim `processed_messages/{wamid}` (create-if-absent). Already there: acknowledge and stop. The claim is released if processing fails with a retryable error.
2. Resolve `wa_links/{wa_id}`; `auth_fresh` when `customers/{uid}.last_sign_in_at` is within `AUTH_FRESH_HOURS`.
3. Images and documents: download from the Graph API and store at `receipts/{customer_id or wa_id}/{wamid}.{ext}`.
4. Reuse the session in `wa_sessions/{wa_id}` or rotate it after `SESSION_IDLE_HOURS` idle. Sign a turn token and write `wa_id`, `customer_id`, `is_linked`, `auth_fresh`, `turn_token` into session state.
5. Run the turn. If the agent set `sign_in_requested`, issue a link token (`link_tokens/{sha256(jti)}`), put the link where `{{SIGN_IN_LINK}}` is (or append it) and reset the flag.
6. Send the reply, then any `deliveries` waiting for the window for this `wa_id` (query on `wa_id` + `status`, backed by a composite index in Terraform). Every `deliveries/{order_id}` document keeps `status`, `delivered_at`, `wa_id`, `customer_id` and `images`.

## Code layout

```
main_worker/
  domain/        events, policy (freshness, rotation, 24 h window), text rendering
  application/   Conversation (one turn), InboundHandler, OrderDeliveries
  ports.py       ChannelStore, MediaStore, WhatsApp, AgentRuntime
  adapters/      Firestore, Cloud Storage, Graph API, Vertex AI Agent Engine
  api.py         push endpoints and ack policy
  main.py        composition root
tests/           in-memory fakes; no cloud access needed
```

## Environment

`GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `AGENT_RESOURCE_NAME`, `FIRESTORE_CHANNEL_DB`, `MEDIA_BUCKET`, `META_ACCESS_TOKEN` (secret), `WA_PHONE_NUMBER_ID`, `META_GRAPH_VERSION`, `WA_ORDER_READY_TEMPLATE`, `WA_TEMPLATE_LANG`, `LINK_WEB_URL`, `SESSION_IDLE_HOURS`, `AUTH_FRESH_HOURS`, `TOKEN_SIGNER`, `SIGNER_SA_EMAIL`, `LOCAL_TOKEN_SECRET` (local only). Defaults are in the contract.

## Run and test

```sh
uv run pytest services/main-worker
docker build -f services/main-worker/Dockerfile .
```
