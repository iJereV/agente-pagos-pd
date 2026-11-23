# Media bucket layout (docs/contracts.md):
#   orders/{order_id}/{n}.png, orders/{order_id}/manifest.json   written by image-generator
#   receipts/{customer_id or wa_id}/{wamid}.{ext}                  written by main-worker

resource "google_storage_bucket" "media" {
  name     = "${var.project_id}-media"
  location = upper(var.region)

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  depends_on = [google_project_service.this]
}

# Staging area used by the Agent Platform SDK when deploying the agent.
resource "google_storage_bucket" "agent_staging" {
  name     = "${var.project_id}-agent-staging"
  location = upper(var.region)

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = true

  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.this]
}

locals {
  media_objects_prefix = "projects/_/buckets/${google_storage_bucket.media.name}/objects"
}
