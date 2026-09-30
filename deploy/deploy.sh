#!/usr/bin/env bash
# ============================================================================
# Case Study 2 -- Automated Deployment Script
#
# Run this from YOUR LOCAL machine (must be on the WPI network or WPI VPN --
# the VM is not reachable from the public internet). It:
#   1. Copies your personal public key to the VM and adds it to
#      authorized_keys (using the still-valid student-admin default key).
#   2. Verifies your personal key works.
#   3. Removes the student-admin default key from authorized_keys, so only
#      your group can log in from then on.
#   4. Bootstraps the remote environment (git, python3-venv), clones/updates
#      the GitHub repo, creates a venv, installs dependencies.
#   5. Installs and (re)starts the systemd services for both products plus
#      the recovery watchdog and resource monitor.
#
# Usage:
#   ./deploy.sh
#
# Configure the variables below (or export them before running) first.
# ============================================================================
set -euo pipefail

# ---- Configuration ---------------------------------------------------------
VM_HOST="${VM_HOST:-paffenroth-23.dyn.wpi.edu}"
VM_PORT="${VM_PORT:-22012}"
VM_USER="${VM_USER:-student-admin}"

DEFAULT_KEY="${DEFAULT_KEY:-../../student-admin_key}"      # provided by professor
PERSONAL_KEY_PUB="${PERSONAL_KEY_PUB:-../../tmp/mykey.pub}" # your own keypair
PERSONAL_KEY_PRIV="${PERSONAL_KEY_PRIV:-../../tmp/mykey}"

REPO_URL="${REPO_URL:-https://github.com/AdityaPatil7900/musical_genre_illustrators.git}"
REPO_DIR="${REPO_DIR:-musical_genre_illustrators}"

SSH_DEFAULT="ssh -i $DEFAULT_KEY -p $VM_PORT -o StrictHostKeyChecking=accept-new"
SSH_MINE="ssh -i $PERSONAL_KEY_PRIV -p $VM_PORT -o StrictHostKeyChecking=accept-new"

log() { echo -e "\n\033[1;34m[deploy]\033[0m $*"; }

# ---- Step 1: rotate SSH keys ----------------------------------------------
log "Step 1/5: installing your personal public key on the VM..."
PUB_CONTENT="$(cat "$PERSONAL_KEY_PUB")"
$SSH_DEFAULT "$VM_USER@$VM_HOST" bash -s <<EOF
set -e
mkdir -p ~/.ssh
chmod 700 ~/.ssh
touch ~/.ssh/authorized_keys
grep -qxF '$PUB_CONTENT' ~/.ssh/authorized_keys || echo '$PUB_CONTENT' >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
EOF

log "Step 1/5: verifying your personal key works..."
if ! $SSH_MINE "$VM_USER@$VM_HOST" "echo OK" | grep -q OK; then
  echo "ERROR: personal key login failed -- aborting before removing the default key." >&2
  exit 1
fi

log "Step 1/5: removing the student-admin default key from authorized_keys..."
DEFAULT_PUB_CONTENT="$(cat "${DEFAULT_KEY}.pub")"
$SSH_MINE "$VM_USER@$VM_HOST" bash -s <<EOF
set -e
grep -vxF '$DEFAULT_PUB_CONTENT' ~/.ssh/authorized_keys > ~/.ssh/authorized_keys.tmp || true
mv ~/.ssh/authorized_keys.tmp ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
echo "authorized_keys now contains:"
cat ~/.ssh/authorized_keys
EOF
log "Key rotation complete. Only your group's key is authorized from here on."

# ---- Step 2: bootstrap remote environment ----------------------------------
log "Step 2/5: installing system dependencies (python3-venv, git) on the VM..."
$SSH_MINE "$VM_USER@$VM_HOST" bash -s <<'EOF'
set -e
if ! command -v git >/dev/null; then
  sudo apt-get update -y && sudo apt-get install -y git
fi
if ! python3 -m venv --help >/dev/null 2>&1; then
  sudo apt-get update -y && sudo apt-get install -y python3-venv python3-pip
fi
EOF

# ---- Step 3: clone / update the repo ---------------------------------------
log "Step 3/5: cloning/updating the GitHub repo on the VM..."
$SSH_MINE "$VM_USER@$VM_HOST" bash -s <<EOF
set -e
if [ -d "$REPO_DIR/.git" ]; then
  cd "$REPO_DIR" && git pull
else
  git clone "$REPO_URL" "$REPO_DIR"
fi
EOF

# ---- Step 4: create venv + install deps -------------------------------------
log "Step 4/5: creating virtualenv and installing dependencies..."
$SSH_MINE "$VM_USER@$VM_HOST" bash -s <<EOF
set -e
cd "$REPO_DIR"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-vm.txt
if [ ! -f .env ]; then
  cp deploy/.env.example .env
  echo "Created .env from template -- edit it with real HF_TOKEN / DISCORD_WEBHOOK_URL before services start correctly."
fi
chmod 600 .env
EOF

# ---- Step 5: install systemd units + start services -------------------------
log "Step 5/5: installing systemd units and starting services..."
scp -i "$PERSONAL_KEY_PRIV" -P "$VM_PORT" \
  deploy/systemd/*.service deploy/systemd/*.timer \
  "$VM_USER@$VM_HOST:/tmp/"

$SSH_MINE "$VM_USER@$VM_HOST" bash -s <<EOF
set -e
sudo mv /tmp/*.service /tmp/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now genre-api.service
sudo systemctl enable --now genre-local.service
sudo systemctl enable --now genre-watchdog.timer
sudo systemctl enable --now genre-monitor.timer
sudo systemctl status --no-pager genre-api.service genre-local.service | cat
EOF

log "Deployment complete."
log "API-based product:   http://$VM_HOST:8012"
log "Local product:       http://$VM_HOST:8013  (tunnel via 'ssh -i $PERSONAL_KEY_PRIV -p $VM_PORT -L 8013:localhost:8013 $VM_USER@$VM_HOST' if not externally routed)"
