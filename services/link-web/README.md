# link-web

Public Cloud Run service behind the one-time sign-in link that main-worker sends on
WhatsApp. The customer signs in with Google (Identity Platform); link-web binds the
WhatsApp number to the Google account on first use, or checks that it is the same
account on re-authentication, then tells main-worker through a `sign_in_completed`
system event on `wa-inbound`.

Token, Firestore and event shapes are defined in [docs/contracts.md](../../docs/contracts.md).

## Endpoints

| Method | Path | Behaviour |
|---|---|---|
| `GET` | `/link?t=<link token>` | Sign-in page (Spanish copy). Loads the Firebase JS SDK from `gstatic.com`, signs in with Google (popup, redirect fallback) and posts both tokens to `/api/link`. Sent with `Referrer-Policy: no-referrer` and `Cache-Control: no-store` because the token is in the URL; the server never echoes the token. |
| `POST` | `/api/link` | Body `{"link_token", "id_token"}`. `200 {"status": "linked" \| "reauthenticated"}` or `{"status": <code>}` with 400 (`invalid_link`, `token_not_found`, `token_mismatch`), 401 (`invalid_identity`), 403 (`google_account_required`), 409 (`not_linked`, `account_mismatch`, `number_linked_to_other_account`, `account_linked_to_other_number`), 410 (`token_used`, `token_expired`, including a link token past its JWT `exp`). |

## Flow of `POST /api/link`

1. Verify the link token with `shared.tokens.verify_link_token` (signature, `aud`, `exp`).
2. Verify the Identity Platform ID token (`google.oauth2.id_token.verify_firebase_token`,
   audience = project id) and require `sign_in_provider == "google.com"` and a verified
   email. This happens before the single-use token is touched, so a failed sign-in
   does not burn the link.
3. In one Firestore transaction on the `channel` database: read
   `link_tokens/{sha256(jti)}`, `wa_links/{wa_id}` and `customers/{uid}`; apply the rules
   in `link_web/domain.py`; on acceptance mark the token `used_at`, create
   `wa_links/{wa_id}` on first link, and merge `customers/{uid}` (`email`, `wa_id`,
   `last_sign_in_at`, plus `linked_at` on first link). Rejections write nothing, so the
   customer can retry the same link with the right Google account.
4. Publish `sign_in_completed` to `WA_INBOUND_TOPIC`. A publish failure is logged and
   the request still succeeds: the binding is committed and the token spent.

Rules: `link` rejects a number bound to another uid and a uid bound to another
number; `reauth` requires the number to be bound to the same uid.

## Layout

```
link_web/
  domain.py     rules (decide), token hash, document fields
  ports.py      LinkTokenVerifier, IdentityVerifier, ChannelStore, EventPublisher
  service.py    use case
  page.py       HTML page
  app.py        FastAPI routes (driving adapter)
  main.py       composition root
  adapters/     Firestore, Identity Platform token verification, shared tokens and Pub/Sub
```

## Environment

`GOOGLE_CLOUD_PROJECT` (also the ID token audience), `FIRESTORE_CHANNEL_DB` (default
`channel`), `WA_INBOUND_TOPIC`, `IDENTITY_API_KEY`, `IDENTITY_AUTH_DOMAIN`,
`TOKEN_SIGNER` and `TOKEN_ISSUER` (read by `shared.tokens`), `PORT` (default `8080`).

Identity Platform must list the link-web host among its authorized domains. Browsers
that block third-party storage can break the redirect fallback when the page host and
`IDENTITY_AUTH_DOMAIN` differ; the popup flow is the primary path.

## Run and test

```sh
uv run --package link-web pytest services/link-web/tests
docker build -f services/link-web/Dockerfile .
```
