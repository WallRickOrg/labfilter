#!/bin/sh
set -eu

# Resolve paths relative to this script so it works from any current directory.
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)

# Load only the ignored local environment file; the sample file is never sourced automatically.
if [ ! -f "$repo_dir/.env" ]; then
    printf '%s\n' "Missing $repo_dir/.env; copy .env.example and fill in local values." >&2
    exit 1
fi
# Export the local environment values so Ansible inventory lookups can consume them.
set -a
# shellcheck disable=SC1091
. "$repo_dir/.env"
set +a

# Validate required names without printing their values or the decoded private key.
: "${OPENWRT_HOST:?OPENWRT_HOST is required in .env}"
: "${OPENWRT_PRIVATE_KEY_BASE64:?OPENWRT_PRIVATE_KEY_BASE64 is required in .env}"

# Decode the key only into a private temporary file for this child process.
key_dir=$(mktemp -d)
key_file="$key_dir/openwrt"
cleanup() {
    rm -f "$key_file"
    rmdir "$key_dir" 2>/dev/null || true
}
trap cleanup EXIT HUP INT TERM
printf '%s' "$OPENWRT_PRIVATE_KEY_BASE64" | base64 --decode > "$key_file"
chmod 600 "$key_file"

# Keep Ansible pointed at the repository inventory and temporary key.
export ANSIBLE_CONFIG="$repo_dir/ansible/ansible.cfg"
export ANSIBLE_PRIVATE_KEY_FILE="$key_file"
export ANSIBLE_HOST_KEY_CHECKING=true

# Execute the requested Ansible command without exposing environment secrets in arguments.
cd "$repo_dir"
exec "$@"
