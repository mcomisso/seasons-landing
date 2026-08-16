"""Deterministic public artifact renderer for sealed Provider Action releases."""

from __future__ import annotations

import base64
import hashlib
import html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping
from urllib.parse import urlparse

from .artifact import _scan_artifact_directory, _validate_public_artifact_structure


_STYLESHEET = b"""\
:root{color-scheme:dark;font-family:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,\"Segoe UI\",sans-serif;background:#090b13;color:#f7f7fb}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;background:radial-gradient(circle at top,#20194b 0,#090b13 42rem);line-height:1.6}
main{width:min(44rem,calc(100% - 2rem));margin:0 auto;padding:4rem 0}
.shell{border:1px solid #3e4160;border-radius:1.25rem;background:#111522;padding:clamp(1.25rem,4vw,2.5rem);box-shadow:0 1.5rem 5rem #0008}
.eyebrow{color:#bdb4ff;font-weight:700;letter-spacing:.08em;text-transform:uppercase}
h1,h2{line-height:1.2}h1{font-size:clamp(2rem,7vw,3.25rem);margin:.5rem 0 1rem}h2{font-size:1.15rem;margin-top:2rem}
.warning{border-left:.25rem solid #f8cc69;padding:.75rem 1rem;background:#29230f}
.actions{display:flex;flex-wrap:wrap;gap:.75rem;margin-top:2rem}
.button{display:inline-flex;min-height:2.75rem;align-items:center;justify-content:center;border-radius:999px;padding:.65rem 1.1rem;background:#5d43d8;color:#fff;font-weight:700;text-decoration:none}
.button.secondary{border:1px solid #777b98;background:transparent}
a{color:#c9c2ff}a:focus-visible{outline:.2rem solid #fff;outline-offset:.2rem}
footer{margin-top:2rem;color:#bfc1d1;font-size:.9rem}
"""

_BOOTSTRAP_TEMPLATE = """(() => {
  "use strict";
  const fragment = window.location.hash;
  const context = fragment.length > 1 ? fragment.slice(1) : "";
  try {
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
  } catch (_) {
    return;
  }
  const bindReturnAction = () => {
    const returnAction = document.getElementById("seasons-return");
    if (!returnAction || !context) return;
    try {
      const destination = new URL(%s + encodeURIComponent(context));
      if (destination.protocol !== "https:" || destination.hostname !== "getseasons.app") return;
      returnAction.textContent = %s;
      returnAction.addEventListener("click", (event) => {
        event.preventDefault();
        window.location.assign(destination.href);
      }, { once: true });
    } catch (_) {
      return;
    }
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindReturnAction, { once: true });
  } else {
    bindReturnAction();
  }
})();"""

_RELEASE_FIELDS = {
    "schemaVersion",
    "releaseId",
    "releaseSha256",
    "canonicalOrigin",
    "templateContractVersion",
    "pages",
    "credits",
    "publicAssets",
}
_PAGE_FIELDS = {
    "responseId",
    "actionKind",
    "tmdbProviderId",
    "region",
    "providerDisplayName",
    "countryDisplayName",
    "locale",
    "outcome",
    "httpStatus",
    "canonicalUrl",
    "indexability",
    "title",
    "metaDescription",
    "h1",
    "summary",
    "warnings",
    "orderedSteps",
    "resolvedBranches",
    "supportBlocks",
    "providerAction",
    "supportAction",
    "reportAction",
    "genericSeasonsReturnAction",
    "contextualSeasonsReturnPrefix",
    "contextualSeasonsReturnLabel",
    "screenshot",
    "creditsHref",
}
_CREDITS_FIELDS = {"tmdbNotice", "justWatchAttribution"}
_BLOCK_FIELDS = {"heading", "body"}
_INTERNAL_ACTION_FIELDS = {"label", "href"}
_EXTERNAL_ACTION_FIELDS = {"label", "href", "approvedHosts"}
_ASSET_FIELDS = {"assetId", "kind", "mediaType", "sha256", "contentBase64"}
_SCREENSHOT_FIELDS = {"assetId", "alt", "rightsReference", "state"}
_OUTCOMES = {
    "guide",
    "not_applicable",
    "instructions_unavailable",
    "research_blocked",
    "unpublished",
    "unknown",
}


@dataclass(frozen=True)
class GeneratedPublicArtifact:
    """Content-addressed files safe to hand to a public delivery adapter."""

    files: Mapping[str, bytes]


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        .encode("utf-8")
        + b"\n"
    )


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _reject_unknown(value: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"unexpected field on {label}: {unknown[0]}")
    missing = sorted(allowed - set(value))
    if missing:
        raise ValueError(f"missing field on {label}: {missing[0]}")


def _require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    if "\r" in value:
        raise ValueError(f"{label} must use LF line endings")
    return value


def _validated_https_url(value: Any, label: str) -> tuple[str, str]:
    url = _require_text(value, label)
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(f"{label} must be an approved HTTPS URL")
    return url, parsed.hostname.lower()


def _validate_internal_action(value: Any, label: str, origin_host: str) -> None:
    action = _require_mapping(value, label)
    _reject_unknown(action, _INTERNAL_ACTION_FIELDS, label)
    _require_text(action["label"], f"{label}.label")
    _, host = _validated_https_url(action["href"], f"{label}.href")
    if host != origin_host:
        raise ValueError(f"{label}.href must use the canonical Seasons host")


def _validate_external_action(value: Any, label: str) -> None:
    action = _require_mapping(value, label)
    _reject_unknown(action, _EXTERNAL_ACTION_FIELDS, label)
    _require_text(action["label"], f"{label}.label")
    _, host = _validated_https_url(action["href"], f"{label}.href")
    approved_hosts = action["approvedHosts"]
    if not isinstance(approved_hosts, list) or not approved_hosts:
        raise ValueError(f"{label}.approvedHosts must be a non-empty list")
    for approved_host in approved_hosts:
        _require_text(approved_host, f"{label}.approvedHosts item")
        if approved_host != approved_host.lower() or "*" in approved_host or "/" in approved_host:
            raise ValueError(f"{label}.approvedHosts must contain exact lowercase hosts")
    if host not in approved_hosts:
        raise ValueError(f"{label}.href host is not approved")


def _validate_release_schema(release: Mapping[str, Any]) -> None:
    _reject_unknown(release, _RELEASE_FIELDS, "sealed release")
    if release["schemaVersion"] != "1" or release["templateContractVersion"] != "1":
        raise ValueError("unsupported release or template contract version")
    _require_text(release["releaseId"], "releaseId")
    if not re.fullmatch(r"[0-9a-f]{64}", _require_text(release["releaseSha256"], "releaseSha256")):
        raise ValueError("releaseSha256 must be lowercase SHA-256")
    origin, origin_host = _validated_https_url(release["canonicalOrigin"], "canonicalOrigin")
    if origin != "https://getseasons.app":
        raise ValueError("canonicalOrigin must be https://getseasons.app")

    credits = _require_mapping(release["credits"], "credits")
    _reject_unknown(credits, _CREDITS_FIELDS, "credits")
    if credits["tmdbNotice"] != "This product uses the TMDB API but is not endorsed or certified by TMDB.":
        raise ValueError("credits.tmdbNotice must use the accepted exact notice")
    _require_text(credits["justWatchAttribution"], "credits.justWatchAttribution")

    assets = release["publicAssets"]
    if not isinstance(assets, list):
        raise ValueError("publicAssets must be a list")
    asset_ids: set[str] = set()
    for index, raw_asset in enumerate(assets):
        asset = _require_mapping(raw_asset, f"publicAssets[{index}]")
        _reject_unknown(asset, _ASSET_FIELDS, f"publicAssets[{index}]")
        asset_id = _require_text(asset["assetId"], f"publicAssets[{index}].assetId")
        if asset_id in asset_ids:
            raise ValueError(f"duplicate public asset: {asset_id}")
        asset_ids.add(asset_id)
        if asset["kind"] != "screenshot":
            raise ValueError("only publication-cleared screenshot assets are supported")
        if asset["mediaType"] not in {"image/png", "image/jpeg", "image/webp"}:
            raise ValueError("unsupported public asset media type")
        if not re.fullmatch(r"[0-9a-f]{64}", _require_text(asset["sha256"], "asset.sha256")):
            raise ValueError("asset.sha256 must be lowercase SHA-256")
        try:
            content = base64.b64decode(asset["contentBase64"], validate=True)
        except (ValueError, TypeError) as error:
            raise ValueError("asset.contentBase64 must be canonical base64") from error
        if _sha256(content) != asset["sha256"]:
            raise ValueError("public asset SHA-256 does not match its bytes")

    pages = release["pages"]
    if not isinstance(pages, list):
        raise ValueError("pages must be a list")
    seen_response_ids: set[str] = set()
    seen_canonical_urls: set[str] = set()
    referenced_asset_ids: set[str] = set()
    for index, raw_page in enumerate(pages):
        label = f"pages[{index}]"
        page = _require_mapping(raw_page, label)
        _reject_unknown(page, _PAGE_FIELDS, label)
        response_id = _require_text(page["responseId"], f"{label}.responseId")
        if response_id in seen_response_ids:
            raise ValueError(f"duplicate responseId: {response_id}")
        seen_response_ids.add(response_id)
        if page["actionKind"] not in {"cancel", "start"}:
            raise ValueError(f"{label}.actionKind is unsupported")
        provider_id = page["tmdbProviderId"]
        if not isinstance(provider_id, int) or isinstance(provider_id, bool) or provider_id <= 0:
            raise ValueError(f"{label}.tmdbProviderId must be a positive integer")
        region = _require_text(page["region"], f"{label}.region")
        if region == "GG" or not re.fullmatch(r"[A-Z]{2}", region):
            raise ValueError(f"{label}.region must be canonical uppercase and cannot be GG")
        for field in (
            "providerDisplayName", "countryDisplayName", "locale", "title",
            "metaDescription", "h1", "summary", "creditsHref",
            "contextualSeasonsReturnPrefix",
            "contextualSeasonsReturnLabel",
        ):
            _require_text(page[field], f"{label}.{field}")
        if page["outcome"] not in _OUTCOMES:
            raise ValueError(f"{label}.outcome is unsupported")
        if page["outcome"] == "guide":
            raise ValueError("zero-publication rendering cannot accept a published guide")
        if page["indexability"] not in {"index", "noindex"}:
            raise ValueError(f"{label}.indexability is unsupported")
        if page["indexability"] == "index" and page["outcome"] != "guide":
            raise ValueError("only current published guides may be indexable")
        if page["httpStatus"] not in {200, 400, 404}:
            raise ValueError(f"{label}.httpStatus is unsupported for a page")
        canonical_url, canonical_host = _validated_https_url(page["canonicalUrl"], f"{label}.canonicalUrl")
        expected_url = f"{origin}/provider-actions/{page['actionKind']}/{provider_id}/{region}/"
        if canonical_host != origin_host or canonical_url != expected_url:
            raise ValueError(f"{label}.canonicalUrl is not the exact canonical pair URL")
        if canonical_url in seen_canonical_urls:
            raise ValueError(f"duplicate canonicalUrl: {canonical_url}")
        seen_canonical_urls.add(canonical_url)
        for sequence_name in ("warnings", "orderedSteps", "resolvedBranches", "supportBlocks"):
            if not isinstance(page[sequence_name], list):
                raise ValueError(f"{label}.{sequence_name} must be a list")
        for warning in page["warnings"]:
            _require_text(warning, f"{label}.warnings item")
        for block_index, raw_block in enumerate(page["supportBlocks"]):
            block = _require_mapping(raw_block, f"{label}.supportBlocks[{block_index}]")
            _reject_unknown(block, _BLOCK_FIELDS, f"{label}.supportBlocks[{block_index}]")
            _require_text(block["heading"], "support block heading")
            _require_text(block["body"], "support block body")
        if page["outcome"] != "guide":
            if page["orderedSteps"] or page["resolvedBranches"] or page["providerAction"] is not None:
                raise ValueError("safe outcomes cannot expose guide steps, branches, or provider CTAs")
            if page["screenshot"] is not None:
                raise ValueError("safe outcomes cannot expose screenshots")
        elif page["indexability"] != "index":
            raise ValueError("a guide without current publication authority cannot render as a guide")
        if page["providerAction"] is not None:
            _validate_external_action(page["providerAction"], f"{label}.providerAction")
        if page["supportAction"] is not None:
            _validate_external_action(page["supportAction"], f"{label}.supportAction")
        _validate_internal_action(page["reportAction"], f"{label}.reportAction", origin_host)
        if page["reportAction"]["href"] != f"{origin}/provider-actions/report/":
            raise ValueError("reportAction.href must use the canonical report route")
        _validate_internal_action(
            page["genericSeasonsReturnAction"],
            f"{label}.genericSeasonsReturnAction",
            origin_host,
        )
        if page["genericSeasonsReturnAction"]["href"] != f"{origin}/":
            raise ValueError("genericSeasonsReturnAction.href must use the generic Seasons route")
        _, credits_host = _validated_https_url(page["creditsHref"], f"{label}.creditsHref")
        if credits_host != origin_host:
            raise ValueError("creditsHref must use the canonical Seasons host")
        if page["creditsHref"] != f"{origin}/provider-actions/credits/":
            raise ValueError("creditsHref must use the canonical Provider Actions credits route")
        prefix, prefix_host = _validated_https_url(
            page["contextualSeasonsReturnPrefix"], f"{label}.contextualSeasonsReturnPrefix"
        )
        if prefix_host != origin_host or prefix != f"{origin}/provider-actions/return/#":
            raise ValueError("contextualSeasonsReturnPrefix must be fragment-only on the Seasons host")
        if page["screenshot"] is not None:
            screenshot = _require_mapping(page["screenshot"], f"{label}.screenshot")
            _reject_unknown(screenshot, _SCREENSHOT_FIELDS, f"{label}.screenshot")
            if screenshot["state"] != "verified_publishable":
                raise ValueError("screenshot must be verified_publishable")
            if screenshot["assetId"] not in asset_ids:
                raise ValueError("screenshot must reference a sealed public asset")
            referenced_asset_ids.add(screenshot["assetId"])
            _require_text(screenshot["alt"], "screenshot.alt")
            _require_text(screenshot["rightsReference"], "screenshot.rightsReference")
        if page["outcome"] == "guide" and page["screenshot"] is None:
            raise ValueError("published guides require a verified_publishable screenshot")
    if assets and not any(page["outcome"] == "guide" for page in pages):
        raise ValueError("safe-only releases require empty publicAssets")
    if asset_ids != referenced_asset_ids:
        raise ValueError("every public asset must be referenced by exactly one eligible page")


def _verify_release_pin(release: Mapping[str, Any]) -> None:
    payload = dict(release)
    claimed_sha256 = payload.pop("releaseSha256", None)
    canonical = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    if claimed_sha256 != _sha256(canonical):
        raise ValueError("releaseSha256 does not match the sealed release payload")


def _render_page(page: Mapping[str, Any], credits: Mapping[str, Any], stylesheet_path: str) -> bytes:
    def escape(value: Any) -> str:
        return html.escape(str(value), quote=True)

    bootstrap = _BOOTSTRAP_TEMPLATE % (
        json.dumps(page["contextualSeasonsReturnPrefix"], ensure_ascii=True),
        json.dumps(page["contextualSeasonsReturnLabel"], ensure_ascii=True),
    )
    bootstrap_hash = base64.b64encode(hashlib.sha256(bootstrap.encode("utf-8")).digest()).decode("ascii")
    robots = "index, follow" if page["indexability"] == "index" else "noindex, nofollow"
    warnings = "".join(f'<p class="warning">{escape(item)}</p>' for item in page["warnings"])
    support_blocks = "".join(
        f'<section><h2>{escape(block["heading"])}</h2><p>{escape(block["body"])}</p></section>'
        for block in page["supportBlocks"]
    )
    actions = []
    for name in ("providerAction", "supportAction", "reportAction"):
        action = page[name]
        if action is not None:
            actions.append(f'<a class="button" href="{escape(action["href"])}">{escape(action["label"])}</a>')
    generic = page["genericSeasonsReturnAction"]
    actions.append(
        f'<a class="button secondary" id="seasons-return" href="{escape(generic["href"])}">'
        f'{escape(generic["label"])}</a>'
    )
    document = f"""<!doctype html>
<html lang="{escape(page['locale'])}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<meta http-equiv="content-security-policy" content="default-src 'none'; script-src 'sha256-{bootstrap_hash}'; style-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'">
<script>
{bootstrap}
</script>
<title>{escape(page['title'])}</title>
<meta name="description" content="{escape(page['metaDescription'])}">
<meta name="robots" content="{robots}">
<link rel="canonical" href="{escape(page['canonicalUrl'])}">
<link rel="stylesheet" href="/provider-actions/{escape(stylesheet_path)}">
</head>
<body>
<main>
<article class="shell">
<p class="eyebrow">{escape(page['providerDisplayName'])} in {escape(page['countryDisplayName'])}</p>
<h1>{escape(page['h1'])}</h1>
<p>{escape(page['summary'])}</p>
{warnings}
{support_blocks}
<nav class="actions" aria-label="Available actions">{''.join(actions)}</nav>
<footer>
<a href="{escape(page['creditsHref'])}">Credits and data attribution</a>
<p>{escape(credits['tmdbNotice'])}</p>
<p>{escape(credits['justWatchAttribution'])}</p>
</footer>
</article>
</main>
</body>
</html>
"""
    return document.encode("utf-8")


def render(sealed_public_release: Mapping[str, Any]) -> GeneratedPublicArtifact:
    """Render a sealed release into deterministic, content-addressed public files."""

    _validate_release_schema(sealed_public_release)
    _verify_release_pin(sealed_public_release)
    stylesheet_sha = _sha256(_STYLESHEET)
    stylesheet_path = f"assets/provider-actions-{stylesheet_sha}.css"
    files: dict[str, bytes] = {stylesheet_path: _STYLESHEET}
    responses = []
    published_guide_count = 0

    ordered_pages = sorted(
        sealed_public_release["pages"],
        key=lambda page: (page["tmdbProviderId"], page["region"], page["outcome"]),
    )
    for page in ordered_pages:
        content = _render_page(page, sealed_public_release["credits"], stylesheet_path)
        content_sha = _sha256(content)
        path = f"responses/{content_sha}.html"
        files[path] = content
        if page["outcome"] == "guide" and page["indexability"] == "index":
            published_guide_count += 1
        responses.append(
            {
                "actionKind": page["actionKind"],
                "canonicalUrl": page["canonicalUrl"],
                "httpStatus": page["httpStatus"],
                "indexability": page["indexability"],
                "outcome": page["outcome"],
                "path": path,
                "region": page["region"],
                "responseId": page["responseId"],
                "sha256": content_sha,
                "tmdbProviderId": page["tmdbProviderId"],
            }
        )

    manifest = {
        "files": [
            {"path": path, "sha256": _sha256(content), "size": len(content)}
            for path, content in sorted(files.items())
        ],
        "publishedGuideCount": published_guide_count,
        "releaseId": sealed_public_release["releaseId"],
        "releaseSha256": sealed_public_release["releaseSha256"],
        "responseCount": len(responses),
        "responses": responses,
        "schemaVersion": sealed_public_release["schemaVersion"],
        "templateContractVersion": sealed_public_release["templateContractVersion"],
    }
    files["manifest.json"] = _canonical_json(manifest)
    sorted_files = dict(sorted(files.items()))
    _validate_public_artifact_structure(sorted_files)
    return GeneratedPublicArtifact(MappingProxyType(sorted_files))


def verify_artifact_directory(
    directory: Path,
    sealed_public_release: Mapping[str, Any],
) -> dict:
    """Require a directory to exactly equal a fresh render of a pinned release."""

    expected = render(sealed_public_release)
    return _scan_artifact_directory(directory, expected_files=expected.files)

__all__ = ["GeneratedPublicArtifact", "render", "verify_artifact_directory"]
