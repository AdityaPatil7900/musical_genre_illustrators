#!/usr/bin/env bash
# ============================================================================
# Case Study 3 -- Docker Deployment Script
#
# Deploys both products + the Prometheus/Grafana monitoring stack onto the
# shared class Docker VM, via Docker Compose. Mirrors the key-rotation +
# bootstrap pattern from deploy.sh (Case Study 2), but installs Docker
# instead of a venv/systemd stack and ends with `docker compose up -d --build`.
#
# Run this from YOUR LOCAL machine (WPI network or WPI VPN required -- the
# VM is not reachable from the public internet).
#
# Before running:
#   1. Claim a port block on the class Google Sheet (rubric item 1c) and
#      set docker/.env from docker/.env.example to match what you claimed.
#   2. Fill in VM_HOST / VM_PORT below (or export them) with the shared
#      Docker VM's address and YOUR GROUP'S assigned SSH port -- these are
#      NOT the same as the Case Study 2 VM/port.
#
# Usage:
#   ./deploy/deploy_docker.sh
# ============================================================================
set -euo pipefail

# ---- Configuration ---------------------------------------------------------
VM_HOST="${VM_HOST:-paffenroth-23.dyn.wpi.edu}"   # shared Docker VM for CS3 -- confirm with course staff
VM_PORT="${VM_PORT:-REPLACE_WITH_YOUR_GROUPS_SSH_PORT}"
VM_USER="${VM_USER:-student-admin}"

PERSONAL_KEY_PRIV="${PERSONAL_KEY_PRIV:-../../tmp/mykey}"   # reuse the CS2 personal key if this VM accepts it,
                                                             # otherwise point at whatever key this VM issued you

REPO_URL="${REPO_URL:-https://github.com/AdityaPatil7900/musical_genre_illustrators.git}"
REPO_DIR="${REPO_DIR:-musical_genre_illustrators}"
BRANCH="${BRANCH:-case-study-3}"

SSH_MINE="ssh -i $PERSONAL_KEY_PRIV -p $VM_PORT -o StrictHostKeyChecking=accept-new"

log() { echo -e "\n\033[1;34m[deploy]\033[0m $*"; }

if [ "$VM_PORT" = "REPLACE_WITH_YOUR_GROUPS_SSH_PORT" ]; then
  echo "ERROR: set VM_PORT to your group's actual SSH port on the shared Docker VM before running." >&2
  exit 1
fi

# ---- Step 1: confirm access + bootstrap Docker ------------------------------
log "Step 1/4: confirming SSH access and that Docker is available..."
if ! $SSH_MINE "$VM_USER@$VM_HOST" "echo OK" | grep -q OK; then
  echo "ERROR: SSH login failed -- check VM_HOST/VM_PORT/PERSONAL_KEY_PRIV." >&2
  exit 1
fi
$SSH_MINE "$VM_USER@$VM_HOST" bash -s <<'EOF'
set -e
if ! command -v docker >/dev/null; then
  echo "ERROR: docker not found on the VM -- it should be pre-installed per the assignment. Contact course staff." >&2
  exit 1
fi
docker --version
docker compose version
EOF

# ---- Step 2: clone / update the repo ---------------------------------------
log "Step 2/4: cloning/updating the GitHub repo (branch: $BRANCH) on the VM..."
$SSH_MINE "$VM_USER@$VM_HOST" bash -s <<EOF
set -e
if [ -d "$REPO_DIR/.git" ]; then
  cd "$REPO_DIR" && git fetch origin && git checkout "$BRANCH" && git pull origin "$BRANCH"
else
  git clone --branch "$BRANCH" "$REPO_URL" "$REPO_DIR"
fi
EOF

# ---- Step 3: push docker/.env (not committed to git) ------------------------
log "Step 3/4: copying docker/.env to the VM..."
if [ ! -f "docker/.env" ]; then
  echo "ERROR: docker/.env not found locally -- copy docker/.env.example to docker/.env and fill it in first." >&2
  exit 1
fi
scp -i "$PERSONAL_KEY_PRIV" -P "$VM_PORT" -o StrictHostKeyChecking=accept-new \
  docker/.env "$VM_USER@$VM_HOST:~/$REPO_DIR/docker/.env"

# ---- Step 4: build + start the stack ----------------------------------------
log "Step 4/4: building and starting the Docker Compose stack..."
$SSH_MINE "$VM_USER@$VM_HOST" bash -s <<EOF
set -e
cd "$REPO_DIR"
docker compose --env-file docker/.env up -d --build
docker compose ps
EOF

log "Deployment complete. On the VM:"
log "  API product     -> host port from API_APP_PORT in docker/.env (default 8012), container port 7860"
log "  Local product    -> host port from LOCAL_APP_PORT in docker/.env (default 8013), container port 7860"
log "  Prometheus       -> host port from PROMETHEUS_PORT (default 9090)"
log "  Grafana          -> host port from GRAFANA_PORT (default 3000)"
log "Next: SSH in and run 'ngrok start --all --config docker/ngrok/ngrok.yml' to expose these — see docker/README.md."
