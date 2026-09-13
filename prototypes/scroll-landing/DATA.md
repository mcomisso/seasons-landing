# Artwork and freshness

`data.json` contains the first 12 TV results returned by Seasons' public `trendingThisWeek` onboarding catalog for GB and en-GB. The initial snapshot was fetched and verified on 13 September 2026. `generatedAt` and `staleAt` come from the source response; `updatedAt` records the refresh time. Trending is the source's weekly trend order, not a claim about UK audience size.

Source: [Seasons public trending catalog](https://seasons-backend.fly.dev/v2/onboarding/catalog/browse?mediaType=tv&category=trendingThisWeek&region=GB&language=en-GB&page=1).

Posters are actual TMDB artwork. All 12 poster and six provider image URLs returned HTTP 200 with `image/jpeg` during verification. The provider logos represent familiar streaming services. They are not a verified popularity ranking, and their placement must not imply that a particular show is available on that provider in GB.

The six provider artwork paths are pinned independently from trending. Netflix, Prime Video and Sky Go also occur in the app's existing TMDB fixture. A current provider catalog refresh is supported using a server-side TMDB token, because Seasons' provider endpoint requires account authentication. Do not expose that token in HTML or JavaScript.

## Refresh

From this directory:

```sh
python3 refresh_data.py
```

This requires network access and no credentials. It replaces the snapshot only after a successful response containing at least 12 usable posters. Failure preserves the previous snapshot. To refresh provider names and logos from TMDB too, run the same command with `TMDB_READ_ACCESS_TOKEN` set securely in the process environment. The script never serializes or prints the token.

The prototypes are local explorations. A snapshot is not an automatic freshness service. For a published landing page, run this script during a daily scheduled build, publish the resulting JSON, and retain the visible refresh date if refresh fails. Avoid calling the anonymous backend endpoint separately from every animation or every frame. Public endpoint caching and rate limits still apply.

## Rendering contract

```text
shows: [{id, title, poster, backdrop, rank}]
providers: [{id, name, logo}]
updatedAt, generatedAt, staleAt, sourceUrl, region, attribution, providerSource
```

Display provider artwork in circles and title posters in rounded rectangles. Include the supplied TMDB notice and link: "This product uses the TMDB API but is not endorsed or certified by TMDB." Artwork remains owned by its respective rights holders.
