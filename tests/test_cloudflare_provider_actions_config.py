from __future__ import annotations

import tomllib
import unittest
from pathlib import Path


CONFIGURATION_DIRECTORY = (
    Path(__file__).parents[1] / "cloudflare" / "provider-actions"
)
SEASONS_CLOUDFLARE_ACCOUNT_ID = "48039421df9478545ee479d6272049da"
PRODUCTION_ROUTES = [
    {
        "pattern": "getseasons.app/provider-actions",
        "zone_name": "getseasons.app",
    },
    {
        "pattern": "getseasons.app/provider-actions/*",
        "zone_name": "getseasons.app",
    },
]


def load_configuration(name: str) -> dict:
    with (CONFIGURATION_DIRECTORY / name).open("rb") as stream:
        return tomllib.load(stream)


class CloudflareProviderActionsConfigTests(unittest.TestCase):
    def test_every_configuration_pins_the_seasons_cloudflare_account(self) -> None:
        for name in (
            "wrangler.toml",
            "wrangler.safe-baseline.toml",
            "wrangler.staging.toml",
        ):
            with self.subTest(name=name):
                self.assertEqual(
                    load_configuration(name)["account_id"],
                    SEASONS_CLOUDFLARE_ACCOUNT_ID,
                )

    def test_production_and_safe_baseline_bind_only_the_canonical_routes(self) -> None:
        for name in ("wrangler.toml", "wrangler.safe-baseline.toml"):
            with self.subTest(name=name):
                self.assertEqual(load_configuration(name)["routes"], PRODUCTION_ROUTES)

    def test_staging_uses_workers_dev_without_a_zone_route(self) -> None:
        configuration = load_configuration("wrangler.staging.toml")

        self.assertIs(configuration["workers_dev"], True)
        self.assertNotIn("routes", configuration)


if __name__ == "__main__":
    unittest.main()
