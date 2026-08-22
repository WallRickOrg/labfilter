# OpenWrt network architecture

Status: verified topology and intended security policy. This document records
the design boundary; it does not authorize a live firewall or network change.
Any implementation change must be represented in Ansible and applied only by
the guarded Ansible workflow.

## Purpose

OpenWrt is an inline device between the home lab and an upstream route to the
internet. It has three distinct security planes:

1. A management plane on `eth0`.
2. A wireless DMZ-side plane on `phy0-sta0`.
3. An untrusted transparent bridge on `br-lan`, made from `eth1` and `eth2`.

Private addresses, hostnames, wireless identity, and credentials are runtime
values from the ignored `.env`. They are referenced below by policy variable
names rather than stored in tracked documentation.

## Verified live topology

The live device was inspected read-only after the management address was
corrected. The following facts were confirmed:

- OpenWrt runs on a Raspberry Pi 5 with the `bcm27xx/bcm2712` target.
- `eth0` is the `management` interface and obtains its address through DHCP.
- `eth1` and `eth2` are ports of `br-lan`; the `lan` interface has no L3 address
  and is configured as a bridge-facing interface.
- `phy0-sta0` is the wireless station interface and belongs to `lanwifi`, which
  obtains its address through DHCP.
- The default route leaves through `eth0`; the wireless station has a separate
  upstream route.
- The live firewall has a `lan` zone with ACCEPT input, output, and forwarding,
  and a `lanwifi` zone with ACCEPT input, output, and forwarding.
- Dropbear currently listens on TCP port 22. LuCI's HTTP services listen on
  TCP ports 80 and 443.
- A custom firewall rule is named `ssh` but currently targets TCP port 21 and
  does not represent Dropbear's current port 22.

## Intended security policy

### Management plane: `eth0`

- The management service must be reachable on the user-approved SSH port,
  currently described as TCP port 21, from the approved source CIDR stored in
  `OPENWRT_MANAGEMENT_ALLOWED_SOURCE_CIDR`.
- Traffic from `OPENWRT_GATEWAY_ADDRESS` must be explicitly rejected before the
  broader source allow rule. The gateway address must be populated and verified
  before implementing this rule; it must not be inferred from the source CIDR.
- The destination of this rule must be the management address on `eth0`, never
  the wireless station address.
- Management access from the local network is a hard invariant. Every Ansible
  application must verify the current management address before a protected
  change and verify it remains present afterward.

### Wireless DMZ plane: `phy0-sta0` / `lanwifi`

- The wireless station is an untrusted DMZ-side ingress, not a trusted LAN.
- Only TCP ports 21, 80, and 443 may be accepted to the OpenWrt device from the
  DMZ policy source. The policy is represented by
  `OPENWRT_DMZ_ALLOWED_TCP_PORTS` and defaults conceptually to `21,80,443`.
- All other input from the DMZ must be rejected. Output may remain allowed for
  the device's upstream operation, but forwarding must be explicitly defined
  rather than inherited from an ACCEPT-all zone.
- The port-21 intent must be resolved against the current Dropbear port-22
  configuration before application. Do not silently move SSH or expose a
  different service under the name `ssh`.

### Inline bridge: `br-lan` / `eth1` / `eth2`

- Traffic arriving from either physical bridge port is untrusted.
- The bridge must not be a trusted management path and must not be allowed to
  reach the router's management services by default.
- Forwarding between the home-lab side and the upstream route must be limited
  to explicitly approved stateful policy. Input to the OpenWrt device defaults
  to reject; forwarding defaults to reject until a specific flow is required.
- A transparent L2 bridge can bypass ordinary routed firewall-zone rules. The
  current `lan` interface is `proto none`, so assigning it an ACCEPT zone does
  not by itself prove that traffic crossing between `eth1` and `eth2` is
  filtered. Enforcing the untrusted policy requires either a routed design or
  an intentionally verified bridge/netfilter policy.

### Bridge filtering implementation

The reproducible implementation uses an Ansible-managed nftables file in
firewall4's `ruleset-pre` include directory. It defines a separate
`bridge`-family table with a `forward` hook, matching ingress on the physical
bridge ports and dropping destinations in the externally supplied CNN IPv4 and
IPv6 sets. This is intentionally separate from the routed `inet fw4` zones and
does not require `br_netfilter` or bridge sysctl changes.

The required `kmod-nft-bridge` kernel package is also part of the tracked
Ansible desired state. Read-only verification found firewall4 and nftables
core installed but this bridge expression module absent on the live device.

The CNN address sets are a DNS/CDN snapshot in the ignored `.env`, not a claim
that a hostname is permanently represented by fixed addresses. Refresh the
sets through the repository's Ansible variables and apply workflow when DNS
answers change. Encrypted DNS and alternate hostnames require separate policy
if they are in scope.

## Current gaps requiring explicit resolution

The live state does not yet implement the stated intent:

1. The current `lan` and `lanwifi` zones accept all input, output, and forwarding.
2. The current named `ssh` rule uses port 21 while Dropbear listens on port 22.
3. The current named rule must be redirected to the `eth0` management address
   if it is intended to protect management access; its existing destination is
   not the management interface.
4. The exact gateway address to exclude is not recorded in the tracked
   repository and must be supplied through ignored `.env` before implementation.
5. The bridge filter has been represented in Ansible but has not been applied
   or demonstrated by a live packet-path test; the current UCI zone names are
   not evidence that transparent forwarding is filtered.

## Ansible implementation invariants

- Put policy values in ignored `.env` and non-secret structure in tracked
  Ansible templates/variables.
- Make all firewall, network, service, and reboot changes through Ansible.
- Require explicit apply confirmation and local-access confirmation.
- Require the management address/interface guard for network and firewall work.
- Back up `/etc/config` before a protected change and do not reload services
  unless the service list is explicitly reviewed.
- Validate management access from an independent local-network path before
  declaring the change successful.

## Acceptance tests before implementation is considered complete

- The approved source can reach the intended SSH service on `eth0`.
- The gateway address cannot reach that SSH service.
- The DMZ-side wireless interface can reach only TCP 21, 80, and 443 on the
  device; another test port is rejected.
- The bridge ports cannot reach management services.
- Required lab-to-internet forwarding works only through the explicitly approved
  stateful path.
- The tests pass after service reload and after a controlled reboot, with local
  management access retained throughout.
