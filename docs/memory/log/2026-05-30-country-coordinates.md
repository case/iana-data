---
title: Country point-coordinate overlay for no-polygon territories
summary: data/manual/country-coordinates.json overlays info_link + Wikidata P625 coordinates onto derived country records that have no map polygon; identity stays pycountry-derived
created: 2026-05-30
author: Eric Case
tags: [places, coordinates, wikidata, build, maps]
---

# Country coordinate overlay (2026-05-30)

Countries are derived mechanically from pycountry and were intentionally *areas* with no stored point ("rendered from geometry, so not here"). Downstream consumers need to render every ccTLD, but ~12 territories have **no boundary polygon** in the Natural Earth 50m dataset — either too small (`bv cc cx tk gi`), folded into their sovereign (`gf gp mq re yt` → France, `sj` → Norway), or non-ISO (`ac`). Those can only be shown as a **map pin**, which needs a lat/lon the geometry can't supply.

The decision (driven by a downstream consumer's needs; augment over move):

- **`data/manual/country-coordinates.json`** — editorial overlay keyed by country slug, each entry an `info_link` (Wikipedia URL) and, once fetched, `coordinates: {lat, lon}`. Currently the 12 no-polygon territories.
- **Augment, not move.** These slugs stay pycountry-derived countries; the build overlays only `info_link` + `coordinates` onto the existing record (`src/build/places.py:_overlay_country_coordinates`). Rejected the alternative of moving them into `data/manual/places.json` (the `claimed`-reroute), which would have dropped their derived `iso_numeric`/`iso_designation` and forced hand-maintaining identity fields — a drift surface.
- **Coordinates from Wikidata P625**, same mechanism as the 57 geo places. `scripts/fetch_place_coordinates.py` now processes both files: `places.json` (subtype-filtered) and the overlay (`subtypes=None`, no subtype field). Run `bin/fetch-coordinates` on demand; never in the build.

**Why it matters:** revises the "countries carry no coordinates" invariant to "countries carry no coordinates *except* no-polygon territories, via an additive overlay." Scope is driven by the consumer's polygon coverage, but iana-data stays decoupled — the overlay is just an explicit editorial list, no Natural Earth knowledge upstream.
