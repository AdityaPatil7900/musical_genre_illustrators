# Deployment of Products on the VM (Case Study 2, Deliverable 2)

## Architecture

Both Case Study 1 products come from a single codebase
(`musical_genre_illustrator`), split at deploy time into two independently
running, independently recoverable systemd services via an `APP_MODE`
environment variable:

| Product | Service | Port | Image generation |
|---|---|---|---|
| **API-based product** (2a) | `genre-api.service` | 8012 (external: `http://paffenroth-23.dyn.wpi.edu:8012`) | Remote HF Inference API: `Llama-3.1-8B-Instruct` writes the prompt, `Qwen/Qwen-Image` renders it |
| **Locally-executed product** (2b) | `genre-local.service` | 8013 | Fully local `segmind/tiny-sd` diffusion model, no network calls, no HF token required |

Genre classification (`dima806/music_genres_classification`) always runs
locally in both modes, matching the original Case Study 1 design.

## Modifications made for the VM environment

The original `app.py` targets Hugging Face Spaces specifically:
- It imports `spaces` and uses `@spaces.GPU` decorators, which only work
  inside HF's ZeroGPU runtime and aren't installable/usable on a plain VM.
- It authenticates via HF OAuth login button (`gr.LoginButton()`), which
  requires an HF Spaces OAuth app registration the VM doesn't have.
- It has no VM-appropriate host/port binding and no notion of "run only the
  local path" or "run only the remote path" as separate processes.

`vm_app.py` (new file, `app.py` is left untouched for the original HF Spaces
submission) addresses all of this:
- Reads `HF_TOKEN` directly from the environment instead of OAuth login.
- `APP_MODE=api|local` env var fixes which image-generation path a given
  process serves, instead of a UI checkbox.
- Binds `0.0.0.0:$PORT` so systemd-managed processes are reachable
  externally.
- Checks a degraded-mode flag file at request time (see Extra Credit #6)
  and skips image generation under high resource load.

## Deployment steps

Run `deploy/deploy.sh` from a machine on the WPI network/VPN (see
`docs/RUNBOOK.md` for the exact commands). It performs SSH key rotation,
remote environment bootstrap (git, python3-venv), clones the repo, creates
a venv, installs `requirements-vm.txt`, and installs+starts all five
systemd units (2 products + watchdog timer + monitor timer).

## Challenges encountered

- **`spaces`/ZeroGPU dependency**: not portable off HF Spaces at all;
  resolved by writing `vm_app.py` as a VM-specific entrypoint rather than
  trying to make `app.py` conditionally support both environments in one
  file.
- **No GPU on the VM** (assumed, until confirmed via `nvidia-smi` on
  first login — see `docs/RUNBOOK.md`): `tiny-sd` on CPU is slow
  (~30-60s/image) but functional; documented as a known limitation rather
  than blocking the deployment.
- **HF OAuth not usable off Spaces**: switched the API-mode product to a
  server-side `HF_TOKEN` env var instead of per-user OAuth login, which is
  actually a better fit for a fixed-deployment VM anyway (no per-visitor HF
  account needed).
