#!/usr/bin/env python3
"""Refresh the public landing-page trending snapshot from the Seasons API."""
from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "trending-shows.json"
SOURCE = "https://seasons-backend.fly.dev/v2/onboarding/catalog/browse?" + urlencode({"mediaType":"tv","category":"trendingThisWeek","region":"GB","language":"en-GB","page":1})
IMAGE = "https://image.tmdb.org/t/p/"
MAX_SNAPSHOT_AGE = timedelta(days=8)


class NetworkLogoParser(HTMLParser):
    """Find the first network logo in a public TMDB title page."""

    def __init__(self) -> None:
        super().__init__()
        self.in_network_section = False
        self.result: dict[str, str] | None = None

    def handle_data(self, data: str) -> None:
        if data.strip() == "Network":
            self.in_network_section = True

    def handle_starttag(self, tag: str, attributes: list[tuple[str, str | None]]) -> None:
        if tag != "img" or not self.in_network_section or self.result is not None:
            return
        values = dict(attributes)
        source, name = values.get("src"), values.get("alt")
        if source and name and "/t/p/" in source:
            path = source.split("/t/p/", 1)[1].split("/", 1)[1]
            prefix = "See more TV shows from "
            clean_name = name.removeprefix(prefix).removesuffix("...")
            self.result = {"id": path, "name": clean_name, "logo": IMAGE + "w185/" + path}


def fetch_network(tmdb_id: int) -> dict[str, str] | None:
    request = Request(
        f"https://www.themoviedb.org/tv/{tmdb_id}",
        headers={"Accept": "text/html", "User-Agent": "Seasons-Landing/1.0"},
    )
    with urlopen(request, timeout=20) as response:
        parser = NetworkLogoParser()
        parser.feed(response.read().decode("utf-8", errors="replace"))
    return parser.result


def current_networks(shows: list[dict[str, object]]) -> list[dict[str, str]]:
    networks: list[dict[str, str]] = []
    seen: set[str] = set()
    for show in shows:
        network = fetch_network(int(show["id"]))
        if network and network["name"] not in seen:
            networks.append(network)
            seen.add(network["name"])
        if len(networks) == 6:
            break
    if len(networks) < 4:
        raise ValueError("fewer than 4 current network logos")
    return networks


def checked_in_snapshot() -> dict[str, object]:
    snapshot = json.loads(OUTPUT.read_text(encoding="utf-8"))
    updated = datetime.fromisoformat(str(snapshot["updatedAt"]).replace("Z", "+00:00"))
    if datetime.now(timezone.utc) - updated > MAX_SNAPSHOT_AGE:
        raise RuntimeError("checked-in trending snapshot is older than 8 days")
    return snapshot

def main() -> int:
    try:
        request = Request(SOURCE, headers={"Accept":"application/json","User-Agent":"Seasons-Landing/1.0"})
        with urlopen(request, timeout=30) as response:
            page = json.load(response)
        shows = [{"id":item["tmdbId"],"title":item["title"],"poster":IMAGE+"w342"+item["posterPath"],"rank":rank} for rank,item in enumerate(page["items"],1) if item.get("posterPath")][:12]
        if len(shows) < 12:
            raise ValueError("fewer than 12 posters")
        networks = current_networks(shows)
        snapshot = {"updatedAt":datetime.now(timezone.utc).isoformat(),"generatedAt":page["generatedAt"],"staleAt":page["staleAt"],"sourceUrl":SOURCE,"region":"GB","attribution":page["attribution"],"providerSource":"Networks associated with the current trending titles on TMDB","shows":shows,"providers":networks}
        OUTPUT.write_text(json.dumps(snapshot,separators=(",",":"),ensure_ascii=False)+"\n",encoding="utf-8")
        print(f"refreshed {len(shows)} landing-page shows and {len(networks)} networks")
    except Exception as error:
        if not OUTPUT.is_file():
            raise
        checked_in_snapshot()
        print(f"landing trends refresh unavailable; using checked-in snapshot: {type(error).__name__}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
