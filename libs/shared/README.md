# shared

Library used by every service. The binding contract is [docs/contracts.md](../../docs/contracts.md).

| Module | Purpose |
|---|---|
| `shared.tokens` | Issue and verify the turn token (`aud=mcp-shop`, 120 s) and the link token (`aud=link-web`, 600 s). |
| `shared.pubsub` | `decode_push` for push envelopes, `publish_json` for JSON messages with a `type` attribute. |
| `shared.logging` | `setup_logging()`: JSON lines on stdout with a `severity` key for Cloud Logging. |
| `shared.config` | Small typed environment helpers. |

## Tokens

- `TOKEN_SIGNER=iam` (default): signs with IAM Credentials `signJwt` as `SIGNER_SA_EMAIL`; verifies RS256 against `https://www.googleapis.com/service_accounts/v1/jwk/<TOKEN_ISSUER>`.
- `TOKEN_SIGNER=local`: HS256 with `LOCAL_TOKEN_SECRET`, for local runs and tests. Verifiers must use the same mode, and `TOKEN_ISSUER` must equal the signer's `SIGNER_SA_EMAIL` (default `local-signer`).
- Verification raises `InvalidToken`; an authentic but expired token raises its subclass `ExpiredToken` (link-web answers 410 for it).

## Tests

```sh
uv run pytest libs/shared
```
