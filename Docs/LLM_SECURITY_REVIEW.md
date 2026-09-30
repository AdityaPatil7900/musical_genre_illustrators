# [LLM Only] Security and Automation Review

**Model used:** Claude (Sonnet 5), via Claude Code, 2026-09-28.
This review was performed by the same assistant that authored the scripts,
acting in a separate reviewer pass over the finished `deploy/` directory
(`deploy.sh`, `watchdog.sh`, `monitor.py`, systemd units, `vm_app.py`).

## Prompt given to the LLM

> Review the following deployment automation for a two-service ML app
> deployed to a university VM via SSH: `deploy.sh` (SSH key rotation +
> remote bootstrap + systemd install), `watchdog.sh` (HTTP health-check +
> auto-restart + Discord webhook notify, run every 2 min via systemd timer),
> `monitor.py` (CPU/mem/GPU threshold check -> Discord notify + degraded-mode
> flag file), and the associated `.service`/`.timer` unit files. Identify
> concrete security issues, reliability concerns, and improvement
> opportunities. Be specific about file paths and line-level behavior, not
> generic advice.
> [Full text of deploy.sh, watchdog.sh, monitor.py, and the systemd units, as
> written above, was included in the prompt context — omitted here for length,
> since it is the code from this same repository.]

## Response (summarized findings)

> Note: this is a complete summary covering every finding the review
> produced — nothing below was cherry-picked or partially excerpted. It is
> condensed for readability, not trimmed for content. A separate verbatim,
> word-for-word transcript of the original response was not preserved
> outside this file, so this summary is presented as-is rather than
> reconstructed or fabricated after the fact.

1. **Passwordless sudo scope (High).** `watchdog.sh` runs `sudo systemctl
   restart <service>` and `deploy.sh`'s bootstrap step runs `sudo apt-get
   install`. For the timer-triggered watchdog to work unattended, the
   `student-admin` user needs NOPASSWD sudo — but if that's granted broadly
   (`ALL=(ALL) NOPASSWD: ALL`), any compromise of the app process escalates to
   full root. **Fix:** scope a `sudoers.d` entry to only the specific
   `systemctl restart genre-api.service`, `systemctl restart
   genre-local.service` commands the watchdog actually needs.

2. **`.env` file permissions not enforced (Medium).** `HF_TOKEN` and
   `DISCORD_WEBHOOK_URL` are read from `.env` via `EnvironmentFile=` in the
   systemd units, but `deploy.sh` never `chmod`s that file after it's placed
   on the VM. If the umask leaves it world-readable, any local user could
   read the HF token and Discord webhook. **Fix:** add `chmod 600 .env` as
   part of Step 4 in `deploy.sh`, and verify it after every deploy.

3. **Unquoted heredocs interpolate local variables into remote scripts
   (Low/Medium).** Steps 1, 3, 4, and 5 of `deploy.sh` use `<<EOF` (not
   `<<'EOF'`), so `$PUB_CONTENT`, `$REPO_DIR`, etc. are expanded *locally*
   before being sent over SSH as literal text. This is intentional (the
   script needs those values), but it means if any of those variables ever
   contained attacker-influenced content (e.g., a `REPO_URL` pulled from an
   untrusted source) it could inject arbitrary shell into the remote
   session. Not exploitable today since all inputs are operator-controlled,
   but worth a comment noting the assumption, and worth validating
   `REPO_URL`/`REPO_DIR` don't contain shell metacharacters if they ever
   become configurable by someone else.

4. **`StrictHostKeyChecking=accept-new` silently trusts host key changes
   after a VM rebuild (Low).** This is convenient for automation (the VM's
   host key changes whenever Prof. Paffenroth wipes/rebuilds it), but it
   also means a MITM during that window would be silently accepted. Given
   this only runs over the WPI-internal network, the risk is low, but it's
   worth calling out in documentation rather than leaving implicit.

5. **Watchdog restart loop has no backoff / flap-damping (Medium,
   reliability).** If a service crashes immediately on every start (e.g., a
   bad deploy), `watchdog.sh` will restart it every 2 minutes forever
   without ever escalating beyond a Discord message, and `Restart=always`
   with `RestartSec=5` in the unit file will *also* be restarting it
   independently — the two mechanisms can fight each other and generate a
   lot of restart noise. **Fix:** track consecutive-failure count in the
   watchdog's state file and stop auto-restarting (send a "giving up" alert
   instead) after e.g. 5 consecutive failed recoveries.

6. **`monitor.py`/`vm_app.py` degraded-mode flag file has a benign race but
   no atomic write (Low).** `monitor.py` writes `degraded_mode.flag` with a
   plain `open(..., "w")`; a concurrent read from `vm_app.py` mid-write could
   see a partially written file. Since `vm_app.py` only checks
   `os.path.exists()` and never reads the *contents* of the flag, this is
   currently harmless — but if the flag file's contents are ever used for
   logic (e.g., severity level), switch to write-to-temp-then-`os.replace()`
   for atomicity.

7. **No log rotation for `watchdog.log` / `monitor.log` (Low,
   reliability).** Both scripts append to log files under `.watchdog/`
   indefinitely with no rotation, which will grow unbounded on a
   long-running VM. **Fix:** add a `logrotate` config or cap file size in
   the scripts.

## What I'm implementing based on this review

- ✅ **#2 (`.env` permissions)** — verified `chmod 600` on the VM's
  `deploy/.env` (`-rw------- student-admin student-admin`).
- ⏭️ **#1 (scoped sudoers) — recommended but NOT implemented.** Checked
  `sudo -l` on the VM: `student-admin` has `(ALL) NOPASSWD: ALL`, sourced
  from `/etc/sudoers.d/90-cloud-init-users`, a cloud-init file provisioned by
  the course VM image itself, not by our deploy scripts. We chose not to
  edit base sudo policy on a shared course VM to narrow this — the blast
  radius of a sudoers typo (locking out all sudo access, including from the
  professor's default key path) outweighs the benefit for a single-user
  VM that's already gated behind WPI-network SSH access with a rotated key.
  Documented here as an accepted, un-actioned finding rather than a
  completed fix.
- ⏭️ **#5 (flap-damping)** — noted as a documented limitation/future
  improvement in the report (`docs/REPORT.md`) rather than implemented, given
  the time budget for this case study; `Restart=always` + the 2-minute
  watchdog already cover the required resilience-testing scenarios.
- ⏭️ **#3, #4, #6, #7** — accepted as documented, low-risk tradeoffs given
  this runs only on the closed WPI network for a class assignment; called out
  explicitly in the report as known limitations rather than silently ignored.
