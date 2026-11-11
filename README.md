# Labfilter configuration management repository

This repository is the Ansible source of truth for a Debian-based Raspberry Pi
4 Labfilter. Connection details, Wi-Fi credentials, and private network data
stay in the ignored `.env`; secrets there must be base64 encoded.

## Current topology

- Independent DHCP management Ethernet and Wi-Fi paths provide SSH access.
- `br0` is an unnumbered transparent bridge made from `eth0` and `eth1`.
- The WireGuard client at `192.168.2.9` has narrow ICMP and UDP/51820
  exceptions. Its direct public egress is denied, while local-network traffic
  remains available; torrent traffic therefore must use the VPN tunnel.
- Common BitTorrent ports (`6881-6889` and `51413`) are blocked in both TCP and
  UDP directions for every bridge source. This is a known-port safeguard, not
  application identification; arbitrary-port or encrypted torrent sessions
  require endpoint-level controls.
- nftables filters the bridge in the `bridge`-family `forward` hook.
- DHCP client requests (`UDP/68→67`) and server replies (`UDP/67→68`) are
  explicitly allowed through the bridge before destination blocking.
- DNS queries and replies using UDP or TCP port 53 are explicitly allowed
  through the bridge before destination blocking.
- Allowed traffic is logged with a global rate limit of 5 events per second
  with a burst of 20, while blocked traffic retains its separate log policy.
- WireGuard client ICMP and UDP/51820 exception traffic is accepted without
  generating allowed-traffic log events.
- The bridge always accepts sources from `192.168.86.0/24` and the standard
  Tailscale IPv4/IPv6 ranges before destination deny sets.
- Fixed and learned GeoIP deny policy logs dropped packets with
  `LABFILTER_BLOCKED`. The WireGuard client's direct public egress kill-switch
  uses the same blocked-event path, while other bridge traffic is accepted and
  monitored.

To validate the common BitTorrent-port deny from a client behind Labfilter,
run the counter-based probe with a reachable IPv4 destination:

```sh
scripts/validate-torrent-block.sh --target-ip <reachable-ipv4>
```

The script requires `nc`, probes TCP and UDP ports `6881-6889` and `51413`, and
checks that the live `block_torrent` nftables counter increases through the
Ansible wrapper. It cannot identify arbitrary-port, encrypted, or
VPN-encapsulated torrent traffic.

## Setup and discovery

Copy `.env.example` to `.env`, fill local values, and never commit `.env`.
The wrapper loads `.env` and the SSH key, but it does not install Ansible.
Create or activate an Ansible virtual environment before running it:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip ansible-core
```

Discovery is read-only and stores private reports under ignored artifacts:

```sh
./scripts/ansible.sh .venv/bin/ansible-playbook ansible/playbooks/discover.yml
```

## Guarded apply

Network and filtering changes require all three safeguards:

```sh
./scripts/ansible.sh .venv/bin/ansible-playbook ansible/playbooks/apply.yml \
  -e labfilter_apply_confirmed=true \
  -e labfilter_allow_local_access=true \
  -e labfilter_allow_network_changes=true
```

The playbook preserves the management path, validates nftables before reload,
and verifies the active bridge policy afterward. It manages rsyslog only as the
blocked-event forwarder; it does not install or run Docker/Compose.

Set `LABFILTER_ELASTICSEARCH_URL` in the ignored `.env` to an Elasticsearch URL
reachable through Labfilter's independent management path. The external host
firewall should permit TCP/9200 only from Labfilter; Elastic security is
currently disabled.

## Automated destination blocking

The blocker resolves configured OpenAI, Codex, GitHub, and GitHub Container
Registry service hostnames each hourly run and excludes their current addresses
from the deny sets. This avoids hard-coding provider IPs and removes previously
learned matching addresses during the same nftables reconciliation. GitHub's
published Meta API ranges are useful for reference, but GitHub documents that
they are not exhaustive for every service, so hostname protection is the
managed policy here.

The blocker resolves configured service hostnames, including Docker Hub
authentication/registry/index endpoints and the npm registry, on every hourly
run. It also checks the indexed destination reverse-DNS hostname
and protects `docker.io` plus every subdomain ending in `.docker.io`. Matching
addresses are removed from the persistent deny inventory during the same
reconciliation, allowing Docker image pulls to continue while CDN addresses
rotate normally.

An Ansible-managed cron job runs at the start of every hour and uses a paginated
Elasticsearch aggregation over the previous 12 hours of `labfilter-*` events.
It ignores IPv4 destinations in `192.168.0.0/16` and destinations geolocated to
the configured safe-country set (`AU`, `CA`, `GB`, `NZ`, and `US` by default).
All other IPv4 and IPv6 destinations, including addresses without a GeoIP
country, are added once to persistent nftables sets.

The learned inventory is grouped by country code or `UNKNOWN` in
`/var/lib/labfilter/geo-block-elements.nft`. On nftables versions that support
element comments, each entry includes its original UTC added date. The JSON
inventory preserves uniqueness and first-added metadata across hourly runs,
service reloads, and reboots. Cron writes aggregate counts, not addresses or raw
events, to the local journal under the `labfilter-geo-blocker` tag.

## External ELK monitoring

The Docker Compose stack runs on a separate Docker server. See
[`../monitoring/`](../monitoring/) for the pinned Elastic images, persistent named
volumes, Logstash pipeline, remote-listener environment sample, and weekly ILM
bootstrap. Configure the Docker server firewall to permit UDP/5514 only from
Labfilter.

## Layout

- `ansible/playbooks/discover.yml` — read-only Debian discovery.
- `ansible/playbooks/apply.yml` — guarded Labfilter baseline and filtering.
- `ansible/files/labfilter-geo-blocker.py` — hourly Elasticsearch policy worker.
- `ansible/templates/` — NetworkManager, nftables, cron, and rsyslog configuration.
- `ansible/vars/labfilter.yml` — non-sensitive desired state.
- `../monitoring/` — independent reusable monitoring project with the bundled
  Labfilter integration and the existing `monitoring` Compose data identity.
- `pihole/` — external Docker-server Pi-hole Compose project; its DNS firewall
  enforcement is intentionally deferred until clients are migrated.
- `ARCHITECTURE.md` — packet path, monitoring path, and safety constraints.
