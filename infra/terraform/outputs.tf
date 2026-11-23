output "service_urls" {
  description = "Cloud Run service URLs."
  value       = { for name, svc in google_cloud_run_v2_service.this : name => svc.uri }
}

output "wa_webhook_url" {
  description = "Callback URL to configure in the Meta app (WhatsApp > Configuration)."
  value       = "${google_cloud_run_v2_service.this["wa-webhook"].uri}/webhook"
}

output "mcp_shop_url" {
  description = "MCP endpoint used by the agent (MCP_SHOP_URL)."
  value       = "${google_cloud_run_v2_service.this["mcp-shop"].uri}/mcp"
}

output "link_web_url" {
  description = "Public URL of link-web as passed to main-worker (LINK_WEB_URL)."
  value       = local.run_url["link-web"]
}

output "topics" {
  description = "Pub/Sub topic ids."
  value       = { for name, topic in google_pubsub_topic.this : name => topic.name }
}

output "dead_letter_topics" {
  description = "Dead-letter topic ids."
  value       = { for name, topic in google_pubsub_topic.dead_letter : name => topic.name }
}

output "service_account_emails" {
  description = "Service account e-mails."
  value       = local.sa
}

output "media_bucket" {
  description = "Media bucket (orders/, receipts/)."
  value       = google_storage_bucket.media.name
}

output "agent_staging_bucket" {
  description = "Staging bucket for agent deployments."
  value       = google_storage_bucket.agent_staging.name
}

output "image_registry" {
  description = "Artifact Registry prefix for service images."
  value       = local.image_registry
}

output "firestore_databases" {
  description = "Firestore database ids."
  value       = { for name, db in google_firestore_database.this : name => db.name }
}

output "workload_identity_provider" {
  description = "Full WIF provider name, for the GCP_WIF_PROVIDER repository variable."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "ci_deployer_email" {
  description = "Deployer service account, for the GCP_DEPLOYER_SA repository variable."
  value       = local.sa["sa-ci-deployer"]
}
