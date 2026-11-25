#!/usr/bin/env bash
# Case Study 4 -- deploy the API-based product to Azure Container Apps.
#
# Run this from a shell where `az` is authenticated (`az login`) against
# the Azure for Students subscription set up with your WPI email. HF_TOKEN
# is read only from your local environment and pushed straight into the
# Container App's own secret store -- never committed, never in this chat.
#
# Required environment variables:
#   HF_TOKEN       - your Hugging Face token
# Optional (sensible defaults given, but ACR_NAME must be globally unique):
#   RESOURCE_GROUP - defaults to genre-cs4-rg
#   LOCATION       - defaults to eastus
#   ACR_NAME       - defaults to genrecs4acr<random>; must be globally
#                    unique across ALL of Azure, lowercase alphanumeric only
set -euo pipefail

: "${HF_TOKEN:?Set HF_TOKEN in your local shell before running this script}"
RESOURCE_GROUP="${RESOURCE_GROUP:-genre-cs4-rg}"
LOCATION="${LOCATION:-eastus}"
ACR_NAME="${ACR_NAME:-genrecs4acr$RANDOM}"
ENV_NAME="genre-cs4-env"
APP_NAME="genre-api"

echo "== Registering required providers (idempotent, safe to re-run) =="
az provider register --namespace Microsoft.App --wait
az provider register --namespace Microsoft.ContainerRegistry --wait
# Container Apps environments create a Log Analytics workspace; fresh
# subscriptions (e.g. Azure for Students) are not registered for it by default.
az provider register --namespace Microsoft.OperationalInsights --wait

echo "== Creating resource group =="
az group create --name "${RESOURCE_GROUP}" --location "${LOCATION}" >/dev/null

echo "== Creating Azure Container Registry (Basic SKU, free-tier friendly) =="
az acr create --resource-group "${RESOURCE_GROUP}" --name "${ACR_NAME}" \
  --sku Basic --admin-enabled true >/dev/null

echo "== Building and pushing image via ACR Tasks (no local docker needed) =="
if ! az acr build --registry "${ACR_NAME}" --image genre-api:latest -f Dockerfile.cloud .; then
  # Azure for Students subscriptions can block ACR Tasks
  # (TasksOperationsNotAllowed). Fall back to a local docker build + push.
  echo "== ACR Tasks unavailable; falling back to local docker build + push =="
  az acr login --name "${ACR_NAME}"
  LOCAL_IMAGE="${ACR_NAME}.azurecr.io/genre-api:latest"
  docker build -f Dockerfile.cloud -t "${LOCAL_IMAGE}" .
  docker push "${LOCAL_IMAGE}"
fi

echo "== Creating Container Apps environment =="
az containerapp env create --name "${ENV_NAME}" \
  --resource-group "${RESOURCE_GROUP}" --location "${LOCATION}" >/dev/null

ACR_SERVER=$(az acr show --name "${ACR_NAME}" --query loginServer -o tsv)
ACR_USER=$(az acr credential show --name "${ACR_NAME}" --query username -o tsv)
ACR_PASS=$(az acr credential show --name "${ACR_NAME}" --query "passwords[0].value" -o tsv)

echo "== Creating Container App =="
az containerapp create \
  --name "${APP_NAME}" \
  --resource-group "${RESOURCE_GROUP}" \
  --environment "${ENV_NAME}" \
  --image "${ACR_SERVER}/genre-api:latest" \
  --registry-server "${ACR_SERVER}" \
  --registry-username "${ACR_USER}" \
  --registry-password "${ACR_PASS}" \
  --target-port 8080 \
  --ingress external \
  --cpu 2.0 --memory 4.0Gi \
  --min-replicas 0 --max-replicas 2 \
  --secrets "hf-token=${HF_TOKEN}" \
  --env-vars "APP_MODE=api" "PORT=8080" "HF_TOKEN=secretref:hf-token" >/dev/null

echo "== Done. External URL: =="
az containerapp show --name "${APP_NAME}" --resource-group "${RESOURCE_GROUP}" \
  --query properties.configuration.ingress.fqdn -o tsv
