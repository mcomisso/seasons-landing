# Source and provenance record

## Claim record

| Field | Value |
|---|---|
| Campaign | Stop Paying for the Wait |
| Market | United Kingdom |
| Claim type | Modelled worked example |
| Checked date | 23 August 2026 |
| Claim expiry | 23 September 2026, or immediately after a source or product change |
| Owner | Unassigned. Assign before publication. |
| Result | Potential saving: £19.98 |
| Required qualifier | Worked example, cancellable UK £9.99 monthly plan, exact dates, one binge month, and no other Apple TV viewing in the release window |

## Evidence

- Schedule: [Apple release schedule for Your Friends & Neighbors season two](https://www.apple.com/tv-pr/news/2025/12/apples-acclaimed-drama-your-friends-neighbors-starring-and-executive-produced-by-jon-hamm-returns-for-season-two-on-friday-april-3-2026/)
- Price and monthly-plan terms: [Apple TV UK](https://www.apple.com/uk/apple-tv-plus/)
- Advertising boundary: [CAP Code section 3](https://www.asa.org.uk/type/non_broadcast/code_section/03.html)
- Internal research synthesis: `../../../../SeasonsBackend/docs/research/streaming-savings-marketing-model-2026-08-23.md`
- Approved campaign plan: `../../../docs/plans/2026-08-23-stop-paying-for-the-wait-campaign.md`

## Source preservation

The renderer reads the canonical Seasons logo from `../../seasonslogo.png`. It embeds the pixels without redrawing or relabelling the mark. Existing product screenshots were reviewed but intentionally excluded because they include programme artwork and provider marks that are not required for this proof-led campaign.

All factual copy, figures, dates, qualification text, source labels, dimensions, and logo placement are produced deterministically from `scripts/render-assets.js`. No image-generation model was used. No testimonials, ratings, user counts, prices beyond the sourced example, endorsements, provider logos, show art, clips, or music were invented or imported.

## Verification status

The asset renderer and exact export checks must be rerun after any edit. Record the current file hashes in `verification-sha256.txt`; regenerated outputs are expected to remain byte-stable when the same Sharp and FFmpeg versions are used.
