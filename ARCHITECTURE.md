# Labfilter architecture

## Management plane

The management Ethernet connection is independent from the bridge and receives
its address through DHCP. The Wi-Fi station is also DHCP-managed. SSH remains
enabled. Guarded Ansible applies verify that the configured management address
is assigned to its configured interface before and after any change.

## Transparent bridge

`br0` is an unnumbered Linux bridge composed of `eth0` and `eth1`:

```text
untrusted side ── eth0 ── br0 ── eth1 ── other side
```

The bridge has IPv4 disabled and IPv6 ignored. It has no IP address, CIDR,
gateway, DNS configuration, or management service. NetworkManager creates the
bridge and its two Layer-2-only port profiles through Ansible.

## Packet filtering

nftables owns a `bridge`-family `forward` hook. This hook is used because
transparent frames crossing `br0` are not routed through an IP forwarding path.
The current policy is intentionally narrow:

- drop IPv4 and IPv6 destinations in the controller-resolved snapshot for the
  fixed `Block CNN` test hostnames;
- allow every other frame crossing the bridge.

nftables cannot match a hostname directly. Each guarded apply resolves the
fixed hostnames on the controller and renders validated address sets. The deny
is therefore a point-in-time DNS/CDN snapshot; reapply after relevant DNS
changes and do not treat it as durable content filtering.

The policy is active in `/etc/nftables.conf` and can be inspected locally with
`nft list table bridge labfilter`. No policy-management web UI is installed on
this Debian baseline, so Ansible remains the only permitted edit path.

## Safety and verification

- Network and firewall changes require explicit apply confirmation, local-access
  confirmation, and network-change confirmation.
- The playbook writes and reloads NetworkManager profiles, activates only `br0`
  and its declared ports, and never moves the management connection into the
  bridge.
- Before nftables starts, the managed configuration passes `nft -c` syntax
  validation. Afterward, Ansible checks bridge existence, both member ports,
  the loaded policy structure, and retained management access.
- A functional forwarding/block test still requires a client on each side of
  `br0`; controller-side SSH arrives through the independent management path.
