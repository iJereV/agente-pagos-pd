# One identity per workload. Sharing an account, or falling back to the default
# compute account, would give a compromised service the permissions of all.

locals {
  service_accounts = {
    "sa-wa-webhook"      = "wa-webhook (public WhatsApp webhook)"
    "sa-main-worker"     = "main-worker (conversation orchestrator)"
    "sa-agent"           = "Shop agent on Agent Runtime"
    "sa-mcp-shop"        = "mcp-shop (domain tools, money)"
    "sa-image-generator" = "image-generator"
    "sa-link-web"        = "link-web (Google sign-in and linking)"
    "sa-pubsub-push"     = "Pub/Sub push subscriptions (OIDC identity)"
    "sa-ci-deployer"     = "GitHub Actions deployer (Workload Identity Federation)"
  }
}

resource "google_service_account" "this" {
  for_each = local.service_accounts

  account_id   = each.key
  display_name = each.value

  depends_on = [google_project_service.this]
}

locals {
  sa = { for name, account in google_service_account.this : name => account.email }

  # Service accounts that run our Cloud Run services and the agent; CI acts as them.
  runtime_service_accounts = [
    "sa-wa-webhook",
    "sa-main-worker",
    "sa-agent",
    "sa-mcp-shop",
    "sa-image-generator",
    "sa-link-web",
  ]
}
