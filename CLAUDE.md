# CLAUDE.md

Guidance for agents working in `seasons-landing`.

## Purpose

This repository delivers two public surfaces for `getseasons.app`:

- hand-authored static marketing, legal, and app-handoff pages;
- deterministic public Provider Action artifacts produced from a pinned sealed release.

The marketing pages use vanilla HTML, Tailwind CDN styles, HubSpot, and Ahrefs. Generated Provider Action responses use local content-addressed CSS, one reviewed fragment bootstrap, and no third-party code.

## Provider Actions boundary

`provider_actions.render(sealedPublicRelease)` is the public rendering seam. It validates the complete sealed schema and release SHA, renders stable UTF-8 and LF bytes without a clock, and returns a content-addressed artifact with `manifest.json`, `assets/`, optional `media/`, and `responses/`.

This repository is a delivery adapter. It does not own pair resolution, provider destinations, regional fallback, freshness, rights, activation, or the private runtime index. The checked-in release is a pinned zero-publication safe baseline, and the renderer refuses published guides until the later publication-cleared integration.

Every direct artifact scan must rebuild from the same pinned sealed release and require exact byte equality. Do not weaken this to hash-shaped metadata or substring scanning. Restricted evidence and private runtime data must never enter the public artifact.

## Pages pipeline

`.github/workflows/static.yml` performs this order:

1. run the Python tests;
2. render `provider-actions-safe-baseline-release.json`;
3. exact-scan the generated artifact against that pinned render;
4. stage only the explicit allowlist plus the verified artifact into `_site`;
5. upload `_site`, never the repository root, to GitHub Pages.

`scripts/stage_pages.py` accepts only the repository-local `_site` target, rejects symlinks and unsafe inputs before replacement, and preserves the previous `_site` if validation or staging fails. When adding a public static file, update its allowlist and focused staging tests.

The root `sitemap.xml` is a sitemap index pointing to the runtime-owned `https://getseasons.app/provider-actions/sitemap.xml`. Never generate a stale static Provider Actions sitemap.

## Commands

```bash
python3 -m unittest discover -s tests -v
ruff check provider_actions scripts tests
python3 -m provider_actions render provider-actions-safe-baseline-release.json provider-actions-public-artifact
python3 -m provider_actions scan provider-actions-public-artifact provider-actions-safe-baseline-release.json
python3 scripts/stage_pages.py --output _site --provider-actions-artifact provider-actions-public-artifact --sealed-release provider-actions-safe-baseline-release.json
```

Preview `_site`, not the repository root, when checking deployable output. Do not deploy or push unless the user asks.

## Existing static integrations

- Domain: `getseasons.app`, configured by `CNAME`.
- App Store: `https://apps.apple.com/gb/app/seasons-streaming-companion/id6502302869`.
- Feedback: `feedback@getseasons.app`.
- Marketing analytics and HubSpot remain limited to the marketing page and must not enter Provider Action responses.
