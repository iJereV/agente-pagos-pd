# Contracts

Single source of truth for everything that crosses a service boundary. Every service implements against this file. Change it first, then the code.

## Conventions

- Python 3.12+, managed as a `uv` workspace (root `pyproject.toml`). Each deployable lives in its own folder with its own `pyproject.toml` and `Dockerfile`.
- Docker builds run from the repo root: `docker build -f services/<name>/Dockerfile .` so images can copy `libs/shared`.
- HTTP services use FastAPI + uvicorn and listen on `$PORT` (default `8080`).
- Money is always integer cents (`int`). Never floats.
- Timestamps are stored and compared in UTC (`datetime` with `tzinfo=UTC`, ISO 8601 in JSON).
- Code, comments, logs and docs are in English. Customer-facing agent replies are in Spanish (Argentina), because the customers are Argentine.
- Structured JSON logs to stdout (`{"severity": ..., "message": ..., ...}`) so Cloud Logging parses them.
- No HTTP access logs from the apps (uvicorn runs with `--no-access-log` / `access_log=False`): request lines carry query strings with tokens (`hub.verify_token`, link `?t=`). Cloud Run's own request logs still record the full URL.
- Tests with `pytest`. No real credentials or real personal data in fixtures: synthetic only.

## Repository layout

```
libs/shared/              shared package `shared` (tokens, pubsub envelope, logging, config helpers)
services/wa-webhook/      package `wa_webhook`      public Cloud Run
services/main-worker/     package `main_worker`     private Cloud Run
services/mcp-shop/        package `mcp_shop`        private Cloud Run (MCP server)
services/image-generator/ package `image_generator` private Cloud Run
services/link-web/        package `link_web`        public Cloud Run
agent/                    package `shop_agent`      ADK agent deployed to Agent Runtime
infra/terraform/          all GCP resources
infra/bootstrap/          one-time bootstrap (state bucket, first apply)
docs/                     contracts, architecture diagram
```

## Catalog and domain constants

| animal     | price (cents) |
|------------|---------------|
| `dog`      | 100           |
| `penguin`  | 300           |
| `capybara` | 500           |

- Prepaid balance: every customer gets a one-time welcome credit of `WELCOME_CREDIT_CENTS=1000`, granted by mcp-shop on the first balance-touching call as the movement `movements/welcome:{customer_id}` (created in the same transaction, so it is granted once).
- An order is accepted only when `balance >= order_total`; it is debited in the same transaction. The balance never goes negative.
- A verified transfer adds its amount to the balance. There is no debt and no allocation to orders.
- Quantity per line: 1 to 5.

## Pub/Sub topics

All messages: JSON object in `message.data` (base64 in push envelopes), UTF-8. Attribute `type` repeats the event type.

### `wa-inbound`

Published by `wa-webhook` (one Pub/Sub message per WhatsApp message; delivery `statuses` are ignored) and by `link-web` (system events).

```json
{
  "type": "customer_message",
  "wamid": "wamid.HBg...",
  "wa_id": "5490000000001",
  "timestamp": "2026-11-23T15:14:10Z",
  "message_type": "text | image | document | other",
  "text": "quiero dos perritos",
  "media_id": "1234567890",
  "mime_type": "image/jpeg",
  "profile_name": "Juan"
}
```

```json
{
  "type": "system_event",
  "event": "sign_in_completed",
  "event_id": "uuid4",
  "wa_id": "5490000000001",
  "timestamp": "2026-11-23T15:20:00Z",
  "data": {"customer_id": "<firebase uid>"}
}
```

### `order-created`

Published by `mcp-shop` after the order transaction commits.

```json
{
  "type": "order_created",
  "order_id": "ord_01J...",
  "customer_id": "<firebase uid>",
  "wa_id": "5490000000001",
  "items": [{"animal": "dog", "qty": 2}, {"animal": "capybara", "qty": 1}],
  "created_at": "2026-11-23T15:14:10Z"
}
```

### `order-ready`

Published by `image-generator` after all images and the manifest are stored.

```json
{
  "type": "order_ready",
  "order_id": "ord_01J...",
  "customer_id": "<firebase uid>",
  "wa_id": "5490000000001",
  "images": ["orders/ord_01J.../1.png", "orders/ord_01J.../2.png", "orders/ord_01J.../3.png"],
  "ready_at": "2026-11-23T15:15:02Z"
}
```

Every consumer is idempotent: Pub/Sub delivery is at least once.

## Tokens (`libs/shared/shared/tokens.py`)

Both tokens are JWTs (RS256) signed by `sa-main-worker` through IAM Credentials `signJwt`. Verification uses the service account's public JWKS at `https://www.googleapis.com/service_accounts/v1/jwk/<sa_email>`. For local development and tests, `TOKEN_SIGNER=local` switches to HS256 with `LOCAL_TOKEN_SECRET`.

### Turn token

Signed by `main-worker` before every agent turn, stored in session state key `turn_token`, sent by the agent's MCP connector as header `X-Turn-Token` on every MCP call.

```json
{
  "iss": "<sa-main-worker email>",
  "aud": "mcp-shop",
  "sub": "<customer_id or empty string when not linked>",
  "wa_id": "5490000000001",
  "auth_fresh": true,
  "last_receipt_ref": "receipts/<customer_id>/<wamid>.jpg or null",
  "iat": 1795473000,
  "exp": 1795473120
}
```

Lifetime: 120 seconds.

### Link token

Signed by `main-worker` when the agent requested a sign-in. Sent to the customer as the URL of a WhatsApp call-to-action button: `https://<LINK_WEB_URL>/link?t=<token>`.

```json
{"iss": "<sa-main-worker email>", "aud": "link-web", "wa_id": "5490000000001", "jti": "uuid4", "purpose": "link | reauth", "iat": 0, "exp": 0}
```

Lifetime: 600 seconds. Single use: `channel/link_tokens/{sha256(jti)}` is created at issue time and marked `used_at` by `link-web`. The link is `{LINK_WEB_URL}/link?t=<token>`, where `LINK_WEB_URL` includes the scheme (`https://...`).

## HTTP endpoints

| Service | Endpoint |
|---|---|
| wa-webhook | `GET /webhook` (verification), `POST /webhook` (events) |
| main-worker | `POST /pubsub/wa-inbound`, `POST /pubsub/order-ready` |
| image-generator | `POST /pubsub/order-created` |
| mcp-shop | `/mcp` (streamable HTTP), `GET /health` |
| link-web | `GET /link`, `POST /api/link` (400 invalid link, 401 invalid Google token, 403 not a Google sign-in, 409 binding conflict incl. `account_linked_to_other_number`, 410 link used or expired) |

Pub/Sub push OIDC audience is the service root URI. Timeouts: main-worker 300 s, image-generator 600 s, mcp-shop 120 s.

### Shared API

```python
# shared/tokens.py
@dataclass(frozen=True)
class TurnClaims: customer_id: str | None; wa_id: str; auth_fresh: bool; last_receipt_ref: str | None
@dataclass(frozen=True)
class LinkClaims: wa_id: str; jti: str; purpose: str

class TokenSigner(Protocol):
    def sign(self, claims: dict) -> str: ...

def make_signer() -> TokenSigner: ...            # IamSigner(SIGNER_SA_EMAIL) or LocalSigner
def issue_turn_token(signer, *, customer_id, wa_id, auth_fresh, last_receipt_ref) -> str
def issue_link_token(signer, *, wa_id, purpose) -> tuple[str, str]   # (token, jti)
def verify_turn_token(token: str) -> TurnClaims    # raises InvalidToken
def verify_link_token(token: str) -> LinkClaims    # raises InvalidToken
class InvalidToken(Exception): ...
class ExpiredToken(InvalidToken): ...             # link-web answers 410 for it
```

Verifiers read `TOKEN_SIGNER` (`iam` or `local`) and `TOKEN_ISSUER` (the main-worker service account email; in local mode it must equal the signer's `SIGNER_SA_EMAIL`, default `local-signer`). The signer sets `iss` itself.

`shared/pubsub.py`: `decode_push(body: dict) -> tuple[dict, dict]` returning `(payload, attributes)`, and `publish_json(topic: str, payload: dict, **attributes) -> str` (attribute `type` defaults to `payload["type"]`).

## Agent session

- App: the Agent Runtime resource. `user_id = wa_id`. One active session per `wa_id`, pointer in `channel/wa_sessions/{wa_id}`.
- Rotation: new session when `now - last_activity > SESSION_IDLE_HOURS` (24).
- State keys written by main-worker before each turn: `wa_id`, `customer_id`, `is_linked`, `auth_fresh`, `turn_token`. Written by the agent: `sign_in_requested` (bool, reset by main-worker after the turn).
- Turn input: customer text as-is; images as `"[image received]"` plus any caption; documents as `"[document received]"`; other types as `"[unsupported message received]"`; system events as a single line `SYSTEM_EVENT {json}` with no customer ids, e.g. `SYSTEM_EVENT {"event":"sign_in_completed"}` and `SYSTEM_EVENT {"event":"order_ready","order_id":"ord_...","image_count":3}`. The agent replies with plain text only.
- Failed turn: when the turn raises or returns no text, main-worker does not retry it (no second model call). A customer message gets the fixed reply `Perdón, tuve un problema para responderte. Probá de nuevo en un ratito.`; an `order_ready` delivery still sends the images, with the fixed caption `¡Listo! Acá tenés tus imágenes.`; other system events send nothing. Session errors before the turn are still retried through Pub/Sub.
- Placeholder: when the agent wants a sign-in it calls `request_sign_in()` and writes `{{SIGN_IN_LINK}}` in its reply. main-worker removes the placeholder and sends the reply as an interactive `cta_url` message whose button ("Iniciar sesión") opens the link. A reply over 1024 characters goes out as text followed by a separate button message; an empty reply gets a default button text. The link never appears in the message text.

## MCP server (`mcp-shop`)

Streamable HTTP MCP endpoint at `/mcp`. Cloud Run IAM (only `sa-agent` may invoke) plus `X-Turn-Token` on every request.

| Tool | Arguments | Requires | Returns (JSON) |
|---|---|---|---|
| `get_balance` | none | linked + `auth_fresh` | `{"status": "ok", "balance_cents", "welcome_credit_cents"}` or `{"status": "auth_required" \| "not_linked"}` |
| `create_order` | `items: [{"animal": "dog"\|"penguin"\|"capybara", "qty": 1..5}]` | linked + `auth_fresh` | `{"status": "created", "order_id", "total_cents", "balance_cents", "welcome_credit_cents"}` (balance after the debit) or `{"status": "insufficient_balance", "balance_cents", "total_cents", "payment_needed_cents", "welcome_credit_cents"}` (`total - balance`; the welcome credit is stored even though the order is refused) / `auth_required` / `not_linked` / `invalid_items` |
| `verify_receipt` | none | linked | `{"status": "credited", "amount_cents", "balance_cents", "welcome_credit_cents"}` (balance after the credit) or `already_used` / `not_found_yet` / `manual_review` / `not_a_receipt` / `no_receipt` / `temporarily_unavailable` (the receipt could not be read right now; nothing was recorded, send it again) / `not_linked` |
| `get_order_status` | `order_id: str` | linked | `{"status": "ok", "order_status": "unpaid"\|"partially_paid"\|"paid", "total_cents", "paid_cents"}` or `not_found` (new orders are always `paid`; the other values only appear on orders from the earlier credit model) |

`welcome_credit_cents` is the welcome credit granted by that same call (a new customer's first balance, order or payment), so the agent can announce it exactly once; it is `0` afterwards.

Local agent tools (not in mcp-shop): `get_catalog()`, `request_sign_in()`.

A missing, expired or forged `X-Turn-Token` is an MCP tool error (`isError`), not an outcome: it means the caller is broken, not the customer.

Manual review reasons: `amount_mismatch`, `near_coelsa_id`, `coelsa_mismatch`, `multiple_candidates`, `unreadable_receipt`. Document id: first 32 hex chars of `sha256(receipt_ref)`.

Matching: an exact COELSA id + amount match wins. When the receipt shows a COELSA id that no candidate has, the amount + CUIT + window fallback is not used: same-amount candidates → `manual_review` (`coelsa_mismatch`), none → `not_found_yet`. The fallback applies only to receipts without a COELSA id.

## Firestore

Two databases.

`channel` (main-worker, link-web):

```
customers/{uid}            email, wa_id, linked_at, last_sign_in_at
wa_links/{wa_id}           customer_id, linked_at
wa_sessions/{wa_id}        session_id, last_activity, last_inbound_at, last_receipt_ref
link_tokens/{sha256(jti)}  wa_id, purpose, expires_at, used_at
deliveries/{order_id}      status (delivered | awaiting_window), delivered_at, wa_id, customer_id, images[]
                           (all fields kept for every status)
processed_messages/{id}    processed_at   (id = wamid or system event_id)
```

`shop` (mcp-shop only):

```
accounts/{customer_id}     balance_cents   (legacy credit_balance_cents is read as the balance
                           and removed on the next write)
movements/{movement_id}    customer_id, kind (welcome_credit | order | payment), amount_cents (signed),
                           balance_after_cents, reference, created_at
                           (id = welcome:{customer_id} | order:{order_id} | payment:{payment_key};
                           create-only)
orders/{order_id}          customer_id, wa_id, items[], total_cents, paid_cents, status, created_at,
                           event_published (outbox flag for order_created)
payments/{e2e_id}          provider, provider_payment_id, amount_cents, received_at, payer_cuit,
                           customer_id, match_method (coelsa_id | amount_cuit_window),
                           receipt_ref, created_at
manual_reviews/{id}        customer_id, receipt_ref, reason, extracted{}, candidates[], created_at
```

Composite indexes (Terraform): `shop/orders` on `customer_id` + `status` (no longer queried since the prepaid model), `shop/orders` on `customer_id` + `event_published`, `channel/deliveries` on `wa_id` + `status`.

## Cloud Storage

Bucket `${PROJECT_ID}-media`, `us-central1`, uniform access, private.

```
orders/{order_id}/{n}.png
orders/{order_id}/manifest.json     {"order_id", "images": [...], "variants": [...], "model", "created_at"}
receipts/{customer_id or wa_id}/{wamid}.{ext}
```

## Environment variables

Secrets come from Secret Manager, mounted as env vars by Cloud Run.

| Variable | Used by | Secret | Notes |
|---|---|---|---|
| `GOOGLE_CLOUD_PROJECT` | all | | |
| `GOOGLE_CLOUD_LOCATION` | all | | `us-central1` |
| `PORT` | HTTP services | | set by Cloud Run, default `8080` |
| `META_APP_SECRET` | wa-webhook | yes | HMAC for `X-Hub-Signature-256` |
| `META_VERIFY_TOKEN` | wa-webhook | yes | webhook verification `GET` |
| `WA_INBOUND_TOPIC` | wa-webhook, link-web | | topic id |
| `META_ACCESS_TOKEN` | main-worker | yes | system user token |
| `WA_PHONE_NUMBER_ID` | main-worker | | |
| `META_GRAPH_VERSION` | main-worker | | default `v21.0` |
| `WA_ORDER_READY_TEMPLATE` | main-worker | | template used outside the 24 h window, default `hello_world` |
| `WA_TEMPLATE_LANG` | main-worker | | default `en_US` |
| `AGENT_RESOURCE_NAME` | main-worker | | `projects/.../locations/.../reasoningEngines/...` |
| `FIRESTORE_CHANNEL_DB` | main-worker, link-web | | `channel` |
| `FIRESTORE_SHOP_DB` | mcp-shop | | `shop` |
| `MEDIA_BUCKET` | main-worker, mcp-shop, image-generator | | |
| `LINK_WEB_URL` | main-worker | | public URL of link-web |
| `SESSION_IDLE_HOURS` | main-worker | | default `24` |
| `AUTH_FRESH_HOURS` | main-worker | | default `24` |
| `TOKEN_SIGNER` | main-worker | | `iam` (default) or `local` |
| `SIGNER_SA_EMAIL` | main-worker | | its own service account |
| `TOKEN_ISSUER` | mcp-shop, link-web | | main-worker service account email |
| `LOCAL_TOKEN_SECRET` | local dev only | | HS256 key when `TOKEN_SIGNER=local` |
| `MP_ACCESS_TOKEN` | mcp-shop | yes | production token of the collecting account |
| `MP_COLLECTOR_ID` | mcp-shop | | numeric MP user id of the shop account |
| `TRANSFER_VERIFIER` | mcp-shop | | `mercadopago` or `simulated` |
| `ORDER_CREATED_TOPIC` | mcp-shop | | |
| `EXTRACTION_MODEL` | mcp-shop | | default `meta/llama-4-maverick-17b-128e-instruct-maas` (open model on Vertex AI, OpenAI-compatible endpoint; enable it once in Model Garden); a bare id such as `gemini-3.5-flash` is Gemini and needs a paid billing account |
| `EXTRACTION_MODEL_LOCATION` | mcp-shop | | default `us-east5` (where the extraction model is served; `global` for Gemini) |
| `WELCOME_CREDIT_CENTS` | mcp-shop | | default `1000`; one-time welcome credit per customer |
| `MATCH_WINDOW_MINUTES` | mcp-shop | | default `120` |
| `SIMULATED_TRANSFERS_PATH` | mcp-shop | | optional fixture for `TRANSFER_VERIFIER=simulated` |
| `TOKEN_SIGNER` | mcp-shop, link-web | | must match main-worker's mode |
| `ORDER_READY_TOPIC` | image-generator | | |
| `IMAGE_MODEL` | image-generator | | default `@cf/black-forest-labs/flux-1-schnell` (Cloudflare Workers AI); any id without `@cf/` is a Gemini image model on Vertex AI |
| `CLOUDFLARE_ACCOUNT_ID` | image-generator | | Cloudflare account for `@cf/` models |
| `CLOUDFLARE_API_TOKEN` | image-generator | yes | Workers AI token, for `@cf/` models |
| `IMAGE_MODEL_LOCATION` | image-generator | | default `global` (where a Gemini image model is served; ignored for `@cf/`) |
| `DAILY_GENERATION_CAP` | image-generator | | default `200` images per day |
| `IDENTITY_API_KEY` | link-web | | Identity Platform web API key (public by design) |
| `IDENTITY_AUTH_DOMAIN` | link-web | | `<project>.firebaseapp.com` |
| `MCP_SHOP_URL` | agent | | `https://<mcp-shop>/mcp` |
| `AGENT_MODEL` | agent | | default `vertex_ai/openai/gpt-oss-120b-maas` (LiteLLM); a Gemini id such as `gemini-3.5-flash` needs a paid billing account |
| `PAYMENT_ALIAS`, `PAYMENT_CVU`, `PAYMENT_HOLDER` | agent | yes (alias or CVU) | where customers transfer to; returned by `get_payment_details` |
| `AGENT_MODEL_LOCATION` | agent | | default `global` (where the agent model is served; the agent runs in `GOOGLE_CLOUD_LOCATION`) |
| `MCP_TIMEOUT_SECONDS` | agent | | default `30` (MCP session setup; covers mcp-shop cold starts) |

## Service accounts

`sa-wa-webhook`, `sa-main-worker`, `sa-agent` (also `logging.logWriter`, `cloudtrace.agent`, `monitoring.metricWriter` for Agent Runtime telemetry), `sa-mcp-shop`, `sa-image-generator`, `sa-link-web`, `sa-pubsub-push`, `sa-ci-deployer`. Permissions as in the design plan's service account table; `sa-link-web` may also publish to `wa-inbound`.
