#!/usr/bin/env python3
"""Fetch geo-place coordinates from Wikidata into data/manual/places.json.

For each place lacking lat/lon, looks up its Wikipedia article's P625 coordinate
and writes it back. Idempotent (--refresh forces); run on demand, not in the build.
"""

import argparse
import logging
import sys
import time
import urllib.parse
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import MANUAL_DIR, MANUAL_FILES  # noqa: E402
from src.utilities.content_changed import write_json_if_changed  # noqa: E402
from src.utilities.file_io import read_json_file  # noqa: E402
from src.utilities.retry import ServerError, make_request_with_retry  # noqa: E402

logger = logging.getLogger(__name__)

WIKIDATA_API_URL = "https://www.wikidata.org/w/api.php"
# Wikimedia asks for a descriptive User-Agent and may block generic ones.
USER_AGENT = "iana-data (+https://github.com/case/iana-data)"
REQUEST_DELAY = 0.5  # politeness between Wikidata calls
COORD_PRECISION = 5  # ~1 m; ample for a map pin

# data/manual/places.json holds only non-country geo places; every one is a
# point we pin. Countries are areas (rendered from geometry), so not here.
GEO_SUBTYPES = {"city", "subdivision", "supranational"}


def enwiki_title_from_url(info_link: str) -> str | None:
    """Extract the English Wikipedia article title from an info_link URL."""
    marker = "/wiki/"
    if marker not in info_link:
        return None
    slug = info_link.split(marker, 1)[1]
    slug = slug.split("#", 1)[0].split("?", 1)[0].rstrip("/")
    return urllib.parse.unquote(slug).replace("_", " ") or None


def parse_coordinate_claim(entity: dict) -> tuple[float, float]:
    """Extract (lat, lon) from a Wikidata entity's P625 claim.

    Raises ``ValueError`` if the claim is missing, malformed, or out of range.
    """
    try:
        value = entity["claims"]["P625"][0]["mainsnak"]["datavalue"]["value"]
        lat = float(value["latitude"])
        lon = float(value["longitude"])
    except (KeyError, IndexError, TypeError, ValueError) as e:
        raise ValueError(f"no usable P625 coordinate claim: {e}") from e
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise ValueError(f"coordinate out of range: lat={lat} lon={lon}")
    return lat, lon


def fetch_coordinates(client: httpx.Client, title: str) -> tuple[float, float]:
    """Fetch (lat, lon) for an enwiki article title via the Wikidata API."""
    params = urllib.parse.urlencode(
        {
            "action": "wbgetentities",
            "sites": "enwiki",
            "titles": title,
            "props": "claims",
            "format": "json",
        }
    )
    url = f"{WIKIDATA_API_URL}?{params}"
    response = make_request_with_retry(client, url, headers={"User-Agent": USER_AGENT})
    if response.status_code != 200:
        raise ValueError(f"HTTP {response.status_code}")
    entities = response.json().get("entities", {})
    if not entities:
        raise ValueError("no entity for title")
    entity = next(iter(entities.values()))
    return parse_coordinate_claim(entity)


def enrich_places(
    places: dict,
    client: httpx.Client,
    *,
    refresh: bool,
    delay: float = REQUEST_DELAY,
) -> tuple[int, list[str]]:
    """Add lat/lon to geo places in place. Returns (added_count, failed_slugs)."""
    pending = [
        (slug, rec)
        for slug, rec in places.items()
        if rec.get("subtype") in GEO_SUBTYPES and (refresh or "coordinates" not in rec)
    ]
    added = 0
    failed: list[str] = []
    made_request = False
    for slug, rec in pending:
        title = enwiki_title_from_url(rec.get("info_link", ""))
        if title is None:
            logger.warning("%s: no Wikipedia title in info_link", slug)
            failed.append(slug)
            continue
        # Space every request (success or failure) by delaying before all but
        # the first; title-less skips make no request, so they don't count.
        if made_request and delay > 0:
            time.sleep(delay)
        made_request = True
        try:
            lat, lon = fetch_coordinates(client, title)
        except (ValueError, httpx.HTTPError, ServerError) as e:
            logger.warning("%s (%s): %s", slug, title, e)
            failed.append(slug)
            continue
        rec["coordinates"] = {
            "lat": round(lat, COORD_PRECISION),
            "lon": round(lon, COORD_PRECISION),
        }
        added += 1
        logger.info(
            "%s: %.5f, %.5f", slug, rec["coordinates"]["lat"], rec["coordinates"]["lon"]
        )
    return added, failed


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="re-fetch coordinates even for places that already have them",
    )
    args = parser.parse_args()

    path = Path(MANUAL_DIR) / MANUAL_FILES["PLACES"]
    places = read_json_file(path, default={})
    if not places:
        logger.error("no places loaded from %s", path)
        return 1

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        added, failed = enrich_places(places, client, refresh=args.refresh)

    _, status = write_json_if_changed(path, places)
    logger.info("added=%d failed=%d write=%s", added, len(failed), status)
    if failed:
        logger.warning("no coordinates for: %s", ", ".join(sorted(failed)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
