#!/usr/bin/env python3
"""Fetch geo-place coordinates from Wikidata into data/manual/places.json and
data/manual/country-coordinates.json, looking up each record's P625 coordinate via
its Wikipedia article. Idempotent (--refresh forces); run on demand, not the build.
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

# Point geo-places we pin; countries (areas) live elsewhere, except no-polygon
# territories via the country-coordinates overlay. frozenset: it's a default arg.
GEO_SUBTYPES = frozenset({"city", "subdivision", "supranational"})


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
    subtypes: frozenset[str] | None = GEO_SUBTYPES,
    delay: float = REQUEST_DELAY,
) -> tuple[int, list[str]]:
    """Add lat/lon to records lacking them, in place. Returns (added, failed_slugs).
    ``subtypes`` filters by the ``subtype`` field; None processes all (the overlay has none)."""
    pending = [
        (slug, rec)
        for slug, rec in places.items()
        if (subtypes is None or rec.get("subtype") in subtypes)
        and (refresh or "coordinates" not in rec)
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

    places_path = Path(MANUAL_DIR) / MANUAL_FILES["PLACES"]
    places = read_json_file(places_path, default={})
    if not places:
        logger.error("no places loaded from %s", places_path)
        return 1
    overlay_path = Path(MANUAL_DIR) / MANUAL_FILES["COUNTRY_COORDINATES"]
    overlay = read_json_file(overlay_path, default={})

    failed: list[str] = []
    # 30s per request: Wikidata's wbgetentities is normally sub-second, so this only
    # bounds a stalled connection on an interactive, maintenance-time run.
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        # Non-country geo places (cities, subdivisions, supranational regions).
        added, place_failed = enrich_places(places, client, refresh=args.refresh)
        _, status = write_json_if_changed(places_path, places)
        logger.info("places.json: added=%d write=%s", added, status)
        failed += place_failed
        # Point overlay for no-polygon country territories (entries carry no subtype).
        if overlay:
            added, overlay_failed = enrich_places(
                overlay, client, refresh=args.refresh, subtypes=None
            )
            _, status = write_json_if_changed(overlay_path, overlay)
            logger.info("country-coordinates.json: added=%d write=%s", added, status)
            failed += overlay_failed
        else:
            logger.warning("country-coordinates: %s missing or empty", overlay_path)

    if failed:
        logger.warning("no coordinates for: %s", ", ".join(sorted(failed)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
