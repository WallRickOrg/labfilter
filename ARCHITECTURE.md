# Labfilter architecture

## Management plane

The system hostname `labfilter` and its independent management connection are
managed by Ansible. The management Ethernet interface uses DHCP, Wi-Fi is a
separate DHCP station, and SSH remains reachable through that path. Guarded
applies verify the configured management address before and after changes.

## Transparent bridge

`br0` is an unnumbered Layer-2 bridge composed of `eth0` and `eth1`:

```text
untrusted side ── eth0 ── br0 ── eth1 ── other side
```

The bridge has no management address, route, gateway, or DHCP profile.

## Packet filtering

Ansible owns the `bridge`-family nftables table `labfilter` and its `forward`
hook. The policy drops the controller-resolved fixed test destinations and the
persistent IPv4/IPv6 sets learned by the hourly GeoIP job, then accepts all
other transparent bridge traffic. Each deny chain logs a
rate-limited `LABFILTER_BLOCKED` prefix, then drops unconditionally; log
rate-limiting can never turn a deny into an allow. The apply validates nftables
syntax before replacing only this dedicated table, so unrelated firewall tables
are not flushed.

The GeoIP job queries only aggregations of `destination.ip` and
`destination.geo.country_iso_code` from the preceding 12 hours. Destinations in
`192.168.0.0/16`, the US, or Canada are excluded. Other and unknown locations
are retained in a root-owned JSON inventory and a generated nftables include,
grouped by location. The job compares that inventory with the live sets and
adds only missing unique elements. This keeps first-added dates stable and
restores policy after a reload without replacing the static table hourly.

## External blocked-traffic monitoring

The monitoring stack runs on a separate Docker server, not on Labfilter:

```text
br0 blocked packet
        │ nftables kernel log: LABFILTER_BLOCKED
        ▼
Labfilter rsyslog ── management path/UDP ──> remote Logstash
                                             │
                                      private Compose network
                                             │
                                  Elasticsearch ──> Kibana
```

Labfilter Ansible installs only rsyslog and a filter that forwards matching
kernel messages to the configured remote Logstash host. It does not install,
start, or configure Docker or Compose. The stack definition, Logstash pipeline,
and ILM bootstrap are in `monitoring/` and are operated on the Docker server.
The Docker server's firewall must restrict UDP/5514 to Labfilter. Elasticsearch
must be reachable over the independent management path for the scheduled
query, but TCP/9200 must be restricted to Labfilter and trusted administrators.
Kibana binds to its configured management address. ELK traffic does not
traverse Labfilter's `br0` hook.

The external stack uses persistent named Docker volumes and rolls the
blocked-event write alias every seven days without deleting older data. Elastic
security is disabled for this initial trusted-home-network deployment. Add
authentication and encrypted transport before exposing it more broadly.

## Safety and rebuild rules

- All Labfilter target changes go through guarded `ansible/playbooks/apply.yml`.
- Protected applies require explicit confirmation, local-access permission, and
  network-change permission.
- The playbook validates the rendered nftables policy before reload and checks
  management reachability, bridge membership, and the loaded policy afterward.
- No real forwarding test is inferred from controller SSH; test both bridge
  sides separately.
