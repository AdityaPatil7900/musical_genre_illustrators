#!/bin/bash
# =============================================================================
# Case Study 2 - deploy_second_part.sh  (Group 12)
# Runs from YOUR laptop; drives setup ON the VM over SSH using your key.
# Builds the Python env and launches the product. App listens on 7860 inside
# the VM, reachable externally at http://paffenroth-23.dyn.wpi.edu:8012
# =============================================================================
set -euo pipefail

# ---- CONFIG -----------------------------------------------------------------
PORT=22012
MACHINE=paffenroth-23.dyn.wpi.edu
# -----------------------------------------------------------------------------

cd tmp   # your key (mykey) lives here from part 1

# Helper: one SSH connection prefix, reused for every remote command
COMMAND="ssh -i mykey -p ${PORT} -o StrictHostKeyChecking=no student-admin@${MACHINE}"

echo "==> [1/5] Confirming the code is on the VM"
${COMMAND} "ls DSCS553_example"

echo "==> [2/5] Installing python venv support (system package)"
${COMMAND} "sudo apt-get update -qq && sudo apt-get install -qq -y python3-venv"

echo "==> [3/5] Creating the virtual environment"
${COMMAND} "cd DSCS553_example && python3 -m venv venv"

echo "==> [4/5] Installing dependencies (CPU torch build, may take a few minutes)"
${COMMAND} "cd DSCS553_example && source venv/bin/activate && pip install -r requirements.txt"

echo "==> [5/5] Launching the app persistently (survives logout); output -> ~/log.txt"
# nohup + '&' keeps it running after the SSH session closes.
${COMMAND} "nohup DSCS553_example/venv/bin/python3 DSCS553_example/app.py > log.txt 2>&1 &"

echo "==> Part 2 complete."
echo "    Open:  http://${MACHINE}:8012"
echo "    Logs:  ${COMMAND} \"tail -f log.txt\""
