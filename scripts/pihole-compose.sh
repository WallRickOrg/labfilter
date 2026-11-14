#!/bin/sh
set -eu

# Resolve paths relative to this script so Pi-hole can be managed from any
# working directory without exposing the local environment to Git.
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
pihole_dir="$repo_dir/pihole"
env_file="$pihole_dir/.env"
secret_dir="$pihole_dir/secrets"
secret_file="$secret_dir/pihole_web_password"

[ -f "$env_file" ] || {
    printf '%s\n' "Missing $env_file; copy pihole/.env.example and fill it locally." >&2
    exit 1
}

# Export Compose settings and require the password to be base64 encoded in the
# ignored .env, then decode it only into the ignored Docker secret path.
set -a
# shellcheck disable=SC1091
. "$env_file"
set +a
: "${PIHOLE_WEBPASSWORD_BASE64:?PIHOLE_WEBPASSWORD_BASE64 is required in pihole/.env}"

mkdir -p "$secret_dir"
umask 077
temporary_secret=$(mktemp "$secret_dir/.pihole_web_password.XXXXXX")
cleanup() {
    rm -f "$temporary_secret"
}
trap cleanup EXIT HUP INT TERM

if ! printf '%s' "$PIHOLE_WEBPASSWORD_BASE64" | base64 --decode > "$temporary_secret"; then
    printf '%s\n' 'PIHOLE_WEBPASSWORD_BASE64 is not valid base64.' >&2
    exit 1
fi
[ -s "$temporary_secret" ] || {
    printf '%s\n' 'The decoded Pi-hole web password is empty.' >&2
    exit 1
}
mv "$temporary_secret" "$secret_file"

cd "$pihole_dir"
exec docker compose --env-file "$env_file" -f compose.yaml "$@"
