# Labfilter configuration management repository

This repository is the Ansible source of truth for a Debian-based Raspberry Pi
4 Labfilter. Connection details, Wi-Fi credentials, and private network data
stay in the ignored `.env`; secrets there must be base64 encoded.

## Current topology

- Independent DHCP management Ethernet and Wi-Fi paths provide SSH access.
- `br0` is an unnumbered transparent bridge made from `eth0` and `eth1`.
- nftables filters the bridge in the `bridge`-family `forward` hook.
- The fixed test deny policy logs only dropped packets with
  `LABFILTER_BLOCKED`; other bridge traffic is accepted.

## Setup and discovery

Copy `.env.example` to `.env`, fill local values, and never commit `.env`.
Discovery is read-only and stores private reports under ignored artifacts:

```sh
./scripts/ansible.sh ansible-playbook ansible/playbooks/discover.yml
```

## Guarded apply

Network and filtering changes require all three safeguards:

```sh
./scripts/ansible.sh ansible-playbook ansible/playbooks/apply.yml \
  -e labfilter_apply_confirmed=true \
  -e labfilter_allow_local_access=true \
  -e labfilter_allow_network_changes=true
```

The playbook preserves the management path, validates nftables before reload,
and verifies the active bridge policy afterward. It manages rsyslog only as the
blocked-event forwarder; it does not install or run Docker/Compose.

## External ELK monitoring

The Docker Compose stack runs on a separate Docker server. See
[`monitoring/`](monitoring/) for the pinned Elastic images, persistent named
volumes, Logstash pipeline, remote-listener environment sample, and weekly ILM
bootstrap. Configure the Docker server firewall to permit UDP/5514 only from
Labfilter.

## Layout

- `ansible/playbooks/discover.yml` — read-only Debian discovery.
- `ansible/playbooks/apply.yml` — guarded Labfilter baseline and filtering.
- `ansible/templates/` — NetworkManager, nftables, and rsyslog configuration.
- `ansible/vars/labfilter.yml` — non-sensitive desired state.
- `monitoring/` — external Docker-server Compose project.
- `ARCHITECTURE.md` — packet path, monitoring path, and safety constraints.
