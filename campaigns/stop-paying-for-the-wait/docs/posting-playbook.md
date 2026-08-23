# Posting playbook

## Suggested launch cadence

| Day | Platform | Asset | Purpose |
|---|---|---|---|
| Monday | Instagram | Five-slide carousel | Explain the full mechanism |
| Wednesday | TikTok | 24-second proof video | Test hook retention and shares |
| Friday | Instagram | Story sequence | Drive a qualified action |
| Following Monday | Reddit | One community-specific text post | Invite scrutiny and collect objections |
| Following Wednesday | Instagram Reels | Proof video with Reel cover | Reuse the strongest vertical master |

Do not post identical Reddit copy to multiple communities on the same day. Adapt one variant to one community after reading its rules and recent discussions.

## Preflight checklist

1. Open both official Apple sources and recheck the schedule, monthly UK price, product name, and plan terms.
2. Record the check date and reviewer in `provenance/source-record.md`.
3. Stop if the record is expired, the price changed, the schedule changed, or the monthly plan is no longer eligible.
4. Confirm “Potential saving” or “could avoid” appears with every £19.98 result.
5. Include the exact qualification and source line in the creative or same-post copy.
6. Confirm the destination URL resolves and preserves the UTM parameters.
7. Confirm the iOS destination is live before describing it as an install path. Keep Android language waitlist-only until store availability is separately verified.
8. Preview on a phone at normal size. Confirm the qualification is readable and no platform UI covers it.
9. Add platform alt text. Confirm colour is not the only way a billing date or finale is communicated.
10. Save a screenshot or URL of the published post in the campaign log.

## Accessibility

- Use the supplied alt text as a starting point and edit it if platform stickers change the content.
- Keep the video understandable with sound off. The supplied MP4 has burned-in captions and no audio.
- Do not add rapid flashing, copyrighted footage, provider logos, show artwork, or unlicensed audio.
- Keep text inside platform-safe areas. Story and TikTok overlays should not cover the brand, CTA, amount, qualification, or source line.
- Preserve strong contrast and the text labels attached to amber billing markers and the green finale flag.

## Source refresh and claim expiry

The schedule is tied to a dated official announcement. The price and plan terms are more volatile. The public claim expires on 23 September 2026 unless it is rechecked sooner. Any source correction, price change, plan-term change, schedule change, or product-behaviour change invalidates the asset immediately.

When refreshing:

1. Update the evidence record and checked date.
2. Update the constants and visible dates in `scripts/render-assets.js` if required.
3. Update all platform copy and the worked-example document.
4. Rerun the deterministic renderer.
5. Verify dimensions, arithmetic, contact sheets, and video metadata again.
6. Record the new hashes and approval before publishing.

Do not edit a currency figure directly in a PNG or social composer.

## Moderation and community handling

- Disclose the builder affiliation near the top.
- Lead with useful arithmetic and assumptions.
- Follow moderator direction immediately.
- Post in one relevant community at a time.
- Answer eligibility objections directly. Annual plans, bundles, another wanted show, minimum terms, and changed prices can make the example inapplicable.
- Thank people for corrections and verify them before responding with certainty.
- Do not use fake questions, fake testimonials, vote solicitation, private-message funnels, or repeated promotional comments.
- Remove or correct a stale numeric claim rather than defending it.

## Attribution and reporting

Use the UTM pattern in `cta-library.md`. Record platform, asset ID, post URL, publish time, source-check date, CTA destination, and moderation outcome. Report reach, saves, shares, qualified site visits, attributed first opens, and current complete Personal Plans separately. A click, app-store visit, cancellation handoff, or user confirmation is not proof that money was saved.

