# Case Study 2 — Group 12 deploy scripts

Adapted from Prof. Paffenroth's `case_study_2` reference. Port is set to **22012**
(22000 + group 12); external app URL is **http://paffenroth-23.dyn.wpi.edu:8012**.

## Before you run

1. Download `student-admin_key` (and `student-admin_key.pub` if present) from Canvas.
2. In `deploy_first_part.sh`, set `STUDENT_ADMIN_KEY_PATH` to the folder holding that
   key (default assumes `~/Downloads`).
3. If you're deploying **your own** CS1 apps instead of the professor's example, change
   `REPO_URL` / `REPO_BRANCH` in `deploy_first_part.sh` to your repo.
4. Make the scripts executable:
   ```
   chmod +x deploy_first_part.sh deploy_second_part.sh connect.sh
   ```

## Run order

```
./deploy_first_part.sh     # rotates SSH key (locks out default), copies code to VM
./deploy_second_part.sh    # builds venv, installs deps, launches the app
```

Then open **http://paffenroth-23.dyn.wpi.edu:8012** in a browser to see it running.
Use `./connect.sh` any time you need a shell on the VM.

## What each script does (for your report)

- **deploy_first_part.sh** — stages the shared key in a git-ignored `tmp/`, generates your
  own `mykey`, overwrites the VM's `authorized_keys` with **only your key** (adds yours +
  removes the default in one step), verifies your key works, then clones the repo and copies
  it to the VM as `~/DSCS553_example`.
- **deploy_second_part.sh** — over SSH: installs `python3-venv`, creates the venv, installs
  `requirements.txt` (CPU torch), and launches `app.py` with `nohup` so it survives logout.
  Output goes to `~/log.txt` on the VM.

## Safety notes

- `tmp/` holds your private key — keep it git-ignored (the course repo's `.gitignore`
  already lists `tmp/`). **Never commit keys, never paste a private key into an LLM.**
- The empty passphrase (`-N ""`) is chosen so the Phase 3 recovery cron job can use the key
  unattended. The professor's original used `-N "careful"` + `ssh-add`; either is fine, but
  no-passphrase is simpler for automation.
- After part 1, confirm you're locked down: the default `student-admin_key` should be
  **refused**, and only `mykey` should work. That secures you before the Sept 29 red-team
  window and earns the key-rotation points.
