# --- Project ------------------------------------------------------------------

variable "project_id" {
  description = "GCP project id."
  type        = string
}

variable "region" {
  description = "Region for every regional resource."
  type        = string
  default     = "us-central1"
}

variable "tfstate_bucket" {
  description = "Terraform state bucket created by the bootstrap script. Defaults to <project_id>-tfstate."
  type        = string
  default     = ""
}

# --- Images and deployment ----------------------------------------------------

variable "image_tag" {
  description = "Tag of the service images in Artifact Registry (CI passes the commit SHA)."
  type        = string
  default     = "latest"
}

variable "use_placeholder_images" {
  description = "Deploy Google's hello container instead of our images. Used for the first apply, before any image exists and before secrets have values."
  type        = bool
  default     = true
}

variable "agent_resource_name" {
  description = "Agent Runtime resource name (projects/.../locations/.../reasoningEngines/...). Empty until the agent is deployed."
  type        = string
  default     = ""
}

# --- WhatsApp -----------------------------------------------------------------

variable "wa_phone_number_id" {
  description = "WhatsApp Business phone number id (Meta app dashboard, WhatsApp > API Setup)."
  type        = string
  default     = ""
}

variable "meta_graph_version" {
  description = "Meta Graph API version."
  type        = string
  default     = "v21.0"
}

variable "wa_order_ready_template" {
  description = "Template sent outside the 24 h customer service window."
  type        = string
  default     = "hello_world"
}

variable "wa_template_lang" {
  description = "Language code of the template."
  type        = string
  default     = "en_US"
}

# --- Shop ---------------------------------------------------------------------

variable "mp_collector_id" {
  description = "Numeric Mercado Pago user id of the collecting account."
  type        = string
  default     = ""
}

variable "transfer_verifier" {
  description = "Transfer verifier adapter used by mcp-shop: mercadopago or simulated."
  type        = string
  default     = "mercadopago"

  validation {
    condition     = contains(["mercadopago", "simulated"], var.transfer_verifier)
    error_message = "transfer_verifier must be mercadopago or simulated."
  }
}

variable "credit_limit_cents" {
  description = "Credit limit per customer, in cents."
  type        = number
  default     = 1000
}

variable "match_window_minutes" {
  description = "Time window used to match a receipt against received transfers."
  type        = number
  default     = 120
}

variable "session_idle_hours" {
  description = "Hours of inactivity after which main-worker starts a new agent session."
  type        = number
  default     = 24
}

variable "auth_fresh_hours" {
  description = "Hours a Google sign-in counts as fresh."
  type        = number
  default     = 24
}

# --- Models -------------------------------------------------------------------

variable "extraction_model" {
  description = "Gemini model used by mcp-shop to extract receipt fields."
  type        = string
  default     = "gemini-3.5-flash"
}

variable "extraction_model_location" {
  description = "Vertex AI location where the extraction model is served."
  type        = string
  default     = "global"
}

variable "image_model" {
  description = "Model used by image-generator."
  type        = string
  default     = "gemini-3.1-flash-lite-image"
}

variable "image_model_location" {
  description = "Vertex AI location where the image model is served."
  type        = string
  default     = "global"
}

variable "daily_generation_cap" {
  description = "Global cap of generated images per day."
  type        = number
  default     = 200
}

# --- Identity Platform --------------------------------------------------------

variable "google_oauth_client_id" {
  description = "OAuth 2.0 web client id for the Google sign-in provider (created manually in the console). Leave empty to skip the provider."
  type        = string
  default     = ""
}

variable "google_oauth_client_secret" {
  description = "OAuth 2.0 web client secret for the Google sign-in provider."
  type        = string
  default     = ""
  sensitive   = true
}

# --- CI/CD --------------------------------------------------------------------

variable "github_repository" {
  description = "GitHub repository (owner/name) allowed to deploy through Workload Identity Federation."
  type        = string
}

variable "github_branch" {
  description = "Only workflows running on this branch can impersonate the deployer."
  type        = string
  default     = "main"
}

# --- Budget -------------------------------------------------------------------

variable "billing_account_id" {
  description = "Billing account id (XXXXXX-XXXXXX-XXXXXX). Leave empty to skip the budget."
  type        = string
  default     = ""
}

variable "budget_amount" {
  description = "Monthly budget amount, in budget_currency."
  type        = number
  default     = 20
}

variable "budget_currency" {
  description = "Currency of the budget. Must match the billing account currency."
  type        = string
  default     = "USD"
}
