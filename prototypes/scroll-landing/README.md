# Seasons motion prototypes

Five throwaway landing-page directions answer the same question: which scroll sequence best explains scattered shows and services becoming an ordered Seasons watch plan?

Run from the landing repository:

```sh
python3 prototypes/scroll-landing/serve.py
```

Open http://localhost:8765/prototypes/scroll-landing/?variant=A. Use the floating selector or left/right arrow keys. Scroll normally to reverse or advance the animation. Replay returns to the start. Reduce motion replaces the animation with static artwork and a shorter page.

| Variant | Direction | Composition |
| --- | --- | --- |
| A | The gathering | Light, centered cloud and funnel based on the supplied sketch |
| B | In orbit | Dark orbital movement into the Seasons mark |
| C | The filmstrip | Warm editorial typography and horizontal poster lanes |
| D | Make room | Left-aligned story with the assembly on the right, centered on phones |
| E | Into focus | Dark tunnel with depth-scaled artwork |

All use real Three.js textured meshes, staggered intake and sequential release. Posters have rounded corners; provider containers are circular. Shared catalogue content is below the pinned scene. No wheel interception or perpetual animation loop. Rendering happens on scroll, resize and variant changes.

## Data freshness

The preview server refreshes the public Seasons trending-TV snapshot at startup and every 24 hours while running. Reload the page to see refreshed data. Failed refreshes preserve the last snapshot; the page displays its date. The checked-in selection was retrieved on 13 September 2026. See DATA.md for provenance, optional provider-logo refresh credentials and the standalone refresh command.

Providers are representative services, not ranked trending networks. The animated order is illustrative and does not imply that adjacent services carry adjacent titles, or claim release dates. Production should refresh during a scheduled build or through a cached server feed. This local prototype does not change backend contracts or install a production scheduler.

## Design references

- Existing product message and supplied Seasons artwork: https://getseasons.app/
- Mobbin Apple iPhone hero, large subject and restrained navigation: https://mobbin.com/sites/sections/59514a44-5eff-4d00-bef5-4ebc45f88af0
- Mobbin Apple AirPods composition, generous whitespace: https://mobbin.com/sites/sections/c7866721-985d-44d3-b3e6-ba39c201dc12
- User sketch, cloud entering the Seasons logo and emerging in order.

Three.js 0.180.0 is vendored with its MIT license. Fonts and title artwork require internet access. WebGL failure falls back to static artwork.

Local-only study. The existing homepage and Pages staging allowlist are unchanged, so these files are excluded from deployment. No direction has been selected for production yet.
