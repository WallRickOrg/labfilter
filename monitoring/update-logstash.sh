#!/usr/bin/env bash
set -Eeuo pipefail

# Resolve the Compose project from this script so deployment works from any
# client working directory without exposing the monitoring `.env` contents.
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
compose_file="$script_dir/docker-compose.yml"
env_file="$script_dir/.env"

if [[ ! -f "$env_file" ]]; then
  printf 'Missing %s; copy .env.example and set local bind values.\n' "$env_file" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  printf 'Docker is required to deploy the external monitoring stack.\n' >&2
  exit 1
fi

compose=(docker compose --env-file "$env_file" -f "$compose_file")

# Validate interpolation before stopping the running service.
"${compose[@]}" config --quiet

# Build the image containing the DNS filter before replacing the container.
"${compose[@]}" build logstash
"${compose[@]}" stop logstash
"${compose[@]}" create logstash

# Upload through the Docker API into the named volume; the daemon never needs
# a bind mount to this repository path.
container_id=$("${compose[@]}" ps -aq logstash | head -n 1)
if [[ -z "$container_id" ]]; then
  printf 'Unable to identify the created Logstash container.\n' >&2
  exit 1
fi
docker cp "$script_dir/logstash/pipeline/blocked.conf" \
  "$container_id:/usr/share/logstash/pipeline/blocked.conf"

# Start only Logstash; Elasticsearch and Kibana are intentionally left alone.
"${compose[@]}" up -d logstash

# Wait briefly for the replacement container before checking its contents.
for _ in {1..30}; do
  state=$(docker inspect --format '{{.State.Status}}' "$container_id" 2>/dev/null || true)
  [[ "$state" == "running" ]] && break
  sleep 2
done

state=$(docker inspect --format '{{.State.Status}}' "$container_id" 2>/dev/null || true)
if [[ "$state" != "running" ]]; then
  printf 'Logstash did not reach running state (state: %s).\n' "${state:-unknown}" >&2
  "${compose[@]}" logs --tail=80 logstash >&2 || true
  exit 1
fi

# Confirm both the uploaded pipeline and the required DNS plugin are present.
docker exec "$container_id" test -s /usr/share/logstash/pipeline/blocked.conf
docker exec "$container_id" sh -c \
  'bin/logstash-plugin list --verbose | grep -q "^logstash-filter-dns "'

"${compose[@]}" ps logstash
printf 'Logstash pipeline uploaded and container restarted successfully.\n'
