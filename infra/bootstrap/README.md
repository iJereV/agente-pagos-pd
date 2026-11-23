# Bootstrap

One-time setup that has to exist before Terraform can manage the rest.

```sh
gcloud auth login
gcloud auth application-default login
infra/bootstrap/bootstrap.sh <PROJECT_ID>          # region defaults to us-central1
```

The script is idempotent. It:

1. Checks that `gcloud` and `terraform` are installed and the project exists.
2. Enables the APIs Terraform needs to start (`cloudresourcemanager`, `serviceusage`, `iam`, `storage`). Every other API is enabled by `infra/terraform/apis.tf`.
3. Creates the state bucket `gs://<PROJECT_ID>-tfstate` (uniform access, public access prevention, versioning on).
4. Sets the ADC quota project, needed for Identity Platform, API keys and budgets.
5. Runs `terraform init -backend-config="bucket=<PROJECT_ID>-tfstate"` in `infra/terraform`.

The Workload Identity Federation pool for GitHub Actions is created by Terraform (`wif.tf`) on the first apply, run locally with your own credentials. After that, CI deploys through it. See [SETUP.md](../../SETUP.md) for the full sequence.
