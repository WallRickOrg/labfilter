"""Focused policy tests for the Ansible-deployed GeoIP blocker."""

import importlib.util
import json
from pathlib import Path
import unittest
from unittest import mock


# Import the executable source directly so the deployed file remains standalone.
SCRIPT = Path(__file__).parents[1] / "ansible/files/labfilter-geo-blocker.py"
SPEC = importlib.util.spec_from_file_location("labfilter_geo_blocker", SCRIPT)
assert SPEC and SPEC.loader
blocker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(blocker)


class GeoBlockPolicyTests(unittest.TestCase):
    """Verify the safety-relevant address and deduplication behavior."""

    def test_classifies_ipv4_ipv6_unknown_and_allowed_destinations(self):
        destinations = {
            "192.168.1.10": set(),
            "198.51.100.1": {"US"},
            "198.51.100.2": {"CA"},
            "203.0.113.10": {"DE"},
            "2001:db8::10": {"DE"},
            "10.0.0.8": set(),
            "not-an-address": {"FR"},
        }

        self.assertEqual(
            blocker.classify_blocks(destinations),
            {
                "203.0.113.10": "DE",
                "2001:db8::10": "DE",
                "10.0.0.8": "UNKNOWN",
            },
        )

    def test_any_us_or_canada_observation_keeps_destination_allowed(self):
        destinations = {
            "198.51.100.20": {"GB", "US"},
            "2001:db8::20": {"CA", "FR"},
        }

        self.assertEqual(blocker.classify_blocks(destinations), {})

    def test_protected_openai_or_codex_address_is_not_blocked(self):
        destinations = {
            "203.0.113.40": {"DE"},
            "2001:db8::40": {"FR"},
        }
        protected = {
            blocker.ipaddress.ip_address("203.0.113.40"),
            blocker.ipaddress.ip_address("2001:db8::40"),
        }
        self.assertEqual(blocker.classify_blocks(destinations, protected), {})

    def test_docker_hostname_suffix_protects_subdomains_only(self):
        hostnames = {
            "203.0.113.40": {"registry-1.docker.io"},
            "203.0.113.41": {"docker.io"},
            "203.0.113.42": {"not-docker.io"},
        }

        protected = blocker.protected_hostname_addresses(
            hostnames, {"protected_hostname_suffixes": [".docker.io"]}
        )

        self.assertEqual(
            protected,
            {
                blocker.ipaddress.ip_address("203.0.113.40"),
                blocker.ipaddress.ip_address("203.0.113.41"),
            },
        )
        self.assertTrue(blocker.hostname_matches_suffix("AUTH.DOCKER.IO.", ".docker.io"))
        self.assertFalse(blocker.hostname_matches_suffix("not-docker.io", ".docker.io"))

    def test_docker_hostname_protection_removes_learned_block(self):
        destinations = {"203.0.113.40": {"DE"}}
        protected = {
            blocker.ipaddress.ip_address("203.0.113.40"),
        }

        self.assertEqual(
            blocker.classify_blocks(
                destinations,
                allowed_countries={"AU", "CA", "GB", "NZ", "US"},
                protected_hostname_addresses=protected,
            ),
            {},
        )

    def test_protected_records_are_removed_for_live_set_reconciliation(self):
        records = {
            "203.0.113.40": {"country": "DE", "added": "2026-09-30"},
            "203.0.113.41": {"country": "DE", "added": "2026-09-30"},
        }
        protected = {blocker.ipaddress.ip_address("203.0.113.40")}
        self.assertEqual(blocker.remove_protected_records(records, protected), 1)
        self.assertNotIn("203.0.113.40", records)
        self.assertIn("203.0.113.41", records)

    def test_inventory_preserves_first_added_metadata_and_uniqueness(self):
        records = {"203.0.113.1": {"country": "GB", "added": "2026-09-30"}}

        added = blocker.update_inventory(
            records,
            {"203.0.113.1": "UNKNOWN", "2001:db8::1": "DE"},
            "2026-10-02",
        )

        self.assertEqual(added, 1)
        self.assertEqual(records["203.0.113.1"], {"country": "GB", "added": "2026-09-30"})
        self.assertEqual(records["2001:db8::1"], {"country": "DE", "added": "2026-10-02"})

    def test_render_groups_locations_and_adds_supported_comments(self):
        records = {
            "2001:db8::1": {"country": "DE", "added": "2026-10-02"},
            "203.0.113.1": {"country": "DE", "added": "2026-10-01"},
        }

        rendered = blocker.render_elements(records, include_comments=True, flush_sets=False)

        self.assertIn("# Geolocation: DE", rendered)
        self.assertIn('2001:db8::1 comment "DE; added 2026-10-02"', rendered)
        self.assertIn('203.0.113.1 comment "DE; added 2026-10-01"', rendered)

    def test_default_safe_country_set_includes_five_eyes(self):
        destinations = {
            "203.0.113.1": {"AU"},
            "203.0.113.2": {"GB"},
            "203.0.113.3": {"NZ"},
            "203.0.113.4": {"US"},
        }

        self.assertEqual(blocker.classify_blocks(destinations), {})

    def test_country_allowlist_can_be_managed_by_configuration(self):
        destinations = {"203.0.113.1": {"DE"}, "203.0.113.2": {"FR"}}

        self.assertEqual(
            blocker.classify_blocks(destinations, allowed_countries={"DE"}),
            {"203.0.113.2": "FR"},
        )

    def test_destination_query_nests_hostname_aggregation_under_composite(self):
        captured = {}

        class FakeResponse:
            """Provide the minimal response interface used by json.load."""

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps(
                    {
                        "aggregations": {
                            "destinations": {
                                "buckets": [],
                            }
                        }
                    }
                ).encode("utf-8")

        def fake_urlopen(http_request, timeout):
            """Capture the request body without contacting Elasticsearch."""
            captured["body"] = json.loads(http_request.data)
            captured["timeout"] = timeout
            return FakeResponse()

        config = {
            "elasticsearch_url": "http://example.invalid:9200",
            "index_pattern": "labfilter-*",
            "lookback_hours": 12,
        }
        with mock.patch.object(blocker.request, "urlopen", fake_urlopen):
            destinations, hostnames = blocker.query_destinations(config)

        composite = captured["body"]["aggs"]["destinations"]
        self.assertIn("composite", composite)
        self.assertIn("hostnames", composite["aggs"])
        self.assertNotIn("hostnames", composite)
        self.assertEqual(destinations, {})
        self.assertEqual(hostnames, {})


if __name__ == "__main__":
    unittest.main()
