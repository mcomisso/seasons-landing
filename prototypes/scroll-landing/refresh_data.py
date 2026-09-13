#!/usr/bin/env python3
"""Refresh public prototype artwork, without putting credentials in the browser."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
BASE = "https://seasons-backend.fly.dev"
SOURCE = BASE + "/v2/onboarding/catalog/browse?" + urlencode({
    "mediaType": "tv", "category": "trendingThisWeek", "region": "GB",
    "language": "en-GB", "page": 1,
})
IMAGE = "https://image.tmdb.org/t/p/"
PROVIDERS = [
    (8, "Netflix", "/pbpMk2JmcoNnQwx5JGpXngfoWtp.jpg"),
    (119, "Prime Video", "/dQeAar5H991VYporEjUspolDarG.jpg"),
    (350, "Apple TV+", "/6uhKBfmtzFqOcLousHwZuzcrScK.jpg"),
    (337, "Disney+", "/97yvRBw1GzX7fXprcF80er19ot.jpg"),
    (531, "Paramount+", "/xbhHHa1YgtpwhC8lb1NQ3ACVcLd.jpg"),
    (29, "Sky Go", "/1UrT2H9x6DuQ9ytNhsSCUFtTUwS.jpg"),
]


def fetch(url, token=None):
    headers = {"Accept": "application/json", "User-Agent": "Seasons-Landing-Prototype/1.0"}
    if token:
        headers["Authorization"] = "Bearer " + token
    with urlopen(Request(url, headers=headers), timeout=30) as response:
        return json.load(response)


def refresh():
    page = fetch(SOURCE)
    shows = [{"id": item["tmdbId"], "title": item["title"],
              "poster": IMAGE + "w342" + item["posterPath"],
              "backdrop": IMAGE + "w780" + item["backdropPath"] if item.get("backdropPath") else None,
              "rank": rank}
             for rank, item in enumerate(page["items"], 1) if item.get("posterPath")][:12]
    if len(shows) < 12:
        raise ValueError("Trending response contained fewer than 12 usable posters; preserving snapshot")
    providers = [{"id": id_, "name": name, "logo": IMAGE + "w185" + path}
                 for id_, name, path in PROVIDERS]
    provider_source = "Pinned TMDB artwork; representative services, not a popularity ranking"
    token = os.environ.get("TMDB_READ_ACCESS_TOKEN")
    if token:
        result = fetch("https://api.themoviedb.org/3/watch/providers/tv?watch_region=GB&language=en-GB", token)
        by_id = {item["provider_id"]: item for item in result["results"]}
        for provider in providers:
            item = by_id.get(provider["id"])
            if item and item.get("logo_path"):
                provider.update(name=item["provider_name"], logo=IMAGE + "w185" + item["logo_path"])
        provider_source = "TMDB watch/providers/tv, GB; representative services, not a popularity ranking"
    snapshot = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "generatedAt": page["generatedAt"], "staleAt": page["staleAt"],
        "sourceUrl": SOURCE, "region": "GB", "attribution": page["attribution"],
        "providerSource": provider_source, "shows": shows, "providers": providers,
    }
    temp = ROOT / "data.json.tmp"
    temp.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n")
    temp.replace(ROOT / "data.json")
    print(f"Refreshed {len(shows)} shows and {len(providers)} providers")


if __name__ == "__main__":
    refresh()
