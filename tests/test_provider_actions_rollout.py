import base64
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).parents[1]
TOOL = ROOT / "scripts/provider_actions_rollout.py"


def run_tool(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def write_json(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def response(status: int, *, release: str | None = None, region: str | None = None,
             provider: int | None = None, body: str = "", location: str | None = None,
             content_type: str = "text/html; charset=utf-8", robots: str = "noindex"):
    headers = {
        "Cache-Control": "no-store",
        "Content-Security-Policy": "default-src 'none'",
        "Content-Type": content_type,
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-Robots-Tag": robots,
    }
    if release is not None:
        headers["X-Seasons-Provider-Actions-Release"] = release
    if region is not None:
        headers["X-Seasons-Provider-Actions-Region"] = region
    if provider is not None:
        headers["X-Seasons-Provider-Actions-Provider"] = str(provider)
    if location is not None:
        headers["Location"] = location
    return {
        "status": status,
        "headers": headers,
        "bodyBase64": base64.b64encode(body.encode()).decode(),
    }


def sealed_release() -> dict[str, object]:
    release = {
        "schemaVersion": 3,
        "releaseId": "release-7",
        "sourceSnapshotId": "snapshot-7",
        "sourcePairAccountingSha256": "a" * 64,
        "publicSupportedPairs": [["GB", 8], ["GB", 9], ["GB", 10]],
        "retainedAnomalyPairs": [],
        "publishedGuides": [
            {
                "region": "GB",
                "tmdbProviderId": 8,
                "providerDisplayName": "Netflix",
                "countryDisplayName": "United Kingdom",
                "sourceTitle": "Netflix help",
                "sourceUrl": "https://help.netflix.com/cancel",
                "verifiedAt": "2026-09-01T00:00:00Z",
                "staleAt": "2026-10-01T00:00:00Z",
                "orderedSteps": ["Open settings", "Finish cancellation"],
                "warnings": [],
            },
            {
                "region": "GB",
                "tmdbProviderId": 9,
                "providerDisplayName": "Old service",
                "countryDisplayName": "United Kingdom",
                "sourceTitle": "Old help",
                "sourceUrl": "https://example.com/old",
                "verifiedAt": "2026-07-01T00:00:00Z",
                "staleAt": "2026-08-01T00:00:00Z",
                "orderedSteps": ["OLD SECRET STEP"],
                "warnings": [],
            },
        ],
        "startDestinations": {"8": "https://www.netflix.com/"},
    }
    release["sealSha256"] = hashlib.sha256(
        json.dumps(release, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    return release


def minimal_readback_case(temporary: Path):
    release = {
        "schemaVersion": 2,
        "releaseId": "safe-release",
        "sourceSnapshotId": "snapshot",
        "sourcePairAccountingSha256": "b" * 64,
        "publicSupportedPairs": [["GB", 8]],
        "retainedAnomalyPairs": [],
        "publishedGuides": [],
        "startDestinations": {"8": "https://www.netflix.com/"},
    }
    release["sealSha256"] = hashlib.sha256(
        json.dumps(release, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    release_path = write_json(temporary / "safe-release.json", release)
    origin = "https://getseasons.app"
    responses = {
        f"{origin}/provider-actions/cancel/8/GB/": response(
            200, release="safe-release", region="GB", provider=8
        ),
        f"{origin}/provider-actions/start/8/GB/": response(
            302,
            release="safe-release",
            region="GB",
            provider=8,
            location="https://www.netflix.com/",
        ),
        f"{origin}/provider-actions/sitemap.xml": response(
            200,
            release="safe-release",
            body='<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>',
            content_type="application/xml; charset=utf-8",
        ),
    }
    for path, status in {
        "/provider-actions/cancel/999999/ZZ/": 404,
        "/provider-actions/cancel/8/gb/": 400,
        "/provider-actions/cancel/08/GB/": 404,
        "/provider-actions/cancel/8/GB/?context=invalid": 400,
        "/provider-actions/sitemap.xml?context=invalid": 400,
    }.items():
        responses[f"{origin}{path}"] = response(status, release="safe-release")
    plan = write_json(
        temporary / "readback.json",
        {
            "schemaVersion": 1,
            "canonicalOrigin": origin,
            "release": str(release_path),
            "at": "2026-09-04T00:00:00Z",
            "switchCases": [],
            "unrelatedPages": [],
        },
    )
    fixture = write_json(temporary / "responses.json", responses)
    return plan, fixture, responses


class ProviderActionsRolloutTests(unittest.TestCase):
    def test_capture_pins_canonical_json_without_copying_source_values(self):
        with TemporaryDirectory() as directory:
            temporary = Path(directory)
            routes = write_json(
                temporary / "routes.json", {"routes": ["one", "two"]}
            )
            plan = write_json(
                temporary / "control.json",
                {
                    "schemaVersion": 1,
                    "sources": [
                        {"name": "cloudflare-routes", "input": str(routes)}
                    ],
                },
            )
            output = temporary / "pin.json"

            result = run_tool("capture", "--plan", str(plan), "--output", str(output))

            self.assertEqual(result.returncode, 0, result.stderr)
            evidence = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(evidence["schemaVersion"], 1)
            self.assertEqual(evidence["kind"], "provider-actions-control-pin")
            self.assertEqual(
                evidence["sources"],
                [
                    {
                        "name": "cloudflare-routes",
                        "sha256": "c4953897dd65ebf3ed5a2736517c3eb7c5711f3d01f74724ea9fccf845381d58",
                    }
                ],
            )
            self.assertNotIn('"one"', output.read_text(encoding="utf-8"))
            self.assertNotIn('"two"', output.read_text(encoding="utf-8"))
            self.assertEqual(result.stdout, "")

    def test_activate_rejects_changed_state_without_running_command(self):
        with TemporaryDirectory() as directory:
            temporary = Path(directory)
            state = write_json(temporary / "state.json", {"version": "one"})
            marker = temporary / "activated"
            plan = write_json(
                temporary / "control.json",
                {
                    "schemaVersion": 1,
                    "sources": [{"name": "worker", "input": str(state)}],
                    "activationCommand": [
                        sys.executable,
                        "-c",
                        f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')",
                    ],
                },
            )
            pin = temporary / "pin.json"
            capture_result = run_tool(
                "capture", "--plan", str(plan), "--output", str(pin)
            )
            self.assertEqual(capture_result.returncode, 0, capture_result.stderr)
            write_json(state, {"version": "two"})

            result = run_tool(
                "activate",
                "--plan",
                str(plan),
                "--pin",
                str(pin),
                "--output",
                str(temporary / "activation.json"),
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("worker changed", result.stderr)
            self.assertNotIn("two", result.stderr)
            self.assertFalse(marker.exists())

    def test_verify_exhaustive_matrix_and_emit_hashed_evidence(self):
        with TemporaryDirectory() as directory:
            temporary = Path(directory)
            release_path = write_json(temporary / "release.json", sealed_release())
            origin = "https://getseasons.app"
            responses = {}
            for provider in (8, 9, 10):
                cancel_body = "Cancellation instructions are not yet published"
                robots = "noindex"
                if provider == 8:
                    cancel_body = (
                        "Open settings Finish cancellation "
                        "https://help.netflix.com/cancel"
                    )
                    robots = "index"
                elif provider == 9:
                    cancel_body = "Verified cancellation instructions have expired"
                responses[f"{origin}/provider-actions/cancel/{provider}/GB/"] = response(
                    200,
                    release="release-7",
                    region="GB",
                    provider=provider,
                    body=cancel_body,
                    robots=robots,
                )
                responses[f"{origin}/provider-actions/start/{provider}/GB/"] = response(
                    302 if provider == 8 else 200,
                    release="release-7",
                    region="GB",
                    provider=provider,
                    location="https://www.netflix.com/" if provider == 8 else None,
                )
            responses[f"{origin}/provider-actions/sitemap.xml"] = response(
                200,
                release="release-7",
                body=(
                    '<?xml version="1.0"?><urlset>'
                    "<url><loc>https://getseasons.app/provider-actions/cancel/8/GB/</loc></url>"
                    "</urlset>"
                ),
                content_type="application/xml; charset=utf-8",
            )
            for path, status in {
                "/provider-actions/cancel/999999/ZZ/": 404,
                "/provider-actions/cancel/8/gb/": 400,
                "/provider-actions/cancel/08/GB/": 404,
                "/provider-actions/cancel/8/GB/?context=invalid": 400,
                "/provider-actions/sitemap.xml?context=invalid": 400,
            }.items():
                responses[f"{origin}{path}"] = response(status, release="release-7")
            page_body = "unchanged landing page"
            responses[f"{origin}/privacy"] = response(200, body=page_body)
            fixture = write_json(temporary / "responses.json", responses)
            plan = write_json(
                temporary / "readback.json",
                {
                    "schemaVersion": 1,
                    "canonicalOrigin": origin,
                    "release": str(release_path),
                    "at": "2026-09-04T00:00:00Z",
                    "switchCases": [
                        {
                            "name": "netflix-to-provider-9",
                            "paths": [
                                "/provider-actions/cancel/8/GB/",
                                "/provider-actions/start/9/GB/",
                            ],
                        }
                    ],
                    "unrelatedPages": [
                        {
                            "url": f"{origin}/privacy",
                            "sha256": hashlib.sha256(page_body.encode()).hexdigest(),
                        }
                    ],
                },
            )
            output = temporary / "evidence.json"

            result = run_tool(
                "verify",
                "--phase",
                "production",
                "--concurrency",
                "3",
                "--request-timeout",
                "7.5",
                "--plan",
                str(plan),
                "--responses",
                str(fixture),
                "--output",
                str(output),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            evidence = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(evidence["phase"], "production")
            self.assertEqual(evidence["releaseId"], "release-7")
            self.assertEqual(evidence["verifiedActionPairs"], 3)
            self.assertEqual(evidence["verifiedActionResponses"], 6)
            self.assertEqual(evidence["concurrency"], 3)
            self.assertEqual(evidence["requestTimeoutSeconds"], 7.5)
            self.assertEqual(evidence["invalidChecks"], 5)
            self.assertEqual(evidence["switchCases"], ["netflix-to-provider-9"])
            self.assertEqual(evidence["unrelatedPages"][0]["sha256"], hashlib.sha256(page_body.encode()).hexdigest())
            self.assertRegex(evidence["evidenceSha256"], r"^[0-9a-f]{64}$")
            self.assertNotIn("OLD SECRET STEP", output.read_text(encoding="utf-8"))

    def test_verify_fails_closed_when_pair_identity_is_missing(self):
        with TemporaryDirectory() as directory:
            temporary = Path(directory)
            plan, fixture, responses = minimal_readback_case(temporary)
            url = "https://getseasons.app/provider-actions/start/8/GB/"
            del responses[url]["headers"]["X-Seasons-Provider-Actions-Provider"]
            write_json(fixture, responses)
            output = temporary / "evidence.json"

            result = run_tool(
                "verify",
                "--phase",
                "production",
                "--plan",
                str(plan),
                "--responses",
                str(fixture),
                "--output",
                str(output),
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("provider identity did not match", result.stderr)
            self.assertFalse(output.exists())

    def test_verify_rejects_wrong_sitemap_media_type(self):
        with TemporaryDirectory() as directory:
            temporary = Path(directory)
            plan, fixture, responses = minimal_readback_case(temporary)
            url = "https://getseasons.app/provider-actions/sitemap.xml"
            responses[url]["headers"]["Content-Type"] = "text/html; charset=utf-8"
            write_json(fixture, responses)
            output = temporary / "evidence.json"

            result = run_tool(
                "verify",
                "--phase",
                "production",
                "--plan",
                str(plan),
                "--responses",
                str(fixture),
                "--output",
                str(output),
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("content type did not match", result.stderr)
            self.assertFalse(output.exists())

    def test_rollback_phase_requires_and_verifies_restored_control_pin(self):
        with TemporaryDirectory() as directory:
            temporary = Path(directory)
            plan, fixture, _ = minimal_readback_case(temporary)
            state = write_json(temporary / "state.json", {"workerVersion": "safe"})
            control = write_json(
                temporary / "control.json",
                {
                    "schemaVersion": 1,
                    "sources": [{"name": "worker", "input": str(state)}],
                },
            )
            pin = temporary / "rollback-pin.json"
            captured = run_tool(
                "capture", "--plan", str(control), "--output", str(pin)
            )
            self.assertEqual(captured.returncode, 0, captured.stderr)
            output = temporary / "rollback-evidence.json"

            result = run_tool(
                "verify",
                "--phase",
                "rollback",
                "--plan",
                str(plan),
                "--responses",
                str(fixture),
                "--control-plan",
                str(control),
                "--control-pin",
                str(pin),
                "--output",
                str(output),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            evidence = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(evidence["phase"], "rollback")
            self.assertRegex(evidence["controlPinSha256"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
