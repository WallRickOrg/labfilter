#!/bin/sh
set -eu

# Resolve paths relative to this script so Pi-hole can be managed from any
# working directory without exposing the local environment to Git.
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
pihole_dir="$repo_dir/pihole"
env_file="$pihole_dir/.env"

[ -f "$env_file" ] || {
    printf '%s\n' "Missing $env_file; copy pihole/.env.example and fill it locally." >&2
    exit 1
}

# Export Compose settings and require the password to be base64 encoded in the
# ignored .env, then decode it only into this process environment. Compose's
# environment-backed secret sends it through the Docker API for remote daemons.
set -a
# shellcheck disable=SC1091
. "$env_file"
set +a
: "${PIHOLE_WEBPASSWORD_BASE64:?PIHOLE_WEBPASSWORD_BASE64 is required in pihole/.env}"

if ! decoded_password=$(printf '%s' "$PIHOLE_WEBPASSWORD_BASE64" | base64 --decode); then
    printf '%s\n' 'PIHOLE_WEBPASSWORD_BASE64 is not valid base64.' >&2
    exit 1
fi
[ -n "$decoded_password" ] || {
    printf '%s\n' 'The decoded Pi-hole web password is empty.' >&2
    exit 1
}
export PIHOLE_WEBPASSWORD="$decoded_password"
unset PIHOLE_WEBPASSWORD_BASE64

cd "$pihole_dir"
exec docker compose --env-file "$env_file" -f compose.yaml "$@"
