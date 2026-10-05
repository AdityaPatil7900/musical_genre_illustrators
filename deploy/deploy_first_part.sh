#!/bin/bash
# =============================================================================
# Case Study 2 - deploy_first_part.sh  (Group 12)
# Runs on YOUR laptop / linux.wpi.edu. Handles SSH keys + gets code onto the VM.
# Based on Prof. Paffenroth's reference (case_study_2 branch), adapted for group 12.
# =============================================================================
set -euo pipefail   # stop on any error, unset variable, or broken pipe

# ---- CONFIG: the only lines you edit ----------------------------------------
PORT=22012                                   # 22000 + group number (Group 12)
MACHINE=paffenroth-23.dyn.wpi.edu            # the host that fronts all group VMs
STUDENT_ADMIN_KEY_PATH="/d/cs553"    # folder holding student-admin_key from Canvas
REPO_URL="https://github.com/rcpaffenroth/DSCS553_WPI_Fall_2026.git"
REPO_BRANCH="case_study_2"                    # or point this at YOUR own CS1 repo/branch
# -----------------------------------------------------------------------------

echo "==> [1/7] Cleaning any stale host key for this VM (avoids 'host key changed' errors)"
ssh-keygen -R "[${MACHINE}]:${PORT}" 2>/dev/null || true
rm -rf tmp

echo "==> [2/7] Staging the shared student-admin key in tmp/ (git-ignored)"
mkdir tmp
cp "${STUDENT_ADMIN_KEY_PATH}"/student-admin_key* tmp/
chmod 700 tmp
cd tmp
chmod 600 student-admin_key*

echo "==> [3/7] Generating YOUR OWN group key pair (mykey / mykey.pub)"
rm -f mykey*
# -N "" = no passphrase, so the Phase 3 recovery cron job can use it unattended.
# (The professor used -N "careful" + ssh-agent; empty is simpler for automation.)
ssh-keygen -f mykey -t ed25519 -N "" -C "group12-cs553"

echo "==> [4/7] Building authorized_keys with ONLY your key (this locks out the default)"
# ONE '>' overwrites the file so it contains just your key. This both adds yours
# and removes the shared student-admin default in a single atomic step.
cat mykey.pub > authorized_keys
chmod 600 authorized_keys
echo "    authorized_keys now contains:"
cat authorized_keys

echo "==> [5/7] Uploading authorized_keys to the VM (last use of the default key)"
scp -i student-admin_key -P "${PORT}" -o StrictHostKeyChecking=no \
    authorized_keys "student-admin@${MACHINE}:~/.ssh/"

echo "==> [6/7] Verifying: your key works, and the server now holds only your key"
ssh -i mykey -p "${PORT}" -o StrictHostKeyChecking=no \
    "student-admin@${MACHINE}" "echo 'Login with mykey OK on:' && hostname && cat ~/.ssh/authorized_keys"

echo "==> [7/7] Cloning the product repo and copying it to the VM as ~/DSCS553_example"
rm -rf DSCS553_example
git clone --branch "${REPO_BRANCH}" --single-branch "${REPO_URL}" DSCS553_example
scp -i mykey -P "${PORT}" -o StrictHostKeyChecking=no -r \
    DSCS553_example "student-admin@${MACHINE}:~/"

echo "==> Part 1 complete. Default key removed, code is on the VM."
echo "    Next: run ./deploy_second_part.sh to build the env and launch the app."
