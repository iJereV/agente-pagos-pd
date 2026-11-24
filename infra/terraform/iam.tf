# Least-privilege grants for the runtime service accounts, following the plan's
# "Service accounts" table. Deployer (CI) permissions live in wif.tf.
#
#   sa-wa-webhook       publish wa-inbound; Meta app secret + verify token   (secrets.tf)
#   sa-main-worker      Firestore channel; Storage read orders/, write receipts/;
#                       Meta access token; Agent Runtime; signJwt as itself
#   sa-agent            Gemini on Vertex AI; invoke mcp-shop                  (cloud_run.tf);
#                       write its own logs, traces and metrics (Agent Runtime telemetry)
#   sa-mcp-shop         Firestore shop; MP token; publish order-created; Gemini;
#                       Storage read receipts/
#   sa-image-generator  image model; Storage write orders/; publish order-ready
#   sa-link-web         Firestore channel; publish wa-inbound
#   sa-pubsub-push      invoke main-worker and image-generator                (cloud_run.tf)

# --- Firestore: one database per account ---------------------------------------
# Firestore supports IAM conditions on the database resource name, so
# roles/datastore.user is scoped to a single database.

locals {
  firestore_access = {
    "sa-main-worker" = "channel"
    "sa-link-web"    = "channel"
    "sa-mcp-shop"    = "shop"
  }
}

resource "google_project_iam_member" "firestore_user" {
  for_each = local.firestore_access

  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${local.sa[each.key]}"

  condition {
    title       = "only-${each.value}-database"
    description = "Firestore access limited to the ${each.value} database."
    expression  = "resource.name == \"projects/${var.project_id}/databases/${google_firestore_database.this[each.value].name}\""
  }
}

# --- Vertex AI ---------------------------------------------------------------
# roles/aiplatform.user is the narrowest predefined role that covers both model
# calls and Agent Runtime queries/sessions; Vertex AI does not support resource
# conditions for these calls. main-worker uses it only to query the agent.

locals {
  vertex_users = toset(["sa-main-worker", "sa-agent", "sa-mcp-shop", "sa-image-generator"])
}

resource "google_project_iam_member" "vertex_user" {
  for_each = local.vertex_users

  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${local.sa[each.value]}"
}

# --- Agent telemetry ----------------------------------------------------------------
# Agent Runtime exports the agent's logs, traces and metrics as the agent's own
# identity (sa-agent). Cloud Run services get this from the platform; the agent does
# not, so without these grants every export fails with 403.

locals {
  agent_telemetry_roles = toset([
    "roles/cloudtrace.agent",
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
  ])
}

resource "google_project_iam_member" "agent_telemetry" {
  for_each = local.agent_telemetry_roles

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${local.sa["sa-agent"]}"

  # When CI applies, its projectIamAdmin condition must list these roles first.
  depends_on = [google_project_iam_member.ci_deployer_iam_admin]
}

# --- Cloud Storage: one prefix per access pattern --------------------------------
# Object-level conditions on resource.name restrict access to a prefix. Listing
# is evaluated on the bucket resource, so these grants do not allow listing;
# services address objects by their known names.
# Writers get objectUser (create + overwrite) so a retried upload of the same
# object name succeeds.

locals {
  storage_access = {
    "main-worker-read-orders" = {
      account = "sa-main-worker"
      role    = "roles/storage.objectViewer"
      prefix  = "orders/"
    }
    "main-worker-write-receipts" = {
      account = "sa-main-worker"
      role    = "roles/storage.objectUser"
      prefix  = "receipts/"
    }
    "mcp-shop-read-receipts" = {
      account = "sa-mcp-shop"
      role    = "roles/storage.objectViewer"
      prefix  = "receipts/"
    }
    "image-generator-write-orders" = {
      account = "sa-image-generator"
      role    = "roles/storage.objectUser"
      prefix  = "orders/"
    }
  }
}

resource "google_storage_bucket_iam_member" "media" {
  for_each = local.storage_access

  bucket = google_storage_bucket.media.name
  role   = each.value.role
  member = "serviceAccount:${local.sa[each.value.account]}"

  condition {
    title       = each.key
    description = "Objects under ${each.value.prefix} only."
    expression  = "resource.name.startsWith(\"${local.media_objects_prefix}/${each.value.prefix}\")"
  }
}

# --- Pub/Sub publishers ----------------------------------------------------------

locals {
  publishers = {
    "wa-inbound/sa-wa-webhook"       = { topic = "wa-inbound", account = "sa-wa-webhook" }
    "wa-inbound/sa-link-web"         = { topic = "wa-inbound", account = "sa-link-web" }
    "order-created/sa-mcp-shop"      = { topic = "order-created", account = "sa-mcp-shop" }
    "order-ready/sa-image-generator" = { topic = "order-ready", account = "sa-image-generator" }
  }
}

resource "google_pubsub_topic_iam_member" "publisher" {
  for_each = local.publishers

  topic  = google_pubsub_topic.this[each.value.topic].id
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${local.sa[each.value.account]}"
}

# --- Token signing -------------------------------------------------------------
# main-worker signs turn and link tokens with IAM Credentials signJwt as itself,
# so no private key is ever stored. The grant is on its own account only.

resource "google_service_account_iam_member" "main_worker_signs_as_itself" {
  service_account_id = google_service_account.this["sa-main-worker"].name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${local.sa["sa-main-worker"]}"
}
