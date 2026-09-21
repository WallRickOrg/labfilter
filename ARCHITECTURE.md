# Labfilter architecture

## Verified current state

The new Labfilter is a Debian-based Raspberry Pi 4 managed with NetworkManager.
Its independent management path is a DHCP-configured wired Ethernet interface;
the onboard Wi-Fi is a DHCP station using WPA-PSK. SSH is enabled for remote
management.

The two other physical Ethernet ports are present but no active Linux bridge
exists. nftables is installed with an empty base configuration, while its system
service is disabled. Therefore the current device does not filter traffic or
operate as an inline bridge.

No IPv6 ULA network was observed. `LABFILTER_ULA_PREFIX` belonged to the former
platform configuration and has no role in this Debian baseline.

## Rebuild boundary

Ansible recreates the observed management Ethernet and Wi-Fi DHCP profiles,
the verified package baseline, SSH availability, and the inactive nftables
service state. Addresses, SSID, PSK, connection host, and private key remain in
ignored `.env` values.

Network profile application is guarded by explicit confirmation and checks that
the current management address remains assigned to its expected interface both
before and after the work. The playbook loads profiles without explicitly
reconnecting a link.

## Deferred inline bridge design

The intended Labfilter role remains an inline bridge between the home lab and
an upstream network. That role must be designed as a separate, reviewed change
because it will alter Layer-2 forwarding and can remove management access.

Before implementing it, verify and record:

- which physical ports are the bridge members and their directionality;
- which interface must retain local management access;
- whether management must be reachable from Wi-Fi, wired Ethernet, or both;
- the required forwarding policy and how bridge-family nftables will enforce
  it; and
- recovery validation from an independent local management path.

Do not use this baseline to infer a bridge topology or enable filtering. Once
that design is approved, express it in Ansible before applying it to Labfilter.
