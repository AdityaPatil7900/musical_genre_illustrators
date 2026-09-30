# Resilience Testing (Case Study 2, Deliverable 3c)

> Tests 1, 2, and 4 were run live against the VM on 2026-09-30 over an SSH
> session with WPI-network/VPN access; results are real observed output, not
> placeholders. Test 3 (full VM wipe) was not attempted — see its section
> below for why.

## Test 1: Kill the process directly (systemd `Restart=always` should catch this in ~5s)

```bash
ssh -i tmp/mykey -p 22012 student-admin@paffenroth-23.dyn.wpi.edu \
  "sudo systemctl status genre-api.service | cat; sudo pkill -9 -f 'vm_app.py'; sleep 8; sudo systemctl status genre-api.service | cat"
```
**Expected:** service shows `Restart=` triggered, back to `active (running)` within ~5-10s, new PID.
**Actual result (2026-09-30):** Used `sudo systemctl kill -s SIGKILL
genre-api.service` (equivalent to `pkill -9 -f vm_app.py` for that unit)
instead of a raw `pkill`, to target only the intended process. Killed at
05:31:51 UTC. `MainPID` changed 7673 → 11666 within the same second
(`systemctl show -p MainPID`), and `ActiveState=active`/
`SubState=running` immediately — confirming `Restart=always`/`RestartSec=5`
fired as designed. However, `curl` against port 8012 kept returning `000`
(connection refused/empty reply) until 05:33:57 UTC — the process was
"running" per systemd within ~5s, but the genre classifier model took ~2
minutes to reload under this VM's memory pressure (2.6-3.1GB/4GB used,
hundreds of MB swapped) before it actually served HTTP 200 again.
Process-level recovery worked exactly as designed; full request-serving
recovery took materially longer than 5-10s on this hardware.

## Test 2: Stop the service (simulating a hang; watchdog should catch this within 2 min)

```bash
ssh -i tmp/mykey -p 22012 student-admin@paffenroth-23.dyn.wpi.edu \
  "sudo systemctl stop genre-local.service; date"
# wait ~2-3 minutes for the watchdog timer to fire, then:
ssh -i tmp/mykey -p 22012 student-admin@paffenroth-23.dyn.wpi.edu \
  "sudo systemctl status genre-local.service | cat; tail -20 musical_genre_illustrators/.watchdog/watchdog.log"
```
**Expected:** `watchdog.log` shows a detected-down entry and a restart within one 2-minute cycle; Discord channel receives the "unresponsive -> restarted" message; service is `active` again.
**Actual result (2026-09-30):** Before this test could run cleanly, two
pre-existing bugs had to be fixed (see `Docs/REPORT.md` Section 2 for full
diagnosis): (1) `deploy/watchdog.sh` and the fallback default in
`deploy/monitor.py` still hardcoded the old singular repo-name path
(`musical_genre_illustrator` instead of `musical_genre_illustrators`) for
`STATE_DIR`/`ENV_FILE`, so `watchdog.sh` never actually loaded
`DISCORD_WEBHOOK_URL` — its `[ -f "$ENV_FILE" ]` guard just quietly skipped
a file that didn't exist at that path; (2) the working-tree copy of
`watchdog.sh` on this Windows dev machine (`git config core.autocrlf=true`)
had CRLF line endings, and the VM's live `deploy/.env` also had CRLF, which
broke `watchdog.sh` with a bash syntax error on every single 2-minute cycle
(confirmed via `journalctl -u genre-watchdog.service` showing the same
`syntax error near unexpected token '{\r'` on 7 consecutive cycles from
05:22 to 05:36 UTC) and corrupted `HF_TOKEN`/`DISCORD_WEBHOOK_URL` with a
trailing `\r`. Fixed both (corrected the hardcoded paths; stripped `\r`
from both files with `sed 's/\r$//'`), redeployed, restarted both product
services to pick up the corrected `.env`, then re-ran this test:

Stopped `genre-local.service` at 05:39:21 UTC. `watchdog.log`:
```
2026-09-30T05:39:54+00:00 Local product UNRESPONSIVE (port 8013). Restarting genre-local.service...
2026-09-30T05:40:02+00:00 Local product STILL DOWN after restart attempt.
2026-09-30T05:41:54+00:00 Local product recovered (port 8013).
```
Detection happened on the very next timer cycle (33s after the stop).
The "STILL DOWN" line is a false negative — the watchdog's own 8-second
post-restart check fired before the (cold, memory-constrained) model
finished loading, so it sent a "manual intervention needed" Discord alert
even though the restart had actually succeeded; the following cycle's real
health check at 05:41:54 (2m33s after the stop) correctly logged the
recovery and sent the "recovered" alert. Independently confirmed the
Discord webhook itself is reachable and accepting messages: a direct test
POST to the (redacted) webhook URL from the VM, run right after this test,
returned HTTP 204. (No screenshot of the Discord channel was captured in
this session — the SSH/CLI environment used for testing has no Discord
access; visual confirmation of the actual messages landing needs to come
from checking the Discord channel directly.)

## Test 3: Full VM wipe / redeploy from scratch

If Prof. Paffenroth wipes the VM (per the assignment's note that this can
happen), the on-VM watchdog has nothing to run. Recovery is:
```bash
cd musical_genre_illustrator-main/deploy
./deploy.sh
```
**Expected:** full redeploy completes in one run (key rotation will no-op
since the VM's default key is fresh again; bootstrap/clone/install/systemd
steps all re-run cleanly), both services reachable again afterward.
**Actual result:** Not attempted in this session. The VM was not wiped
(professor-triggered or otherwise), and a simulated wipe (stopping/disabling
all units + deleting the repo directory) was judged too disruptive to
perform against a live, currently-working deployment without a specific
need to validate it right now. Left as an untested scenario — `deploy.sh`
itself was not modified in a way that would newly risk this path.

## Test 4: Resource-threshold degraded mode (extra credit #6)

```bash
ssh -i tmp/mykey -p 22012 student-admin@paffenroth-23.dyn.wpi.edu \
  "stress-ng --cpu 4 --timeout 90s &  # or: yes > /dev/null & yes > /dev/null &
   sleep 70; cat musical_genre_illustrators/.watchdog/monitor.log | tail -5"
```
(Install `stress-ng` first if not present: `sudo apt-get install -y stress-ng`,
or just run a couple of `yes > /dev/null &` background loops to peg CPU —
kill them afterward with `pkill yes`.)

**Expected:** `monitor.log` shows CPU% above the 80% threshold, Discord
receives the "resource threshold exceeded / degraded mode" message, and a
subsequent request to either product's UI returns the "operating near
capacity" message instead of generating an image. After killing the stress
load, the next 1-minute monitor cycle should clear degraded mode and send
the "back to normal" Discord message.
**Actual result (2026-09-30):** `stress-ng` was not installed on the VM;
rather than installing another package for a one-off test, temporarily
lowered `CPU_THRESHOLD_PCT` from 80 to 5 in `deploy/.env` at 05:43:12 UTC
(idle CPU on this VM runs ~8-15%, so this reliably breaches the threshold
without any artificial load). `monitor.log`:
```
2026-09-30T05:44:17.902061+00:00 reading: {"cpu_pct": 9.9, "mem_pct": 68.4, ...}
2026-09-30T05:44:17.919342+00:00 ENTERING degraded mode.
...
2026-09-30T05:45:22.111174+00:00 reading: {"cpu_pct": 8.3, "mem_pct": 72.2, ...}
2026-09-30T05:45:22.191530+00:00 EXITING degraded mode.
```
Confirmed the adaptive response actually changes app behavior, not just
that the flag file exists: sent a real audio file to `genre-local`'s
`/analyze_music` endpoint while `degraded_mode.flag` was present and got
back a normal genre/confidence but with `"⚠️ System is currently operating
near capacity — image generation is temporarily disabled. Genre
classification is still available."` and a `None` image path. Reverted
`CPU_THRESHOLD_PCT` to 80 at 05:45:04 UTC; the next monitor cycle (18s
later) cleared the flag as shown above. Independently confirmed the
Discord webhook accepts POSTs (HTTP 204) during this same window. (As with
Test 2, no Discord-channel screenshot was captured from this CLI-only
session — check the channel directly for the two messages.)

## Challenges encountered

- Cold-start model load time (~2 minutes under this VM's memory pressure)
  is close to the watchdog's own 2-minute cycle and well beyond its 8-second
  post-restart re-check, producing a false "manual intervention needed"
  alert in Test 2 for a restart that had actually succeeded.
- `watchdog.sh` had a repo-name path typo (`musical_genre_illustrator`
  instead of `musical_genre_illustrators`) that silently prevented it from
  ever loading `DISCORD_WEBHOOK_URL`, undetected until this testing pass
  because the restart mechanism itself still worked — only the alerting was
  broken.
- CRLF line endings introduced from this Windows development machine
  (`core.autocrlf=true`) broke `watchdog.sh` outright (bash syntax error,
  loud failure in `journalctl`) and silently corrupted `deploy/.env` on the
  VM (trailing `\r` in `HF_TOKEN`/`DISCORD_WEBHOOK_URL`, no error, just
  wrong behavior — visible only as an "unauthenticated requests" warning in
  unrelated HF Hub logs).
- No sudoers permission issues were encountered — `student-admin` has
  blanket `(ALL) NOPASSWD: ALL` sudo from the course-provisioned VM image
  itself (`/etc/sudoers.d/90-cloud-init-users`), so the watchdog's
  `systemctl restart` calls always had permission. (The scoped-sudoers
  hardening recommended by the LLM security review was never actually
  applied — see `Docs/REPORT.md` Section 5.)
