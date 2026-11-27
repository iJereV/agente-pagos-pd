# Setup

Everything needed to stand the system up from an empty GCP project, then to work on it locally. Placeholders look like `<PROJECT_ID>`; never commit real values.

Order of the steps matters: the first Terraform apply uses placeholder images and no secrets, so the infrastructure exists before any service needs it.

1. [Prerequisites](#1-prerequisites)
2. [Meta app and WhatsApp test number](#2-meta-app-and-whatsapp-test-number)
3. [Mercado Pago](#3-mercado-pago)
4. [Google OAuth client for Identity Platform](#4-google-oauth-client-for-identity-platform)
5. [Bootstrap](#5-bootstrap)
6. [First apply with placeholder images](#6-first-apply-with-placeholder-images)
7. [Secret values](#7-secret-values)
8. [Build and push the images](#8-build-and-push-the-images)
9. [Deploy the agent](#9-deploy-the-agent)
10. [Second apply](#10-second-apply)
11. [Connect the WhatsApp webhook](#11-connect-the-whatsapp-webhook)
12. [GitHub Actions](#12-github-actions)
13. [Local development](#13-local-development)
14. [Environment variables](#14-environment-variables)

## 1. Prerequisites

- A GCP project with billing enabled, and Owner on it for the first apply.
- [gcloud](https://cloud.google.com/sdk/docs/install), [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.6, [uv](https://docs.astral.sh/uv/), Docker.
- A Meta developer account and a Mercado Pago account that receives the transfers.

```sh
gcloud auth login
gcloud auth application-default login
gcloud config set project <PROJECT_ID>
```

## 2. Meta app and WhatsApp test number

1. In [Meta for Developers](https://developers.facebook.com/apps), create a **Business** app and add the **WhatsApp** product. Meta gives you a test phone number and a WhatsApp Business Account (WABA).
2. **WhatsApp > API Setup**: copy the **Phone number ID** (`WA_PHONE_NUMBER_ID`) and the **WhatsApp Business Account ID** (`<WABA_ID>`, used in step 11). Add your own phone as a recipient: the test number only messages verified recipients.
3. **App settings > Basic**: copy the **App secret** (`META_APP_SECRET`). wa-webhook uses it to check `X-Hub-Signature-256`.
4. Choose a random **verify token** (`META_VERIFY_TOKEN`), for example `openssl rand -hex 24`. You type the same value in Meta in step 11.
5. **Permanent access token**: in [Business Settings](https://business.facebook.com/settings) > **Users > System users**, create a system user, assign it the app and the WABA, and generate a token with `whatsapp_business_messaging` and `whatsapp_business_management`, expiration *Never*. This is `META_ACCESS_TOKEN`. The temporary token on the API Setup page expires in 24 h; do not use it.

Two WhatsApp rules shape the design:

- **24-hour window.** Free-form messages are allowed only within 24 h of the customer's last message. Outside it, main-worker sends a template (`WA_ORDER_READY_TEMPLATE`).
- On the test number **`hello_world` is the only approved template**, so it is the default. Create and approve your own template once you move to a real number.

## 3. Mercado Pago

1. In [Mercado Pago Developers](https://www.mercadopago.com.ar/developers/panel/app), create an application on the account that receives the transfers.
2. **Production credentials > Access token** (`APP_USR-...`): this is `MP_ACCESS_TOKEN`. Test credentials do not see real transfers.
3. The **collector id** (`MP_COLLECTOR_ID`) is the numeric user id of that account. It is the number after the last `-` in the access token, or:

   ```sh
   curl -s -H "Authorization: Bearer <MP_ACCESS_TOKEN>" https://api.mercadopago.com/users/me | jq .id
   ```

To run without Mercado Pago, set `transfer_verifier = "simulated"`.

## 4. Google OAuth client for Identity Platform

Identity Platform's Google provider needs an OAuth web client, which Terraform cannot create.

1. **APIs & Services > OAuth consent screen**: configure it (External, app name, support email). Scopes: `openid`, `email`, `profile`.
2. **APIs & Services > Credentials > Create credentials > OAuth client ID**, type **Web application**.
   - Authorized JavaScript origins: `https://<PROJECT_ID>.firebaseapp.com` and the link-web URL (after step 6).
   - Authorized redirect URI: `https://<PROJECT_ID>.firebaseapp.com/__/auth/handler`.
3. Copy the client id and secret into `terraform.tfvars` (`google_oauth_client_id`, `google_oauth_client_secret`). The secret variable is marked sensitive; it still ends up in the Terraform state, which lives in a private, versioned bucket.

## 5. Bootstrap

```sh
infra/bootstrap/bootstrap.sh <PROJECT_ID>
```

Creates `gs://<PROJECT_ID>-tfstate` (versioned), enables the APIs Terraform needs to start and runs `terraform init`. Idempotent. See [infra/bootstrap/README.md](infra/bootstrap/README.md).

## 6. First apply with placeholder images

```sh
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # fill it in; keep use_placeholder_images = true
terraform apply
```

`github_repository` (`<OWNER>/<REPO>`) is required: it is the only repository allowed to deploy through Workload Identity Federation (step 12).

This creates the APIs, service accounts and IAM, both Firestore databases with the composite indexes the services query, the media bucket, topics and subscriptions, secret containers, Artifact Registry, Identity Platform, the Workload Identity pool and the five Cloud Run services running Google's `hello` container. Secrets are not attached yet because they have no values.

If the organization enforces domain-restricted sharing, the `allUsers` invoker on `wa-webhook` and `link-web` fails; allow it for this project or use an organization-less project.

Useful outputs: `terraform output service_urls`, `terraform output wa_webhook_url`.

## 7. Secret values

Terraform creates the secret containers only. Add the values from your shell so they never reach the state or the repository:

```sh
printf '%s' '<META_APP_SECRET>'   | gcloud secrets versions add meta-app-secret   --data-file=-
printf '%s' '<META_VERIFY_TOKEN>' | gcloud secrets versions add meta-verify-token --data-file=-
printf '%s' '<META_ACCESS_TOKEN>' | gcloud secrets versions add meta-access-token --data-file=-
printf '%s' '<MP_ACCESS_TOKEN>'   | gcloud secrets versions add mp-access-token   --data-file=-
printf '%s' '<CLOUDFLARE_API_TOKEN>' | gcloud secrets versions add cloudflare-api-token --data-file=-
```

Rotating a secret is the same command; Cloud Run picks `latest` on the next revision.

## 8. Build and push the images

Images build from the repo root so they can copy `libs/shared`:

```sh
REGISTRY=us-central1-docker.pkg.dev/<PROJECT_ID>/agente-pagos
TAG=$(git rev-parse --short HEAD)
gcloud auth configure-docker us-central1-docker.pkg.dev

for svc in wa-webhook main-worker mcp-shop image-generator link-web; do
  docker build -f services/$svc/Dockerfile -t $REGISTRY/$svc:$TAG .
  docker push $REGISTRY/$svc:$TAG
done
```

Then deploy them (the agent needs mcp-shop running):

```sh
terraform -chdir=infra/terraform apply -var use_placeholder_images=false -var image_tag=$TAG
```

## 9. Deploy the agent

```sh
cd infra/terraform
export GOOGLE_CLOUD_PROJECT=<PROJECT_ID> GOOGLE_CLOUD_LOCATION=us-central1
export MCP_SHOP_URL=$(terraform output -raw mcp_shop_url)
export AGENT_SERVICE_ACCOUNT=$(terraform output -json service_account_emails | jq -r '."sa-agent"')
export AGENT_STAGING_BUCKET=gs://$(terraform output -raw agent_staging_bucket)
cd ../..
uv sync --all-packages
uv run python agent/deploy.py
```

The last line printed is the Agent Runtime resource name, `projects/<PROJECT_NUMBER>/locations/us-central1/reasoningEngines/<ID>`. Put it in `terraform.tfvars` as `agent_resource_name`.

Google's Agents CLI (`agents-cli deploy --deployment-target agent_runtime ...`) is an alternative; it builds a container from a `Dockerfile` and creates a different kind of resource. See [agent/README.md](agent/README.md#agents-cli-interactive-alternative). CI uses `deploy.py`.

## 10. Second apply

```sh
terraform -chdir=infra/terraform apply -var use_placeholder_images=false -var image_tag=$TAG
```

main-worker now has `AGENT_RESOURCE_NAME`. Set `use_placeholder_images = false` in `terraform.tfvars` too, so later local applies do not revert to the placeholder.

## 11. Connect the WhatsApp webhook

1. Meta app > **WhatsApp > Configuration > Webhook > Edit**:
   - Callback URL: `terraform output -raw wa_webhook_url`
   - Verify token: the `META_VERIFY_TOKEN` value from step 7.

   Meta calls the URL with a `GET` to verify it.
2. In **Webhook fields**, subscribe to `messages`.
3. Subscribe the app to the WABA so its events reach the webhook:

   ```sh
   curl -X POST "https://graph.facebook.com/v21.0/<WABA_ID>/subscribed_apps" \
     -H "Authorization: Bearer <META_ACCESS_TOKEN>"
   ```

4. Send "hola" from your verified phone to the test number.

## 12. GitHub Actions

`deploy.yml` authenticates through Workload Identity Federation: only workflows of the repository in `github_repository` running on `main` can impersonate `sa-ci-deployer`. There are no JSON keys. CI passes its own repository (`github.repository`) as `TF_VAR_github_repository`, so keep `terraform.tfvars` equal to it.

**Repository variables** (Settings > Secrets and variables > Actions > Variables):

| Variable | Value |
|---|---|
| `GCP_PROJECT_ID` | `<PROJECT_ID>` |
| `GCP_WIF_PROVIDER` | `terraform output -raw workload_identity_provider` |
| `GCP_DEPLOYER_SA` | `terraform output -raw ci_deployer_email` |
| `WA_PHONE_NUMBER_ID` | same as `terraform.tfvars` |
| `MP_COLLECTOR_ID` | same as `terraform.tfvars` |
| `TRANSFER_VERIFIER` | `mercadopago` or `simulated` |
| `GOOGLE_OAUTH_CLIENT_ID` | same as `terraform.tfvars` |
| `AGENT_RESOURCE_NAME` | from step 9 |
| `BILLING_ACCOUNT_ID` | optional, only if you use the budget |

**Repository secret**: `GOOGLE_OAUTH_CLIENT_SECRET`.

CI and local applies share one state, so these values must match `terraform.tfvars`; a mismatch makes the next apply revert the other side.

If you set `BILLING_ACCOUNT_ID`, grant the deployer access to manage the budget:

```sh
gcloud billing accounts add-iam-policy-binding <BILLING_ACCOUNT_ID> \
  --member="serviceAccount:$(terraform -chdir=infra/terraform output -raw ci_deployer_email)" \
  --role=roles/billing.costsManager
```

On every push to `main` the workflow builds the five images tagged with the commit SHA, runs `terraform apply`, and redeploys the agent. If the agent resource name changes, it applies once more and asks you to update `AGENT_RESOURCE_NAME`.

Turn on secret scanning and push protection for the repository, and protect `main`: anything merged there is deployed.

## 13. Local development

```sh
uv sync --all-packages
cp .env.example .env   # fill in; .env is git-ignored
```

Emulators (need Java; install the components once):

```sh
gcloud components install cloud-firestore-emulator pubsub-emulator beta

gcloud emulators firestore start --host-port=localhost:8681
gcloud beta emulators pubsub start --project=<PROJECT_ID> --host-port=localhost:8682
```

The Google client libraries switch to the emulators when `FIRESTORE_EMULATOR_HOST` and `PUBSUB_EMULATOR_HOST` are set (both in `.env.example`). Create the topics in the emulator before publishing.

Local switches:

- `TRANSFER_VERIFIER=simulated`: mcp-shop verifies receipts against a simulated transfer list instead of Mercado Pago.
- `TOKEN_SIGNER=local` with `LOCAL_TOKEN_SECRET`: turn and link tokens use HS256 instead of IAM `signJwt`.

Run lint and every test from the repo root, exactly as CI does:

```sh
uv sync --all-packages
uv run ruff check .
uv run pytest            # libs/, services/ and agent/ in one run
```

## 14. Environment variables

From [docs/contracts.md](docs/contracts.md). On Cloud Run, Terraform sets all of them; secrets come from Secret Manager.

| Variable | Used by | Secret | Default / notes |
|---|---|---|---|
| `GOOGLE_CLOUD_PROJECT` | all | | project id |
| `GOOGLE_CLOUD_LOCATION` | all | | `us-central1` |
| `META_APP_SECRET` | wa-webhook | yes | HMAC key for `X-Hub-Signature-256` |
| `META_VERIFY_TOKEN` | wa-webhook | yes | webhook verification `GET` |
| `WA_INBOUND_TOPIC` | wa-webhook, link-web | | `wa-inbound` |
| `META_ACCESS_TOKEN` | main-worker | yes | system user token |
| `WA_PHONE_NUMBER_ID` | main-worker | | from Meta API Setup |
| `META_GRAPH_VERSION` | main-worker | | `v21.0` |
| `WA_ORDER_READY_TEMPLATE` | main-worker | | `hello_world` |
| `WA_TEMPLATE_LANG` | main-worker | | `en_US` |
| `AGENT_RESOURCE_NAME` | main-worker | | `projects/.../locations/.../reasoningEngines/...` |
| `FIRESTORE_CHANNEL_DB` | main-worker, link-web | | `channel` |
| `FIRESTORE_SHOP_DB` | mcp-shop | | `shop` |
| `MEDIA_BUCKET` | main-worker, mcp-shop, image-generator | | `<PROJECT_ID>-media` |
| `LINK_WEB_URL` | main-worker | | public URL of link-web |
| `SESSION_IDLE_HOURS` | main-worker | | `24` |
| `AUTH_FRESH_HOURS` | main-worker | | `24` |
| `TOKEN_SIGNER` | main-worker, mcp-shop, link-web | | `iam` (Cloud Run) or `local`; the same mode everywhere |
| `SIGNER_SA_EMAIL` | main-worker | | main-worker's service account |
| `TOKEN_ISSUER` | mcp-shop, link-web | | main-worker's service account e-mail (locally, equal to `SIGNER_SA_EMAIL`, default `local-signer`) |
| `LOCAL_TOKEN_SECRET` | local dev only | | HS256 key when `TOKEN_SIGNER=local` |
| `MP_ACCESS_TOKEN` | mcp-shop | yes | production token of the collecting account |
| `MP_COLLECTOR_ID` | mcp-shop | | numeric MP user id |
| `TRANSFER_VERIFIER` | mcp-shop | | `mercadopago` or `simulated` |
| `ORDER_CREATED_TOPIC` | mcp-shop | | `order-created` |
| `EXTRACTION_MODEL` | mcp-shop | | `gemini-3.5-flash` |
| `EXTRACTION_MODEL_LOCATION` | mcp-shop | | `global` (where the extraction model is served) |
| `CREDIT_LIMIT_CENTS` | mcp-shop | | `1000` |
| `MATCH_WINDOW_MINUTES` | mcp-shop | | `120` |
| `SIMULATED_TRANSFERS_PATH` | mcp-shop | | optional fixture for `TRANSFER_VERIFIER=simulated` |
| `ORDER_READY_TOPIC` | image-generator | | `order-ready` |
| `IMAGE_MODEL` | image-generator | | `@cf/black-forest-labs/flux-1-schnell` (Cloudflare Workers AI) |
| `CLOUDFLARE_ACCOUNT_ID` | image-generator | | Cloudflare account for `@cf/` models (`cloudflare_account_id` in tfvars) |
| `CLOUDFLARE_API_TOKEN` | image-generator | yes | Workers AI token |
| `IMAGE_MODEL_LOCATION` | image-generator | | `global` (where the image model is served) |
| `DAILY_GENERATION_CAP` | image-generator | | `200` |
| `IDENTITY_API_KEY` | link-web | | browser API key, public by design (created by Terraform) |
| `IDENTITY_AUTH_DOMAIN` | link-web | | `<PROJECT_ID>.firebaseapp.com` |
| `MCP_SHOP_URL` | agent | | `https://<mcp-shop>/mcp` |
| `AGENT_MODEL` | agent | | `vertex_ai/openai/gpt-oss-120b-maas` (Gemini ids need a paid billing account) |
| `PAYMENT_ALIAS`, `PAYMENT_CVU`, `PAYMENT_HOLDER` | agent | alias or CVU | Where customers transfer to. In CI, repository variables of the same names |
| `AGENT_MODEL_LOCATION` | agent | | `global` (where the agent model is served; the agent itself runs in `GOOGLE_CLOUD_LOCATION`) |
| `MCP_TIMEOUT_SECONDS` | agent | | `30` (MCP session setup; covers mcp-shop cold starts) |

## Cost

At test volume (about 300 messages, 50 receipts and 100 images a month) the estimate is USD 5-10 a month while Agent Runtime stays in its free tier, and roughly USD 75-80 with one agent instance running all month. Gemini and image generation are the main variable cost. Set `billing_account_id` to get budget alerts at 50, 90 and 100 % of USD 20. These figures are estimates; check the official pricing pages.
