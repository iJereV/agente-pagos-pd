# GitHub Actions deploys through Workload Identity Federation: no JSON keys.
# Only workflows from one repository, running on one branch, can impersonate
# sa-ci-deployer.

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"
  description               = "OIDC identities issued by GitHub Actions."

  depends_on = [google_project_service.this]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc"
  display_name                       = "GitHub OIDC"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  # Tokens from any other repository or branch are rejected at the STS exchange.
  attribute_condition = "assertion.repository == \"${var.github_repository}\" && assertion.ref == \"refs/heads/${var.github_branch}\""

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "ci_deployer_wif" {
  service_account_id = google_service_account.this["sa-ci-deployer"].name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repository}"
}

# --- Deployer permissions --------------------------------------------------------
# CI runs `terraform apply` over this whole stack, so it must manage the
# resources here, but it must not read data or secret values. Predefined admin
# roles for Secret Manager, Firestore, Storage and Pub/Sub include data access,
# so those are covered by a custom role with metadata-only permissions.

resource "google_project_iam_custom_role" "ci_infra_manager" {
  role_id     = "ciInfraManager"
  title       = "CI infrastructure manager"
  description = "Manage secrets, Firestore databases, buckets, topics and subscriptions without reading their data."

  permissions = [
    # Secret Manager: containers and IAM, never versions.
    "secretmanager.locations.get",
    "secretmanager.locations.list",
    "secretmanager.secrets.create",
    "secretmanager.secrets.delete",
    "secretmanager.secrets.get",
    "secretmanager.secrets.getIamPolicy",
    "secretmanager.secrets.list",
    "secretmanager.secrets.setIamPolicy",
    "secretmanager.secrets.update",
    # Firestore: databases and indexes, never documents.
    "datastore.databases.create",
    "datastore.databases.delete",
    "datastore.databases.get",
    "datastore.databases.getMetadata",
    "datastore.databases.list",
    "datastore.databases.update",
    "datastore.indexes.create",
    "datastore.indexes.delete",
    "datastore.indexes.get",
    "datastore.indexes.list",
    "datastore.indexes.update",
    # Cloud Storage: buckets, never objects.
    "storage.buckets.create",
    "storage.buckets.delete",
    "storage.buckets.get",
    "storage.buckets.getIamPolicy",
    "storage.buckets.list",
    "storage.buckets.setIamPolicy",
    "storage.buckets.update",
    # Pub/Sub: topics and subscriptions, never publish or consume.
    "pubsub.subscriptions.create",
    "pubsub.subscriptions.delete",
    "pubsub.subscriptions.get",
    "pubsub.subscriptions.getIamPolicy",
    "pubsub.subscriptions.list",
    "pubsub.subscriptions.setIamPolicy",
    "pubsub.subscriptions.update",
    "pubsub.topics.attachSubscription",
    "pubsub.topics.create",
    "pubsub.topics.delete",
    "pubsub.topics.get",
    "pubsub.topics.getIamPolicy",
    "pubsub.topics.list",
    "pubsub.topics.setIamPolicy",
    "pubsub.topics.update",
    # Identity Platform: configuration, never users. getSecret lets Terraform
    # refresh the Google provider config, whose client secret CI already holds.
    "firebaseauth.configs.create",
    "firebaseauth.configs.get",
    "firebaseauth.configs.getSecret",
    "firebaseauth.configs.update",
  ]

  depends_on = [google_project_service.this]
}

locals {
  deployer_project_roles = toset([
    "roles/aiplatform.user",                # deploy and update the agent on Agent Runtime
    "roles/artifactregistry.admin",         # manage the repository and push images
    "roles/browser",                        # read project metadata
    "roles/iam.roleAdmin",                  # manage the custom role above
    "roles/iam.serviceAccountAdmin",        # manage service accounts and their IAM
    "roles/iam.workloadIdentityPoolAdmin",  # manage this pool
    "roles/run.admin",                      # deploy Cloud Run services
    "roles/serviceusage.apiKeysAdmin",      # manage the link-web browser key
    "roles/serviceusage.serviceUsageAdmin", # enable APIs
    google_project_iam_custom_role.ci_infra_manager.name,
  ])

  # Project-level roles this configuration grants. CI may add or remove these
  # and nothing else (see the condition on projectIamAdmin below).
  grantable_project_roles = setunion(
    local.deployer_project_roles,
    ["roles/datastore.user"],
  )
}

resource "google_project_iam_member" "ci_deployer" {
  for_each = local.deployer_project_roles

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${local.sa["sa-ci-deployer"]}"
}

# Project IAM is managed by Terraform, so CI needs projectIamAdmin. The condition
# limits which roles it can grant or revoke; it cannot grant Owner/Editor or
# widen this binding itself.
resource "google_project_iam_member" "ci_deployer_iam_admin" {
  project = var.project_id
  role    = "roles/resourcemanager.projectIamAdmin"
  member  = "serviceAccount:${local.sa["sa-ci-deployer"]}"

  condition {
    title       = "only-managed-roles"
    description = "Grant or revoke only the project roles managed by this configuration."
    expression  = "api.getAttribute('iam.googleapis.com/modifiedGrantsByRole', []).hasOnly([${join(", ", [for role in sort(tolist(local.grantable_project_roles)) : "'${role}'"])}])"
  }
}

# Act as the runtime accounts (deploy Cloud Run and the agent) and as the Pub/Sub
# push identity (create push subscriptions with OIDC tokens).
resource "google_service_account_iam_member" "ci_deployer_acts_as" {
  for_each = toset(concat(local.runtime_service_accounts, ["sa-pubsub-push"]))

  service_account_id = google_service_account.this[each.value].name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${local.sa["sa-ci-deployer"]}"
}

# Terraform state and agent staging: object access on these two buckets only.
resource "google_storage_bucket_iam_member" "ci_deployer_tfstate" {
  bucket = coalesce(var.tfstate_bucket, "${var.project_id}-tfstate")
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${local.sa["sa-ci-deployer"]}"
}

resource "google_storage_bucket_iam_member" "ci_deployer_agent_staging" {
  bucket = google_storage_bucket.agent_staging.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${local.sa["sa-ci-deployer"]}"
}
