FROM grafana/grafana:latest

# Auto-provision the Prometheus datasource so Grafana comes up already
# pointed at our prometheus container -- no manual "Add data source" click
# needed before you can build dashboards and take the report screenshots.
COPY provisioning /etc/grafana/provisioning

EXPOSE 3000
