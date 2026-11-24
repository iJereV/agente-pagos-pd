# mcp-shop

The deterministic half of the shop. The agent decides what a customer wants and writes the
reply; this service validates, reads the truth and moves money. It is an MCP server
(streamable HTTP at `/mcp`) on a private Cloud Run service that only `sa-agent` may invoke.

## The hexagon

```
                 MCP client (shop agent)
                          │  X-Turn-Token
                          ▼
   server.py ──── driving adapter: MCP tools + GET /health
                          │
   application/ ── use cases: get_balance, create_order, verify_receipt, get_order_status
                          │
   domain/ ─────── pure rules: catalog, credit limit, ledger, allocation, matching, parsing
                          │
   ports/ ──────── TokenVerifier · ShopRepository · TransferVerifier · ReceiptStore
                   ReceiptExtractor · EventPublisher
                          │
   adapters/ ───── turn_token (shared.tokens) · firestore_repository · mercadopago · simulated
                   gcs_receipts · gemini_extractor · pubsub_publisher (shared.pubsub)
```

- `domain/` has no I/O and no framework imports. Every money rule lives there and is unit tested.
- `application/` depends only on `domain/` and `ports/`. Use cases are tested with in-memory fakes.
- `bootstrap.py` is the only place that knows which adapter backs each port.

## Identity

Every tool call must carry `X-Turn-Token`, a short-lived JWT signed by main-worker. The server
verifies it and takes `customer_id`, `wa_id`, `auth_fresh` and `last_receipt_ref` from its claims.
No tool argument carries identity, so a compromised agent can only act as the customer in a valid
token. A missing or invalid token is a tool error, not a closed outcome.

## Tools and outcomes

| Tool | Arguments | Access | Outcomes |
|---|---|---|---|
| `get_balance` | none | linked + fresh sign-in | `ok`, `auth_required`, `not_linked` |
| `create_order` | `items: [{animal, qty}]` | linked + fresh sign-in | `created`, `credit_limit`, `invalid_items`, `auth_required`, `not_linked` |
| `verify_receipt` | none | linked | `credited`, `already_used`, `not_found_yet`, `manual_review`, `not_a_receipt`, `no_receipt`, `not_linked` |
| `get_order_status` | `order_id` | linked | `ok`, `not_found`, `not_linked` |

Response shapes are defined in [`docs/contracts.md`](../../docs/contracts.md). Money is always
integer cents.

## Domain rules

- **Credit:** an order is accepted when `debt - credit_balance + total <= CREDIT_LIMIT_CENTS`.
  The credit balance pays the new order first.
- **Allocation:** a payment pays the oldest unpaid order first; the remainder becomes credit
  balance. Order status is `unpaid`, `partially_paid` or `paid`.
- **Receipts:** Gemini only copies fields as printed (`amount_text`, `datetime_local_text`, ...).
  Code parses the Argentine amount (`$ 2.166,35` → `216635`) and converts the local time
  (America/Argentina/Buenos_Aires) to UTC.
- **Matching** against incoming transfers from the provider. A receipt that shows a COELSA id
  can only be matched by that id:
  1. exact id and exact amount → match (`coelsa_id`);
  2. same id but another amount (`amount_mismatch`), or an id that differs only by O/0 or one
     character (`near_coelsa_id`) → `manual_review`;
  3. no such id, but same-amount transfers in the window → `manual_review` (`coelsa_mismatch`);
     none → `not_found_yet` (the transfer may not have arrived).

  Only a receipt without a COELSA id uses the fallback: exact amount, compatible origin CUIT
  (compared when both sides have one) and a UTC window of `MATCH_WINDOW_MINUTES`. One candidate
  → match (`amount_cuit_window`), several → `manual_review` (`multiple_candidates`), none →
  `not_found_yet`. An unparseable amount → `manual_review` (`unreadable_receipt`).
- **Recording:** one Firestore transaction creates `payments/{e2e_id}` (exists → `already_used`),
  allocates and updates orders and account. The credited amount is always the provider's.

## Environment

| Variable | Default | Notes |
|---|---|---|
| `GOOGLE_CLOUD_PROJECT` | | |
| `GOOGLE_CLOUD_LOCATION` | `us-central1` | Vertex AI region for extraction |
| `FIRESTORE_SHOP_DB` | `shop` | named Firestore database |
| `MEDIA_BUCKET` | | required; receipts are read under `receipts/` |
| `TOKEN_SIGNER` | `iam` | `local` switches verification to HS256 for local runs |
| `TOKEN_ISSUER` | | main-worker service account email (in local mode, equals `SIGNER_SA_EMAIL`) |
| `LOCAL_TOKEN_SECRET` | | HS256 key, local runs only |
| `TRANSFER_VERIFIER` | `mercadopago` | `mercadopago` or `simulated` |
| `MP_ACCESS_TOKEN` | | secret; required for `mercadopago` |
| `MP_COLLECTOR_ID` | | shop's MP user id; required for `mercadopago` |
| `SIMULATED_TRANSFERS_PATH` | bundled fixture | JSON list of transfers for `simulated` |
| `ORDER_CREATED_TOPIC` | | required |
| `EXTRACTION_MODEL` | `gemini-3.5-flash` | |
| `EXTRACTION_MODEL_LOCATION` | `global` | Vertex AI location of the extraction model |
| `CREDIT_LIMIT_CENTS` | `1000` | |
| `MATCH_WINDOW_MINUTES` | `120` | |
| `PORT` | `8080` | |

## Run and test

```bash
uv run pytest services/mcp-shop                     # from the repo root
docker build -f services/mcp-shop/Dockerfile .       # image built from the repo root
```

Local runs: set `TRANSFER_VERIFIER=simulated`, `TOKEN_SIGNER=local` and
`FIRESTORE_EMULATOR_HOST` (the Firestore client picks it up), then `python -m mcp_shop`.
The bundled fixture holds synthetic transfers only; a receipt reading `SIMCOELSA0000000000001`
lands in manual review because the fixture's id has a zero where the receipt has an O.

## Notes

- Unpaid orders are queried by `customer_id` and `status in [unpaid, partially_paid]`, and the
  outbox by `customer_id` and `event_published`; both are sorted in memory. Terraform creates a
  composite index for each (`google_firestore_index` in `infra/terraform/firestore.tf`).
- `GET /health` backs the Cloud Run startup and liveness probes.
- `order-created` goes through an outbox. The order is committed with `event_published=false`,
  the event is published after the commit (3 attempts, 0.2 s then 0.4 s backoff) and only then is
  the flag set. If every attempt fails the tool still answers `created`, so the agent never
  retries into a duplicate order, and the customer's next tool call publishes the pending orders
  first. Consumers are idempotent per order, so a repeated event is harmless.
