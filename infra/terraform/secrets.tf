# Secret containers only. Values are added out of band with
#   gcloud secrets versions add <secret> --data-file=-
# so they never reach Terraform state or the repository.

locals {
  secrets = {
    "meta-app-secret"   = { env = "META_APP_SECRET", accessors = ["sa-wa-webhook"] }
    "meta-verify-token" = { env = "META_VERIFY_TOKEN", accessors = ["sa-wa-webhook"] }
    "meta-access-token" = { env = "META_ACCESS_TOKEN", accessors = ["sa-main-worker"] }
    "mp-access-token"   = { env = "MP_ACCESS_TOKEN", accessors = ["sa-mcp-shop"] }
  }

  secret_accessors = merge([
    for secret, cfg in local.secrets : {
      for account in cfg.accessors : "${secret}/${account}" => { secret = secret, account = account }
    }
  ]...)
}

resource "google_secret_manager_secret" "this" {
  for_each = local.secrets

  secret_id = each.key

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  depends_on = [google_project_service.this]
}

resource "google_secret_manager_secret_iam_member" "accessor" {
  for_each = local.secret_accessors

  secret_id = google_secret_manager_secret.this[each.value.secret].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${local.sa[each.value.account]}"
}
