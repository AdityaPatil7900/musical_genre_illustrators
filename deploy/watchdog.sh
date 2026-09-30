#!/usr/bin/env bash
# ============================================================================
# Recovery watchdog -- runs ON THE VM, triggered every 2 minutes by
# genre-watchdog.timer (systemd). Detects when either product has stopped
# responding and restarts it, logging and notifying Discord.
#
# This handles the "process/service crashed or hung" failure mode. It cannot
# recover from the *entire VM* being wiped (nothing would be left to run this
# script) -- that case is handled by re-running deploy.sh from your local
# machine (see docs/RECOVERY.md for the optional external-checker fallback).
# ============================================================================
set -uo pipefail

STATE_DIR="/home/student-admin/musical_genre_illustrators/.watchdog"
mkdir -p "$STATE_DIR"
LOG="$STATE_DIR/watchdog.log"
ENV_FILE="/home/student-admin/musical_genre_illustrators/deploy/.env"
[ -f "$ENV_FILE" ] && source "$ENV_FILE"

log() { echo "$(date -Iseconds) $*" >> "$LOG"; }

notify_discord() {
  local msg="$1"
  [ -z "${DISCORD_WEBHOOK_URL:-}" ] && return 0
  curl -s -H "Content-Type: application/json" \
       -d "{\"content\": \"$msg\"}" \
       "$DISCORD_WEBHOOK_URL" >/dev/null || true
}

check_and_restart() {
  local name="$1" port="$2" service="$3"
  local prev_state_file="$STATE_DIR/${service}.state"
  local prev_state
  prev_state="$(cat "$prev_state_file" 2>/dev/null || echo "unknown")"

  if curl -sf -m 5 "http://localhost:${port}/" >/dev/null; then
    if [ "$prev_state" = "down" ]; then
      log "$name recovered (port $port)."
      notify_discord "✅ **$name** recovered on port $port after watchdog restart."
    fi
    echo "up" > "$prev_state_file"
    return 0
  fi

  log "$name UNRESPONSIVE (port $port). Restarting $service..."
  sudo systemctl restart "$service"
  sleep 8

  if curl -sf -m 5 "http://localhost:${port}/" >/dev/null; then
    log "$name restarted successfully."
    notify_discord "⚠️ **$name** was down and has been automatically restarted by the watchdog."
  else
    log "$name STILL DOWN after restart attempt."
    if [ "$prev_state" != "down" ]; then
      notify_discord "🔴 **$name** is DOWN and the automatic restart did not bring it back. Manual intervention needed."
    fi
  fi
  echo "down" > "$prev_state_file"
}

check_and_restart "API-based product" 8012 genre-api.service
check_and_restart "Local product"     8013 genre-local.service
