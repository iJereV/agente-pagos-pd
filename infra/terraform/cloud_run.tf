# Five Cloud Run services, each running as its own service account.
# Environment variables follow docs/contracts.md.

locals {
  placeholder_image = "us-docker.pkg.dev/cloudrun/container/hello"

  # Deterministic Cloud Run URLs (https://<service>-<project_number>.<region>.run.app).
  # Used where referencing the resource's own `uri` would create a cycle.
  run_url = {
    for name in ["wa-webhook", "main-worker", "mcp-shop", "image-generator", "link-web"] :
    name => "https://${name}-${data.google_project.this.number}.${var.region}.run.app"
  }

  common_env = {
    GOOGLE_CLOUD_PROJECT  = var.project_id
    GOOGLE_CLOUD_LOCATION = var.region
  }

  services = {
    "wa-webhook" = {
      service_account = "sa-wa-webhook"
      public          = true
      timeout         = "30s"
      max_instances   = 5
      health_path     = null
      env = {
        WA_INBOUND_TOPIC = google_pubsub_topic.this["wa-inbound"].name
      }
      secrets = ["meta-app-secret", "meta-verify-token"]
    }

    "main-worker" = {
      service_account = "sa-main-worker"
      public          = false
      timeout         = "300s"
      max_instances   = 3
      health_path     = null
      env = {
        WA_PHONE_NUMBER_ID      = var.wa_phone_number_id
        META_GRAPH_VERSION      = var.meta_graph_version
        WA_ORDER_READY_TEMPLATE = var.wa_order_ready_template
        WA_TEMPLATE_LANG        = var.wa_template_lang
        AGENT_RESOURCE_NAME     = var.agent_resource_name
        FIRESTORE_CHANNEL_DB    = google_firestore_database.this["channel"].name
        MEDIA_BUCKET            = google_storage_bucket.media.name
        LINK_WEB_URL            = local.run_url["link-web"]
        SESSION_IDLE_HOURS      = tostring(var.session_idle_hours)
        AUTH_FRESH_HOURS        = tostring(var.auth_fresh_hours)
        TOKEN_SIGNER            = "iam"
        SIGNER_SA_EMAIL         = local.sa["sa-main-worker"]
      }
      secrets = ["meta-access-token"]
    }

    "mcp-shop" = {
      service_account = "sa-mcp-shop"
      public          = false
      timeout         = "120s"
      max_instances   = 3
      health_path     = "/health"
      env = {
        FIRESTORE_SHOP_DB    = google_firestore_database.this["shop"].name
        MEDIA_BUCKET         = google_storage_bucket.media.name
        TOKEN_SIGNER         = "iam"
        TOKEN_ISSUER         = local.sa["sa-main-worker"]
        MP_COLLECTOR_ID      = var.mp_collector_id
        TRANSFER_VERIFIER    = var.transfer_verifier
        ORDER_CREATED_TOPIC  = google_pubsub_topic.this["order-created"].name
        EXTRACTION_MODEL     = var.extraction_model
        CREDIT_LIMIT_CENTS   = tostring(var.credit_limit_cents)
        MATCH_WINDOW_MINUTES = tostring(var.match_window_minutes)
      }
      secrets = ["mp-access-token"]
    }

    "image-generator" = {
      service_account = "sa-image-generator"
      public          = false
      timeout         = "600s"
      max_instances   = 2
      health_path     = null
      env = {
        MEDIA_BUCKET         = google_storage_bucket.media.name
        ORDER_READY_TOPIC    = google_pubsub_topic.this["order-ready"].name
        IMAGE_MODEL          = var.image_model
        IMAGE_MODEL_LOCATION = var.image_model_location
        DAILY_GENERATION_CAP = tostring(var.daily_generation_cap)
      }
      secrets = []
    }

    "link-web" = {
      service_account = "sa-link-web"
      public          = true
      timeout         = "30s"
      max_instances   = 3
      health_path     = null
      env = {
        WA_INBOUND_TOPIC     = google_pubsub_topic.this["wa-inbound"].name
        FIRESTORE_CHANNEL_DB = google_firestore_database.this["channel"].name
        TOKEN_SIGNER         = "iam"
        TOKEN_ISSUER         = local.sa["sa-main-worker"]
        IDENTITY_API_KEY     = google_apikeys_key.identity_web.key_string
        IDENTITY_AUTH_DOMAIN = "${var.project_id}.firebaseapp.com"
      }
      secrets = []
    }
  }
}

resource "google_cloud_run_v2_service" "this" {
  for_each = local.services

  name     = each.key
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  # Stateless services: allow `terraform destroy` to tear them down.
  deletion_protection = false

  template {
    service_account = local.sa[each.value.service_account]
    timeout         = each.value.timeout

    scaling {
      min_instance_count = 0
      max_instance_count = each.value.max_instances
    }

    containers {
      image = var.use_placeholder_images ? local.placeholder_image : "${local.image_registry}/${each.key}:${var.image_tag}"

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle = true
      }

      # HTTP probes only where the service exposes a health endpoint, and only
      # with real images (the placeholder does not serve it).
      dynamic "startup_probe" {
        for_each = var.use_placeholder_images || each.value.health_path == null ? [] : [each.value.health_path]
        content {
          period_seconds    = 5
          failure_threshold = 6
          http_get {
            path = startup_probe.value
          }
        }
      }

      dynamic "liveness_probe" {
        for_each = var.use_placeholder_images || each.value.health_path == null ? [] : [each.value.health_path]
        content {
          period_seconds = 30
          http_get {
            path = liveness_probe.value
          }
        }
      }

      dynamic "env" {
        for_each = merge(local.common_env, each.value.env)
        content {
          name  = env.key
          value = env.value
        }
      }

      # Secrets are attached only with real images: the placeholder needs none,
      # and the first apply runs before any secret has a version.
      dynamic "env" {
        for_each = var.use_placeholder_images ? [] : each.value.secrets
        content {
          name = local.secrets[env.value].env
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.this[env.value].secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }

  depends_on = [
    google_project_service.this,
    google_secret_manager_secret_iam_member.accessor,
  ]
}

# Public doors: Meta calls wa-webhook, customers open link-web in a browser.
resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  for_each = { for name, svc in local.services : name => svc if svc.public }

  name     = google_cloud_run_v2_service.this[each.key].name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Only Pub/Sub (through its push identity) may invoke the event consumers.
resource "google_cloud_run_v2_service_iam_member" "pubsub_push_invoker" {
  for_each = toset(["main-worker", "image-generator"])

  name     = google_cloud_run_v2_service.this[each.value].name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${local.sa["sa-pubsub-push"]}"
}

# Only the agent may invoke mcp-shop.
resource "google_cloud_run_v2_service_iam_member" "agent_invokes_mcp_shop" {
  name     = google_cloud_run_v2_service.this["mcp-shop"].name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${local.sa["sa-agent"]}"
}
