# OpenWrt desired state

`openwrt.yml` is the tracked, non-secret desired-state entry point. Populate it
only after reviewing a successful local discovery report. Put machine-specific
or secret overrides in an ignored `*.local.yml` file and pass it explicitly to
Ansible when needed.

Do not copy an unredacted `/etc/config` export into Git. The inline bridge's
network and firewall values need an explicit safety review before they are
added to the apply lists.
