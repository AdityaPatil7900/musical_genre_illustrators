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

GPU check: `nvidia-smi` returns `bash: nvidia-smi: command not found` on the
VM. `lspci | grep -i vga` shows two NVIDIA GPUs on the underlying physical
host (`NVIDIA Corporation Device 2684`), but this student VM is a guest that
gets no GPU passthrough or drivers — `lscpu` shows only 2 of the host's 32
threads assigned to this VM (`On-line CPU(s) list: 9,26`), confirming the
"2 vCPU, no GPU" allocation. This is why `requirements-vm.txt` pins CPU-only
wheels (`--extra-index-url https://download.pytorch.org/whl/cpu`,
`torch==2.7.0+cpu`, `torchaudio==2.7.0+cpu`) instead of default PyPI torch,
which would otherwise pull ~2GB of unusable CUDA libraries and risk failing
to run at all. Measured latency impact: a full `/analyze_music` call
(classify + LLM prompt + image generation) took ~75s on the API-mode
product and ~106s on the local-mode product (local `tiny-sd` image
generation on 2 CPU cores is the dominant cost) — both end-to-end tested
2026-09-30 with real audio input (see Section 3 for full evidence).

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

Additional issues hit in practice, diagnosed from actual VM logs during this
session (2026-09-30):

- **Missing `ffmpeg` broke every real request.** Both services returned
  HTTP 200 on their root page and looked "healthy" in `systemctl status`,
  but every actual `/analyze_music` call failed server-side with
  `ValueError: ffmpeg was not found but is required to load audio files
  from filename` (from `transformers/pipelines/audio_classification.py`).
  `requirements-vm.txt` installs `soundfile` but the HF audio-classification
  pipeline shells out to a system `ffmpeg` binary that was never installed
  as an OS package. Diagnosed via `journalctl -u genre-api.service` showing
  the full traceback after a real test call via `gradio_client`; fixed with
  `sudo apt-get install -y ffmpeg` (the VM's passwordless sudo made this a
  one-line fix, but it's a real gap: HTTP-level health checks alone cannot
  catch a missing OS dependency that only breaks the actual inference path,
  not the page load — see `Docs/RESILIENCE_TESTING.md` findings on this).
  Confirmed fixed by re-running the same real request end-to-end afterward.

- **Repo-name typo survived in shell scripts, not just systemd units.**
  The 4 systemd unit files correctly use the actual `musical_genre_illustrators`
  repo name, but `deploy/watchdog.sh` and the default in `deploy/monitor.py`
  still hardcoded an old singular `musical_genre_illustrator` path for
  `STATE_DIR`/`ENV_FILE`. Because `genre-watchdog.service` has no
  `EnvironmentFile=` of its own (it relies entirely on `watchdog.sh` sourcing
  `.env` itself), this meant the watchdog was silently never loading
  `DISCORD_WEBHOOK_URL` — its `[ -f "$ENV_FILE" ]` guard just quietly
  skipped a file that didn't exist at that path. Fixed by correcting both
  hardcoded paths and redeploying.

- **CRLF line endings from a Windows working tree broke both `watchdog.sh`
  and the live `deploy/.env` on the VM.** This local development machine has
  `git config core.autocrlf=true`, so the working-tree copy of `watchdog.sh`
  had CRLF line endings. Copying it to the VM as-is produced `watchdog.sh:
  line 22: syntax error near unexpected token '{\r'` on every single
  watchdog timer cycle — confirmed via `journalctl -u genre-watchdog.service`,
  which showed this exact failure on 7 consecutive 2-minute cycles.
  Separately, `deploy/.env` on the VM itself also had CRLF endings, so
  `source .env` set `DISCORD_WEBHOOK_URL` and `HF_TOKEN` with a trailing
  `\r` baked into the value — visible indirectly as `Warning: You are
  sending unauthenticated requests to the HF Hub` in `genre-api.service`'s
  logs despite `HF_TOKEN` being set. At the time, this was fixed only on the
  VM itself — stripping `\r` from the *deployed* copies (`sed 's/\r$//'`)
  and restarting the affected services, via a manual `scp` of the
  sed-stripped file rather than a git commit — which was enough to stop the
  HF warning and confirm the Discord webhook accepted POSTs (HTTP 204), but
  left the actual committed git blob for `deploy/deploy.sh`,
  `deploy/watchdog.sh`, and `deploy/monitor.py` still CRLF-contaminated. A
  later read-only verification pass (2026-09-30) caught this: a fresh clone
  of the repo on Linux running `bash deploy/watchdog.sh` directly would have
  hit the identical syntax error, since the fix had never actually been
  committed. This has now been fixed for real — all three files normalized
  to LF (`sed -i 's/\r$//'`), verified with `bash -n` / `python -m
  py_compile`, and committed, plus a `.gitattributes` added
  (`*.sh`/`*.py`/`*.service`/`*.timer`/etc. forced to `eol=lf`) so a Windows
  checkout with `core.autocrlf=true` can't silently reintroduce CRLF into
  these files again.

- **Report overclaimed a security fix that was never applied.** The LLM
  security review's own summary and `Docs/RECOVERY.md` both stated a scoped
  `sudoers.d` entry had been "implemented" for the watchdog's restart
  permission. Checking `sudo -l` on the VM during this session showed
  `student-admin` still has blanket `(ALL) NOPASSWD: ALL`, sourced from
  `/etc/sudoers.d/90-cloud-init-users` — a file provisioned by the course VM
  image itself, unrelated to anything our deploy scripts touch. Corrected
  the report and `Docs/RECOVERY.md`/`Docs/LLM_SECURITY_REVIEW.md` to
  reflect this honestly as a recommended-but-not-applied finding (see
  Section 5) rather than leave a false "fixed" claim in the deliverable.

- **External reachability confirmed, not just localhost.** Per
  `Docs/SSH_ACCESS.md`, only the 8000+group-number port (8012, the API-based
  product) is the designated externally-reachable port for this
  assignment. Tested from outside the VM (a separate machine on the WPI
  network) on 2026-09-30: `curl http://paffenroth-23.dyn.wpi.edu:8012`
  returned HTTP 200; the same request against `:8013` (local-mode product)
  timed out/refused, confirming it is intentionally not externally exposed
  rather than accidentally broken.

- **A real secret was found sitting in a tracked template file.**
  `deploy/.env.example` — meant to hold only placeholder values — had a real
  Discord webhook URL committed to it in the repo's git history. Restored
  it to placeholder values and flagged the webhook for rotation, since it
  was already exposed in the public GitHub repository's history
  independent of anything done in this session.

- **Genre classifier model download previously got stuck mid-restart**
  (per prior session history), leaving stale `.lock` files and a corrupt
  partial cache entry under `~/.cache/huggingface/hub/`. This was already
  resolved before this session — `systemctl status` and real end-to-end
  test calls in this session both confirm the classifier loads and
  classifies correctly (see Section 3) with no repeat of that failure mode.

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

All tests below were run live against the VM on 2026-09-30; exact commands
and full log excerpts are in `Docs/RESILIENCE_TESTING.md`.

- **Test 1 — `sudo systemctl kill -s SIGKILL genre-api.service`.**
  Killed at 05:31:51 UTC. `systemctl show -p MainPID` confirmed a new PID
  (7673 → 11666) within the same second, consistent with `Restart=always`
  + `RestartSec=5`. However, the port did not actually start serving HTTP
  200 again until 05:33:57 UTC (~2m6s later) — cold-loading the genre
  classifier model under this VM's memory pressure (2.6-3.1GB/4GB used,
  100s of MB swapped) took far longer than the process-restart itself.
  This confirms systemd's crash recovery works, but also that "process is
  running" and "service is actually usable" are different things on this
  hardware — relevant to Test 2 below.

- **Test 2 — `sudo systemctl stop genre-local.service`** (isolates the
  watchdog layer from `Restart=always`, which a `stop` intentionally
  disables). Stopped at 05:39:21 UTC. The very next `genre-watchdog.timer`
  cycle (fires every 2 min) detected it unresponsive at 05:39:54 UTC — 33s
  after the stop — and issued `systemctl restart genre-local.service`.
  `watchdog.log`:
  ```
  2026-09-30T05:39:54+00:00 Local product UNRESPONSIVE (port 8013). Restarting genre-local.service...
  2026-09-30T05:40:02+00:00 Local product STILL DOWN after restart attempt.
  2026-09-30T05:41:54+00:00 Local product recovered (port 8013).
  ```
  The "STILL DOWN" line at 05:40:02 is the watchdog's own 8-second
  post-restart check firing before the model finished loading (same
  cold-start cost as Test 1) — it correctly triggered a "manual
  intervention needed" Discord alert even though the restart itself had
  actually succeeded, and the next 2-minute cycle logged the real recovery
  at 05:41:54 (2m33s total, from stop to a real HTTP 200) and sent the
  "recovered" Discord alert. Both alert code paths were confirmed to
  actually reach Discord — a direct test POST to the (redacted) webhook URL
  from the VM returned HTTP 204 immediately after this test. This is a real
  limitation, not a hypothetical one: it's the same 5-8s-timeout-vs-cold-load
  mismatch called out as a risk area in the LLM security review and
  `Docs/REPORT.md` Section 4.

- **Test 4 — resource-threshold degraded mode** (extra credit #6).
  Lowered `CPU_THRESHOLD_PCT` from 80 to 5 in `deploy/.env` at 05:43:12 UTC
  (baseline idle CPU on this VM runs ~8-15%, so this reliably breaches
  without needing an external stress tool). The next `genre-monitor.timer`
  cycle (fires every 1 min) logged entry into degraded mode:
  ```
  2026-09-30T05:44:17.919342+00:00 ENTERING degraded mode.
  ```
  and wrote `.watchdog/degraded_mode.flag`. Verified `vm_app.py`'s
  `is_degraded()` actually changes request behavior, not just that the flag
  file exists: sent a real audio file through `genre-local`'s
  `/analyze_music` endpoint while the flag was present, and got back the
  genre/confidence as normal but with image generation skipped and the
  message `"⚠️ System is currently operating near capacity — image
  generation is temporarily disabled. Genre classification is still
  available."` and a `None` image path — the exact adaptive-response
  behavior the extra-credit feature is meant to provide. Reverted
  `CPU_THRESHOLD_PCT` to 80 at 05:45:04 UTC; the next monitor cycle cleared
  it:
  ```
  2026-09-30T05:45:22.191530+00:00 EXITING degraded mode.
  ```
  Both the entering and exiting transitions call `notify_discord()` in
  `monitor.py`; the webhook itself was independently confirmed reachable
  (HTTP 204) during this session.

- **Test 3 — full VM wipe / redeploy.** Not attempted this session (the VM
  was not wiped) — `deploy/deploy.sh` was not re-run end-to-end as a
  destructive test, since doing so is a genuinely disruptive, hard-to-reverse
  action against a live, working deployment and wasn't necessary to
  demonstrate the required resilience scenarios. Documented in
  `Docs/RESILIENCE_TESTING.md` as the untested scenario.

On the scoped-sudoers question specifically: it was never actually applied
(see Section 5) — `student-admin` has blanket `sudo` from a course-provided
cloud-init file, not from anything in this project — so "did the scoped
approach work without issues" doesn't apply; the watchdog's `sudo systemctl
restart ...` calls worked throughout testing because of that blanket
grant, not because of a scoping fix.

## 4. Additional Insights, Challenges, and Future Improvements

**2-minute watchdog interval vs. cold-start time.** Both resilience tests
showed the real bottleneck isn't detection speed (the watchdog caught the
failure within one cycle, 27-33s, every time) but that this VM's cold model
load time (~2 minutes under real memory pressure, for either product) is
close to the watchdog's own interval. The watchdog's internal 8-second
post-restart re-check is too short relative to that load time, which is why
Test 2 logged a "manual intervention needed" alert for a restart that had
actually succeeded — a false-positive alert, not a false sense of health.
A more accurate design would poll for up to ~90s after a restart before
declaring it failed, at the cost of a longer-running watchdog invocation.

**Did `Restart=always` and the watchdog fight each other?** Not observed in
either test. Test 1 (kill) resolved via `Restart=always` alone, well before
any watchdog cycle. Test 2 (stop) disabled `Restart=always` by design (a
`systemctl stop` is deliberate, not a crash), so only the watchdog acted.
The two mechanisms are complementary in practice because they're triggered
by different failure shapes (crash vs. hang), not because of any explicit
coordination — the flap-damping gap flagged in the LLM security review
(item #5) remains a real risk for a *repeatedly*-crashing service, just not
one either test exercised.

**Memory pressure was the dominant constraint, not CPU.** `free -h` during
testing showed 2.6-3.1GB/4GB RAM used with 400MB-1.3GB swapped even at idle
with both services loaded, on a box with no GPU and 2 vCPUs. This is the
real reason cold-starts took ~2 minutes rather than seconds — disk-swap
thrashing while reloading the genre classifier and (for local mode) the
`tiny-sd` pipeline, confirmed by the process sitting in `D` (uninterruptible
disk-wait) state during a restart. With real `linux.wpi.edu`/WPI-CCC access
or a beefier VM, the fix would be simpler: more RAM, or serving genre
classification and image generation as separate processes/services so a
restart of one doesn't have to reload both models into contention for the
same 4GB.

**Windows-to-Linux line-ending drift is a real, recurring risk for this
setup.** Twice during this session, a file edited/copied from this Windows
development machine (`core.autocrlf=true`) silently broke on the VM — once
in a way that failed loudly (`watchdog.sh` syntax error, visible in
`journalctl`) and once in a way that failed silently (`.env`'s CRLF just
corrupted an env-var value, no error, just a wrong behavior). Anyone
continuing this project from Windows should run scripts through
`sed 's/\r$//'` or set `git config core.autocrlf=input` before any file
that will be sourced or executed as a script on the VM.

## 5. [LLM Only] Security and Automation Review

See `Docs/LLM_SECURITY_REVIEW.md` for the full prompt, model used (Claude
Sonnet 5), and complete response. Summary: 7 findings ranging from High
(overly broad sudo scope for the watchdog) to Low (log rotation, heredoc
quoting). Implemented: verified and enforced `chmod 600` on the `.env`
secrets file (confirmed on the VM). Checked but *not* implemented: the
scoped `sudoers.d` entry recommended for item #1 — `sudo -l` on the VM shows
`student-admin` already has blanket `(ALL) NOPASSWD: ALL` from
`/etc/sudoers.d/90-cloud-init-users`, a course-provisioned cloud-init file
predating our deploy scripts. We decided not to edit base sudo policy on
the shared VM (risk of a sudoers typo locking out all sudo access outweighs
the benefit here), and documented this as an accepted, un-actioned finding
rather than claiming a fix that wasn't made. Accepted as documented
limitations given the assignment's scope/timeline: restart flap-damming,
heredoc variable interpolation, host-key-change trust on VM rebuild, and
log rotation.

---
*Extra credit attempted: Resource Monitoring and Adaptive Response (#6) —
implemented via `deploy/monitor.py`, threshold-triggered Discord alerts, and
a degraded-mode flag that `vm_app.py` checks to skip image generation under
load; verified end-to-end (entering and exiting degraded mode, with a real
adaptive-response request) on 2026-09-30 — see Section 3 above and Test 4
in `Docs/RESILIENCE_TESTING.md`. Red-Teaming (#5) attempted — full
evidence-based writeup in `Docs/RED_TEAMING.md`. Summary: 3 groups (13, 14,
20) confirmed still reachable with the shared default `student-admin_key`
during the authorized window (timestamps 2026-09-29 15:22–16:09 UTC), each
check limited to `hostname`/`date` only, no other access. Group 13 was
notified via Canvas with the finding and a recommendation to rotate their
key. Group 20's vulnerability is documented but **no notification was sent
to them** — a known gap in this submission. Two other groups reportedly
probed during the same window (3, 6) plus one more (17) are not claimed as
findings since no saved evidence for them could be located.*
