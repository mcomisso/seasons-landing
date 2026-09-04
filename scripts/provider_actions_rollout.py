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
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


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
PRODUCTION_ROUTES = {
    ("getseasons.app/provider-actions", PRODUCTION_WORKER),
    ("getseasons.app/provider-actions/*", PRODUCTION_WORKER),
}


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
    sources: list[dict[str, object]], values: dict[str, object]
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
    if set(by_type) != required:
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
    if observed_routes != PRODUCTION_ROUTES or len(routes) != len(PRODUCTION_ROUTES):
        raise RolloutError("Cloudflare routes did not match the exact production pair")
    worker = by_type["cloudflare-worker"][1]
    if (
        not isinstance(worker, dict)
        or worker.get("name") != PRODUCTION_WORKER
        or not isinstance(worker.get("versionId"), str)
        or not worker["versionId"]
    ):
        raise RolloutError("Cloudflare production Worker identity is invalid")


def validate_activation_command(plan: dict[str, object]) -> list[str]:
    command = plan.get("activationCommand")
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(part, str) and part for part in command)
    ):
        raise RolloutError("control plan needs an activation command")
    arguments = command[1:]
    if Path(command[0]).name == "npx":
        if not arguments or arguments[0] != "wrangler":
            raise RolloutError("activation command must target Wrangler")
        arguments = arguments[1:]
    elif Path(command[0]).name != "wrangler":
        raise RolloutError("activation command must target Wrangler")
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


def activate(plan_path: Path, pin_path: Path, output: Path) -> None:
    plan, sources = load_control_plan(plan_path)
    pin, observed, before_values = compare_control_pin(plan_path, pin_path)
    validate_activation_sources(sources, before_values)
    command = validate_activation_command(plan)
    transition = plan.get("expectedTransition")
    if (
        not isinstance(transition, dict)
        or not isinstance(transition.get("source"), str)
        or not isinstance(transition.get("afterSha256"), str)
        or len(transition["afterSha256"]) != 64
    ):
        raise RolloutError("control plan needs an expected transition")
    transition_source = transition["source"]
    source_types = {str(source["name"]): source.get("type") for source in sources}
    if source_types.get(transition_source) != "cloudflare-worker":
        raise RolloutError("expected transition must target the production Worker")
    completed = subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=300,
    )
    if completed.returncode != 0:
        raise RolloutError(f"activation failed with exit {completed.returncode}")
    after, after_values = control_snapshot(sources, plan_path.resolve().parent)
    validate_activation_sources(sources, after_values)
    before_by_name = {item["name"]: item["sha256"] for item in observed}
    after_by_name = {item["name"]: item["sha256"] for item in after}
    if any(
        after_by_name[name] != digest
        for name, digest in before_by_name.items()
        if name != transition_source
    ):
        raise RolloutError("non-target control-plane state changed during activation")
    if (
        after_by_name[transition_source] == before_by_name[transition_source]
        or after_by_name[transition_source] != transition["afterSha256"]
    ):
        raise RolloutError("production Worker did not reach the expected state")
    write_evidence(
        output,
        {
            "schemaVersion": 1,
            "kind": "provider-actions-activation",
            "pinSha256": hashlib.sha256(canonical_json(pin)).hexdigest(),
            "activationCommandSha256": hashlib.sha256(
                canonical_json(command)
            ).hexdigest(),
            "sources": after,
            "transitionSource": transition_source,
            "beforeSha256": before_by_name[transition_source],
            "afterSha256": after_by_name[transition_source],
            "status": "verified",
        },
    )


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
    opener = urllib.request.build_opener(NoRedirect)
    request = urllib.request.Request(url, headers={"Accept": "text/html,application/xml"})
    try:
        response = opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as error:
        response = error
    except (OSError, urllib.error.URLError) as error:
        raise RolloutError("canonical readback request failed") from error
    body = response.read(4_194_305)
    if len(body) > 4_194_304:
        raise RolloutError("canonical readback response exceeded 4 MiB")
    return {
        "status": response.status,
        "headers": dict(response.headers.items()),
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
    if headers.get("content-type") != expected_content_type:
        raise RolloutError("canonical response content type did not match")
    if release_id is not None:
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
    evidence: dict[str, object] = {
        "schemaVersion": 1,
        "kind": (
            "provider-actions-readback"
            if responses_path is None
            else "provider-actions-readback-fixture"
        ),
        "transport": "live" if responses_path is None else "fixture",
        "phase": phase,
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
    capture_parser = commands.add_parser("capture")
    capture_parser.add_argument("--plan", type=Path, required=True)
    capture_parser.add_argument("--output", type=Path, required=True)
    activate_parser = commands.add_parser("activate")
    activate_parser.add_argument("--plan", type=Path, required=True)
    activate_parser.add_argument("--pin", type=Path, required=True)
    activate_parser.add_argument("--output", type=Path, required=True)
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
        if arguments.command == "capture":
            capture(arguments.plan, arguments.output)
        elif arguments.command == "activate":
            activate(arguments.plan, arguments.pin, arguments.output)
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
