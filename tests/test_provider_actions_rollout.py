import base64
import hashlib
import importlib.util
import json
import subprocess
import sys
import unittest
import urllib.error
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
TOOL = ROOT / "scripts/provider_actions_rollout.py"
PRODUCTION_CONFIG = ROOT / "cloudflare/provider-actions/wrangler.toml"
ACCOUNT_ID = "48039421df9478545ee479d6272049da"
PRODUCTION_WORKER = "seasons-provider-actions-router"
REPRESENTATIVE_PATHS = ("/", "/privacy.html", "/terms.html")

SPEC = importlib.util.spec_from_file_location("provider_actions_rollout", TOOL)
assert SPEC is not None and SPEC.loader is not None
ROLLOUT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ROLLOUT)


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


def sealed_evidence(value: dict[str, object]) -> dict[str, object]:
    result = dict(value)
    result["evidenceSha256"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    return result


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
    unrelated_pages = []
    for path in REPRESENTATIVE_PATHS:
        body = f"unchanged page {path}"
        responses[f"{origin}{path}"] = response(200, body=body)
        unrelated_pages.append(
            {
                "url": f"{origin}{path}",
                "sha256": hashlib.sha256(body.encode()).hexdigest(),
            }
        )
    plan = write_json(
        temporary / "readback.json",
        {
            "schemaVersion": 1,
            "canonicalOrigin": origin,
            "release": str(release_path),
            "at": "2026-09-04T00:00:00Z",
            "switchCases": [],
            "unrelatedPages": unrelated_pages,
        },
    )
    fixture = write_json(temporary / "responses.json", responses)
    return plan, fixture, responses


class ProviderActionsRolloutTests(unittest.TestCase):
    def test_post_deploy_worker_must_be_proxy_mode(self):
        sources = [
            {"name": "account", "type": "cloudflare-account"},
            {"name": "zone", "type": "cloudflare-zone"},
            {"name": "routes", "type": "cloudflare-routes"},
            {"name": "worker", "type": "cloudflare-worker"},
        ]
        values = {
            "account": {"id": ACCOUNT_ID},
            "zone": {"name": "getseasons.app", "accountId": ACCOUNT_ID},
            "routes": {
                "routes": [
                    {"pattern": pattern, "script": worker}
                    for pattern, worker in ROLLOUT.PRODUCTION_ROUTES
                ]
            },
            "worker": {
                "name": PRODUCTION_WORKER,
                "versionId": "deployed-version",
                "mode": "safe-baseline",
            },
        }

        with self.assertRaisesRegex(ROLLOUT.RolloutError, "Worker identity"):
            ROLLOUT.validate_activation_sources(
                sources, values, after_activation=True
            )

    def test_cloudflare_worker_not_found_normalizes_as_absent(self):
        missing = urllib.error.HTTPError(
            "https://api.cloudflare.invalid/worker", 404, "Not Found", None, None
        )
        with patch.object(ROLLOUT.urllib.request, "urlopen", side_effect=missing):
            value = ROLLOUT.cloudflare_api_get(
                "/worker", "DO NOT COPY", allow_not_found=True
            )
        missing.close()

        self.assertIs(value, ROLLOUT.CLOUDFLARE_NOT_FOUND)

    def test_cloudflare_worker_rejects_empty_split_and_malformed_deployments(self):
        identity = {
            "account": {"result": {"id": ACCOUNT_ID}},
            "zone": {
                "result": [
                    {
                        "id": "zone-id",
                        "name": "getseasons.app",
                        "account": {"id": ACCOUNT_ID},
                    }
                ]
            },
            "settings": {"result": {"bindings": []}},
        }
        invalid = (
            {"result": {"deployments": []}},
            {
                "result": {
                    "deployments": [
                        {
                            "versions": [
                                {"version_id": "one", "percentage": 50},
                                {"version_id": "two", "percentage": 50},
                            ]
                        }
                    ]
                }
            },
            {"result": {"deployments": [{"versions": "broken"}]}},
        )

        for deployments in invalid:
            with self.subTest(deployments=deployments):
                with self.assertRaises(ROLLOUT.RolloutError):
                    ROLLOUT.normalize_cloudflare_state(
                        "worker", {**identity, "deployments": deployments}
                    )

    def test_cloudflare_state_normalizes_api_responses_without_secrets(self):
        with TemporaryDirectory() as directory:
            temporary = Path(directory)
            fixture = write_json(
                temporary / "cloudflare.json",
                {
                    "account": {"result": {"id": ACCOUNT_ID, "name": "MYV Studios", "secret": "DO NOT COPY"}},
                    "zone": {"result": [{"id": "zone-id", "name": "getseasons.app", "account": {"id": ACCOUNT_ID}}]},
                    "routes": {"result": [{"pattern": "getseasons.app/provider-actions", "script": PRODUCTION_WORKER}, {"pattern": "getseasons.app/provider-actions/*", "script": PRODUCTION_WORKER}]},
                    "deployments": {"result": {"deployments": [{"versions": [{"version_id": "version-7", "percentage": 100}]}]}},
                    "settings": {"result": {"bindings": [{"name": "SEASONS_PROVIDER_ACTIONS_MODE", "type": "plain_text", "text": "proxy"}]}},
                },
            )

            values = {}
            for kind in ("account", "zone", "routes", "worker"):
                result = run_tool(
                    "cloudflare-state",
                    "--kind",
                    kind,
                    "--responses",
                    str(fixture),
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn("DO NOT COPY", result.stdout)
                values[kind] = json.loads(result.stdout)

            self.assertEqual(values["account"], {"id": ACCOUNT_ID})
            self.assertEqual(values["zone"], {"name": "getseasons.app", "accountId": ACCOUNT_ID})
            self.assertEqual(len(values["routes"]["routes"]), 2)
            self.assertEqual(values["worker"], {"name": PRODUCTION_WORKER, "versionId": "version-7", "mode": "proxy"})

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

    def test_activate_proves_typed_identity_and_expected_worker_transition(self):
        with TemporaryDirectory() as directory:
            temporary = Path(directory)
            predecessor_sha = "3" * 64
            target_sha = "2" * 64
            seal_sha = "1" * 64
            image = f"sha256:{'4' * 64}"
            deployed_sha = "5" * 40
            pages_sha = "6" * 40
            page_hashes = {
                f"https://getseasons.app{path}": str(index) * 64
                for index, path in enumerate(REPRESENTATIVE_PATHS, start=7)
            }
            account = write_json(temporary / "account.json", {"id": ACCOUNT_ID})
            zone = write_json(
                temporary / "zone.json",
                {"name": "getseasons.app", "accountId": ACCOUNT_ID},
            )
            routes = write_json(
                temporary / "routes.json",
                {"routes": []},
            )
            worker = write_json(
                temporary / "worker.json",
                {"name": PRODUCTION_WORKER, "versionId": None, "mode": None},
            )
            after_worker = {
                "name": PRODUCTION_WORKER,
                "versionId": "after",
                "mode": "proxy",
            }
            after_routes = {
                "routes": [
                    {
                        "pattern": "getseasons.app/provider-actions",
                        "script": PRODUCTION_WORKER,
                    },
                    {
                        "pattern": "getseasons.app/provider-actions/*",
                        "script": PRODUCTION_WORKER,
                    },
                ]
            }
            staging = write_json(
                temporary / "staging.json",
                sealed_evidence({
                    "kind": "provider-actions-readback",
                    "transport": "live",
                    "phase": "staging",
                    "canonicalOrigin": "https://seasons-provider-actions-router-staging.teomatteo89.workers.dev",
                    "releaseId": "release-7",
                    "releaseSealSha256": seal_sha,
                }),
            )
            backend = write_json(
                temporary / "backend.json",
                {
                    "app": "seasons-backend",
                    "activeReleaseId": "safe-release",
                    "artifactSha256": predecessor_sha,
                },
            )
            fly_state = write_json(
                temporary / "fly.json",
                {
                    "app": "seasons-backend",
                    "imageDigest": image,
                    "deployedSha": deployed_sha,
                },
            )
            pages = write_json(
                temporary / "pages.json",
                {
                    "deploymentSha": pages_sha,
                    "pageHashes": page_hashes,
                },
            )
            predecessor = write_json(
                temporary / "predecessor.json",
                {
                    "workerVersionId": None,
                    "backendReleaseId": "safe-release",
                    "backendArtifactSha256": predecessor_sha,
                    "flyImageDigest": image,
                    "flyDeployedSha": deployed_sha,
                    "pagesDeploymentSha": pages_sha,
                    "pageHashes": page_hashes,
                    "compatibleTargetReleaseId": "release-7",
                },
            )
            order = temporary / "order"
            fake_npx = temporary / "npx"
            fake_npx.write_text(
                "#!/usr/bin/env python3\n"
                "import json\n"
                "from pathlib import Path\n"
                f"Path({str(worker)!r}).write_text(json.dumps({after_worker!r}))\n"
                f"Path({str(routes)!r}).write_text(json.dumps({after_routes!r}))\n"
                f"Path({str(order)!r}).write_text('worker\\n')\n",
                encoding="utf-8",
            )
            fake_npx.chmod(0o700)
            operator = (
                "python scripts/provider_action_release.py activate "
                f"--expected-release-id safe-release --expected-sha256 {predecessor_sha} "
                f"--target-release-id release-7 --target-sha256 {target_sha}"
            )
            after_backend = {
                "app": "seasons-backend",
                "activeReleaseId": "release-7",
                "artifactSha256": target_sha,
            }
            fake_fly = temporary / "fly"
            fake_fly.write_text(
                "#!/usr/bin/env python3\n"
                "import json\n"
                "from pathlib import Path\n"
                f"Path({str(backend)!r}).write_text(json.dumps({after_backend!r}))\n"
                f"path = Path({str(order)!r})\n"
                "path.write_text(path.read_text() + 'backend\\n')\n",
                encoding="utf-8",
            )
            fake_fly.chmod(0o700)
            config_sha = hashlib.sha256(PRODUCTION_CONFIG.read_bytes()).hexdigest()
            plan = write_json(
                temporary / "control.json",
                {
                    "schemaVersion": 1,
                    "sources": [
                        {
                            "name": "account",
                            "type": "cloudflare-account",
                            "input": str(account),
                        },
                        {
                            "name": "zone",
                            "type": "cloudflare-zone",
                            "input": str(zone),
                        },
                        {
                            "name": "routes",
                            "type": "cloudflare-routes",
                            "input": str(routes),
                        },
                        {
                            "name": "worker",
                            "type": "cloudflare-worker",
                            "input": str(worker),
                        },
                        {
                            "name": "predecessor",
                            "type": "deployment-predecessor",
                            "input": str(predecessor),
                        },
                        {"name": "staging", "type": "staging-readback", "input": str(staging)},
                        {"name": "backend", "type": "backend-release", "input": str(backend)},
                        {"name": "fly", "type": "fly-deployment", "input": str(fly_state)},
                        {"name": "pages", "type": "pages-deployment", "input": str(pages)},
                    ],
                    "productionConfigSha256": config_sha,
                    "activationCommand": [
                        str(fake_npx),
                        "--yes",
                        "wrangler@4.129.0",
                        "deploy",
                        "--config",
                        str(PRODUCTION_CONFIG),
                        "--name",
                        PRODUCTION_WORKER,
                    ],
                    "backendActivationCommand": [
                        str(fake_fly),
                        "ssh",
                        "console",
                        "-a",
                        "seasons-backend",
                        "-C",
                        operator,
                    ],
                    "activationTarget": {
                        "releaseId": "release-7",
                        "releaseSealSha256": seal_sha,
                        "artifactSha256": target_sha,
                        "flyImageDigest": image,
                        "flyDeployedSha": deployed_sha,
                        "pagesDeploymentSha": pages_sha,
                        "pageHashes": page_hashes,
                    },
                },
            )
            pin = temporary / "pin.json"
            self.assertEqual(
                run_tool("capture", "--plan", str(plan), "--output", str(pin)).returncode,
                0,
            )
            output = temporary / "activation.json"

            result = run_tool(
                "activate",
                "--plan",
                str(plan),
                "--pin",
                str(pin),
                "--output",
                str(output),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            evidence = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(evidence["status"], "verified")
            self.assertEqual(evidence["releaseId"], "release-7")
            self.assertEqual(order.read_text(), "worker\nbackend\n")

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
            page_bodies = {
                path: f"unchanged landing page {path}"
                for path in REPRESENTATIVE_PATHS
            }
            for path, body in page_bodies.items():
                responses[f"{origin}{path}"] = response(200, body=body)
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
                            "url": f"{origin}{path}",
                            "sha256": hashlib.sha256(body.encode()).hexdigest(),
                        }
                        for path, body in page_bodies.items()
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
            self.assertEqual(evidence["kind"], "provider-actions-readback-fixture")
            self.assertEqual(evidence["transport"], "fixture")
            self.assertEqual(evidence["phase"], "production")
            self.assertEqual(evidence["releaseId"], "release-7")
            self.assertEqual(evidence["verifiedActionPairs"], 3)
            self.assertEqual(evidence["verifiedActionResponses"], 6)
            self.assertEqual(evidence["concurrency"], 3)
            self.assertEqual(evidence["requestTimeoutSeconds"], 7.5)
            self.assertEqual(evidence["invalidChecks"], 5)
            self.assertEqual(evidence["switchCases"], ["netflix-to-provider-9"])
            self.assertEqual(len(evidence["unrelatedPages"]), 3)
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

    def test_production_requires_the_fixed_unrelated_pages_allowlist(self):
        with TemporaryDirectory() as directory:
            temporary = Path(directory)
            plan, fixture, _ = minimal_readback_case(temporary)
            plan_value = json.loads(plan.read_text(encoding="utf-8"))
            plan_value["unrelatedPages"] = []
            write_json(plan, plan_value)
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
            self.assertIn("fixed unrelated Pages allowlist", result.stderr)
            self.assertFalse(output.exists())

    def test_staging_accepts_only_the_route_free_seasons_worker_origin(self):
        with TemporaryDirectory() as directory:
            temporary = Path(directory)
            plan, fixture, responses = minimal_readback_case(temporary)
            staging_origin = (
                "https://seasons-provider-actions-router-staging."
                "teomatteo89.workers.dev"
            )
            production_origin = "https://getseasons.app"
            staged_responses = {
                url.replace(production_origin, staging_origin, 1): value
                for url, value in responses.items()
            }
            write_json(fixture, staged_responses)
            plan_value = json.loads(plan.read_text(encoding="utf-8"))
            plan_value["canonicalOrigin"] = staging_origin
            plan_value["unrelatedPages"] = []
            write_json(plan, plan_value)
            output = temporary / "staging-evidence.json"

            result = run_tool(
                "verify",
                "--phase",
                "staging",
                "--plan",
                str(plan),
                "--responses",
                str(fixture),
                "--output",
                str(output),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            evidence = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(evidence["phase"], "staging")
            self.assertTrue(
                all(
                    item["url"].startswith(staging_origin)
                    for item in evidence["observations"]
                )
            )

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

    def test_safe_baseline_rollback_rejects_fixture_before_mutation(self):
        with TemporaryDirectory() as directory:
            temporary = Path(directory)
            plan, fixture, _ = minimal_readback_case(temporary)
            origin = "https://getseasons.app"
            action_paths = [
                "/provider-actions",
                "/provider-actions/",
                "/provider-actions/cancel/8/GB/",
                "/provider-actions/start/8/GB/",
                "/provider-actions/sitemap.xml",
                "/provider-actions/cancel/999999/ZZ/",
                "/provider-actions/cancel/8/gb/",
                "/provider-actions/cancel/08/GB/",
                "/provider-actions/cancel/8/GB/?context=invalid",
                "/provider-actions/sitemap.xml?context=invalid",
            ]
            responses = {
                f"{origin}{path}": response(
                    503,
                    body="Provider Actions are temporarily unavailable",
                )
                for path in action_paths
            }
            page_bodies = {
                path: f"unchanged rollback page {path}"
                for path in REPRESENTATIVE_PATHS
            }
            for path, body in page_bodies.items():
                responses[f"{origin}{path}"] = response(200, body=body)
            write_json(fixture, responses)
            plan_value = json.loads(plan.read_text(encoding="utf-8"))
            plan_value["rollbackProfile"] = "safe-baseline"
            plan_value["unrelatedPages"] = [
                {
                    "url": f"{origin}{path}",
                    "sha256": hashlib.sha256(body.encode()).hexdigest(),
                }
                for path, body in page_bodies.items()
            ]
            write_json(plan, plan_value)
            account = write_json(temporary / "account.json", {"id": ACCOUNT_ID})
            zone = write_json(
                temporary / "zone.json",
                {"name": "getseasons.app", "accountId": ACCOUNT_ID},
            )
            routes = write_json(
                temporary / "routes.json",
                {
                    "routes": [
                        {"pattern": pattern, "script": worker_name}
                        for pattern, worker_name in (
                            ("getseasons.app/provider-actions", PRODUCTION_WORKER),
                            ("getseasons.app/provider-actions/*", PRODUCTION_WORKER),
                        )
                    ]
                },
            )
            worker = write_json(
                temporary / "worker.json",
                {"name": PRODUCTION_WORKER, "versionId": "candidate", "mode": "proxy"},
            )
            safe_worker = {
                "name": PRODUCTION_WORKER,
                "versionId": "safe-version",
                "mode": "safe-baseline",
            }
            fake_npx = temporary / "npx"
            fake_npx.write_text(
                "#!/usr/bin/env python3\n"
                "import json\n"
                "from pathlib import Path\n"
                f"Path({str(worker)!r}).write_text(json.dumps({safe_worker!r}))\n",
                encoding="utf-8",
            )
            fake_npx.chmod(0o700)
            control = write_json(
                temporary / "control.json",
                {
                    "schemaVersion": 1,
                    "sources": [
                        {"name": "account", "type": "cloudflare-account", "input": str(account)},
                        {"name": "zone", "type": "cloudflare-zone", "input": str(zone)},
                        {"name": "routes", "type": "cloudflare-routes", "input": str(routes)},
                        {"name": "worker", "type": "cloudflare-worker", "input": str(worker)},
                    ],
                    "rollbackCommand": [
                        str(fake_npx),
                        "--yes",
                        "wrangler@4.129.0",
                        "deploy",
                        "--config",
                        str(ROOT / "cloudflare/provider-actions/wrangler.safe-baseline.toml"),
                        "--name",
                        PRODUCTION_WORKER,
                    ],
                    "rollbackConfigSha256": hashlib.sha256(
                        (ROOT / "cloudflare/provider-actions/wrangler.safe-baseline.toml").read_bytes()
                    ).hexdigest(),
                },
            )
            pin = temporary / "pin.json"
            self.assertEqual(
                run_tool(
                    "capture", "--plan", str(control), "--output", str(pin)
                ).returncode,
                0,
            )
            output = temporary / "rollback-safe-evidence.json"

            result = run_tool(
                "rollback",
                "--profile",
                "safe-baseline",
                "--responses",
                str(fixture),
                "--control-plan",
                str(control),
                "--current-pin",
                str(pin),
                "--readback-plan",
                str(plan),
                "--output",
                str(output),
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("live canonical readback", result.stderr)
            self.assertEqual(
                json.loads(worker.read_text(encoding="utf-8"))["versionId"],
                "candidate",
            )
            self.assertFalse(output.exists())

    def test_normal_rollback_restores_pinned_worker_and_runs_readback(self):
        with TemporaryDirectory() as directory:
            temporary = Path(directory)
            readback_plan, _, _ = minimal_readback_case(temporary)
            candidate_sha, predecessor_sha = "1" * 64, "2" * 64
            seal_sha = "3" * 64
            image, deployed_sha, pages_sha = f"sha256:{'4' * 64}", "5" * 40, "6" * 40
            page_hashes = {
                f"https://getseasons.app{path}": str(index) * 64
                for index, path in enumerate(REPRESENTATIVE_PATHS, start=7)
            }
            account = write_json(temporary / "account.json", {"id": ACCOUNT_ID})
            zone = write_json(
                temporary / "zone.json",
                {"name": "getseasons.app", "accountId": ACCOUNT_ID},
            )
            routes = write_json(
                temporary / "routes.json",
                {
                    "routes": [
                        {"pattern": pattern, "script": worker}
                        for pattern, worker in (
                            (
                                "getseasons.app/provider-actions",
                                PRODUCTION_WORKER,
                            ),
                            (
                                "getseasons.app/provider-actions/*",
                                PRODUCTION_WORKER,
                            ),
                        )
                    ]
                },
            )
            worker = write_json(
                temporary / "worker.json",
                {"name": PRODUCTION_WORKER, "versionId": "candidate", "mode": "proxy"},
            )
            backend = write_json(temporary / "backend.json", {"app": "seasons-backend", "activeReleaseId": "release-7", "artifactSha256": candidate_sha})
            staging = write_json(temporary / "staging.json", sealed_evidence({"kind": "provider-actions-readback", "transport": "live", "phase": "staging", "canonicalOrigin": "https://seasons-provider-actions-router-staging.teomatteo89.workers.dev", "releaseId": "release-7", "releaseSealSha256": seal_sha}))
            fly_state = write_json(temporary / "fly.json", {"app": "seasons-backend", "imageDigest": image, "deployedSha": deployed_sha})
            pages = write_json(temporary / "pages.json", {"deploymentSha": pages_sha, "pageHashes": page_hashes})
            predecessor = write_json(
                temporary / "predecessor.json", {"workerVersionId": "predecessor-version", "backendReleaseId": "safe-release", "backendArtifactSha256": predecessor_sha, "flyImageDigest": image, "flyDeployedSha": deployed_sha, "pagesDeploymentSha": pages_sha, "pageHashes": page_hashes, "compatibleTargetReleaseId": "release-7"}
            )
            order = temporary / "order"
            fake_npx = temporary / "npx"
            restored_worker = {
                "name": PRODUCTION_WORKER,
                "versionId": "predecessor-version",
                "mode": "proxy",
            }
            fake_npx.write_text(
                "#!/usr/bin/env python3\n"
                "import json\n"
                "from pathlib import Path\n"
                f"Path({str(worker)!r}).write_text(json.dumps({restored_worker!r}))\n"
                f"path = Path({str(order)!r})\n"
                "path.write_text(path.read_text() + 'worker\\n')\n",
                encoding="utf-8",
            )
            fake_npx.chmod(0o700)
            restored_backend = {"app": "seasons-backend", "activeReleaseId": "safe-release", "artifactSha256": predecessor_sha}
            fake_fly = temporary / "fly"
            fake_fly.write_text("#!/usr/bin/env python3\nimport json\nfrom pathlib import Path\n" f"Path({str(backend)!r}).write_text(json.dumps({restored_backend!r}))\n" f"Path({str(order)!r}).write_text('backend\\n')\n", encoding="utf-8")
            fake_fly.chmod(0o700)
            backend_operator = "python scripts/provider_action_release.py rollback " f"--expected-release-id release-7 --expected-sha256 {candidate_sha} " f"--target-release-id safe-release --target-sha256 {predecessor_sha}"
            control = write_json(
                temporary / "control.json",
                {
                    "schemaVersion": 1,
                    "sources": [
                        {"name": "account", "type": "cloudflare-account", "input": str(account)},
                        {"name": "zone", "type": "cloudflare-zone", "input": str(zone)},
                        {"name": "routes", "type": "cloudflare-routes", "input": str(routes)},
                        {"name": "worker", "type": "cloudflare-worker", "input": str(worker)},
                        {"name": "predecessor", "type": "deployment-predecessor", "input": str(predecessor)},
                        {"name": "staging", "type": "staging-readback", "input": str(staging)},
                        {"name": "backend", "type": "backend-release", "input": str(backend)},
                        {"name": "fly", "type": "fly-deployment", "input": str(fly_state)},
                        {"name": "pages", "type": "pages-deployment", "input": str(pages)},
                    ],
                    "rollbackCommand": [
                        str(fake_npx),
                        "--yes",
                        "wrangler@4.129.0",
                        "rollback",
                        "predecessor-version",
                        "--config",
                        str(PRODUCTION_CONFIG),
                        "--name",
                        PRODUCTION_WORKER,
                        "--yes",
                    ],
                    "rollbackConfigSha256": hashlib.sha256(
                        PRODUCTION_CONFIG.read_bytes()
                    ).hexdigest(),
                    "backendRollbackCommand": [str(fake_fly), "ssh", "console", "-a", "seasons-backend", "-C", backend_operator],
                    "activationTarget": {"releaseId": "release-7", "releaseSealSha256": seal_sha, "artifactSha256": candidate_sha, "flyImageDigest": image, "flyDeployedSha": deployed_sha, "pagesDeploymentSha": pages_sha, "pageHashes": page_hashes},
                    "rollbackTarget": {"releaseId": "safe-release", "artifactSha256": predecessor_sha, "workerVersionId": "predecessor-version", "workerMode": "proxy"},
                },
            )
            current_pin = temporary / "current-pin.json"
            self.assertEqual(run_tool("capture", "--plan", str(control), "--output", str(current_pin)).returncode, 0)
            write_json(worker, restored_worker)
            write_json(backend, restored_backend)
            target_pin = temporary / "target-pin.json"
            self.assertEqual(run_tool("capture", "--plan", str(control), "--output", str(target_pin)).returncode, 0)
            write_json(
                worker,
                {"name": PRODUCTION_WORKER, "versionId": "candidate", "mode": "proxy"},
            )
            write_json(backend, {"app": "seasons-backend", "activeReleaseId": "release-7", "artifactSha256": candidate_sha})
            output = temporary / "rollback-evidence.json"
            def live_verify(_phase, _plan, responses, evidence_path, *_args):
                self.assertIsNone(responses)
                write_json(evidence_path, {"schemaVersion": 1, "kind": "provider-actions-readback", "transport": "live", "phase": "rollback"})

            authorized_pin = json.loads(target_pin.read_text(encoding="utf-8"))
            unauthorized_pin = json.loads(target_pin.read_text(encoding="utf-8"))
            unauthorized_pin["sources"][0]["sha256"] = "0" * 64
            write_json(target_pin, unauthorized_pin)
            with self.assertRaises(ROLLOUT.RolloutError), patch.object(
                ROLLOUT, "verify", side_effect=live_verify
            ):
                ROLLOUT.rollback("predecessor", control, current_pin, target_pin, readback_plan, None, output, 16, 20.0)
            self.assertFalse(order.exists())
            write_json(target_pin, authorized_pin)
            with patch.object(ROLLOUT, "verify", side_effect=live_verify):
                ROLLOUT.rollback("predecessor", control, current_pin, target_pin, readback_plan, None, output, 16, 20.0)

            evidence = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(evidence["operation"], "rollback-executed")
            self.assertEqual(evidence["rollbackProfile"], "predecessor")
            self.assertEqual(evidence["controlProof"]["workerVersionId"], "predecessor-version")
            self.assertEqual(evidence["transport"], "live")
            self.assertEqual(order.read_text(), "backend\nworker\n")


if __name__ == "__main__":
    unittest.main()
