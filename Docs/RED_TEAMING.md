# Red-Teaming (Case Study 2, Extra Credit #5)

**Window:** authorized red-team window, Sept 29 – Oct 1 2026 (per assignment).
**Method:** `red_team_check.sh` (adapted from the course-provided
`DSCS553_example/red_team_v1.sh`) — loops over ports `22001`–`22021`
(22000 + group number, skipping our own group 12), attempting
`ssh -i student-admin_key` (the shared default key distributed to every
group) and running only `echo VULNERABLE on group $i; hostname; date` if it
connects. Per the assignment's read-only rule for this exercise, no group's
VM was touched, modified, or inspected beyond that single hostname/date
check.

## What was found

The script was run at least twice during the window (confirmed via shell
history). Screenshots of the terminal output at the time of each run are
the evidence for the findings below; no other file/log capture was made
during the runs themselves.

| Group | Port | Result | Timestamp (UTC) | Evidence |
|---|---|---|---|---|
| 13 | 22013 | **VULNERABLE** — default key still accepted, hostname `group13` | 2026-09-29 16:09:08 | `Screenshot 2026-09-29 121513.png` |
| 14 | 22014 | **VULNERABLE** — default key still accepted, hostname `group14` | 2026-09-29 16:09:09 | `Screenshot 2026-09-29 121504.png` |
| 20 | 22020 | **VULNERABLE** — default key still accepted, hostname `group20` | 2026-09-29 15:22:15 (first run), 2026-09-29 16:09:20 (second run) | `Screenshot 2026-09-29 112919.png`, `Screenshot 2026-09-29 120948.png` |

All three timestamps fall inside the authorized window (Sept 29 – Oct 1
2026), and group 20 was independently confirmed vulnerable across two
separate runs roughly 47 minutes apart.

**Groups 3, 6, and 17** were reportedly part of the original probe scope
but no saved evidence (screenshot, log, or other artifact) for them could
be located. They are **not** claimed as findings here — only what has
direct, timestamped evidence is reported.

## Notifications

- **Group 13:** notified via Canvas Inbox (course: Machine Learning
  Development and Operations), sent 2026-09-29 12:24pm to Andrew Bugbee,
  subject "Heads up — SSH key rotation (Case Study 2)." Message disclosed
  exactly what was done (hostname + date only, no other access), why
  (red-teaming exercise, authorized window), and recommended rotating the
  key before the window closes. The finding screenshot was attached as
  proof.
- **Group 14:** no notification sent or drafted — not found in any saved
  evidence.
- **Group 20:** no notification sent. This is a known gap in this
  submission — the finding above documents the vulnerability and its
  timestamp, but no heads-up was sent to that group before the window
  closed.

## Scope discipline

Consistent with the assignment's rules for this exercise and with how
group 13 was notified: each successful connection ran only `hostname` and
`date` to confirm access — no files were read, written, or modified on any
other group's VM, and no service was restarted or otherwise disturbed.
