resource "google_artifact_registry_repository" "images" {
  repository_id = "agente-pagos"
  location      = var.region
  format        = "DOCKER"
  description   = "Service images, tagged with the commit SHA."

  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 10
    }
  }

  cleanup_policies {
    id     = "delete-old"
    action = "DELETE"
    condition {
      older_than = "2592000s" # 30 days
    }
  }

  depends_on = [google_project_service.this]
}

locals {
  image_registry = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}
