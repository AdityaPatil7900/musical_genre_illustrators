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

**Actual result (2026-10-01) — this really happened, not staged.** Mid-way
through an unrelated testing session, the VM stopped responding on both SSH
and the app ports. Diagnosis: the SSH host key fingerprint had changed
(`SHA256:5eiszgZkJi4naOH24mOGstu/v3iST1X3tAPuJkasg44`, different from the
previously-trusted key), and the default `student-admin_key` worked again
while our rotated personal key was rejected — conclusive evidence the VM
had been wiped back to its initial image (empty home directory, zero
`genre-*` systemd units, fresh Ubuntu 22.04, confirmed via `ls -la ~` and
`systemctl list-units 'genre-*'`).

Recovery, in order:
1. Accepted the new host key (`ssh-keygen -R` to clear the stale entry,
   then `-o StrictHostKeyChecking=accept-new` on reconnect) and confirmed
   the default key worked again.
2. Ran `deploy/deploy.sh`. **Step 1 (key rotation) succeeded cleanly** —
   personal key added, verified, default key removed. **Step 2 (system
   dependency bootstrap) revealed a real bug**: its check
   `python3 -m venv --help >/dev/null 2>&1` exits 0 even when `ensurepip`
   isn't actually installed (`--help` only prints usage text; it never
   tries to create a venv), so it never ran `apt-get install
   python3-venv`. **Step 3 (clone)** succeeded. **Step 4 (venv + pip
   install) failed for real**: `python3 -m venv .venv` errored with
   `ensurepip is not available ... apt install python3.10-venv`, exactly
   the bug in step 2's detection logic. The script's `set -euo pipefail`
   aborted the deploy here, before step 5.
3. Fixed by hand on the live VM: `sudo apt-get install -y python3.10-venv
   ffmpeg` (ffmpeg being the other known gap from a prior session, this
   time installed proactively rather than discovered via a failed
   request), recreated the venv, re-ran `pip install -r
   requirements-vm.txt`, manually copied real secrets into `deploy/.env`
   (stripping CRLF — the Windows-dev-machine line-ending issue recurred in
   the freshly-copied `.env.example` and in all 6 systemd unit files
   copied via `scp`, confirmed via `grep -c $'\r'` showing 7-20 instances
   per file; stripped with `sed -i 's/\r$//'`), then manually completed
   step 5 (systemd install + enable + start).
4. **Found and fixed a new, VM-wipe-specific bug**: `genre-watchdog.timer`
   has `OnBootSec=1min`, so on a system that just booted *and* just had its
   services started, the watchdog's first cycle landed squarely during the
   very first cold-start model load (no HF cache exists yet on a wiped VM,
   so this load is much slower than a warm restart — includes downloading
   ~500MB+ of model weights). The watchdog correctly detected "unresponsive"
   and restarted the services — repeatedly, every 2 minutes, forever
   interrupting the download before it could finish. Confirmed via
   `watchdog.log` showing `UNRESPONSIVE`/`STILL DOWN` pairs at 20:14,
   20:16, 21:12, and 21:14. Fixed by temporarily `sudo systemctl stop
   genre-watchdog.timer`, letting both services complete their first load
   uninterrupted (`genre-api` up at 20:20, `genre-local` up at 20:28 on the
   first attempt), then re-enabling the timer — confirmed via `watchdog.log`
   logging clean `recovered` entries afterward with no further restarts.
5. **Found and fixed a real logging bug while diagnosing the above**:
   neither systemd unit set `PYTHONUNBUFFERED=1`, so `vm_app.py`'s
   `print()` output (including error messages) sat in Python's stdout
   buffer and never reached `journalctl` until the buffer filled or the
   process exited — made live diagnosis of in-progress failures
   impossible. Added `Environment=PYTHONUNBUFFERED=1` to both
   `genre-api.service` and `genre-local.service`.
6. **End-to-end verification, real audio through the real app**: local-mode
   succeeded twice (genre `classical`, confidence `0.97`, real generated
   artwork, 169–219s). API-mode's genre classification and LLM
   prompt-writing succeeded consistently, but the final remote image
   step returned `None` — root-caused via the now-unbuffered logs to
   `402 Payment Required` from Hugging Face's Inference Providers
   (`fal-ai` router): "You have depleted your monthly included credits."
   This is an external account billing limit, not a deployment defect —
   `generate_image_remote`'s existing try/except handled it exactly as
   designed (graceful `None`, no crash), which is itself a working
   resilience behavior, just not a full "success" for that one feature.

**Total time from detecting the wipe to both services fully functional:**
approximately 1 hour, including live debugging of three previously-unseen
bugs (venv-detection, watchdog-vs-cold-start-interval, unbuffered
logging) that only surfaced because this was a genuine from-scratch
rebuild rather than a warm restart. All three fixes were committed back
to `deploy/deploy.sh` and the two systemd unit files so they're handled
automatically on any future wipe.

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

## Test 5: API-mode image-generation failover to local model

**Context:** during Test 3's real VM-wipe recovery, API-mode's remote
image-generation call (`Qwen/Qwen-Image` via HF Inference) started hitting
`402 Payment Required` once the HF account's free-tier monthly Inference
Providers credit ($0.10) was exhausted (see Test 3 above). Until this test,
`vm_app.py`'s API-mode had no fallback for that case -- `generate_image_remote`
returning `None` just meant no image was produced, full stop.

**Change made:** `generate_image_remote` failing (timeout, rate-limit, auth
error, or a billing/quota error like 402) now triggers an automatic fallback
to the local `segmind/tiny-sd` pipeline inside the same API-mode process,
so a result is still produced instead of nothing. The local pipeline is
lazily loaded only on the first actual failover (not at API-mode startup),
so a healthy API-mode deployment never pays the extra load/memory cost. The
UI now also surfaces an **"Image generated by"** field so it's visible
which path actually produced a given image (`Remote Qwen/Qwen-Image (HF
Inference)` vs `Local segmind/tiny-sd (automatic failover — remote image
generation unavailable)`).

**Expected:** with the HF account still over its free-tier cap (reproducing
the real condition from Test 3), uploading audio through the API-mode
product (port 7860 internally / `:8012` externally) should: (1) genre
classification succeed as before, (2) the remote LLM prompt step succeed or
fall back to a static template as before, (3) the remote image call fail
with 402 as before, but now (4) the local tiny-sd pipeline should produce a
real image instead of `None`, with the "Image generated by" field reading
the local-failover label, and a `[FAILOVER]` line appearing in
`journalctl`/stdout for `genre-api.service`.

**Actual result:** *(not yet run on the VM as of this commit — this section
documents what was implemented and what to verify; it is intentionally
left unfilled rather than asserting success that hasn't been observed.
Whoever runs this test next should replace this paragraph with the real
HTTP/UI/log evidence, the same way every other test in this document is
documented, and should also confirm an unrelated healthy run of API mode
(before deliberately triggering a failure) shows the "Remote Qwen/Qwen-Image"
label and does NOT eagerly load the local model, to prove the lazy-load
guarantee holds.)*

## Real (unplanned) resilience event — 2026-09-30 07:00–07:11 UTC

Unlike Tests 1, 2, and 4 above, this was **not a staged test** — it happened
under genuine resource load on the VM (from unrelated ad-hoc boot-testing
work earlier the same session) and was caught after the fact by reading the
live logs. It's included here because it exercised the same recovery paths
as the synthetic tests, under real conditions, and surfaced two findings
the synthetic tests didn't: a real Discord delivery failure, and a longer
real-world recovery time.

`monitor.log`:
```
2026-09-30T07:00:23.347317+00:00 reading: {"cpu_pct": 10.2, "mem_pct": 95.8, ...}
2026-09-30T07:00:26.880899+00:00 ENTERING degraded mode.
2026-09-30T07:00:44.211262+00:00 Discord notify failed: ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))
2026-09-30T07:01:21.684731+00:00 reading: {"cpu_pct": 16.5, "mem_pct": 44.1, ...}
2026-09-30T07:01:21.729435+00:00 EXITING degraded mode.
```

`watchdog.log`:
```
2026-09-30T07:02:27+00:00 Local product UNRESPONSIVE (port 8013). Restarting genre-local.service...
2026-09-30T07:02:35+00:00 Local product STILL DOWN after restart attempt.
2026-09-30T07:04:36+00:00 Local product UNRESPONSIVE (port 8013). Restarting genre-local.service...
2026-09-30T07:04:45+00:00 Local product STILL DOWN after restart attempt.
2026-09-30T07:06:57+00:00 Local product UNRESPONSIVE (port 8013). Restarting genre-local.service...
2026-09-30T07:07:05+00:00 Local product STILL DOWN after restart attempt.
2026-09-30T07:08:46+00:00 Local product UNRESPONSIVE (port 8013). Restarting genre-local.service...
2026-09-30T07:08:54+00:00 Local product STILL DOWN after restart attempt.
2026-09-30T07:11:02+00:00 Local product recovered (port 8013).
```

**What actually happened:** real memory exhaustion (95.8% — not a lowered
threshold) correctly triggered degraded mode at 07:00:26, and correctly
cleared it 55 seconds later once memory pressure eased. That part worked
exactly as designed. But the "entering degraded mode" Discord notification
itself **failed to send** — `Connection aborted... RemoteDisconnected`,
distinct from the "webhook rejected the request" failure mode; this looks
like the HTTP connection to Discord's API being dropped mid-request, most
plausibly because the VM was under enough memory/network pressure at that
exact moment (95.8% mem) to disrupt the outbound connection itself. This is
a real-world failure mode the synthetic Test 4 (which ran under light load
and got a clean HTTP 204) never exercised.

Separately, `genre-local.service` needed **4 consecutive watchdog cycles**
(07:02, 07:04, 07:06, 07:08) before recovering at 07:11:02 — roughly **8.5
minutes**, versus the ~2m33s recovery documented in Test 2. Both events
involve the same service and the same underlying cold-start/memory-pressure
mechanism discussed in "Challenges encountered" below, but this real
episode shows the failure mode compounding for longer than the synthetic
test captured — worth noting as a real-world data point beyond what the
staged tests showed, not a contradiction of them.

**Current state:** verified healthy after this event and unrelated to it —
`genre-local.service` has been `active` with HTTP 200 on port 8013 in every
subsequent check this session.

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
