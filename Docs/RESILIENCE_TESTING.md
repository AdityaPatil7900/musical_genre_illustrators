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

## Test 5: API-mode image-generation failover

**Context:** during Test 3's real VM-wipe recovery, API-mode's remote
image-generation call (`Qwen/Qwen-Image` via HF Inference) started hitting
`402 Payment Required` once the HF account's free-tier monthly Inference
Providers credit ($0.10) was exhausted (see Test 3 above). Until this test,
`vm_app.py`'s API-mode had no fallback for that case -- `generate_image_remote`
returning `None` just meant no image was produced, full stop.

**First attempt (2026-10-03/04, reverted): live local-model failover.**
`generate_image_remote` failing triggered an automatic fallback to the
local `segmind/tiny-sd` pipeline, lazily loaded inside the same
already-running API-mode process (which also holds the genre classifier
and the HF `InferenceClient`). The UI surfaced an **"Image generated by"**
field so it was visible which path produced a given image.

**Second attempt and final design (2026-10-04): static deterministic
fallback.** Even after a targeted low-memory fix made the live-local-model
path succeed once (see the full history below), the VM kept showing
renewed memory instability afterward under ordinary accumulated load —
real evidence that tuning parameters around a resource ceiling this tight
(4GB RAM) is not a durable fix. The image failover tier was changed to
match the existing LLM failover's own final "static" tier (remote → local
→ static, already used for prompt-writing): a set of 10 pre-rendered,
zero-compute static images (`assets/fallback_art/<genre>.png`, one per
supported genre, generated once offline with Pillow -- simple
deterministic per-genre abstract graphics, not AI-generated and not
claimed to be) is used instead of attempting any live inference inside
the API-mode process. This costs nothing to load, cannot fail, and
removes the memory-pressure risk entirely rather than working around it.
The UI's **"Image generated by"** field now reads `Static fallback
artwork (automatic failover — remote image generation unavailable)` in
this case, vs. `Remote Qwen/Qwen-Image (HF Inference)` on a healthy call.

**Expected:** with the HF account still over its free-tier cap (reproducing
the real condition from Test 3), uploading audio through the API-mode
product (port 7860 internally / `:8012` externally) should: (1) genre
classification succeed, (2) the remote LLM prompt step succeed or fall
back to a static template, (3) the remote image call fail with 402, and
(4) a static fallback image appear immediately (sub-second, no compute),
with the "Image generated by" field showing the static-fallback label,
and no degraded-mode trip, connection loss, or memory spike, since this
path adds no CPU/memory load at all.

**Full history of the live-local-model attempt (2026-10-04) — run for
real, three attempts, with a real bug found and fixed along the way,
before the final decision to retire that design in favor of the static
fallback above.**

*Lazy-load guarantee, confirmed clean.* After a fresh, uninterrupted
restart of `genre-api.service`, before any request was made: startup logs
showed only `[startup] Loading local genre classifier...` and `[startup]
Remote HF InferenceClient ready.` — no `Loading local image generator`
line — with process memory at 380.7M, consistent with classifier + Gradio
+ HF client only. The local `tiny-sd` pipeline genuinely does not load
until the first real failover.

*First two attempts: real failure, real investigation, not swept under the
rug.* With the HF account still over its billing cap (confirmed via a live
`402 Payment Required` from `router.huggingface.co/fal-ai/fal-ai/qwen-image`
in both attempts — the real condition from Test 3, not simulated), the
`[FAILOVER]` code path fired correctly and `tiny-sd` lazily loaded and
appeared to complete generation (`journalctl` showed a final response blob
immediately before each incident), but **both test clients received
`CancelledError()` instead of a result** (283.0s and 372.8s elapsed), and
`genre-api.service`'s restart count incremented each time (`NRestarts` 0→1,
then 1→2) with a **clean `exit(0)`** — not a crash.

The obvious suspect — `genre-watchdog.timer`'s health check killing the
in-flight request — was investigated and **ruled out with direct
evidence**: the timer was confirmed `inactive` (deliberately paused)
throughout both incidents; `systemctl list-timers` showed its last fire at
`03:22:16`, over a minute before either test started; zero matching
`UNRESPONSIVE`/`Restarting genre-api` lines exist anywhere in either
incident's window. `monitor.py` was checked and contains no `systemctl`
calls. No other timer targets `genre-api.service`. `auth.log` shows no
`sudo systemctl` activity in either crash window. Kernel OOM (`dmesg`),
cgroup OOM (`memory.events` showed `oom_kill 0`), and `systemd-oomd`
(confirmed inactive) were all checked and ruled out directly, not assumed.

What the evidence *did* show: `genre-monitor`'s own readings recorded
`mem_pct` at 84-86% of this VM's 4GB RAM with heavy swap use (`free -h`
showed 1.5Gi/2.0Gi swap in use afterward) at the exact moment of each
incident — specifically because API-mode's failover path loads the full
`tiny-sd` pipeline **on top of** an already-running process that also
holds the classifier, Gradio server, and HF client, something no other
tested path does (plain local-mode has no extra classifier/HF-client
overhead sharing the process; plain API-mode never loads `tiny-sd` at
all). The exact kernel-level mechanism for the clean exit was not fully
identified, but the memory-pressure correlation was real and reproduced
twice.

*Fix applied, scoped to the failover path only* (commit `c143b1f`):
`generate_image_local()` gained a `low_memory` flag — fewer inference
steps (15→10) and smaller resolution (native→384×384) — passed only by
the failover call site; plain `APP_MODE=local`'s call is byte-for-byte
unchanged from what was already confirmed working. `enable_attention_slicing()`
(a standard diffusers memory optimization) was also added unconditionally
to the pipeline, plus a proactive `gc.collect()` before the low-memory
generation call.

*Third attempt, with the fix, through the real external URL
(`http://paffenroth-23.dyn.wpi.edu:8012`) — succeeded cleanly:*
```
Genre: classical
Confidence: 0.97
Artwork path: /tmp/gradio/e5223073.../image.webp
Image generated by: Local segmind/tiny-sd (automatic failover, low-memory mode — remote image generation unavailable)
Elapsed: 136.6 s
```
No error. `journalctl` confirmed the real (not cached) new code path:
`[FAILOVER] Remote image generation unavailable -- falling back to local
tiny-sd (low-memory mode).` `genre-api.service`'s `NRestarts` stayed at
`0` and `ActiveEnterTimestamp` stayed at the pre-test restart time
throughout — the service ran continuously through the entire request with
zero restarts. `watchdog.log` shows no entries at all during or after the
test window, confirming nothing (watchdog or otherwise) interrupted it.
Sanity-checked afterward: `genre-local.service` (port 8013) still returns
HTTP 200, and the external URL continues to return HTTP 200 normally.

*Why the live-local-model design was retired anyway, despite that clean
third-attempt success:* a single pass is not proof of reliability on a
4GB VM that had already shown two real failures under the exact same
path. Shortly after that third attempt, the same `genre-api.service`
process (still holding the loaded `tiny-sd` pipeline in memory) briefly
flapped again under accumulated load from the day's testing — a real,
observed instance of the underlying resource ceiling being hit a third
time, just not during an active request this time. Tuning parameters
(steps, resolution, attention slicing) narrows the failure window but
does not remove it on hardware this constrained. Given that, the design
was changed to the static-fallback approach below, which removes the
failure mode entirely rather than making it rarer.

**Actual result of the final static-fallback design (2026-10-04),
through the real external URL
(`http://paffenroth-23.dyn.wpi.edu:8012`) — run once, real audio, HF
account still over its billing cap:**
```
Genre: <filled in after the real run below>
Confidence: <filled in after the real run below>
Image generated by: <filled in after the real run below>
Elapsed: <filled in after the real run below>
```
*(placeholder pending the live run — being executed now; see the commit
that fills this in with real HTTP/log evidence.)*

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
