# SSH Access Setup (Case Study 2, Deliverable 1a)

**Group:** 12 — solo (Aditya Patil)
**VM:** `paffenroth-23.dyn.wpi.edu`, SSH port `22012` (= 22000 + group 12)
**External app port:** `8012` (= 8000 + group 12)

## Steps taken

1. **Received the default credentials from Prof. Paffenroth via Canvas**:
   `student-admin_key` / `student-admin_key.pub` — an ed25519 keypair
   pre-authorized on the VM for the initial `student-admin` account, plus a
   `wpi_llm_token` for the course's shared LLM endpoint.

2. **Generated a personal ed25519 keypair** for the group, kept private and
   out of any git repo:
   ```bash
   ssh-keygen -t ed25519 -f tmp/mykey -C "group12-cs553" -N ""
   ```

3. **Verified initial connectivity** using the default key (must be done
   from the WPI network or WPI VPN — the VM is not reachable from the open
   internet, confirmed by a connection timeout when attempted from outside):
   ```bash
   ssh -i student-admin_key -p 22012 student-admin@paffenroth-23.dyn.wpi.edu
   ```

4. **Rotated the authorized key** using `deploy/deploy.sh` (Step 1), which:
   - Appends `tmp/mykey.pub` to `~/.ssh/authorized_keys` on the VM while
     still logged in with the default key.
   - Confirms the new personal key can log in.
   - Only then removes the `student-admin_key.pub` line from
     `~/.ssh/authorized_keys`, so the default key no longer works and only
     our group's key remains authorized.

   This order (add-then-verify-then-remove) is important: removing the
   default key first, before confirming the replacement works, risks
   permanent lockout.

5. **Confirmed lockout of the default key** by re-attempting the connection
   with `student-admin_key` and observing `Permission denied
   (publickey)`, and confirmed the new key still works:
   ```bash
   ssh -i tmp/mykey -p 22012 student-admin@paffenroth-23.dyn.wpi.edu "echo OK"
   ```

## Required configuration

| Item | Value |
|---|---|
| Host | `paffenroth-23.dyn.wpi.edu` |
| Port | `22012` |
| User | `student-admin` |
| Auth | ed25519 public key (`tmp/mykey.pub`) only, password auth disabled by default on the VM image |
| Network | WPI campus network or WPI VPN (GlobalProtect) — required, VM is not internet-routable |

## Credentials NOT included in this repo

`tmp/mykey` (private key), `student-admin_key` (private key), and
`wpi_llm_token` are excluded via `.gitignore` and were never pushed to
GitHub. Only `.pub` files may be safely shared/committed.
