"""Focused policy tests for the Ansible-deployed GeoIP blocker."""

import importlib.util
from pathlib import Path
import unittest


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
            "203.0.113.10": {"GB"},
            "2001:db8::10": {"DE"},
            "10.0.0.8": set(),
            "not-an-address": {"FR"},
        }

        self.assertEqual(
            blocker.classify_blocks(destinations),
            {
                "203.0.113.10": "GB",
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
            "203.0.113.1": {"country": "GB", "added": "2026-10-01"},
        }

        rendered = blocker.render_elements(records, include_comments=True, flush_sets=False)

        self.assertIn("# Geolocation: DE", rendered)
        self.assertIn("# Geolocation: GB", rendered)
        self.assertIn('2001:db8::1 comment "DE; added 2026-10-02"', rendered)
        self.assertIn('203.0.113.1 comment "GB; added 2026-10-01"', rendered)


if __name__ == "__main__":
    unittest.main()
