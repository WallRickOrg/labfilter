#!/bin/sh
set -eu

# Resolve paths relative to this script so the wrapper works from any directory.
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)

# Load only the ignored local environment file; the committed sample is never
# sourced automatically. `set -a` exports values for Ansible's env lookups.
if [ ! -f "$repo_dir/.env" ]; then
  printf '%s\n' "Missing $repo_dir/.env; copy .env.example and fill it locally." >&2
  exit 1
fi
set -a
# shellcheck disable=SC1091
. "$repo_dir/.env"
set +a

: "${LABFILTER_HOST:?LABFILTER_HOST is required in .env}"
: "${LABFILTER_PRIVATE_KEY_BASE64:?LABFILTER_PRIVATE_KEY_BASE64 is required in .env}"

# Decode the key only for this child process and remove it when Ansible exits.
key_dir=$(mktemp -d)
key_file="$key_dir/labfilter"
cleanup() {
  rm -f "$key_file"
  rmdir "$key_dir" 2>/dev/null || true
}
trap cleanup EXIT HUP INT TERM
printf '%s' "$LABFILTER_PRIVATE_KEY_BASE64" | base64 --decode > "$key_file"
chmod 600 "$key_file"

ANSIBLE_CONFIG="$repo_dir/ansible/ansible.cfg" \
ANSIBLE_PRIVATE_KEY_FILE="$key_file" \
ANSIBLE_HOST_KEY_CHECKING=true \
exec "$@"
