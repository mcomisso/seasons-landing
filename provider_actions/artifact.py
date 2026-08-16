"""Fail-closed validation for generated public Provider Action artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Mapping


_MANIFEST_FIELDS = {
    "files",
    "publishedGuideCount",
    "releaseId",
    "releaseSha256",
    "responseCount",
    "responses",
    "schemaVersion",
    "templateContractVersion",
}
_FILE_FIELDS = {"path", "sha256", "size"}
_RESPONSE_FIELDS = {
    "actionKind",
    "canonicalUrl",
    "httpStatus",
    "indexability",
    "outcome",
    "path",
    "region",
    "responseId",
    "sha256",
    "tmdbProviderId",
}
_FORBIDDEN_PUBLIC_BYTES = (
    b"privateRuntimeIndex",
    b"providerCredentials",
    b"providerAccountIdentifier",
    b"localStorage",
    b"sessionStorage",
    b"console.log",
    b"hubspot",
    b"ahrefs",
    b"tailwind",
    b"account-link.js",
)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _exact_fields(value: object, allowed: set[str], label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    unknown = sorted(set(value) - allowed)
    missing = sorted(allowed - set(value))
    if unknown:
        raise ValueError(f"unexpected field on {label}: {unknown[0]}")
    if missing:
        raise ValueError(f"missing field on {label}: {missing[0]}")
    return value


def _validate_artifact_path(path: object) -> str:
    if not isinstance(path, str) or not path:
        raise ValueError("artifact path must be a non-empty string")
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or ".." in parsed.parts or str(parsed) != path:
        raise ValueError(f"unsafe artifact path: {path}")
    if parsed.parts[0] not in {"assets", "media", "responses"}:
        raise ValueError(f"artifact path is outside the public allowlist: {path}")
    if len(parsed.parts) != 2:
        raise ValueError(f"artifact path must have one allowlisted directory: {path}")
    if path.endswith("sitemap.xml"):
        raise ValueError("a static Provider Actions sitemap must not enter the artifact")
    return path


def _validate_public_artifact_structure(files: Mapping[str, bytes]) -> dict:
    """Validate the exact bytes that may be copied into the public site."""

    if "manifest.json" not in files:
        raise ValueError("public artifact is missing manifest.json")
    try:
        manifest = json.loads(files["manifest.json"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("public artifact manifest must be canonical UTF-8 JSON") from error
    manifest = _exact_fields(manifest, _MANIFEST_FIELDS, "manifest")
    canonical_manifest = (
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        + b"\n"
    )
    if files["manifest.json"] != canonical_manifest:
        raise ValueError("public artifact manifest must use canonical JSON and LF")
    if manifest["schemaVersion"] != "1" or manifest["templateContractVersion"] != "1":
        raise ValueError("unsupported public artifact version")
    if not isinstance(manifest["releaseId"], str) or not manifest["releaseId"]:
        raise ValueError("manifest releaseId must be a non-empty string")
    if not isinstance(manifest["releaseSha256"], str) or not re.fullmatch(
        r"[0-9a-f]{64}", manifest["releaseSha256"]
    ):
        raise ValueError("manifest releaseSha256 must be lowercase SHA-256")
    if not isinstance(manifest["files"], list) or not isinstance(manifest["responses"], list):
        raise ValueError("manifest files and responses must be lists")
    if manifest["responseCount"] != len(manifest["responses"]):
        raise ValueError("manifest responseCount does not match responses")
    if not isinstance(manifest["publishedGuideCount"], int) or isinstance(
        manifest["publishedGuideCount"], bool
    ):
        raise ValueError("manifest publishedGuideCount must be an integer")

    declared_paths: set[str] = set()
    declared_path_order: list[str] = []
    for index, raw_entry in enumerate(manifest["files"]):
        entry = _exact_fields(raw_entry, _FILE_FIELDS, f"manifest.files[{index}]")
        path = _validate_artifact_path(entry["path"])
        if path in declared_paths:
            raise ValueError(f"duplicate artifact path: {path}")
        declared_paths.add(path)
        declared_path_order.append(path)
        if path not in files:
            raise ValueError(f"manifest file is missing: {path}")
        content = files[path]
        if entry["size"] != len(content) or entry["sha256"] != _sha256(content):
            raise ValueError(f"manifest integrity mismatch: {path}")
        if path.startswith("assets/") and entry["sha256"] not in PurePosixPath(path).name:
            raise ValueError(f"public asset path is not content addressed: {path}")
        if path.startswith("media/") and not PurePosixPath(path).name.startswith(entry["sha256"] + "."):
            raise ValueError(f"public media path is not content addressed: {path}")
        lowered = content.lower()
        for forbidden in _FORBIDDEN_PUBLIC_BYTES:
            if forbidden.lower() in lowered:
                raise ValueError(f"forbidden public content in {path}: {forbidden.decode('ascii')}")
    if declared_path_order != sorted(declared_path_order):
        raise ValueError("manifest files must use path order")

    actual_paths = set(files) - {"manifest.json"}
    if actual_paths != declared_paths:
        extra = sorted(actual_paths - declared_paths)
        missing = sorted(declared_paths - actual_paths)
        detail = (extra or missing)[0]
        raise ValueError(f"public artifact does not exactly match its manifest: {detail}")

    response_paths: set[str] = set()
    published_guides = 0
    response_sort_keys: list[tuple[int, str, str]] = []
    for index, raw_response in enumerate(manifest["responses"]):
        response = _exact_fields(raw_response, _RESPONSE_FIELDS, f"manifest.responses[{index}]")
        if (
            not isinstance(response["tmdbProviderId"], int)
            or isinstance(response["tmdbProviderId"], bool)
            or response["tmdbProviderId"] <= 0
        ):
            raise ValueError("manifest response provider ID must be a positive integer")
        for field in ("region", "outcome", "actionKind", "responseId", "canonicalUrl", "indexability"):
            if not isinstance(response[field], str) or not response[field]:
                raise ValueError(f"manifest response {field} must be a non-empty string")
        if response["actionKind"] not in {"cancel", "start"}:
            raise ValueError("manifest response actionKind is unsupported")
        if response["indexability"] not in {"index", "noindex"}:
            raise ValueError("manifest response indexability is unsupported")
        if response["httpStatus"] not in {200, 400, 404}:
            raise ValueError("manifest response httpStatus is unsupported")
        path = _validate_artifact_path(response["path"])
        expected = f"responses/{response['sha256']}.html"
        if path != expected or not re.fullmatch(r"[0-9a-f]{64}", response["sha256"]):
            raise ValueError(f"response path is not content addressed: {path}")
        if path in response_paths:
            raise ValueError(f"duplicate response path: {path}")
        response_paths.add(path)
        if path not in declared_paths or _sha256(files[path]) != response["sha256"]:
            raise ValueError(f"response bytes are missing or invalid: {path}")
        text = files[path].decode("utf-8")
        response_sort_keys.append(
            (response["tmdbProviderId"], response["region"], response["outcome"])
        )
        if response["region"] == "GG" or not re.fullmatch(r"[A-Z]{2}", response["region"]):
            raise ValueError(f"response region is not canonical: {path}")
        expected_canonical = (
            "https://getseasons.app/provider-actions/"
            f"{response['actionKind']}/{response['tmdbProviderId']}/{response['region']}/"
        )
        if response["canonicalUrl"] != expected_canonical:
            raise ValueError(f"response canonical URL is not exact: {path}")
        if response["indexability"] == "index" and response["outcome"] != "guide":
            raise ValueError(f"only published guides may be indexable: {path}")
        expected_robots = (
            '<meta name="robots" content="index, follow">'
            if response["indexability"] == "index"
            else '<meta name="robots" content="noindex, nofollow">'
        )
        if expected_robots not in text:
            raise ValueError(f"response indexing metadata mismatch: {path}")
        required_before_script = (
            '<meta charset="utf-8">',
            '<meta name="viewport"',
            '<meta name="referrer" content="no-referrer">',
            '<meta http-equiv="content-security-policy"',
        )
        script_offset = text.find("<script>")
        if script_offset < 0 or text.count("<script") != 1 or "<script src=" in text.lower():
            raise ValueError(f"response must contain exactly one inline bootstrap: {path}")
        if any(text.find(marker) < 0 or text.find(marker) > script_offset for marker in required_before_script):
            raise ValueError(f"fragment bootstrap is not the first executable code: {path}")
        if "window.location.hash" not in text or "window.history.replaceState" not in text:
            raise ValueError(f"response is missing fragment removal bootstrap: {path}")
        if response["outcome"] == "guide" and response["indexability"] == "index":
            published_guides += 1
    if response_sort_keys != sorted(response_sort_keys):
        raise ValueError("manifest responses must use provider, region, outcome order")
    if manifest["publishedGuideCount"] != published_guides:
        raise ValueError("manifest publishedGuideCount does not match responses")
    return manifest


def _scan_artifact_directory(
    directory: Path,
    *,
    expected_files: Mapping[str, bytes],
) -> dict:
    """Validate a directory and require exact bytes from a pinned render."""

    if directory.is_symlink():
        raise ValueError(f"public artifact directory cannot be a symlink: {directory}")
    directory = directory.resolve()
    if not directory.is_dir():
        raise ValueError(f"public artifact directory does not exist: {directory}")
    files: dict[str, bytes] = {}
    for candidate in sorted(directory.rglob("*")):
        if candidate.is_symlink():
            raise ValueError(f"public artifact cannot contain symlinks: {candidate}")
        if candidate.is_file():
            files[candidate.relative_to(directory).as_posix()] = candidate.read_bytes()
    manifest = _validate_public_artifact_structure(files)
    if dict(files) != dict(expected_files):
        raise ValueError("public artifact does not exactly match the sealed render")
    return manifest


__all__: list[str] = []
