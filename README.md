# Labfilter configuration management

This repository is the Ansible source of truth for the Debian-based Raspberry
Pi 4 Labfilter. Connection details, Wi-Fi credentials, and private network
information stay in the ignored local `.env` file.

The managed system hostname is `labfilter`.

## Current managed topology

- The independent wired management path and Wi-Fi station use NetworkManager
  DHCP profiles; SSH is enabled for management.
- `eth0` and `eth1` are unnumbered ports of transparent bridge `br0`.
- nftables is enabled with a `bridge`-family forward hook. It allows ordinary
  bridge traffic and drops the controller-resolved address snapshot for the
  fixed `Block CNN` test policy.

The bridge has no IPv4 or IPv6 address, CIDR, route, or gateway. It cannot
replace the management path.

## Setup and discovery

Copy `.env.example` to `.env` and replace every placeholder locally. Base64
encode the SSH private key and Wi-Fi PSK; never commit `.env`.

```sh
./scripts/ansible.sh ansible-playbook ansible/playbooks/discover.yml
```

Discovery is read-only and writes private reports under ignored
`artifacts/discovery/debian/`. Review those reports before representing manual
changes in Ansible.

## Apply

Network and filtering changes need all three safeguards:

```sh
./scripts/ansible.sh ansible-playbook ansible/playbooks/apply.yml \
  -e labfilter_apply_confirmed=true \
  -e labfilter_allow_local_access=true \
  -e labfilter_allow_network_changes=true
```

The playbook checks the management address before and after application, verifies
that both bridge ports are attached to `br0`, validates the nftables syntax, and
confirms the active bridge policy. It does not prove real forwarding without a
client on each bridge side.

`LABFILTER_ULA_PREFIX` is unused and should remain absent: no ULA network is
configured on this Labfilter.

## Layout

- `ansible/playbooks/discover.yml` — read-only Debian discovery.
- `ansible/playbooks/apply.yml` — guarded bridge and baseline application.
- `ansible/templates/` — NetworkManager and nftables configuration.
- `ansible/vars/labfilter.yml` — non-sensitive desired state and fixed policy.
- `ARCHITECTURE.md` — packet path, safeguards, and policy limitations.
