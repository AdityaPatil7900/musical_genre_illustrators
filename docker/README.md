# Case Study 3 — Docker + Monitoring + Public Exposure

This covers deploying both products as Docker containers, scraping them with
Prometheus, visualizing in Grafana, and exposing everything publicly with
ngrok, on the shared class Docker VM.

## 1. Claim your ports

The Docker VM is shared across every group. Before deploying, claim an
unused block of ports on the **class Google Sheet** (rubric item 1c) —
container app ports, metrics ports, node-exporter ports, Prometheus, and
Grafana. Once claimed, copy the env template and fill in the real numbers:

```bash
cp docker/.env.example docker/.env
# edit docker/.env: HF_TOKEN + the 8 port variables
```

`docker/.env` is gitignored — it never gets committed, since it holds your
HF token.

## 2. Build and run the stack

From the repo root, on the VM (or locally if you have Docker and just want
to sanity-check the build first):

```bash
docker compose --env-file docker/.env up -d --build
docker compose ps
```

This builds one image (`Dockerfile` at the repo root) and starts it twice —
`genre-api` (`APP_MODE=api`, needs `HF_TOKEN`) and `genre-local`
(`APP_MODE=local`, no token needed) — plus `genre-prometheus` and
`genre-grafana`. `deploy/deploy_docker.sh` automates doing this over SSH on
the shared VM (fill in `VM_PORT` at the top first — see the script's
comments).

Each product container runs **two processes** (matching the pattern shown
in class): `prometheus-node-exporter` on `:9100` for host/container metrics,
and the Gradio app itself, which also starts a `prometheus_client` HTTP
server on `:8000` for the 9 custom application metrics added to `vm_app.py`
(request counts, success/failure, per-genre classification counts,
classifier confidence, image-generation duration, degraded-mode state, and
which code path produced the artwork — local/remote/static-fallback).

Verify metrics locally before moving on:

```bash
curl localhost:${API_METRICS_PORT}/metrics     # app metrics, API product
curl localhost:${API_NODE_EXPORTER_PORT}/metrics  # node-exporter, API product
```

(swap in the `LOCAL_*` ports for the local product.)

## 3. Prometheus

`docker/prometheus/prometheus.yml` scrapes all four targets
(`genre-api:8000`, `genre-api:9100`, `genre-local:8000`, `genre-local:9100`)
over the `genre_net` Docker network using Compose service names — no host
ports involved for this part. Open `http://<vm-host>:${PROMETHEUS_PORT}`
(default 9090) → **Status → Targets** to confirm all four are `UP`.

## 4. Grafana

`docker/grafana/` builds `grafana/grafana` with the Prometheus datasource
pre-provisioned (`provisioning/datasources/datasource.yml` → points at
`http://prometheus:9090`), so it's ready to use immediately — no manual
"Add data source" step. Log in at `http://<vm-host>:${GRAFANA_PORT}`
(default admin/admin, you'll be asked to change it), confirm the
**Prometheus** datasource is there, and build a dashboard against the
`app_*` and node-exporter metrics above. Screenshot it for the report
(rubric item 4a).

## 5. Expose everything with ngrok

Install ngrok on the VM if it isn't already there, then:

```bash
cp docker/ngrok/ngrok.yml.example docker/ngrok/ngrok.yml
# edit docker/ngrok/ngrok.yml: your authtoken + the ports you actually claimed
ngrok start --all --config docker/ngrok/ngrok.yml
```

This opens three public URLs in one agent session: the API product, the
local product, and Grafana. Record all of them — you need the product URLs
for the class Google Sheet (rubric item 3b) and all three (plus the
Grafana screenshots) for the report. `docker/ngrok/ngrok.yml` is gitignored
since it holds your authtoken.

## 6. Tear down

```bash
docker compose --env-file docker/.env down
```
