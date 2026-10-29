# ============================================================================
# Case Study 3 -- single parameterized image for BOTH products.
#
# The same image is used to run both deliverables required by the rubric:
#   - "API-based product"       -> docker run / compose with APP_MODE=api
#   - "Locally executed product" -> docker run / compose with APP_MODE=local
# docker-compose.yml builds this once and starts it as two separate
# containers (genre-api, genre-local) with different APP_MODE/PORT env vars
# and different host port mappings, so each is independently a full
# deployment of its product rather than a shared process.
#
# Follows the same pattern demoed in class
# (github.com/rcpaffenroth/DSCS553_WPI_Fall_2026, case_study_3 branch):
# install prometheus-node-exporter inside the image itself, and start it
# alongside the Python app in the container's CMD so each product container
# self-reports both host-level (:9100) and application-level (:8000) metrics
# without a separate sidecar container.
# ============================================================================
FROM python:3.10-slim

WORKDIR /opt/app

# Install Python dependencies first (better layer caching on rebuilds).
COPY requirements-vm.txt /opt/app/requirements-vm.txt
RUN pip install --no-cache-dir -r /opt/app/requirements-vm.txt

# Install prometheus-node-exporter for container/host-level metrics (:9100),
# per the Case Study 3 rubric's "Monitoring of the Docker Container" item.
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && \
    apt-get upgrade -yq ca-certificates && \
    apt-get install -yq --no-install-recommends prometheus-node-exporter && \
    rm -rf /var/lib/apt/lists/*

# Now bring in application code (changes most often -> last layer).
COPY vm_app.py /opt/app/vm_app.py
COPY assets /opt/app/assets

RUN mkdir -p /opt/app/generated_images /opt/app/.watchdog

EXPOSE 7860
# Gradio app
EXPOSE 8000
# prometheus_client application metrics
EXPOSE 9100
# prometheus-node-exporter

ENV GRADIO_SERVER_NAME="0.0.0.0"
ENV PORT=7860
ENV METRICS_PORT=8000
# APP_MODE (api|local) and HF_TOKEN (required only for APP_MODE=api) are
# supplied at `docker run`/compose time -- see docker-compose.yml.

CMD bash -c "prometheus-node-exporter --web.listen-address=':9100' & python /opt/app/vm_app.py"
