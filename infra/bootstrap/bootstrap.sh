#!/usr/bin/env bash
# One-time bootstrap: Terraform state bucket, minimum APIs and `terraform init`.
# Safe to run again: every step checks before it creates.
#
# Usage: infra/bootstrap/bootstrap.sh <PROJECT_ID> [REGION]

set -euo pipefail

PROJECT_ID="${1:-${PROJECT_ID:-}}"
REGION="${2:-${REGION:-us-central1}}"

if [ -z "$PROJECT_ID" ]; then
  echo "usage: $0 <PROJECT_ID> [REGION]" >&2
  exit 1
fi

STATE_BUCKET="${PROJECT_ID}-tfstate"
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
TF_DIR=$(cd "${SCRIPT_DIR}/../terraform" && pwd)

step() { printf '\n==> %s\n' "$*"; }

for tool in gcloud terraform; do
  command -v "$tool" >/dev/null 2>&1 || { echo "missing required tool: $tool" >&2; exit 1; }
done

step "Project ${PROJECT_ID}"
gcloud projects describe "$PROJECT_ID" --format="value(projectId)" >/dev/null
gcloud config set project "$PROJECT_ID" >/dev/null

step "Enabling the APIs Terraform needs to start (the rest are managed in apis.tf)"
gcloud services enable \
  cloudresourcemanager.googleapis.com \
  serviceusage.googleapis.com \
  iam.googleapis.com \
  storage.googleapis.com \
  --project "$PROJECT_ID"

step "Terraform state bucket gs://${STATE_BUCKET}"
if gcloud storage buckets describe "gs://${STATE_BUCKET}" --project "$PROJECT_ID" >/dev/null 2>&1; then
  echo "already exists"
else
  gcloud storage buckets create "gs://${STATE_BUCKET}" \
    --project "$PROJECT_ID" \
    --location "$REGION" \
    --uniform-bucket-level-access \
    --public-access-prevention
fi
gcloud storage buckets update "gs://${STATE_BUCKET}" --versioning >/dev/null
echo "versioning on"

step "Application Default Credentials quota project"
if gcloud auth application-default print-access-token >/dev/null 2>&1; then
  gcloud auth application-default set-quota-project "$PROJECT_ID" >/dev/null 2>&1 || true
  echo "ok"
else
  echo "no ADC found: run 'gcloud auth application-default login' before terraform plan/apply"
fi

step "terraform init"
(cd "$TF_DIR" && terraform init -input=false -reconfigure -backend-config="bucket=${STATE_BUCKET}")

step "Done"
cat <<EOF
Next:
  cd infra/terraform
  cp terraform.tfvars.example terraform.tfvars   # then edit it
  terraform apply
See SETUP.md for the full sequence.
EOF
