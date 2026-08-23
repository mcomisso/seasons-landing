# Stop Paying for the Wait campaign pack

This directory contains publish-ready organic social assets and operating copy for the UK-first Seasons campaign.

The campaign explains one mechanism: weekly releases can cross multiple billing dates, while waiting for the finale can concentrate viewing into one paid month. It does not promise that every user will save money.

## Pack contents

- `exports/instagram/`: five-slide carousel, three-frame Story, and Reel cover.
- `exports/tiktok/`: 24-second silent vertical MP4, six storyboard frames, and cover.
- `exports/reddit/`: link-card and native proof-card images.
- `exports/previews/`: contact sheets for rapid visual review.
- `source/svg/`: deterministic SVG source for every still image.
- `scripts/render-assets.js`: reproducible PNG, preview, manifest, and MP4 renderer.
- `docs/`: worked arithmetic, platform copy, CTA library, and publishing playbook.
- `provenance/`: dated evidence and source-preservation record.
- `asset-manifest.json`: machine-readable asset inventory.

## Approved message

Campaign line:

> Stop paying for the wait.

Proof line:

> 10 weekly episodes. 3 billing dates. 1 month to binge.

Result line:

> Potential saving: £19.98.

Alternative result line:

> Waiting until the finale could avoid two £9.99 renewals in this worked example.

Primary CTA:

> Build my savings plan

Use the result only with the full qualification in `docs/worked-examples.md` and the dated source record in `provenance/source-record.md`.

## Render

From this directory:

```bash
NODE_PATH=/Users/matcom/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules \
  /Users/matcom/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node \
  scripts/render-assets.js
```

The script reads the canonical Seasons logo from `../../seasonslogo.png`. It writes exact platform dimensions, then uses FFmpeg to assemble six four-second TikTok scenes into a 24-second H.264 MP4. The video intentionally has no audio. Every spoken idea is present as burned-in on-screen copy.

## Pre-publish gate

1. Recheck the official Apple schedule and UK price.
2. Confirm the claim has not passed its expiry date in `provenance/source-record.md`.
3. Confirm the full qualification is visible in the creative or included in the post copy exactly.
4. Confirm the destination page is live before replacing the root-site UTM link with a campaign-page link.
5. Review the rendered contact sheets and the original-size final qualification frame.
6. Follow the community rules before posting on Reddit.

No provider logo, programme art, publicity still, clip, licensed music, testimonial, rating, user count, or endorsement appears in this pack.

