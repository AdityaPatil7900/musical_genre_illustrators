# Case Study 2 — Project Report

**Group members:** Aditya Patil (solo group, Group 12)

## 1. Virtual Machine Setup Process

VM: `paffenroth-23.dyn.wpi.edu`, SSH port 22012 (22000 + group 12), reachable
only from the WPI network/VPN. Started with a professor-provided
`student-admin_key` ed25519 keypair and `wpi_llm_token`. Generated a personal
ed25519 keypair (`tmp/mykey`), used it to add our own public key to
`~/.ssh/authorized_keys` on the VM while still authenticated with the
default key, verified the new key worked, then removed the default key's
line from `authorized_keys` so only our group's key remains authorized (see
`docs/SSH_ACCESS.md` for full step-by-step).

Environment: Python 3 virtualenv (`.venv`) created via `python3 -m venv`,
dependencies from `requirements-vm.txt` (Gradio, transformers,
huggingface_hub, diffusers, torch/torchaudio, psutil, requests — notably
*without* the HF-Spaces-only `spaces` package). Secrets (`HF_TOKEN`,
`DISCORD_WEBHOOK_URL`) live in a `chmod 600` `.env` file on the VM, loaded by
systemd's `EnvironmentFile=`, never committed to git.

TODO: paste `nvidia-smi` output (or its absence) confirming whether the VM
has a GPU, and note how that affected image-generation latency.

## 2. Deployment Process

Both Case Study 1 products (API-based, locally-executed) come from one
codebase, deployed as two independent systemd services distinguished by an
`APP_MODE` env var — `genre-api.service` (port 8012, remote LLM +
Qwen-Image API) and `genre-local.service` (port 8013, local tiny-sd, no
network calls). Genre classification is always local in both. Full
architecture and the changes needed to make the original HF-Spaces-targeted
`app.py` VM-portable (removing `spaces`/ZeroGPU decorators, dropping HF
OAuth login in favor of a server-side token, adding host/port binding) are
in `docs/DEPLOYMENT.md`.

Main challenge: `app.py`'s `@spaces.GPU` decorators and `gr.LoginButton()`
OAuth flow only work inside Hugging Face Spaces infrastructure and have no
equivalent on a generic VM — resolved by writing a separate `vm_app.py`
entrypoint rather than trying to branch one file across both environments.

TODO: add any additional deployment issues you hit in practice (package
install failures, disk space, model download time, firewall/port routing
quirks) once you've actually run `deploy.sh`.

## 3. Automated Recovery

Recovery is layered: (1) systemd `Restart=always` catches process crashes
within ~5s; (2) a `watchdog.sh` script, run every 2 minutes via a systemd
timer, HTTP-health-checks both services and force-restarts + Discord-alerts
on failure, specifically to catch hangs that a crash-only restart policy
would miss; (3) for a full VM wipe (which the on-VM watchdog cannot detect,
since nothing survives to run it), recovery is a single re-run of
`deploy/deploy.sh` from an operator machine, optionally supplemented by an
external Windows-Task-Scheduler health checker that alerts if the VM
becomes entirely unreachable. Full design rationale in `docs/RECOVERY.md`.

TODO: summarize what `docs/RESILIENCE_TESTING.md` actually showed —
recovery time for each test, whether Discord alerts fired as expected, and
whether the scoped-sudoers approach for the watchdog's restart permission
worked without issues.

## 4. Additional Insights, Challenges, and Future Improvements

TODO — write this after running the tests. Suggested angles: how well a
2-minute watchdog interval balances detection speed vs. overhead; whether
`Restart=always` and the watchdog ever fought each other (flagged as a risk
in the LLM security review, item #5); whether CPU-only `tiny-sd` inference
time made the health-check timeout (5s) too aggressive during real image
generation; what you'd do differently with real `linux.wpi.edu`/WPI-CCC
access instead of an on-VM watchdog.

## 5. [LLM Only] Security and Automation Review

See `docs/LLM_SECURITY_REVIEW.md` for the full prompt, model used (Claude
Sonnet 5), and complete response. Summary: 7 findings ranging from High
(overly broad sudo scope for the watchdog) to Low (log rotation, heredoc
quoting). Implemented: scoped `sudoers.d` entry limited to the two specific
`systemctl restart` commands the watchdog needs (instead of blanket NOPASSWD
sudo), and enforced `chmod 600` on the `.env` secrets file. Accepted as
documented limitations given the assignment's scope/timeline: restart
flap-damming, heredoc variable interpolation, host-key-change trust on VM
rebuild, and log rotation.

---
*Extra credit attempted: Resource Monitoring and Adaptive Response (#6) —
implemented via `deploy/monitor.py`, threshold-triggered Discord alerts, and
a degraded-mode flag that `vm_app.py` checks to skip image generation under
load. See Test 4 in `docs/RESILIENCE_TESTING.md`. Red-Teaming (#5) not
attempted — TODO: decide whether to attempt within the Sept 29 – Oct 1
window if another group's default key is still active.*
