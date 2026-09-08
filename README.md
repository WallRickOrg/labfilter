# Labfilter configuration management

Labfilter is the reproducible management surface for the home OpenWrt
instance. Ansible connects over SSH and uses OpenWrt's native `uci` and service
commands, so the playbooks do not require Python to be installed on the router.

The live device is an inline bridge. Network and firewall changes are therefore
deliberately opt-in and guarded; local-network management must remain available
before and after any future configuration change.

## Prerequisites

- Ansible Core on the management machine.
- A local `.env` copied from `.env.example`.
- An SSH private key encoded as base64 in `LABFILTER_PRIVATE_KEY_BASE64`.
- A route from the management machine to the OpenWrt host.

The repository does not contain the live endpoint or key. The existing local
`.env` is intentionally ignored by Git.

The live-specific values required by the reproduced templates are also kept in
`.env`: management interface/address, device hostname, private topology values,
wireless SSID, and base64-encoded wireless/rpcd credentials. Keep those values
local and verify them before applying.

When the wireless template is selected, Ansible writes those ignored SSID/PSK
values, reloads the managed station, and waits for its configured DHCP network
to recover.
The apply fails if association or IPv4 recovery does not complete.

## Discover the live state

Run the read-only discovery playbook after the management machine can reach the
router:

```sh
./scripts/ansible.sh ansible-playbook ansible/playbooks/discover.yml
```

The playbook writes a redacted report under `artifacts/discovery/`. It captures
the OpenWrt release, UCI export, interfaces, routes, and enabled services while
redacting common credential fields. Review that report locally and convert
the verified desired state into the tracked templates and variables; never
commit the report or unredacted backups.

## Apply configuration

The checked-in templates contain the observed non-secret UCI structure. Private
and machine-specific values are loaded from the ignored `.env`. Review the
templates and local values before applying:

```sh
./scripts/ansible.sh ansible-playbook ansible/playbooks/apply.yml \
  -e labfilter_apply_confirmed=true \
  -e labfilter_allow_local_access=true \
  -e labfilter_allow_network_changes=true
```

The apply playbook requires both `labfilter_apply_confirmed=true` and
`labfilter_allow_local_access=true`. It also requires
`labfilter_allow_network_changes=true` for this firewall change, and refuses
protected changes unless the management-address guard is present.
Review the playbook and desired-state lists before applying. These playbooks
use OpenWrt's `raw` interface because the router may not have Python, so do not
rely on Ansible check mode as a substitute for that review:

```sh
./scripts/ansible.sh ansible-playbook ansible/playbooks/apply.yml --list-tasks
```

The wrapper creates a temporary key file from the base64 value, uses it for the
Ansible process, and removes it on exit. It never writes the decoded key into
the repository.

Kernel packages are checksum-pinned in `ansible/vars/labfilter.yml`. Because the
router management path cannot reach package feeds, Ansible downloads them to a
private controller temporary directory, transfers them over the same SSH
connection, verifies them again on OpenWrt, and removes both staged copies.
Update the pinned filename, URL, and checksum after an OpenWrt kernel upgrade;
`opkg` intentionally rejects a module built for a different kernel ABI.

`Block CNN` is a fixed test policy in the tracked Ansible variables. During
each guarded apply, the controller resolves its tracked hostnames to validated
A and AAAA records and renders that one snapshot into the bridge nftables sets.
No CNN rule name, hostname, or address configuration belongs in `.env`.
Because transparent bridge forwarding bypasses LuCI's routed Traffic Rules,
the policy is managed as a native firewall4 script include instead. Its actual
nftables rules are visible at **Network → Firewall → Custom Rules**; see
[`ARCHITECTURE.md`](ARCHITECTURE.md) for the packet-path limitation.
On this fw4-only image, the packaged Custom Rules menu is hidden by an obsolete
fw3 dependency. Ansible therefore installs **Network → Bridge nftables Rules**
as a dedicated editor for the same script. Direct UI edits are permitted, but
must be synchronized into the Ansible template before the next managed apply.
The Ansible deployment also clears LuCI's transient menu cache so the route is
visible on the next browser refresh.
The TCP 8006 bridge test exception is also fixed in tracked Ansible and contains
no private backend address or `.env` configuration.

## Repository layout

- `ARCHITECTURE.md`: verified topology, intended security policy, and acceptance tests.
- `ansible/playbooks/discover.yml`: read-only live-state capture with redaction.
- `ansible/playbooks/apply.yml`: guarded UCI and service application.
- `ansible/templates/uci/`: current non-secret UCI package templates.
- `ansible/templates/nft/`: bridge-family nftables policies for transparent
  forwarding.
- `ansible/inventory/hosts.yml`: inventory whose host comes from `.env`.
- `ansible/vars/labfilter.yml`: tracked, non-secret desired-state data.
- `scripts/ansible.sh`: safe `.env` loading and temporary-key handling.
- `artifacts/` and `backups/`: ignored local runtime outputs.

The live discovery has been completed and the tracked templates reflect the
observed package structure. Re-run discovery after any manual router change;
do not hand-edit bridge or firewall behavior from assumptions.
