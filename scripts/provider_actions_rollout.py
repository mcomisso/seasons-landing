#!/usr/bin/env python3
"""Fail-closed Provider Actions rollout and readback evidence tool."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import tomllib
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit


class RolloutError(Exception):
    """A safe, user-facing rollout failure without command output."""


SAFETY_HEADERS = {
    "cache-control": "no-store",
    "referrer-policy": "no-referrer",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
}
INVALID_PATHS = {
    "unknown-pair": ("/provider-actions/cancel/999999/ZZ/", 404),
    "lowercase-region": ("/provider-actions/cancel/8/gb/", 400),
    "leading-zero-provider": ("/provider-actions/cancel/08/GB/", 404),
    "query-bearing-action": (
        "/provider-actions/cancel/8/GB/?context=invalid",
        400,
    ),
    "query-bearing-sitemap": (
        "/provider-actions/sitemap.xml?context=invalid",
        400,
    ),
}
PRODUCTION_ORIGIN = "https://getseasons.app"
STAGING_ORIGIN = (
    "https://seasons-provider-actions-router-staging.teomatteo89.workers.dev"
)
SEASONS_ACCOUNT_ID = "48039421df9478545ee479d6272049da"
SEASONS_ZONE = "getseasons.app"
PRODUCTION_WORKER = "seasons-provider-actions-router"
PRODUCTION_CONFIG = (
    Path(__file__).parents[1] / "cloudflare/provider-actions/wrangler.toml"
).resolve()
SAFE_BASELINE_CONFIG = (
    Path(__file__).parents[1]
    / "cloudflare/provider-actions/wrangler.safe-baseline.toml"
).resolve()
PRODUCTION_ROUTES = {
    ("getseasons.app/provider-actions", PRODUCTION_WORKER),
    ("getseasons.app/provider-actions/*", PRODUCTION_WORKER),
}
REPRESENTATIVE_PAGES = {
    "https://getseasons.app/family-invite/",
    "https://getseasons.app/account-link.css",
    "https://getseasons.app/seasonslogo.png",
}
CLOUDFLARE_API = "https://api.cloudflare.com/client/v4"
CLOUDFLARE_NOT_FOUND = object()


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RolloutError(f"invalid JSON input: {path.name}") from error


def write_evidence(path: Path, value: object) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical_json(value) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_wrangler_oauth_token() -> str:
    completed = subprocess.run(
        ["npx", "--yes", "wrangler@4.129.0", "whoami"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=60,
    )
    if completed.returncode != 0:
        raise RolloutError("pinned Wrangler authentication check failed")
    candidates = (
        Path.home() / "Library/Preferences/.wrangler/config/default.toml",
        Path.home() / ".wrangler/config/default.toml",
    )
    for path in candidates:
        try:
            value = tomllib.loads(path.read_text(encoding="utf-8")).get("oauth_token")
        except (OSError, UnicodeError, tomllib.TOMLDecodeError):
            continue
        if isinstance(value, str) and value:
            return value
    raise RolloutError("Wrangler OAuth token is unavailable")


def cloudflare_api_get(
    path: str, token: str, *, allow_not_found: bool = False
) -> object:
    request = urllib.request.Request(
        f"{CLOUDFLARE_API}{path}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read(4_194_305))
    except urllib.error.HTTPError as error:
        if allow_not_found and error.code == 404:
            return CLOUDFLARE_NOT_FOUND
        raise RolloutError("Cloudflare control-plane read failed") from error
    except (OSError, UnicodeError, urllib.error.URLError, json.JSONDecodeError) as error:
        raise RolloutError("Cloudflare control-plane read failed") from error
    if (
        not isinstance(payload, dict)
        or payload.get("success") is False
        or "result" not in payload
    ):
        raise RolloutError("Cloudflare control-plane response is invalid")
    return payload


def normalize_cloudflare_state(kind: str, payloads: dict[str, object]) -> object:
    account_payload = payloads.get("account")
    account = account_payload.get("result") if isinstance(account_payload, dict) else None
    if not isinstance(account, dict) or account.get("id") != SEASONS_ACCOUNT_ID:
        raise RolloutError("Cloudflare account identity did not match Seasons")
    if kind == "account":
        return {"id": SEASONS_ACCOUNT_ID}
    zone_payload = payloads.get("zone")
    zones = zone_payload.get("result") if isinstance(zone_payload, dict) else None
    if (
        not isinstance(zones, list)
        or len(zones) != 1
        or not isinstance(zones[0], dict)
        or zones[0].get("name") != SEASONS_ZONE
        or not isinstance(zones[0].get("account"), dict)
        or zones[0]["account"].get("id") != SEASONS_ACCOUNT_ID
    ):
        raise RolloutError("Cloudflare zone identity did not match Seasons")
    if kind == "zone":
        return {"name": SEASONS_ZONE, "accountId": SEASONS_ACCOUNT_ID}
    if kind == "routes":
        route_payload = payloads.get("routes")
        routes = route_payload.get("result") if isinstance(route_payload, dict) else None
        if not isinstance(routes, list) or any(not isinstance(item, dict) for item in routes):
            raise RolloutError("Cloudflare routes response is invalid")
        return {
            "routes": sorted(
                (
                    {"pattern": item.get("pattern"), "script": item.get("script")}
                    for item in routes
                ),
                key=lambda item: str(item["pattern"]),
            )
        }
    deployments_payload = payloads.get("deployments")
    settings_payload = payloads.get("settings")
    if deployments_payload is CLOUDFLARE_NOT_FOUND:
        if settings_payload is not CLOUDFLARE_NOT_FOUND:
            raise RolloutError("Cloudflare Worker absence was inconsistent")
        return {"name": PRODUCTION_WORKER, "versionId": None, "mode": None}
    if settings_payload is CLOUDFLARE_NOT_FOUND:
        raise RolloutError("Cloudflare Worker topology was inconsistent")
    result = (
        deployments_payload.get("result")
        if isinstance(deployments_payload, dict)
        else None
    )
    deployments = result.get("deployments") if isinstance(result, dict) else None
    if (
        not isinstance(deployments, list)
        or not deployments
        or not isinstance(deployments[0], dict)
    ):
        raise RolloutError("Cloudflare Worker deployment topology is invalid")
    versions = (
        deployments[0].get("versions")
        if isinstance(deployments[0].get("versions"), list)
        else []
    )
    if (
        len(versions) != 1
        or not isinstance(versions[0], dict)
        or versions[0].get("percentage") != 100
        or not isinstance(versions[0].get("version_id"), str)
        or not versions[0]["version_id"]
    ):
        raise RolloutError("Cloudflare Worker deployment is not singular")
    version_id = versions[0]["version_id"]
    settings = settings_payload.get("result") if isinstance(settings_payload, dict) else None
    bindings = settings.get("bindings") if isinstance(settings, dict) else []
    mode = next(
        (
            binding.get("text", binding.get("value"))
            for binding in bindings
            if isinstance(binding, dict)
            and binding.get("name") == "SEASONS_PROVIDER_ACTIONS_MODE"
        ),
        None,
    )
    return {"name": PRODUCTION_WORKER, "versionId": version_id, "mode": mode}


def cloudflare_state(kind: str, responses_path: Path | None) -> None:
    if responses_path is not None:
        payloads = read_json(responses_path)
        if not isinstance(payloads, dict):
            raise RolloutError("Cloudflare response fixture is invalid")
    else:
        token = read_wrangler_oauth_token()
        payloads = {
            "account": cloudflare_api_get(
                f"/accounts/{SEASONS_ACCOUNT_ID}", token
            )
        }
        if kind != "account":
            query = urlencode(
                {"name": SEASONS_ZONE, "account.id": SEASONS_ACCOUNT_ID}
            )
            payloads["zone"] = cloudflare_api_get(f"/zones?{query}", token)
        if kind == "routes":
            zone_result = payloads["zone"]
            assert isinstance(zone_result, dict)
            zone_id = zone_result["result"][0]["id"]
            payloads["routes"] = cloudflare_api_get(
                f"/zones/{zone_id}/workers/routes", token
            )
        if kind == "worker":
            prefix = f"/accounts/{SEASONS_ACCOUNT_ID}/workers/scripts/{PRODUCTION_WORKER}"
            payloads["deployments"] = cloudflare_api_get(
                f"{prefix}/deployments", token, allow_not_found=True
            )
            payloads["settings"] = cloudflare_api_get(
                f"{prefix}/settings", token, allow_not_found=True
            )
    value = normalize_cloudflare_state(kind, payloads)
    sys.stdout.buffer.write(canonical_json(value) + b"\n")


def source_value(source: dict[str, object], plan_directory: Path) -> object:
    name = source.get("name")
    if not isinstance(name, str) or not name or any(c.isspace() for c in name):
        raise RolloutError("every control-plane source needs a safe name")
    has_input = "input" in source
    has_command = "command" in source
    if has_input == has_command:
        raise RolloutError(f"source {name} needs exactly one input or command")
    if has_input:
        raw_path = source["input"]
        if not isinstance(raw_path, str) or not raw_path:
            raise RolloutError(f"source {name} has an invalid input")
        path = Path(raw_path)
        if not path.is_absolute():
            path = plan_directory / path
        return read_json(path)
    command = source["command"]
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(part, str) and part for part in command)
    ):
        raise RolloutError(f"source {name} has an invalid command")
    completed = subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        timeout=60,
    )
    if completed.returncode != 0:
        raise RolloutError(
            f"control-plane source {name} failed with exit {completed.returncode}"
        )
    try:
        return json.loads(completed.stdout)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise RolloutError(f"control-plane source {name} returned invalid JSON") from error


def load_control_plan(path: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    value = read_json(path)
    if not isinstance(value, dict) or value.get("schemaVersion") != 1:
        raise RolloutError("unsupported control plan")
    sources = value.get("sources")
    if not isinstance(sources, list) or not sources or not all(
        isinstance(source, dict) for source in sources
    ):
        raise RolloutError("control plan needs sources")
    names = [source.get("name") for source in sources]
    if len(set(names)) != len(names):
        raise RolloutError("control source names must be unique")
    return value, sources


def capture(plan_path: Path, output: Path) -> None:
    _, sources = load_control_plan(plan_path)
    pins = []
    for source in sources:
        value = source_value(source, plan_path.resolve().parent)
        pins.append(
            {
                "name": source["name"],
                "sha256": hashlib.sha256(canonical_json(value)).hexdigest(),
            }
        )
    write_evidence(
        output,
        {
            "schemaVersion": 1,
            "kind": "provider-actions-control-pin",
            "sources": pins,
        },
    )


def control_snapshot(
    sources: list[dict[str, object]], plan_directory: Path
) -> tuple[list[dict[str, str]], dict[str, object]]:
    pins = []
    values = {}
    for source in sources:
        name = str(source["name"])
        value = source_value(source, plan_directory)
        values[name] = value
        pins.append(
            {
                "name": name,
                "sha256": hashlib.sha256(canonical_json(value)).hexdigest(),
            }
        )
    return pins, values


def compare_control_pin(
    plan_path: Path, pin_path: Path
) -> tuple[dict[str, object], list[dict[str, str]], dict[str, object]]:
    _, sources = load_control_plan(plan_path)
    pin = read_json(pin_path)
    if (
        not isinstance(pin, dict)
        or pin.get("schemaVersion") != 1
        or pin.get("kind") != "provider-actions-control-pin"
        or not isinstance(pin.get("sources"), list)
    ):
        raise RolloutError("invalid control pin")
    expected = {
        item.get("name"): item.get("sha256")
        for item in pin["sources"]
        if isinstance(item, dict)
    }
    observed, values = control_snapshot(sources, plan_path.resolve().parent)
    if set(expected) != {item["name"] for item in observed}:
        raise RolloutError("control pin source set changed")
    for item in observed:
        if expected[item["name"]] != item["sha256"]:
            raise RolloutError(f"control-plane source {item['name']} changed")
    return pin, observed, values


def validate_activation_sources(
    sources: list[dict[str, object]],
    values: dict[str, object],
    *,
    after_activation: bool,
    expected_worker_mode: str | None = None,
) -> None:
    by_type: dict[str, tuple[str, object]] = {}
    for source in sources:
        source_type = source.get("type")
        name = str(source["name"])
        if not isinstance(source_type, str) or source_type in by_type:
            raise RolloutError("activation control source types are invalid")
        by_type[source_type] = (name, values[name])
    required = {
        "cloudflare-account",
        "cloudflare-zone",
        "cloudflare-routes",
        "cloudflare-worker",
    }
    if not required.issubset(by_type):
        raise RolloutError("activation needs the four typed Cloudflare sources")
    account = by_type["cloudflare-account"][1]
    if not isinstance(account, dict) or account.get("id") != SEASONS_ACCOUNT_ID:
        raise RolloutError("Cloudflare account identity did not match Seasons")
    zone = by_type["cloudflare-zone"][1]
    if (
        not isinstance(zone, dict)
        or zone.get("name") != SEASONS_ZONE
        or zone.get("accountId") != SEASONS_ACCOUNT_ID
    ):
        raise RolloutError("Cloudflare zone identity did not match Seasons")
    routes_value = by_type["cloudflare-routes"][1]
    routes = routes_value.get("routes") if isinstance(routes_value, dict) else None
    if not isinstance(routes, list) or any(not isinstance(route, dict) for route in routes):
        raise RolloutError("Cloudflare routes response is invalid")
    observed_routes = {(route.get("pattern"), route.get("script")) for route in routes}
    allowed_routes = {frozenset(), frozenset(PRODUCTION_ROUTES)}
    if (
        frozenset(observed_routes) not in allowed_routes
        or len(routes) != len(observed_routes)
        or (after_activation and observed_routes != PRODUCTION_ROUTES)
    ):
        raise RolloutError("Cloudflare routes did not match the exact production pair")
    worker = by_type["cloudflare-worker"][1]
    if after_activation and expected_worker_mode is None:
        expected_worker_mode = "proxy"
    if (
        not isinstance(worker, dict)
        or worker.get("name") != PRODUCTION_WORKER
        or (
            after_activation
            and (
                not isinstance(worker.get("versionId"), str)
                or not worker["versionId"]
                or worker.get("mode") != expected_worker_mode
            )
        )
        or (
            not after_activation
            and worker.get("versionId") is not None
            and (
                not isinstance(worker.get("versionId"), str)
                or not worker["versionId"]
            )
        )
    ):
        raise RolloutError("Cloudflare production Worker identity is invalid")


def typed_control_values(
    sources: list[dict[str, object]], values: dict[str, object]
) -> dict[str, tuple[str, object]]:
    result: dict[str, tuple[str, object]] = {}
    for source in sources:
        source_type = source.get("type")
        name = str(source["name"])
        if not isinstance(source_type, str) or source_type in result:
            raise RolloutError("control source types are invalid")
        result[source_type] = (name, values[name])
    return result


def require_sha256(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise RolloutError(f"{field} must be a lowercase SHA-256")
    return value


def require_revision(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) not in {40, 64}
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise RolloutError(f"{field} must be a fixed revision SHA")
    return value


def validate_release_authorization(
    plan: dict[str, object],
    sources: list[dict[str, object]],
    values: dict[str, object],
    *,
    phase: str,
) -> tuple[dict[str, object], dict[str, tuple[str, object]]]:
    by_type = typed_control_values(sources, values)
    required = {
        "staging-readback",
        "backend-release",
        "fly-deployment",
        "pages-deployment",
        "deployment-predecessor",
    }
    if not required.issubset(by_type):
        raise RolloutError("release operation needs all typed authorization sources")
    target = plan.get("activationTarget")
    expected_target_fields = {
        "releaseId",
        "releaseSealSha256",
        "artifactSha256",
        "flyImageDigest",
        "flyDeployedSha",
        "pagesDeploymentSha",
        "pageHashes",
    }
    if not isinstance(target, dict) or set(target) != expected_target_fields:
        raise RolloutError("control plan needs an exact activation target")
    release_id = target.get("releaseId")
    if not isinstance(release_id, str) or not release_id:
        raise RolloutError("activation target release ID is invalid")
    seal = require_sha256(target.get("releaseSealSha256"), "release seal")
    artifact = require_sha256(target.get("artifactSha256"), "release artifact")
    staging = by_type["staging-readback"][1]
    if (
        not isinstance(staging, dict)
        or staging.get("kind") != "provider-actions-readback"
        or staging.get("transport") != "live"
        or staging.get("phase") != "staging"
        or staging.get("canonicalOrigin") != STAGING_ORIGIN
        or staging.get("releaseId") != release_id
        or staging.get("releaseSealSha256") != seal
    ):
        raise RolloutError("live staging readback did not authorize the release")
    staging_evidence_sha = require_sha256(
        staging.get("evidenceSha256"), "staging evidence"
    )
    unsealed_staging = {
        key: value for key, value in staging.items() if key != "evidenceSha256"
    }
    if hashlib.sha256(canonical_json(unsealed_staging)).hexdigest() != staging_evidence_sha:
        raise RolloutError("live staging readback evidence seal did not match")
    image = target.get("flyImageDigest")
    deployed_sha = target.get("flyDeployedSha")
    if not isinstance(image, str) or not image.startswith("sha256:"):
        raise RolloutError("Fly deployment authorization is invalid")
    require_sha256(image.removeprefix("sha256:"), "Fly image")
    require_revision(deployed_sha, "Fly deployed SHA")
    pages_sha = target.get("pagesDeploymentSha")
    require_revision(pages_sha, "Pages deployment SHA")
    page_hashes = target.get("pageHashes")
    if (
        not isinstance(page_hashes, dict)
        or set(page_hashes) != REPRESENTATIVE_PAGES
    ):
        raise RolloutError("fixed pre-change Pages hashes are invalid")
    for value in page_hashes.values():
        require_sha256(value, "Pages hash")
    fly = by_type["fly-deployment"][1]
    if not isinstance(fly, dict) or fly != {
        "app": "seasons-backend",
        "imageDigest": image,
        "deployedSha": deployed_sha,
    }:
        raise RolloutError("Fly deployment did not match the authorized backend")
    pages = by_type["pages-deployment"][1]
    if not isinstance(pages, dict) or pages != {
        "deploymentSha": pages_sha,
        "pageHashes": page_hashes,
    }:
        raise RolloutError("Pages deployment did not match the authorization")
    predecessor = by_type["deployment-predecessor"][1]
    if not isinstance(predecessor, dict):
        raise RolloutError("deployment predecessor is invalid")
    backend = by_type["backend-release"][1]
    expected_backend = (
        {
            "app": "seasons-backend",
            "activeReleaseId": release_id,
            "artifactSha256": artifact,
        }
        if phase == "final"
        else {
            "app": "seasons-backend",
            "activeReleaseId": predecessor.get("backendReleaseId"),
            "artifactSha256": predecessor.get("backendArtifactSha256"),
        }
    )
    if backend != expected_backend:
        raise RolloutError("backend active release did not match the authorized state")
    if (
        predecessor.get("compatibleTargetReleaseId") != release_id
        or predecessor.get("flyImageDigest") != image
        or predecessor.get("flyDeployedSha") != deployed_sha
        or predecessor.get("pagesDeploymentSha") != pages_sha
        or predecessor.get("pageHashes") != page_hashes
    ):
        raise RolloutError("Worker and backend predecessor are not a compatible set")
    worker = by_type["cloudflare-worker"][1]
    if phase == "before" and isinstance(worker, dict):
        if (
            worker.get("versionId") != predecessor.get("workerVersionId")
            or (worker.get("versionId") is not None and worker.get("mode") != "safe-baseline")
        ):
            raise RolloutError("production Worker is not at the authorized safe predecessor")
    return target, by_type


def validate_backend_operator(
    plan: dict[str, object],
    operation: str,
    expected_release_id: object,
    expected_sha256: object,
    target_release_id: object,
    target_sha256: object,
) -> list[str]:
    key = "backendActivationCommand" if operation == "activate" else "backendRollbackCommand"
    command = plan.get(key)
    expected = (
        f"python scripts/provider_action_release.py {operation} "
        f"--expected-release-id {expected_release_id} "
        f"--expected-sha256 {expected_sha256} "
        f"--target-release-id {target_release_id} "
        f"--target-sha256 {target_sha256}"
    )
    if (
        not isinstance(command, list)
        or len(command) != 7
        or not all(isinstance(item, str) and item for item in command)
        or Path(command[0]).name != "fly"
        or command[1:6] != ["ssh", "console", "-a", "seasons-backend", "-C"]
        or command[6] != expected
    ):
        raise RolloutError(f"backend {operation} command is invalid")
    return command


def validate_activation_command(plan: dict[str, object]) -> list[str]:
    command = plan.get("activationCommand")
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(part, str) and part for part in command)
    ):
        raise RolloutError("control plan needs an activation command")
    if Path(command[0]).name != "npx" or command[1:3] != [
        "--yes",
        "wrangler@4.129.0",
    ]:
        raise RolloutError("activation command must use pinned Wrangler 4.129.0")
    arguments = command[3:]
    if len(arguments) != 5 or arguments[:2] != ["deploy", "--config"]:
        raise RolloutError("activation command is not the pinned production deploy")
    if arguments[3:5] != ["--name", PRODUCTION_WORKER]:
        raise RolloutError("activation command targets the wrong Worker")
    config = Path(arguments[2])
    if not config.is_absolute():
        config = Path(__file__).parents[1] / config
    if config.resolve() != PRODUCTION_CONFIG:
        raise RolloutError("activation command targets the wrong config")
    expected_config_sha = plan.get("productionConfigSha256")
    if (
        not isinstance(expected_config_sha, str)
        or hashlib.sha256(PRODUCTION_CONFIG.read_bytes()).hexdigest()
        != expected_config_sha
    ):
        raise RolloutError("production config pin did not match")
    return command


def validate_rollback_command(
    plan: dict[str, object], profile: str
) -> tuple[list[str], str | None]:
    command = plan.get("rollbackCommand")
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(part, str) and part for part in command)
        or Path(command[0]).name != "npx"
        or command[1:3] != ["--yes", "wrangler@4.129.0"]
    ):
        raise RolloutError("rollback command must use pinned Wrangler 4.129.0")
    arguments = command[3:]
    expected_config = (
        PRODUCTION_CONFIG if profile == "predecessor" else SAFE_BASELINE_CONFIG
    )
    target_version = None
    if profile == "predecessor":
        if (
            len(arguments) != 7
            or arguments[0] != "rollback"
            or arguments[2] != "--config"
            or arguments[4:] != ["--name", PRODUCTION_WORKER, "--yes"]
        ):
            raise RolloutError("normal rollback command is invalid")
        target_version = arguments[1]
        config_argument = arguments[3]
    else:
        if (
            len(arguments) != 5
            or arguments[:2] != ["deploy", "--config"]
            or arguments[3:] != ["--name", PRODUCTION_WORKER]
        ):
            raise RolloutError("safe-baseline rollback command is invalid")
        config_argument = arguments[2]
    config = Path(config_argument)
    if not config.is_absolute():
        config = Path(__file__).parents[1] / config
    if config.resolve() != expected_config:
        raise RolloutError("rollback command targets the wrong config")
    expected_sha = plan.get("rollbackConfigSha256")
    if (
        not isinstance(expected_sha, str)
        or hashlib.sha256(expected_config.read_bytes()).hexdigest() != expected_sha
    ):
        raise RolloutError("rollback config pin did not match")
    return command, target_version


def activate(plan_path: Path, pin_path: Path, output: Path) -> None:
    plan, sources = load_control_plan(plan_path)
    pin, observed, before_values = compare_control_pin(plan_path, pin_path)
    validate_activation_sources(sources, before_values, after_activation=False)
    target, before_types = validate_release_authorization(
        plan, sources, before_values, phase="before"
    )
    worker_command = validate_activation_command(plan)
    predecessor = before_types["deployment-predecessor"][1]
    assert isinstance(predecessor, dict)
    backend_command = validate_backend_operator(
        plan,
        "activate",
        predecessor.get("backendReleaseId"),
        predecessor.get("backendArtifactSha256"),
        target["releaseId"],
        target["artifactSha256"],
    )
    completed = subprocess.run(
        worker_command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=300,
    )
    if completed.returncode != 0:
        raise RolloutError(f"Worker activation failed with exit {completed.returncode}")
    worker_after, worker_after_values = control_snapshot(
        sources, plan_path.resolve().parent
    )
    validate_activation_sources(sources, worker_after_values, after_activation=True)
    validate_release_authorization(
        plan, sources, worker_after_values, phase="worker"
    )
    before_by_name = {item["name"]: item["sha256"] for item in observed}
    worker_after_by_name = {item["name"]: item["sha256"] for item in worker_after}
    transition_source = before_types["cloudflare-worker"][0]
    route_source = next(
        str(source["name"])
        for source in sources
        if source.get("type") == "cloudflare-routes"
    )
    if any(
        worker_after_by_name[name] != digest
        for name, digest in before_by_name.items()
        if name not in {transition_source, route_source}
    ):
        raise RolloutError("non-target control-plane state changed during activation")
    before_worker = before_values[transition_source]
    after_worker = worker_after_values[transition_source]
    assert isinstance(before_worker, dict) and isinstance(after_worker, dict)
    if after_worker["versionId"] == before_worker.get("versionId"):
        raise RolloutError("production Worker did not reach the expected state")
    completed = subprocess.run(
        backend_command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=300,
    )
    if completed.returncode != 0:
        raise RolloutError(f"backend activation failed with exit {completed.returncode}")
    after, after_values = control_snapshot(sources, plan_path.resolve().parent)
    validate_activation_sources(sources, after_values, after_activation=True)
    after_target, final_types = validate_release_authorization(
        plan, sources, after_values, phase="final"
    )
    after_by_name = {item["name"]: item["sha256"] for item in after}
    backend_source = final_types["backend-release"][0]
    if any(
        after_by_name[name] != digest
        for name, digest in worker_after_by_name.items()
        if name != backend_source
    ):
        raise RolloutError("non-backend state changed during backend activation")
    write_evidence(
        output,
        {
            "schemaVersion": 1,
            "kind": "provider-actions-activation",
            "pinSha256": hashlib.sha256(canonical_json(pin)).hexdigest(),
            "workerActivationCommandSha256": hashlib.sha256(
                canonical_json(worker_command)
            ).hexdigest(),
            "backendActivationCommandSha256": hashlib.sha256(
                canonical_json(backend_command)
            ).hexdigest(),
            "sources": after,
            "releaseId": after_target["releaseId"],
            "releaseSealSha256": after_target["releaseSealSha256"],
            "workerBeforeSha256": before_by_name[transition_source],
            "workerAfterSha256": after_by_name[transition_source],
            "backendAfterSha256": after_by_name[backend_source],
            "status": "verified",
        },
    )


def control_proof(
    sources: list[dict[str, object]], values: dict[str, object]
) -> dict[str, object]:
    by_type = {source.get("type"): values[str(source["name"])] for source in sources}
    worker = by_type["cloudflare-worker"]
    routes = by_type["cloudflare-routes"]
    assert isinstance(worker, dict)
    assert isinstance(routes, dict)
    proof = {
        "accountId": SEASONS_ACCOUNT_ID,
        "zone": SEASONS_ZONE,
        "routes": sorted(
            routes["routes"], key=lambda item: (item["pattern"], item["script"])
        ),
        "worker": PRODUCTION_WORKER,
        "workerVersionId": worker["versionId"],
        "workerMode": worker.get("mode"),
    }
    backend = by_type.get("backend-release")
    if backend is not None:
        backend_value = backend
        assert isinstance(backend_value, dict)
        proof["backendReleaseId"] = backend_value.get("activeReleaseId")
        proof["backendArtifactSha256"] = backend_value.get("artifactSha256")
    return proof


def rollback(
    profile: str,
    control_plan_path: Path,
    current_pin_path: Path,
    target_pin_path: Path | None,
    readback_plan_path: Path,
    responses_path: Path | None,
    output: Path,
    concurrency: int,
    request_timeout: float,
) -> None:
    plan, sources = load_control_plan(control_plan_path)
    current_pin, before, before_values = compare_control_pin(
        control_plan_path, current_pin_path
    )
    validate_activation_sources(sources, before_values, after_activation=True)
    command, target_version = validate_rollback_command(plan, profile)
    if profile == "predecessor" and target_pin_path is None:
        raise RolloutError("normal rollback needs a target pin")
    if profile == "safe-baseline" and target_pin_path is not None:
        raise RolloutError("safe-baseline rollback does not accept a target pin")
    if responses_path is not None:
        raise RolloutError("executable rollback requires live canonical readback")
    worker_source = next(
        str(source["name"])
        for source in sources
        if source.get("type") == "cloudflare-worker"
    )
    before_by_name = {item["name"]: item["sha256"] for item in before}
    if profile == "predecessor":
        assert target_pin_path is not None and target_version is not None
        current_target, current_types = validate_release_authorization(
            plan, sources, before_values, phase="final"
        )
        rollback_target = plan.get("rollbackTarget")
        if (
            not isinstance(rollback_target, dict)
            or set(rollback_target)
            != {"releaseId", "artifactSha256", "workerVersionId", "workerMode"}
            or rollback_target.get("workerVersionId") != target_version
        ):
            raise RolloutError("normal rollback target is invalid")
        require_sha256(rollback_target.get("artifactSha256"), "rollback artifact")
        predecessor = current_types["deployment-predecessor"][1]
        assert isinstance(predecessor, dict)
        if (
            rollback_target.get("releaseId") != predecessor.get("backendReleaseId")
            or rollback_target.get("artifactSha256")
            != predecessor.get("backendArtifactSha256")
            or rollback_target.get("workerVersionId")
            != predecessor.get("workerVersionId")
        ):
            raise RolloutError("rollback target was not the compatible predecessor")
        backend_command = validate_backend_operator(
            plan,
            "rollback",
            current_target["releaseId"],
            current_target["artifactSha256"],
            rollback_target["releaseId"],
            rollback_target["artifactSha256"],
        )
        target_pin = read_json(target_pin_path)
        target_sources = target_pin.get("sources") if isinstance(target_pin, dict) else None
        if (
            not isinstance(target_pin, dict)
            or target_pin.get("schemaVersion") != 1
            or target_pin.get("kind") != "provider-actions-control-pin"
            or not isinstance(target_sources, list)
        ):
            raise RolloutError("normal rollback target pin is invalid")
        authorized_values = dict(before_values)
        backend_source = current_types["backend-release"][0]
        authorized_values[backend_source] = {
            "app": "seasons-backend",
            "activeReleaseId": rollback_target["releaseId"],
            "artifactSha256": rollback_target["artifactSha256"],
        }
        authorized_values[worker_source] = {
            "name": PRODUCTION_WORKER,
            "versionId": rollback_target["workerVersionId"],
            "mode": rollback_target["workerMode"],
        }
        expected_target = {
            name: hashlib.sha256(canonical_json(value)).hexdigest()
            for name, value in authorized_values.items()
        }
        supplied_target = {
            item.get("name"): item.get("sha256")
            for item in target_sources
            if isinstance(item, dict)
        }
        if supplied_target != expected_target or len(target_sources) != len(expected_target):
            raise RolloutError("normal rollback target pin was not authorized")
        completed = subprocess.run(
            backend_command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=300,
        )
        if completed.returncode != 0:
            raise RolloutError(f"backend rollback failed with exit {completed.returncode}")
        backend_after, backend_after_values = control_snapshot(
            sources, control_plan_path.resolve().parent
        )
        backend_after_by_name = {
            item["name"]: item["sha256"] for item in backend_after
        }
        if (
            backend_after_values[backend_source] != authorized_values[backend_source]
            or any(
                backend_after_by_name[name] != digest
                for name, digest in before_by_name.items()
                if name != backend_source
            )
        ):
            raise RolloutError("backend rollback transition did not match")
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=300,
        )
        if completed.returncode != 0:
            raise RolloutError(f"Worker rollback failed with exit {completed.returncode}")
        target_pin, after, after_values = compare_control_pin(
            control_plan_path, target_pin_path
        )
        validate_activation_sources(sources, after_values, after_activation=True)
        worker = after_values[worker_source]
        if worker != authorized_values[worker_source]:
            raise RolloutError("restored Worker did not match the rollback target")
        verification_pin_path = target_pin_path
        after_pin = target_pin
    else:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=300,
        )
        if completed.returncode != 0:
            raise RolloutError(f"rollback failed with exit {completed.returncode}")
        after, after_values = control_snapshot(
            sources, control_plan_path.resolve().parent
        )
        validate_activation_sources(
            sources,
            after_values,
            after_activation=True,
            expected_worker_mode="safe-baseline",
        )
        after_by_name = {item["name"]: item["sha256"] for item in after}
        if any(
            digest != after_by_name[name]
            for name, digest in before_by_name.items()
            if name != worker_source
        ):
            raise RolloutError("non-Worker control state changed during rollback")
        worker = after_values[worker_source]
        assert isinstance(worker, dict)
        if (
            worker.get("mode") != "safe-baseline"
            or worker.get("versionId") == before_values[worker_source].get("versionId")
        ):
            raise RolloutError("safe-baseline Worker transition did not match")
        after_pin = {
            "schemaVersion": 1,
            "kind": "provider-actions-control-pin",
            "sources": after,
        }
        verification_pin_path = None
    with tempfile.TemporaryDirectory(prefix="provider-actions-rollback-") as directory:
        temporary = Path(directory)
        if verification_pin_path is None:
            verification_pin_path = temporary / "post-pin.json"
            write_evidence(verification_pin_path, after_pin)
        readback_output = temporary / "readback.json"
        verify(
            "rollback",
            readback_plan_path,
            responses_path,
            readback_output,
            control_plan_path,
            verification_pin_path,
            concurrency,
            request_timeout,
        )
        evidence = read_json(readback_output)
    assert isinstance(evidence, dict)
    evidence.update(
        {
            "operation": "rollback-executed",
            "rollbackProfile": profile,
            "rollbackCommandSha256": hashlib.sha256(
                canonical_json(command)
            ).hexdigest(),
            "controlBeforePinSha256": hashlib.sha256(
                canonical_json(current_pin)
            ).hexdigest(),
            "controlAfterPinSha256": hashlib.sha256(
                canonical_json(after_pin)
            ).hexdigest(),
            "controlProof": control_proof(sources, after_values),
        }
    )
    if profile == "predecessor":
        evidence["backendRollbackCommandSha256"] = hashlib.sha256(
            canonical_json(backend_command)
        ).hexdigest()
    evidence.pop("evidenceSha256", None)
    evidence["evidenceSha256"] = hashlib.sha256(canonical_json(evidence)).hexdigest()
    write_evidence(output, evidence)


def parse_time(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise RolloutError(f"readback plan needs {field}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise RolloutError(f"readback plan has invalid {field}") from error
    if parsed.utcoffset() is None:
        raise RolloutError(f"readback plan {field} needs an offset")
    return parsed


def load_release(path: Path) -> dict[str, object]:
    release = read_json(path)
    if not isinstance(release, dict):
        raise RolloutError("release artifact must be an object")
    seal = release.get("sealSha256")
    unsealed = {key: value for key, value in release.items() if key != "sealSha256"}
    if (
        not isinstance(seal, str)
        or hashlib.sha256(canonical_json(unsealed)).hexdigest() != seal
    ):
        raise RolloutError("release artifact seal does not match")
    if not isinstance(release.get("releaseId"), str):
        raise RolloutError("release artifact needs an ID")
    return release


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, url):
        return None


def live_response(url: str, timeout: float) -> dict[str, object]:
    total_attempts = 3
    opener = urllib.request.build_opener(NoRedirect)
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "text/html,application/xml",
            "User-Agent": "Seasons-Provider-Actions-Readback/1",
        },
    )
    for attempt in range(total_attempts):
        try:
            response = opener.open(request, timeout=timeout)
            break
        except urllib.error.HTTPError as error:
            response = error
            break
        except (OSError, urllib.error.URLError) as error:
            if attempt == total_attempts - 1:
                raise RolloutError("canonical readback request failed") from error
    try:
        body = response.read(4_194_305)
        status = response.status
        headers = dict(response.headers.items())
    finally:
        response.close()
    if len(body) > 4_194_304:
        raise RolloutError("canonical readback response exceeded 4 MiB")
    return {
        "status": status,
        "headers": headers,
        "bodyBase64": base64.b64encode(body).decode("ascii"),
    }


class Responses:
    def __init__(self, fixture: Path | None, timeout: float):
        self._fixture = read_json(fixture) if fixture is not None else None
        self._timeout = timeout
        if self._fixture is not None and not isinstance(self._fixture, dict):
            raise RolloutError("response fixture must be an object")

    def get(self, url: str) -> tuple[int, dict[str, str], bytes]:
        raw = (
            live_response(url, self._timeout)
            if self._fixture is None
            else self._fixture.get(url)
        )
        if not isinstance(raw, dict):
            raise RolloutError("required readback response is missing")
        status = raw.get("status")
        headers = raw.get("headers")
        encoded = raw.get("bodyBase64")
        if (
            not isinstance(status, int)
            or not isinstance(headers, dict)
            or not all(isinstance(key, str) and isinstance(value, str) for key, value in headers.items())
            or not isinstance(encoded, str)
        ):
            raise RolloutError("readback response has an invalid shape")
        try:
            body = base64.b64decode(encoded, validate=True)
        except ValueError as error:
            raise RolloutError("readback response body is not valid base64") from error
        return status, {key.lower(): value for key, value in headers.items()}, body


def require_safe_headers(headers: dict[str, str]) -> None:
    for name, expected in SAFETY_HEADERS.items():
        if headers.get(name) != expected:
            raise RolloutError(f"canonical response has invalid {name}")
    if "content-security-policy" not in headers or "x-robots-tag" not in headers:
        raise RolloutError("canonical response is missing safety headers")


def observe(
    responses: Responses,
    url: str,
    *,
    expected_status: int,
    release_id: str | None = None,
    region: str | None = None,
    provider: int | None = None,
    expected_location: str | None = None,
    expected_content_type: str = "text/html; charset=utf-8",
    require_safety: bool = False,
    forbid_identity: bool = False,
) -> tuple[dict[str, object], bytes, dict[str, str]]:
    status, headers, body = responses.get(url)
    if status != expected_status:
        raise RolloutError("canonical response status did not match")
    if release_id is not None and headers.get("x-seasons-provider-actions-release") != release_id:
        raise RolloutError("canonical response release identity did not match")
    if region is not None and headers.get("x-seasons-provider-actions-region") != region:
        raise RolloutError("canonical response region identity did not match")
    if provider is not None and headers.get("x-seasons-provider-actions-provider") != str(provider):
        raise RolloutError("canonical response provider identity did not match")
    if forbid_identity and any(
        headers.get(name) is not None
        for name in (
            "x-seasons-provider-actions-release",
            "x-seasons-provider-actions-region",
            "x-seasons-provider-actions-provider",
        )
    ):
        raise RolloutError("safe baseline response exposed backend identity")
    if headers.get("content-type") != expected_content_type:
        raise RolloutError("canonical response content type did not match")
    if release_id is not None or require_safety:
        require_safe_headers(headers)
    location = headers.get("location")
    if location != expected_location:
        raise RolloutError("canonical response redirect location did not match")
    return (
        {
            "url": url,
            "status": status,
            "bodySha256": hashlib.sha256(body).hexdigest(),
            "releaseId": headers.get("x-seasons-provider-actions-release"),
            "region": headers.get("x-seasons-provider-actions-region"),
            "provider": headers.get("x-seasons-provider-actions-provider"),
            "location": location,
            "contentType": headers.get("content-type"),
            "robots": headers.get("x-robots-tag"),
        },
        body,
        headers,
    )


def verify_unrelated_pages(
    plan: dict[str, object], responses: Responses
) -> list[dict[str, object]]:
    pages = []
    for page in plan.get("unrelatedPages", []):
        if not isinstance(page, dict) or not isinstance(page.get("url"), str) or not isinstance(page.get("sha256"), str):
            raise RolloutError("unrelated Pages check is invalid")
        url = page["url"]
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "getseasons.app" or parsed.query or parsed.fragment or parsed.path.startswith("/provider-actions"):
            raise RolloutError("unrelated Pages URL is outside the canonical site")
        status, _, body = responses.get(url)
        digest = hashlib.sha256(body).hexdigest()
        if status != 200 or digest != page["sha256"]:
            raise RolloutError("unrelated Pages response changed")
        pages.append({"url": url, "status": status, "sha256": digest})
    return pages


def verify(
    phase: str,
    plan_path: Path,
    responses_path: Path | None,
    output: Path,
    control_plan_path: Path | None,
    control_pin_path: Path | None,
    concurrency: int,
    request_timeout: float,
) -> None:
    plan = read_json(plan_path)
    if not isinstance(plan, dict) or plan.get("schemaVersion") != 1:
        raise RolloutError("unsupported readback plan")
    origin = plan.get("canonicalOrigin")
    expected_origin = STAGING_ORIGIN if phase == "staging" else PRODUCTION_ORIGIN
    if origin != expected_origin:
        raise RolloutError(f"{phase} origin must be {expected_origin}")
    if phase in {"production", "rollback"}:
        unrelated = plan.get("unrelatedPages")
        urls = {
            page.get("url")
            for page in unrelated
            if isinstance(page, dict)
        } if isinstance(unrelated, list) else set()
        if urls != REPRESENTATIVE_PAGES or len(unrelated or []) != len(urls):
            raise RolloutError("readback plan needs the fixed unrelated Pages allowlist")
    release_value = plan.get("release")
    if not isinstance(release_value, str) or not release_value:
        raise RolloutError("readback plan needs a release artifact")
    release_path = Path(release_value)
    if not release_path.is_absolute():
        release_path = plan_path.resolve().parent / release_path
    release = load_release(release_path)
    release_id = str(release["releaseId"])
    at = parse_time(plan.get("at"), "at")
    raw_pairs = release.get("publicSupportedPairs")
    if not isinstance(raw_pairs, list) or not raw_pairs:
        raise RolloutError("release needs supported pairs")
    pairs: list[tuple[str, int]] = []
    for pair in raw_pairs:
        if (
            not isinstance(pair, list)
            or len(pair) != 2
            or not isinstance(pair[0], str)
            or not isinstance(pair[1], int)
        ):
            raise RolloutError("release has an invalid supported pair")
        pairs.append((pair[0], pair[1]))
    if len(set(pairs)) != len(pairs):
        raise RolloutError("release supported pairs are not unique")
    destinations = release.get("startDestinations")
    if not isinstance(destinations, dict):
        raise RolloutError("release needs start destinations")
    raw_guides = release.get("publishedGuides")
    if not isinstance(raw_guides, list):
        raise RolloutError("release needs published guides")
    guides: dict[tuple[str, int], dict[str, object]] = {}
    for guide in raw_guides:
        if not isinstance(guide, dict):
            raise RolloutError("release has an invalid guide")
        key = (guide.get("region"), guide.get("tmdbProviderId"))
        if not isinstance(key[0], str) or not isinstance(key[1], int) or key not in pairs or key in guides:
            raise RolloutError("release guide pair is invalid")
        guides[key] = guide
    responses = Responses(responses_path, request_timeout)
    control_pin_sha256 = None
    if phase == "rollback":
        if control_plan_path is None or control_pin_path is None:
            raise RolloutError("rollback verification needs a control plan and pin")
        control_pin, _, _ = compare_control_pin(control_plan_path, control_pin_path)
        control_pin_sha256 = hashlib.sha256(canonical_json(control_pin)).hexdigest()
    elif control_plan_path is not None or control_pin_path is not None:
        if control_plan_path is None or control_pin_path is None:
            raise RolloutError("control plan and pin must be supplied together")
        control_pin, _, _ = compare_control_pin(control_plan_path, control_pin_path)
        control_pin_sha256 = hashlib.sha256(canonical_json(control_pin)).hexdigest()
    rollback_profile = plan.get("rollbackProfile")
    if rollback_profile is not None and (
        phase != "rollback" or rollback_profile != "safe-baseline"
    ):
        raise RolloutError("readback plan has an invalid rollback profile")
    if rollback_profile == "safe-baseline":
        safe_paths = [
            "/provider-actions",
            "/provider-actions/",
            *(
                path
                for region, provider in sorted(pairs)
                for path in (
                    f"/provider-actions/cancel/{provider}/{region}/",
                    f"/provider-actions/start/{provider}/{region}/",
                )
            ),
            "/provider-actions/sitemap.xml",
            *(path for path, _ in INVALID_PATHS.values()),
        ]

        def verify_safe_path(path: str) -> dict[str, object]:
            observation, _, _ = observe(
                responses,
                f"{origin}{path}",
                expected_status=503,
                require_safety=True,
                forbid_identity=True,
            )
            return observation

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            observations = list(executor.map(verify_safe_path, safe_paths))
        evidence = {
            "schemaVersion": 1,
            "kind": (
                "provider-actions-readback"
                if responses_path is None
                else "provider-actions-readback-fixture"
            ),
            "transport": "live" if responses_path is None else "fixture",
            "phase": phase,
            "rollbackProfile": rollback_profile,
            "releaseId": None,
            "enumerationReleaseSealSha256": release["sealSha256"],
            "verifiedAt": plan["at"],
            "verifiedActionPairs": len(pairs),
            "safeBaselineResponses": len(safe_paths),
            "concurrency": concurrency,
            "requestTimeoutSeconds": request_timeout,
            "unrelatedPages": verify_unrelated_pages(plan, responses),
            "observations": observations,
            "controlPinSha256": control_pin_sha256,
        }
        evidence["evidenceSha256"] = hashlib.sha256(
            canonical_json(evidence)
        ).hexdigest()
        write_evidence(output, evidence)
        return

    def verify_pair(pair: tuple[str, int]) -> tuple[list[dict[str, object]], str | None]:
        region, provider = pair
        pair = (region, provider)
        guide = guides.get(pair)
        fresh_url = None
        cancel_url = f"{origin}/provider-actions/cancel/{provider}/{region}/"
        cancel_observation, cancel_body, cancel_headers = observe(
            responses,
            cancel_url,
            expected_status=200,
            release_id=release_id,
            region=region,
            provider=provider,
        )
        if guide is None:
            if cancel_headers.get("x-robots-tag") != "noindex":
                raise RolloutError("unpublished cancellation response is indexable")
        else:
            stale = parse_time(guide.get("staleAt"), "guide staleAt") <= at
            steps = guide.get("orderedSteps")
            source_url = guide.get("sourceUrl")
            if not isinstance(steps, list) or not all(isinstance(step, str) for step in steps) or not isinstance(source_url, str):
                raise RolloutError("release guide content is invalid")
            if stale:
                if cancel_headers.get("x-robots-tag") != "noindex" or any(step.encode() in cancel_body for step in steps) or source_url.encode() in cancel_body:
                    raise RolloutError("stale cancellation response exposed old guide content")
            else:
                if cancel_headers.get("x-robots-tag") != "index" or any(step.encode() not in cancel_body for step in steps) or source_url.encode() not in cancel_body:
                    raise RolloutError("fresh cancellation response did not match its guide")
                fresh_url = (
                    f"{PRODUCTION_ORIGIN}/provider-actions/cancel/"
                    f"{provider}/{region}/"
                )
        destination = destinations.get(str(provider))
        if destination is not None and not isinstance(destination, str):
            raise RolloutError("release start destination is invalid")
        start_observation, _, _ = observe(
            responses,
            f"{origin}/provider-actions/start/{provider}/{region}/",
            expected_status=302 if destination else 200,
            release_id=release_id,
            region=region,
            provider=provider,
            expected_location=destination,
        )
        return [cancel_observation, start_observation], fresh_url

    observations: list[dict[str, object]] = []
    fresh_urls: set[str] = set()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        for pair_observations, fresh_url in executor.map(
            verify_pair, sorted(pairs)
        ):
            observations.extend(pair_observations)
            if fresh_url is not None:
                fresh_urls.add(fresh_url)
    sitemap_observation, sitemap_body, _ = observe(
        responses,
        f"{origin}/provider-actions/sitemap.xml",
        expected_status=200,
        release_id=release_id,
        expected_content_type="application/xml; charset=utf-8",
    )
    try:
        root = ET.fromstring(sitemap_body)
        sitemap_urls = {
            element.text for element in root.iter() if element.tag.endswith("loc")
        }
    except ET.ParseError as error:
        raise RolloutError("canonical sitemap is invalid XML") from error
    if sitemap_urls != fresh_urls:
        raise RolloutError("canonical sitemap did not match fresh guides")
    observations.append(sitemap_observation)
    invalid_names = []
    for name, (path, status) in INVALID_PATHS.items():
        invalid_observation, _, _ = observe(
            responses,
            f"{origin}{path}",
            expected_status=status,
            release_id=release_id,
        )
        observations.append(invalid_observation)
        invalid_names.append(name)
    switch_names = []
    for case in plan.get("switchCases", []):
        if not isinstance(case, dict) or not isinstance(case.get("name"), str):
            raise RolloutError("switch case is invalid")
        paths = case.get("paths")
        if not isinstance(paths, list) or len(paths) != 2 or not all(isinstance(path, str) for path in paths):
            raise RolloutError("switch case needs cancel then start paths")
        if "/cancel/" not in paths[0] or "/start/" not in paths[1]:
            raise RolloutError("switch case order must be cancel then start")
        known_paths = {urlsplit(item["url"]).path for item in observations}
        if any(urlsplit(path).path not in known_paths for path in paths):
            raise RolloutError("switch case references an unverified action")
        switch_names.append(case["name"])
    pages = verify_unrelated_pages(plan, responses)
    evidence: dict[str, object] = {
        "schemaVersion": 1,
        "kind": (
            "provider-actions-readback"
            if responses_path is None
            else "provider-actions-readback-fixture"
        ),
        "transport": "live" if responses_path is None else "fixture",
        "phase": phase,
        "canonicalOrigin": origin,
        "releaseId": release_id,
        "releaseSealSha256": release["sealSha256"],
        "verifiedAt": plan["at"],
        "verifiedActionPairs": len(pairs),
        "verifiedActionResponses": len(pairs) * 2,
        "concurrency": concurrency,
        "requestTimeoutSeconds": request_timeout,
        "invalidChecks": len(invalid_names),
        "invalidCheckNames": invalid_names,
        "switchCases": switch_names,
        "unrelatedPages": pages,
        "observations": observations,
    }
    if control_pin_sha256 is not None:
        evidence["controlPinSha256"] = control_pin_sha256
    evidence["evidenceSha256"] = hashlib.sha256(canonical_json(evidence)).hexdigest()
    write_evidence(output, evidence)


def bounded_concurrency(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if not 1 <= parsed <= 64:
        raise argparse.ArgumentTypeError("must be between 1 and 64")
    return parsed


def bounded_timeout(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a number") from error
    if not 0.1 <= parsed <= 120:
        raise argparse.ArgumentTypeError("must be between 0.1 and 120 seconds")
    return parsed


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    state_parser = commands.add_parser("cloudflare-state")
    state_parser.add_argument(
        "--kind", choices=("account", "zone", "routes", "worker"), required=True
    )
    state_parser.add_argument("--responses", type=Path)
    capture_parser = commands.add_parser("capture")
    capture_parser.add_argument("--plan", type=Path, required=True)
    capture_parser.add_argument("--output", type=Path, required=True)
    activate_parser = commands.add_parser("activate")
    activate_parser.add_argument("--plan", type=Path, required=True)
    activate_parser.add_argument("--pin", type=Path, required=True)
    activate_parser.add_argument("--output", type=Path, required=True)
    rollback_parser = commands.add_parser("rollback")
    rollback_parser.add_argument(
        "--profile", choices=("predecessor", "safe-baseline"), required=True
    )
    rollback_parser.add_argument("--control-plan", type=Path, required=True)
    rollback_parser.add_argument("--current-pin", type=Path, required=True)
    rollback_parser.add_argument("--target-pin", type=Path)
    rollback_parser.add_argument("--readback-plan", type=Path, required=True)
    rollback_parser.add_argument("--responses", type=Path)
    rollback_parser.add_argument("--concurrency", type=bounded_concurrency, default=16)
    rollback_parser.add_argument(
        "--request-timeout", type=bounded_timeout, default=20.0
    )
    rollback_parser.add_argument("--output", type=Path, required=True)
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument(
        "--phase", choices=("staging", "production", "rollback"), required=True
    )
    verify_parser.add_argument("--plan", type=Path, required=True)
    verify_parser.add_argument("--responses", type=Path)
    verify_parser.add_argument("--control-plan", type=Path)
    verify_parser.add_argument("--control-pin", type=Path)
    verify_parser.add_argument("--concurrency", type=bounded_concurrency, default=16)
    verify_parser.add_argument(
        "--request-timeout", type=bounded_timeout, default=20.0
    )
    verify_parser.add_argument("--output", type=Path, required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if arguments.command == "cloudflare-state":
            cloudflare_state(arguments.kind, arguments.responses)
        elif arguments.command == "capture":
            capture(arguments.plan, arguments.output)
        elif arguments.command == "activate":
            activate(arguments.plan, arguments.pin, arguments.output)
        elif arguments.command == "rollback":
            rollback(
                arguments.profile,
                arguments.control_plan,
                arguments.current_pin,
                arguments.target_pin,
                arguments.readback_plan,
                arguments.responses,
                arguments.output,
                arguments.concurrency,
                arguments.request_timeout,
            )
        elif arguments.command == "verify":
            verify(
                arguments.phase,
                arguments.plan,
                arguments.responses,
                arguments.output,
                arguments.control_plan,
                arguments.control_pin,
                arguments.concurrency,
                arguments.request_timeout,
            )
        return 0
    except (RolloutError, subprocess.TimeoutExpired) as error:
        message = str(error) if isinstance(error, RolloutError) else "control command timed out"
        print(f"provider-actions-rollout: {message}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
