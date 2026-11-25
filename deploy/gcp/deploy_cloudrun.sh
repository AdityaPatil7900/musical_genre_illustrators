#!/usr/bin/env bash
# Case Study 4 -- deploy the API-based product to GCP Cloud Run.
#
# Run this from a shell where `gcloud` is authenticated
# (`gcloud auth login`) against the GCP project you set up with your WPI
# account. Nothing in this script or the repo ever stores your HF_TOKEN or
# any GCP credential -- HF_TOKEN is read from your local environment only
# and pushed straight into Secret Manager.
#
# Required environment variables (set these in your shell before running):
#   PROJECT_ID   - your GCP project id (e.g. wpi-cs553-group12)
#   HF_TOKEN     - your Hugging Face token (never committed, never pasted
#                  into chat -- export it in your own shell)
# Optional:
#   REGION       - defaults to us-central1
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID to your GCP project id}"
: "${HF_TOKEN:?Set HF_TOKEN in your local shell before running this script}"
REGION="${REGION:-us-central1}"
REPO_NAME="genre-api-repo"
SERVICE_NAME="genre-api"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${SERVICE_NAME}:latest"

echo "== Setting active project =="
gcloud config set project "${PROJECT_ID}"

echo "== Enabling required APIs (idempotent) =="
gcloud services enable run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com

echo "== Ensuring Artifact Registry repo exists =="
gcloud artifacts repositories describe "${REPO_NAME}" --location="${REGION}" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "${REPO_NAME}" \
    --repository-format=docker --location="${REGION}" \
    --description="Case Study 4 - genre-api images"

echo "== Configuring docker auth for Artifact Registry =="
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

echo "== Building and pushing image (Dockerfile.cloud) =="
docker build -f Dockerfile.cloud -t "${IMAGE}" .
docker push "${IMAGE}"

echo "== Pushing HF_TOKEN to Secret Manager =="
if gcloud secrets describe hf-token >/dev/null 2>&1; then
  printf '%s' "${HF_TOKEN}" | gcloud secrets versions add hf-token --data-file=-
else
  printf '%s' "${HF_TOKEN}" | gcloud secrets create hf-token --data-file=-
fi

echo "== Deploying to Cloud Run =="
gcloud run deploy "${SERVICE_NAME}" \
  --image="${IMAGE}" \
  --region="${REGION}" \
  --allow-unauthenticated \
  --port=8080 \
  --memory=2Gi \
  --cpu=2 \
  --min-instances=0 \
  --max-instances=2 \
  --set-env-vars=APP_MODE=api \
  --set-secrets=HF_TOKEN=hf-token:latest

echo "== Done. External URL: =="
gcloud run services describe "${SERVICE_NAME}" --region="${REGION}" --format='value(status.url)'
