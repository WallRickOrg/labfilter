# Labfilter Ansible variables

`labfilter.yml` contains only verified, non-sensitive desired state for the
Debian-based Raspberry Pi 4. Private addresses and Wi-Fi credentials are loaded
from the ignored `.env` file by `scripts/ansible.sh`.

Do not add bridge topology, SSIDs, private addresses, secrets, or keys here.
First capture manual changes with the read-only discovery playbook, then convert
only the non-sensitive configuration structure into this file or a template.
