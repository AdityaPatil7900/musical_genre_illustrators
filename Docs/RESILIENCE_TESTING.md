# Resilience Testing (Case Study 2, Deliverable 3c)

> **Fill in the actual results after running these on your machine** — the
> commands are exact and ready to run, but the outcomes/timestamps/logs below
> are placeholders (`TODO`) since this assistant cannot reach the
> WPI-internal VM to execute them directly. Replace each `TODO` with what you
> actually observed, then copy the finished sections into `docs/REPORT.md`.

## Test 1: Kill the process directly (systemd `Restart=always` should catch this in ~5s)

```bash
ssh -i tmp/mykey -p 22012 student-admin@paffenroth-23.dyn.wpi.edu \
  "sudo systemctl status genre-api.service | cat; sudo pkill -9 -f 'vm_app.py'; sleep 8; sudo systemctl status genre-api.service | cat"
```
**Expected:** service shows `Restart=` triggered, back to `active (running)` within ~5-10s, new PID.
**Actual result:** TODO — paste `systemctl status` before/after, and the PID change.

## Test 2: Stop the service (simulating a hang; watchdog should catch this within 2 min)

```bash
ssh -i tmp/mykey -p 22012 student-admin@paffenroth-23.dyn.wpi.edu \
  "sudo systemctl stop genre-local.service; date"
# wait ~2-3 minutes for the watchdog timer to fire, then:
ssh -i tmp/mykey -p 22012 student-admin@paffenroth-23.dyn.wpi.edu \
  "sudo systemctl status genre-local.service | cat; tail -20 musical_genre_illustrator/.watchdog/watchdog.log"
```
**Expected:** `watchdog.log` shows a detected-down entry and a restart within one 2-minute cycle; Discord channel receives the "unresponsive -> restarted" message; service is `active` again.
**Actual result:** TODO — paste the watchdog.log excerpt and a screenshot of the Discord message.

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
**Actual result:** TODO — document the timestamp of the wipe (if
professor-triggered) or of a manual `sudo rm -rf /*`-avoidant simulated
wipe (e.g., stopping and disabling all five units + deleting the repo
directory, then redeploying), total time-to-recovery, and any manual steps
that were needed beyond running `deploy.sh`.

## Test 4: Resource-threshold degraded mode (extra credit #6)

```bash
ssh -i tmp/mykey -p 22012 student-admin@paffenroth-23.dyn.wpi.edu \
  "stress-ng --cpu 4 --timeout 90s &  # or: yes > /dev/null & yes > /dev/null &
   sleep 70; cat musical_genre_illustrator/.watchdog/monitor.log | tail -5"
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
**Actual result:** TODO — paste monitor.log excerpts for entering and
exiting degraded mode, and a screenshot of both Discord messages.

## Challenges encountered

TODO — fill in after running the above (e.g., timing quirks, sudoers
permission issues, cold-start model load time affecting the first health
check after a restart, etc.)
