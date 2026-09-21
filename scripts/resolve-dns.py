#!/usr/bin/env python3
"""Resolve policy hostnames to nftables-compatible, validated IP addresses."""

import ipaddress
import json
import socket
import sys


def main() -> int:
    """Emit one sorted IPv4/IPv6 snapshot for the supplied policy hostnames."""
    ipv4: set[str] = set()
    ipv6: set[str] = set()

    for hostname in sys.argv[1:]:
        try:
            answers = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        except socket.gaierror as error:
            print(f"Unable to resolve policy hostname {hostname!r}: {error}", file=sys.stderr)
            return 1

        for family, _, _, _, sockaddr in answers:
            address = ipaddress.ip_address(sockaddr[0])
            if family == socket.AF_INET:
                ipv4.add(str(address))
            elif family == socket.AF_INET6:
                ipv6.add(str(address))

    print(json.dumps({"ipv4": sorted(ipv4), "ipv6": sorted(ipv6)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
