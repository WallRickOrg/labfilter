#!/usr/bin/env python3
"""Resolve policy hostnames to validated A and AAAA addresses as JSON."""

import argparse
import ipaddress
import json
import socket
import sys
import urllib.parse
import urllib.request


# DNS over HTTPS avoids depending on optional resolver tools such as dig on the
# Ansible controller while still requesting both address families explicitly.
DOH_ENDPOINT = "https://cloudflare-dns.com/dns-query"
RECORD_TYPES = {"A": (1, 4), "AAAA": (28, 6)}


def resolve(hostname: str, record_type: str) -> set[str]:
    """Return validated addresses of one DNS record type for a hostname."""
    query = urllib.parse.urlencode({"name": hostname, "type": record_type})
    request = urllib.request.Request(
        f"{DOH_ENDPOINT}?{query}",
        headers={"Accept": "application/dns-json", "User-Agent": "openwrt-ansible"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.load(response)

    if payload.get("Status") != 0:
        raise RuntimeError(
            f"DNS query for {hostname} {record_type} returned status "
            f"{payload.get('Status')}"
        )

    dns_type, ip_version = RECORD_TYPES[record_type]
    addresses: set[str] = set()
    for answer in payload.get("Answer", []):
        if answer.get("type") != dns_type:
            continue
        address = ipaddress.ip_address(answer["data"])
        if address.version != ip_version:
            raise RuntimeError(f"Unexpected address family for {hostname}: {address}")
        if not address.is_global:
            raise RuntimeError(f"Refusing non-global answer for {hostname}: {address}")
        addresses.add(str(address))
    return addresses


def resolve_system(hostname: str) -> dict[str, set[str]]:
    """Supplement public DNS answers with the controller's client resolver."""
    addresses = {"ipv4": set(), "ipv6": set()}
    try:
        results = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        # The explicit DNS-over-HTTPS queries below remain authoritative for
        # this apply when the controller's local resolver is unavailable.
        return addresses

    for family, _socket_type, _protocol, _canonical_name, socket_address in results:
        address = ipaddress.ip_address(socket_address[0])
        # A poisoned or local DNS answer must never turn this test rule into a
        # block against private, loopback, link-local, or management space.
        if not address.is_global:
            raise RuntimeError(f"Refusing non-global answer for {hostname}: {address}")
        if family == socket.AF_INET:
            addresses["ipv4"].add(str(address))
        elif family == socket.AF_INET6:
            addresses["ipv6"].add(str(address))
    return addresses


def main() -> int:
    """Resolve all requested hostnames and emit deterministic JSON lists."""
    parser = argparse.ArgumentParser()
    parser.add_argument("hostnames", nargs="+", help="hostnames to resolve")
    args = parser.parse_args()

    resolved = {"ipv4": set(), "ipv6": set()}
    for hostname in args.hostnames:
        system_addresses = resolve_system(hostname)
        resolved["ipv4"].update(system_addresses["ipv4"])
        resolved["ipv6"].update(system_addresses["ipv6"])
        resolved["ipv4"].update(resolve(hostname, "A"))
        resolved["ipv6"].update(resolve(hostname, "AAAA"))

    if not resolved["ipv4"] and not resolved["ipv6"]:
        raise RuntimeError("No A or AAAA answers were returned")

    print(json.dumps({family: sorted(values) for family, values in resolved.items()}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, KeyError, json.JSONDecodeError) as error:
        # Keep failures concise so Ansible reports the resolver problem without
        # printing response payloads or unrelated controller environment data.
        print(f"DNS resolution failed: {error}", file=sys.stderr)
        raise SystemExit(1)
