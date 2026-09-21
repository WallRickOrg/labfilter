# Labfilter configuration management

This repository is the reproducible, Ansible-managed baseline for the current
Debian-based Raspberry Pi 4 Labfilter. Connection details, Wi-Fi credentials,
and private network information stay in the ignored local `.env` file.

## Current verified state

- NetworkManager manages DHCP on the wired management interface and Wi-Fi
  station.
- SSH and NetworkManager are enabled.
- nftables is installed, but its service is disabled and the active ruleset has
  no filtering policy.
- No active Linux bridge or bridge-filtering configuration exists yet.

The baseline deliberately reproduces that state. It does not turn the Pi into
an inline bridge until the physical port roles and policy have been reviewed.

## Setup

Copy `.env.example` to `.env` and replace every placeholder locally. Encode the
SSH private key and Wi-Fi PSK with base64; do not commit `.env`.

```sh
./scripts/ansible.sh ansible-playbook ansible/playbooks/discover.yml
```

Discovery is read-only and stores private reports in ignored
`artifacts/discovery/debian/`. Review those reports before representing a
manual change in Ansible.

## Apply the verified baseline

An apply requires three explicit safeguards because changing NetworkManager
profiles can interrupt the only management path.

```sh
./scripts/ansible.sh ansible-playbook ansible/playbooks/apply.yml \
  -e labfilter_apply_confirmed=true \
  -e labfilter_allow_local_access=true \
  -e labfilter_allow_network_changes=true
```

The playbook verifies that the configured management address is present on its
configured interface before and after the protected work. It reloads connection
profiles without explicitly reconnecting a link.

`LABFILTER_ULA_PREFIX` is not used by this Debian baseline. Discovery found no
active IPv6 Unique Local Address network, so remove that obsolete legacy
setting from the local `.env` rather than choosing a new prefix.

## Layout

- `ansible/playbooks/discover.yml` — read-only Debian discovery.
- `ansible/playbooks/apply.yml` — guarded baseline application.
- `ansible/templates/` — NetworkManager and nftables configuration.
- `ansible/vars/labfilter.yml` — non-sensitive verified desired state.
- `ARCHITECTURE.md` — observed state and the deferred inline-bridge design.
