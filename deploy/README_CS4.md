# Case Study 4 -- Cloud Deployment of the API-based Product

This covers deploying `genre-api` (the Case Study 1 API-based product,
`APP_MODE=api` in `vm_app.py`) to GCP Cloud Run, Azure Container Apps, and
AWS ECS Fargate, plus one GitHub Action that automates the GCP deploy.

## Why one new Dockerfile instead of reusing the Case Study 3 one

`Dockerfile.cloud` (repo root) is a leaner variant of the Case Study 3
`Dockerfile`:
- No `prometheus-node-exporter` -- that was for the VM's host-level
  metrics (Case Study 3's rubric item); none of these three managed
  platforms expose a host to scrape.
- The genre classifier model is pre-downloaded at **build** time instead
  of at first request, so cold starts on scale-to-zero platforms don't
  pay a Hugging Face Hub download on every idle-to-active transition.
- Defaults to `PORT=8080`, matching the ingress/target-port configured on
  all three platforms below (Cloud Run injects its own `PORT` regardless;
  Azure and AWS do not, so this keeps one consistent port number instead
  of three different ones).

See the comment block at the top of `Dockerfile.cloud` for the full
rationale -- this is also the content for the report's "modifications
made" sections (4b/4c/4d).

## Per-cloud deploy scripts

Each script is idempotent (safe to re-run) and reads `HF_TOKEN` only from
your local shell's environment -- it is never written into this repo, any
script, or committed anywhere.

```bash
export HF_TOKEN=your_token_here   # set in YOUR shell, never commit this

# GCP (needs: gcloud auth login, and PROJECT_ID set)
PROJECT_ID=your-gcp-project-id ./deploy/gcp/deploy_cloudrun.sh

# Azure (needs: az login)
./deploy/azure/deploy_containerapps.sh

# AWS (needs: aws configure, with your AWS Educate-linked account)
./deploy/aws/deploy_ecs.sh
```

Run these from a machine/session with real CLI auth -- a local terminal,
or a local Claude Code session with shell + browser access for the
`gcloud auth login` / `az login` interactive steps (same pattern used in
Case Study 3 for the VM's SSH setup).

## What each script needs from you first

| Cloud | You provide | Script figures out |
|---|---|---|
| GCP | `PROJECT_ID` env var, authenticated `gcloud` | region (default us-central1), Artifact Registry repo, Secret Manager, Cloud Run service |
| Azure | authenticated `az` (optionally `ACR_NAME` if the random default collides) | resource group, ACR, Container Apps environment + app |
| AWS | authenticated `aws` (your account's **default VPC** must still exist) | ECR repo, Secrets Manager secret, IAM execution role, cluster, ALB + target group + listener, security groups, service |

## GitHub Action (Deliverable 5 -- picked GCP Cloud Run)

`.github/workflows/deploy-cloudrun.yml` builds and deploys on every push to
`case-study-4` that touches the app/Dockerfile. Needs three **GitHub
repo secrets** (Settings -> Secrets and variables -> Actions), which you
set directly in GitHub's UI -- never pasted into chat:

- `GCP_PROJECT_ID`
- `GCP_SA_KEY` -- JSON key for a service account with Artifact Registry
  Writer + Cloud Run Admin + Service Account User roles (see the comment
  at the top of the workflow file for the exact `gcloud` commands to
  create it)
- `HF_TOKEN`

## Populating the class Google Sheet

Once each deploy script finishes, it prints the external URL -- paste
those into the Sheet's GCP / Azure / AWS URL columns for this case study,
same convention as Case Study 3.

## Report mapping (Deliverable 4)

- 4b/4c/4d ("setup process", "modifications made") -- summarize the
  per-cloud table above plus the Dockerfile.cloud rationale comment;
  don't just paste the scripts verbatim.
- 4e (challenges/insights) -- strong candidates: the cold-start/model-bake
  tradeoff, AWS ECS needing an ALB for a stable URL while Cloud Run/
  Container Apps hand you one for free, and AWS Educate's credit-approval
  lag vs. GCP/Azure's instant self-serve signup.
- 4f (LLM-only) -- literally ask an LLM "What are the main tradeoffs among
  GCP Cloud Run, Azure Container Apps, and AWS ECS for deploying an
  API-based product?" and paste the full response + model name + prompt.
  Don't paraphrase it.
- 4g (human-only) -- your own call as an MLOps manager; not mine to write.

## Account-specific modification: pre-existing ECS execution role (AWS)

`deploy/aws/deploy_ecs.sh` accepts an optional `EXISTING_EXEC_ROLE_NAME`
variable. When set, the script skips creating `genreCS4EcsExecutionRole` and
uses the named, pre-provisioned role as the ECS task execution role (useful
on sandboxed accounts that block `iam:CreateRole`). Left unset, the script
behaves as before.

```bash
EXISTING_EXEC_ROLE_NAME=<role-name> ./deploy/aws/deploy_ecs.sh
```

**Not run for this team:** the AWS credentials provided belong to the IAM
*user* `ML_dev`, which has no ECR/ECS/ELB/EC2/IAM/Secrets Manager
permissions, so the AWS deploy could not proceed. See `CS4_STATUS.md`.

## Account-specific modifications: GCP and Azure

**GCP Cloud Run** (`deploy/gcp/deploy_cloudrun.sh`, mirrored in the workflow):
- Granted the default compute service account `roles/secretmanager.secretAccessor`
  on the `hf-token` secret. New projects no longer grant this implicitly, and
  the first deploy failed with "Permission denied on secret".
- `--execution-environment=gen2`: on the default gVisor sandbox the first
  request hung until the 300 s request timeout (the same image answered in
  ~3 s locally and on Azure); gen2 fixed it.
- `--no-cpu-throttling`, `--memory=4Gi` (was 2Gi), and `NO_PROXY=localhost,127.0.0.1`:
  Gradio's startup self-check against localhost failed on throttled CPU and
  crashed the instance.

**Azure Container Apps** (`deploy/azure/deploy_containerapps.sh`):
- The Students subscription only allows these regions: belgiumcentral,
  westus2, francecentral, norwayeast, northcentralus (policy "Allowed
  resource deployment regions"), so the default `eastus` was rejected. Run
  with `LOCATION=westus2`.
- ACR Tasks (`az acr build`) is blocked on this subscription
  (`TasksOperationsNotAllowed`), so the script falls back to a local
  `docker build` + `docker push`.
- Registered the `Microsoft.OperationalInsights` provider, which Container
  Apps environments need and fresh subscriptions lack.
