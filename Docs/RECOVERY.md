# Automatic Server Recovery (Case Study 2, Deliverable 3b)

## Design

The assignment's suggested pattern (external cron on `linux.wpi.edu`)
requires WPI CCC account access, which is not available for this
group. Per the assignment's "other approaches are also acceptable" clause,
recovery is implemented as a **self-healing watchdog running on the VM
itself**, layered with systemd's own restart supervision:

1. **Process-level supervision (`systemd Restart=always`).** Both
   `genre-api.service` and `genre-local.service` are systemd units with
   `Restart=always` / `RestartSec=5`. If the Python process crashes or is
   `kill -9`'d, systemd restarts it within 5 seconds, no external trigger
   needed.

2. **Application-level health checks (`watchdog.sh` + `genre-watchdog.timer`,
   every 2 minutes).** systemd's process supervision can't detect a process
   that's still *running* but hung/unresponsive (e.g., deadlocked, out of
   memory but not crashed). `watchdog.sh` curls each service's root URL; if
   it doesn't get a response within 5 seconds, it force-restarts that
   service via `systemctl restart` and posts a Discord notification. It logs
   every check to `.watchdog/watchdog.log` and de-duplicates notifications
   (only alerts on state *transitions*, not every failed check).

3. **Scoped sudo for the watchdog.** The watchdog runs as `student-admin`
   and needs `sudo systemctl restart <service>` without a password prompt
   (it's unattended, triggered by a timer). Instead of granting blanket
   NOPASSWD sudo, add this to `/etc/sudoers.d/genre-watchdog` (via `sudo
   visudo -f /etc/sudoers.d/genre-watchdog`):
   ```
   student-admin ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart genre-api.service, /usr/bin/systemctl restart genre-local.service
   ```
   This was flagged by the LLM security review (`Docs/LLM_SECURITY_REVIEW.md`,
   finding #1) as the recommended fix. In practice, `student-admin` already
   has blanket `(ALL) NOPASSWD: ALL` from the course-provisioned
   `/etc/sudoers.d/90-cloud-init-users`, independent of anything our deploy
   scripts configure. We did not add the entry above or edit the base sudo
   policy, since doing so on a shared course VM risks locking out sudo
   entirely on a syntax mistake for a single-user, WPI-network-gated VM. See
   `Docs/LLM_SECURITY_REVIEW.md` for the full reasoning — this is recorded as
   an accepted, un-actioned recommendation, not a completed fix.

## What this does NOT cover: full VM wipe

If the entire VM is wiped (disk reset, not just the app crashing), nothing
is left running to trigger its own recovery — this is a fundamental
limitation of any *on-VM* watchdog. Recovery from a full wipe requires
re-running `deploy/deploy.sh` from an operator's machine.

### Optional fallback: external checker from a personal machine

Since WPI CCC (`linux.wpi.edu`) access wasn't available, an alternative
external checker can run from any machine on the WPI VPN using the OS's own
scheduler (e.g., Windows Task Scheduler running a PowerShell script every 15
minutes) that SSHes in and checks `systemctl is-active genre-api.service`,
alerting via Discord if the SSH connection itself fails (implying the VM is
down) — see `deploy/external_healthcheck.ps1`. This was implemented as a
best-effort supplement, documented as optional since it depends on a
personal machine being powered on and connected to WPI VPN, which is less
reliable than a dedicated always-on host would be.
