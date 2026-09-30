# Runbook — Exact Commands to Run (Case Study 2)

Run all of this from a machine on the **WPI network or WPI VPN**
(GlobalProtect). This sandbox environment cannot reach the VM directly
(confirmed: SSH from here timed out), so these steps must be run by you.

## 0. Prerequisites

```powershell
# Confirm files exist
ls D:\CS553\student-admin_key, D:\CS553\student-admin_key.pub
ls D:\CS553\tmp\mykey, D:\CS553\tmp\mykey.pub

# Confirm you're on WPI network/VPN, then test raw connectivity
ssh -i D:\CS553\student-admin_key -p 22012 -o ConnectTimeout=10 student-admin@paffenroth-23.dyn.wpi.edu "echo OK"
```
If this hangs/times out, you are not on the WPI network/VPN yet — connect
and retry before continuing.

## 1. Push the code to GitHub (if not already there)

```powershell
cd D:\CS553\musical_genre_illustrator-main
git add vm_app.py requirements-vm.txt deploy/ docs/ .gitignore
git commit -m "Add Case Study 2: VM deployment, recovery watchdog, resource monitoring"
git push origin main
```

## 2. Set your Discord webhook locally (not committed)

```powershell
notepad D:\CS553\musical_genre_illustrator-main\deploy\.env.example
# Save a COPY as .env (not committed) with your real values, or just fill
# in DISCORD_WEBHOOK_URL / HF_TOKEN when deploy.sh prompts you to on the VM
# (it creates .env from the template automatically on first deploy).
```

## 3. Run the automated deployment script

From WSL / Git Bash (the script is bash, not PowerShell):
```bash
cd /d/CS553/musical_genre_illustrator-main/deploy
chmod +x deploy.sh watchdog.sh
./deploy.sh
```
This performs SSH key rotation, environment bootstrap, repo clone, venv +
dependency install, and installs/starts all systemd units. Takes several
minutes (model downloads on first classifier/diffusion pipeline load).

## 4. Fill in real secrets on the VM

```bash
ssh -i D:\CS553\tmp\mykey -p 22012 student-admin@paffenroth-23.dyn.wpi.edu
nano musical_genre_illustrator/.env
# Set real HF_TOKEN and DISCORD_WEBHOOK_URL, save, exit
sudo systemctl restart genre-api.service genre-local.service
chmod 600 musical_genre_illustrator/.env
exit
```

## 5. Add the scoped sudoers entry for the watchdog (one-time)

```bash
ssh -i D:\CS553\tmp\mykey -p 22012 student-admin@paffenroth-23.dyn.wpi.edu
sudo visudo -f /etc/sudoers.d/genre-watchdog
# paste this single line, save, exit editor:
# student-admin ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart genre-api.service, /usr/bin/systemctl restart genre-local.service
exit
```

## 6. Verify both products are live

```bash
curl -sf http://paffenroth-23.dyn.wpi.edu:8012/ && echo "API product OK"
ssh -i D:\CS553\tmp\mykey -p 22012 student-admin@paffenroth-23.dyn.wpi.edu "curl -sf http://localhost:8013/ && echo 'Local product OK'"
```
Open `http://paffenroth-23.dyn.wpi.edu:8012` in a browser to confirm the
Gradio UI renders and a test audio file classifies + generates an image.

## 7. Run the resilience tests

Follow `docs/RESILIENCE_TESTING.md` step by step, filling in the `TODO`
sections with your actual output.

## 8. (Optional) Set up the external Windows health checker

```powershell
schtasks /create /tn "GenreVMHealthCheck" /tr "powershell.exe -File D:\CS553\musical_genre_illustrator-main\deploy\external_healthcheck.ps1" /sc minute /mo 15
```

## 9. Write up the report

Fill in `docs/REPORT.md` with your actual screenshots, logs, and timings
from steps 6-8.
