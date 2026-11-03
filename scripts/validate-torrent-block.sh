#!/bin/sh
set -eu

# Generate harmless connection attempts from a host behind Labfilter, then
# verify that the managed nftables drop counter increased on Labfilter.
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)

usage() {
    cat <<'EOF'
Usage: scripts/validate-torrent-block.sh --target-ip IPv4-address

Run this from a client whose traffic crosses Labfilter. The target should be
an IPv4 address reachable through the bridge; it is used only to generate
test packets and is never written to a file.

The validator probes TCP and UDP ports 6881-6889 and 51413, then checks the
live Labfilter block_torrent counter through the guarded Ansible wrapper.
It does not validate arbitrary-port, encrypted, or VPN-encapsulated torrents.
EOF
}

target_ip=
while [ "$#" -gt 0 ]; do
    case "$1" in
        --target-ip)
            [ "$#" -ge 2 ] || { usage >&2; exit 2; }
            target_ip=$2
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            usage >&2
            exit 2
            ;;
    esac
done

[ -n "$target_ip" ] || { usage >&2; exit 2; }
command -v nc >/dev/null 2>&1 || {
    printf '%s\n' 'Error: nc is required on the test client.' >&2
    exit 1
}

read_block_counter() {
    # The chain has separate log and drop counters; summing both detects a
    # packet that reached the managed block chain without exposing raw logs.
    "$repo_dir/scripts/ansible.sh" .venv/bin/ansible labfilter -m shell \
        -a 'nft list chain bridge labfilter block_torrent' |
        sed -n 's/.*counter packets \([0-9][0-9]*\).*/\1/p' |
        awk '{ total += $1 } END { print total + 0 }'
}

before=$(read_block_counter)
printf 'Initial Labfilter torrent-block counter: %s\n' "$before"

for port in 6881 6882 6883 6884 6885 6886 6887 6888 6889 51413; do
    # TCP failure is expected whether the remote service is closed or the
    # packet is dropped; the nftables counter is the authoritative result.
    nc -z -w 2 "$target_ip" "$port" >/dev/null 2>&1 || true

    # Send one UDP datagram. No response is required and the payload contains
    # no credentials or user data.
    printf '%s\n' 'labfilter-torrent-block-test' |
        nc -u -w 2 "$target_ip" "$port" >/dev/null 2>&1 || true
done

after=$(read_block_counter)
printf 'Final Labfilter torrent-block counter: %s\n' "$after"

if [ "$after" -le "$before" ]; then
    printf '%s\n' 'FAIL: no probe reached the Labfilter torrent block chain.' >&2
    printf '%s\n' 'Confirm this client is behind the bridge and repeat with a reachable target IP.' >&2
    exit 1
fi

printf '%s\n' 'PASS: Labfilter blocked the common BitTorrent-port probes.'
printf '%s\n' 'Note: arbitrary-port, encrypted, and VPN-encapsulated torrent traffic is outside this test.'
