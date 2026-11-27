# shop agent

ADK agent (`shop_agent.agent.root_agent`) deployed to Agent Runtime (Vertex AI Agent
Engine). main-worker runs one turn per customer message or system event and sends
whatever text the agent returns. The agent never sends messages, moves money or reads
data directly: domain tools live in mcp-shop. Contracts:
[docs/contracts.md](../docs/contracts.md).

## Tools

| Tool | Where | Notes |
|---|---|---|
| `get_catalog()` | local | Static catalog (dog $1, penguin $3, capybara $5), cents plus a pesos label. |
| `request_sign_in()` | local | Sets `sign_in_requested=True` in session state; the reply carries `{{SIGN_IN_LINK}}`, which main-worker replaces with the link. |
| `get_balance`, `create_order`, `verify_receipt`, `get_order_status` | mcp-shop | `McpToolset` over streamable HTTP at `MCP_SHOP_URL`. |

Every MCP request carries two headers built per call by the toolset's
`header_provider` (ADK calls it with a `ReadonlyContext` before `tools/list` and every
`tools/call`):

- `Authorization: Bearer <Google ID token>` for the mcp-shop base URL (Cloud Run IAM),
  fetched from the runtime's service account (`sa-agent`).
- `X-Turn-Token`: session state key `turn_token`, written by main-worker before the turn.

The instruction is served through an `InstructionProvider`, which makes ADK skip state
injection; otherwise `{{SIGN_IN_LINK}}` would be resolved as a state variable and fail.

## Environment

`MCP_SHOP_URL` (required at import), `AGENT_MODEL` (default `vertex_ai/openai/gpt-oss-120b-maas`, an open model on Vertex AI
through LiteLLM; a bare id such as `gemini-3.5-flash` uses Gemini, which needs a paid
billing account),
`AGENT_MODEL_LOCATION` (default `global`: the Vertex AI location the model is called in,
independent of the region the agent runs in) and `MCP_TIMEOUT_SECONDS` (default `30`:
MCP session setup, long enough for an mcp-shop cold start).

## Deploy

### Scripted (used by CI)

```sh
export GOOGLE_CLOUD_PROJECT=my-project GOOGLE_CLOUD_LOCATION=us-central1
export MCP_SHOP_URL=https://mcp-shop-xxxx.a.run.app/mcp
export AGENT_SERVICE_ACCOUNT=sa-agent@my-project.iam.gserviceaccount.com
export AGENT_STAGING_BUCKET=gs://my-project-agent-staging
# export AGENT_RESOURCE_NAME=projects/.../locations/us-central1/reasoningEngines/...  # update in place
uv run python agent/deploy.py
```

`deploy.py` wraps the agent in `vertexai.agent_engines.AdkApp` and calls
`vertexai.Client(...).agent_engines.create(...)` or `.update(name=...)` with
`service_account`, `env_vars`, `requirements` and `extra_packages=["shop_agent"]`. The
last stdout line is the resource name, which main-worker needs as
`AGENT_RESOURCE_NAME`.

### Agents CLI (interactive alternative)

Google's [Agents CLI](https://google.github.io/agents-cli/) (`uv tool install
google-agents-cli`) can deploy ADK projects to Agent Runtime:

```sh
cd agent
agents-cli scaffold enhance --from-adk-project      # writes agents-cli-manifest.yaml only
agents-cli deploy --deployment-target agent_runtime \
  --project my-project --region us-central1 \
  --service-account sa-agent@my-project.iam.gserviceaccount.com \
  --env-vars MCP_SHOP_URL=https://mcp-shop-xxxx.a.run.app/mcp,AGENT_MODEL=vertex_ai/openai/gpt-oss-120b-maas,AGENT_MODEL_LOCATION=global
```

Agents CLI deploys to Agent Runtime as a container that Agent Runtime builds from a
`Dockerfile` in the project directory (or from a prebuilt `--image`); `agent/` has no
`Dockerfile`, so one must be added first. A container-based agent is a different
resource from the source-based one `deploy.py` creates (an existing agent cannot switch
between the two), so set main-worker's `AGENT_RESOURCE_NAME` to whichever you deploy.
The tool is young and has not been exercised against this repository, so `deploy.py`
stays the reproducible path used by CI. See
[Deploy to Agent Runtime with Agents CLI](https://adk.dev/deploy/agent-runtime/agents-cli/).

## Test

```sh
uv run --package shop-agent pytest agent/tests
```
