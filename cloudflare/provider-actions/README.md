# Provider Actions canonical route

This Cloudflare Worker owns only these public routes:

- `https://getseasons.app/provider-actions`
- `https://getseasons.app/provider-actions/*`

It forwards exact GET path and query bytes to the allowlisted backend origin,
`https://api.getseasons.app`. The backend owns pair resolution, destination
selection, guide content, release activation, and the runtime sitemap. The
Worker does not reproduce those rules.

The Worker strips browser credentials before the origin request and removes
origin cookies from the response. It accepts only origin responses with the
expected status set, `Cache-Control: no-store`, and the required browser safety
headers. A network error or unsafe response produces a keyboard-readable HTML
fallback with no redirect and no subscription state change.

Run the public route tests with:

```sh
node --test cloudflare/provider-actions/worker.test.mjs
```

## Backend interface

The backend must accept GET requests for the full `/provider-actions` path
family. It must preserve the original validation behavior for encoded paths and
query strings. Valid responses use status 200, 302, 400, or 404 and include:

- `Cache-Control: no-store`
- `Content-Security-Policy`
- `Referrer-Policy: no-referrer`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-Robots-Tag`

Canonical readback also needs the backend to expose its sealed release ID and,
when applicable, region and TMDB provider ID as stable response headers. The
Worker preserves those headers unchanged.

## Activation and rollback

`wrangler.toml` selects proxy mode. `wrangler.safe-baseline.toml` selects the
same route family in safe-baseline mode. Safe-baseline mode returns a 503 page
without contacting the backend. It is the containment option when a compatible
previous Worker and backend release cannot both be restored.

Before activation, record the current Worker version, exact route bindings,
backend release ID, Fly image digest, Pages deployment SHA, and compatible
predecessor. Deploy `wrangler.staging.toml` first. It uses the separately named
`seasons-provider-actions-router-staging` Worker on workers.dev and has no
`getseasons.app` routes. Probe its response matrix, then deploy `wrangler.toml`
only if the recorded production state is still current. Never bind
`getseasons.app/*`.

Rollback must restore the recorded compatible Worker and backend release as a
pair. If that pair is unavailable, deploy `wrangler.safe-baseline.toml`. After
either action, test the full canonical matrix and confirm unrelated GitHub Pages
URLs remain unchanged. Removing the routes is containment, not proof of a
successful rollback.
