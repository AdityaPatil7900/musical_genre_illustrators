#!/bin/bash
# Quick connect to the Group 12 VM using your own key.
# Run from the folder that contains tmp/mykey (i.e. where you ran part 1).
set -euo pipefail
PORT=22012
MACHINE=paffenroth-23.dyn.wpi.edu
ssh -i tmp/mykey -p "${PORT}" -o StrictHostKeyChecking=no "student-admin@${MACHINE}"
