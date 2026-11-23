# Google is the only sign-in provider. The OAuth web client is created manually
# in the console (see SETUP.md) and passed in through variables.

resource "google_identity_platform_config" "this" {
  authorized_domains = distinct([
    "localhost",
    "${var.project_id}.firebaseapp.com",
    "${var.project_id}.web.app",
    trimprefix(local.run_url["link-web"], "https://"),
    trimprefix(google_cloud_run_v2_service.this["link-web"].uri, "https://"),
  ])

  depends_on = [google_project_service.this]
}

resource "google_identity_platform_default_supported_idp_config" "google" {
  count = var.google_oauth_client_id == "" ? 0 : 1

  idp_id        = "google.com"
  enabled       = true
  client_id     = var.google_oauth_client_id
  client_secret = var.google_oauth_client_secret

  depends_on = [google_identity_platform_config.this]
}

# Browser API key for the sign-in page. It is public by design; restricting it
# to the auth APIs limits what it can be used for.
resource "google_apikeys_key" "identity_web" {
  name         = "link-web-identity"
  display_name = "link-web Identity Platform key"

  restrictions {
    api_targets {
      service = "identitytoolkit.googleapis.com"
    }
    api_targets {
      service = "securetoken.googleapis.com"
    }
  }

  depends_on = [google_project_service.this]
}
