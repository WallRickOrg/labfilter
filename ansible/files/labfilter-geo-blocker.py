#!/usr/bin/env python3
"""Build a persistent nftables destination block set from recent ELK events."""

from __future__ import annotations

import argparse
from datetime import date
import fcntl
import ipaddress
import json
import os
import socket
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Iterable
from urllib import error, parse, request


# Keep the default conservative; deployments can expand this through managed
# Ansible data without changing the executable.
DEFAULT_ALLOWED_COUNTRIES = {"AU", "CA", "GB", "NZ", "US"}
LOCAL_IPV4_NETWORK = ipaddress.ip_network("192.168.0.0/16")
SET_NAMES = {4: "geo_blocked_ipv4", 6: "geo_blocked_ipv6"}
# These service names are resolved at each scheduled run so changing provider
# addresses do not become permanently blocked by the country-only policy. GitHub
# publishes CIDRs, but its own documentation says that list is not exhaustive;
# hostname protection covers the client endpoints used by Git and Codex safely.
DEFAULT_PROTECTED_HOSTNAMES = (
    "api.openai.com",
    "auth.openai.com",
    "chatgpt.com",
    "chat.openai.com",
    "codex.openai.com",
    "codex.com",
    "github.com",
    "ssh.github.com",
    "api.github.com",
    "raw.githubusercontent.com",
    "objects.githubusercontent.com",
    "codeload.github.com",
    "gist.githubusercontent.com",
    "ghcr.io",
    "auth.docker.io",
    "registry-1.docker.io",
    "index.docker.io",
    "registry.npmjs.org",
)
DEFAULT_PROTECTED_HOSTNAME_SUFFIXES = (".docker.io",)


class BlockerError(RuntimeError):
    """Report an operational error without exposing raw Elasticsearch events."""


def load_json(path: Path) -> dict[str, Any]:
    """Load a required JSON object and give configuration errors clear context."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BlockerError(f"cannot read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BlockerError(f"expected a JSON object in {path}")
    return value


def query_destinations(
    config: dict[str, Any],
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Return destination country observations and indexed reverse hostnames."""
    base_url = str(config["elasticsearch_url"]).rstrip("/")
    index = parse.quote(str(config["index_pattern"]), safe="*,-_")
    lookback_hours = int(config["lookback_hours"])
    page_size = int(config.get("aggregation_page_size", 1000))
    endpoint = (
        f"{base_url}/{index}/_search"
        "?ignore_unavailable=true&allow_no_indices=true"
    )
    after_key: dict[str, Any] | None = None
    destinations: dict[str, set[str]] = {}
    destination_hostnames: dict[str, set[str]] = {}

    while True:
        # Composite aggregation pages through every unique destination without
        # transferring raw documents or depending on a fixed cardinality cap.
        composite: dict[str, Any] = {
            "size": page_size,
            "sources": [{"destination_ip": {"terms": {"field": "destination.ip"}}}],
        }
        if after_key is not None:
            composite["after"] = after_key
        body = {
            "size": 0,
            "query": {
                "bool": {
                    "filter": [
                        {"range": {"@timestamp": {"gte": f"now-{lookback_hours}h", "lte": "now"}}},
                        {"exists": {"field": "destination.ip"}},
                    ]
 },
 },
 "aggs": {
                "destinations": {
                    "composite": composite,
                    "aggs": {
                    "countries": {
                            "terms": {
                                "field": "destination.geo.country_iso_code",
                                "size": 16,
                            }
 },
 # Logstash stores reverse-DNS enrichment in this ECS field.
                    # The keyword subfield keeps the aggregation compatible
                    # with Elasticsearch's default dynamic string mapping.
                    "hostnames": {
                        "terms": {
                            "field": "destination.hostname.keyword",
                            "size": 64,
                        }
 },
 },
 },
 }
        }
        http_request = request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(
                http_request, timeout=int(config.get("request_timeout_seconds", 30))
            ) as response:
                result = json.load(response)
        except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise BlockerError(f"Elasticsearch query failed: {exc}") from exc

        aggregation = result.get("aggregations", {}).get("destinations", {})
        buckets = aggregation.get("buckets", [])
        if not isinstance(buckets, list):
            raise BlockerError("Elasticsearch returned an invalid aggregation response")
        for bucket in buckets:
            address = str(bucket.get("key", {}).get("destination_ip", ""))
            codes: set[str] = set()
            for country in bucket.get("countries", {}).get("buckets", []):
                code = str(country.get("key", "")).upper()
                if code.isascii() and code.isalpha() and 2 <= len(code) <= 3:
                    codes.add(code)
            destinations.setdefault(address, set()).update(codes)
            for hostname in bucket.get("hostnames", {}).get("buckets", []):
                value = str(hostname.get("key", "")).strip().lower().rstrip(".")
                if value:
                    destination_hostnames.setdefault(address, set()).add(value)

        next_after = aggregation.get("after_key")
        if not buckets or next_after is None:
            break
        if next_after == after_key:
            raise BlockerError("Elasticsearch composite aggregation did not advance")
        after_key = next_after

    return destinations, destination_hostnames


def hostname_matches_suffix(hostname: str, suffix: str) -> bool:
    """Match a hostname or subdomain without matching lookalike domains."""
    normalized_hostname = hostname.strip().lower().rstrip(".")
    normalized_suffix = suffix.strip().lower().lstrip(".").rstrip(".")
    return bool(normalized_suffix) and (
        normalized_hostname == normalized_suffix
        or normalized_hostname.endswith(f".{normalized_suffix}")
    )


def protected_hostname_addresses(
    destination_hostnames: dict[str, set[str]], config: dict[str, Any]
) -> set[ipaddress._BaseAddress]:
    """Return addresses whose indexed reverse names match protected suffixes."""
    suffixes = config.get(
        "protected_hostname_suffixes", DEFAULT_PROTECTED_HOSTNAME_SUFFIXES
    )
    if not isinstance(suffixes, list):
        raise BlockerError("protected_hostname_suffixes must be a list")
    protected: set[ipaddress._BaseAddress] = set()
    for raw_address, hostnames in destination_hostnames.items():
        try:
            address = ipaddress.ip_address(raw_address)
        except ValueError:
            continue
        if any(
            hostname_matches_suffix(hostname, suffix)
            for hostname in hostnames
            for suffix in suffixes
        ):
            protected.add(address)
    return protected


def resolve_protected_addresses(config: dict[str, Any]) -> set[ipaddress._BaseAddress]:
    """Resolve configured provider names into addresses excluded from blocking."""
    protected: set[ipaddress._BaseAddress] = set()
    hostnames = config.get("protected_hostnames", DEFAULT_PROTECTED_HOSTNAMES)
    if not isinstance(hostnames, list):
        raise BlockerError("protected_hostnames must be a list")
    for hostname in hostnames:
        try:
            results = socket.getaddrinfo(
                str(hostname), None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM
            )
        except socket.gaierror:
            # A transient DNS failure must not turn a normal policy run into
            # a failure; a later run will resolve the name again.
            continue
        for result in results:
            try:
                protected.add(ipaddress.ip_address(result[4][0]))
            except ValueError:
                continue
    return protected


def classify_blocks(
    destinations: dict[str, set[str]],
    protected_addresses: set[ipaddress._BaseAddress] | None = None,
    allowed_countries: set[str] | None = None,
    protected_hostname_addresses: set[ipaddress._BaseAddress] | None = None,
) -> dict[str, str]:
    """Select canonical addresses that policy requires blocking, once each."""
    blocked: dict[str, str] = {}
    protected_addresses = protected_addresses or set()
    protected_hostname_addresses = protected_hostname_addresses or set()
    allowed_countries = allowed_countries or DEFAULT_ALLOWED_COUNTRIES
    for raw_address, observed_codes in destinations.items():
        try:
            address = ipaddress.ip_address(raw_address)
        except ValueError:
            # Malformed indexed values cannot produce safe nftables elements.
            continue

        comparable = address.ipv4_mapped if isinstance(address, ipaddress.IPv6Address) else address
        if (
            address in protected_addresses
            or comparable in protected_addresses
            or address in protected_hostname_addresses
            or comparable in protected_hostname_addresses
        ):
            continue
        if isinstance(comparable, ipaddress.IPv4Address) and comparable in LOCAL_IPV4_NETWORK:
            continue
        codes = {
            code.upper()
            for code in observed_codes
            if code.isascii() and code.isalpha() and 2 <= len(code) <= 3
        }
        if codes & allowed_countries:
            continue
        # GeoIP can occasionally return multiple observations; a stable joined
        # code preserves that evidence while keeping a deterministic grouping.
        blocked[str(address)] = "+".join(sorted(codes)) if codes else "UNKNOWN"
    return blocked


def load_state(path: Path) -> dict[str, dict[str, str]]:
    """Load and validate the privacy-minimal persistent block inventory."""
    if not path.exists():
        return {}
    document = load_json(path)
    records = document.get("records")
    if document.get("version") != 1 or not isinstance(records, dict):
        raise BlockerError(f"unsupported state format in {path}")
    validated: dict[str, dict[str, str]] = {}
    for raw_address, raw_record in records.items():
        try:
            address = str(ipaddress.ip_address(raw_address))
        except ValueError as exc:
            raise BlockerError(f"invalid address in {path}") from exc
        if not isinstance(raw_record, dict):
            raise BlockerError(f"invalid record in {path}")
        country = str(raw_record.get("country", "UNKNOWN"))
        added = str(raw_record.get("added", ""))
        valid_country = country == "UNKNOWN" or all(
            part.isascii() and part.isalpha() and 2 <= len(part) <= 3
            for part in country.split("+")
        )
        try:
            parsed_added = date.fromisoformat(added)
        except ValueError as exc:
            raise BlockerError(f"invalid added date in {path}") from exc
        if not country or not valid_country or parsed_added.isoformat() != added:
            raise BlockerError(f"incomplete record in {path}")
        validated[address] = {"country": country, "added": added}
    return validated


def atomic_write(path: Path, content: str, mode: int) -> None:
    """Replace persistent state atomically so interruption cannot truncate it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(temporary_name, mode)
        os.replace(temporary_name, path)
    finally:
        if temporary_name:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass


def nft_supports_element_comments(nft_binary: str) -> bool:
    """Ask nftables to parse an isolated element comment without changing state."""
    probe = """table inet labfilter_comment_probe {
    set addresses {
        type ipv4_addr
        elements = { 192.0.2.1 comment \"probe\" }
    }
}
"""
    result = subprocess.run(
        [nft_binary, "--check", "--file", "-"],
        input=probe,
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def render_elements(
    records: dict[str, dict[str, str]], include_comments: bool, *, flush_sets: bool
) -> str:
    """Render deterministic nft commands grouped by GeoIP classification."""
    lines = ["# Managed by labfilter-geo-blocker; manual edits are replaced."]
    if flush_sets:
        lines.extend(
            [
                "flush set bridge labfilter geo_blocked_ipv4",
                "flush set bridge labfilter geo_blocked_ipv6",
            ]
        )
    grouped: dict[str, list[tuple[str, dict[str, str]]]] = {}
    for address, record in records.items():
        grouped.setdefault(record["country"], []).append((address, record))
    for country in sorted(grouped):
        lines.append(f"# Geolocation: {country}")
        for address, record in sorted(
            grouped[country],
            key=lambda item: (
                ipaddress.ip_address(item[0]).version, ipaddress.ip_address(item[0])
            ),
        ):
            family = ipaddress.ip_address(address).version
            comment = f' comment "{country}; added {record["added"]}"' if include_comments else ""
            lines.append(
                f"add element bridge labfilter {SET_NAMES[family]} {{ {address}{comment} }}"
            )
    return "\n".join(lines) + "\n"


def current_set_addresses(nft_binary: str, set_name: str) -> set[str]:
    """Read one live set as JSON so only absent elements are added at runtime."""
    result = subprocess.run(
        [nft_binary, "--json", "list", "set", "bridge", "labfilter", set_name],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise BlockerError(f"cannot inspect nftables set {set_name}: {result.stderr.strip()}")
    try:
        document = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise BlockerError(f"nftables returned invalid JSON for {set_name}") from exc
    addresses: set[str] = set()
    for item in document.get("nftables", []):
        elements = item.get("set", {}).get("elem", []) if isinstance(item, dict) else []
        for element in elements:
            value: Any = element
            if isinstance(value, dict) and "elem" in value:
                value = value["elem"]
            if isinstance(value, dict):
                value = value.get("val")
            try:
                addresses.add(str(ipaddress.ip_address(str(value))))
            except ValueError:
                continue
    return addresses


def apply_missing_elements(
    nft_binary: str,
    records: dict[str, dict[str, str]],
    include_comments: bool,
) -> int:
    """Atomically add only inventory entries absent from the live nftables sets."""
    live = {
        4: current_set_addresses(nft_binary, SET_NAMES[4]),
        6: current_set_addresses(nft_binary, SET_NAMES[6]),
    }
    missing = {
        address: record
        for address, record in records.items()
        if address not in live[ipaddress.ip_address(address).version]
    }
    if not missing:
        return 0
    batch = render_elements(missing, include_comments, flush_sets=False)
    result = subprocess.run(
        [nft_binary, "--file", "-"],
        input=batch,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise BlockerError(f"nftables rejected the dynamic block update: {result.stderr.strip()}")
    return len(missing)


def update_inventory(
    records: dict[str, dict[str, str]], candidates: dict[str, str], added_date: str
) -> int:
    """Add first-seen addresses without changing their original date or group."""
    added = 0
    for address, country in candidates.items():
        if address not in records:
            records[address] = {"country": country, "added": added_date}
            added += 1
    return added


def remove_protected_records(
    records: dict[str, dict[str, str]],
    protected_addresses: set[ipaddress._BaseAddress],
) -> int:
    """Remove previously learned protected addresses before nftables reconciliation."""
    removed = []
    for raw_address in records:
        address = ipaddress.ip_address(raw_address)
        comparable = address.ipv4_mapped if isinstance(address, ipaddress.IPv6Address) else address
        if address in protected_addresses or comparable in protected_addresses:
            removed.append(raw_address)
    for raw_address in removed:
        del records[raw_address]
    return len(removed)


def reconcile_protected_elements(
    nft_binary: str,
    records: dict[str, dict[str, str]],
    include_comments: bool,
) -> int:
    """Replace live sets in one transaction after protected records are removed."""
    # Flushing and restoring in one nft transaction prevents a transient
    # policy gap while removing an address that DNS now identifies as safe.
    batch = render_elements(records, include_comments, flush_sets=True)
    result = subprocess.run(
        [nft_binary, "--file", "-"],
        input=batch,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise BlockerError(
            f"nftables rejected protected-address reconciliation: {result.stderr.strip()}"
        )
    return len(records)


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    """Keep the cron interface small and move machine-specific values to JSON."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", default="/etc/labfilter/geo-blocker.json", type=Path, help="managed JSON config"
    )
    return parser.parse_args(argv)


def configured_countries(config: dict[str, Any]) -> set[str]:
    """Validate the Ansible-managed country allowlist before using it."""
    values = config.get("allowed_countries", sorted(DEFAULT_ALLOWED_COUNTRIES))
    if not isinstance(values, list):
        raise BlockerError("allowed_countries must be a list")
    countries = {str(value).upper() for value in values}
    if not countries or any(
        not country.isascii() or not country.isalpha() or len(country) != 2
        for country in countries
    ):
        raise BlockerError("allowed_countries must contain two-letter ISO country codes")
    return countries


def main(argv: Iterable[str] | None = None) -> int:
    """Serialize the hourly run, update persistence, then update live nftables."""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    config = load_json(args.config)
    required = {
        "elasticsearch_url", "index_pattern", "lookback_hours", "state_file", "include_file"
    }
    missing_config = sorted(required - config.keys())
    if missing_config:
        raise BlockerError(f"missing configuration keys: {', '.join(missing_config)}")

    lock_path = Path(str(config.get("lock_file", "/run/lock/labfilter-geo-blocker.lock")))
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("another geo-blocker run is still active; skipping")
            return 0

        state_path = Path(str(config["state_file"]))
        include_path = Path(str(config["include_file"]))
        nft_binary = str(config.get("nft_binary", "/usr/sbin/nft"))
        destinations, destination_hostnames = query_destinations(config)
        protected_addresses = resolve_protected_addresses(config)
        protected_addresses.update(
            protected_hostname_addresses(destination_hostnames, config)
        )
        candidates = classify_blocks(
            destinations, protected_addresses, configured_countries(config)
        )
        records = load_state(state_path)
        removed = remove_protected_records(records, protected_addresses)
        from datetime import datetime, timezone

        newly_recorded = update_inventory(
            records, candidates, datetime.now(timezone.utc).date().isoformat()
        )
        comments_supported = nft_supports_element_comments(nft_binary)

        # Persist before touching the live set. If the process is interrupted,
        # the next service reload or cron run can still converge safely.
        state_document = (
            json.dumps({"version": 1, "records": records}, indent=2, sort_keys=True)
            + "\n"
        )
        atomic_write(state_path, state_document, 0o640)
        atomic_write(
            include_path,
            render_elements(records, comments_supported, flush_sets=bool(removed)),
            0o640,
        )
        activated = (
            reconcile_protected_elements(nft_binary, records, comments_supported)
            if removed
            else apply_missing_elements(nft_binary, records, comments_supported)
        )

    print(
        f"examined {len(destinations)} unique destinations; "
        f"recorded {newly_recorded} new blocks; activated {activated} missing blocks"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BlockerError, KeyError, TypeError, ValueError) as exc:
        print(f"labfilter-geo-blocker: {exc}", file=sys.stderr)
        raise SystemExit(1)
