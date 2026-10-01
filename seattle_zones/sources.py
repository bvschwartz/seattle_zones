"""Load named street centerlines as (name, [(lon, lat), ...]) pairs.

Two sources are supported:

* OpenStreetMap via the Overpass API (default, no key needed).
* Any local GeoJSON of street centerlines, e.g. the City of Seattle
  "Street Network Database" export from data.seattle.gov.
"""

import json
import os

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Ordinary city streets. Freeways and ramps are left out: they cross zones and
# rarely carry a directional.
HIGHWAY_TYPES = (
    "primary", "secondary", "tertiary", "residential",
    "unclassified", "living_street",
)

OVERPASS_QUERY = """
[out:json][timeout:300];
area["name"="Seattle"]["boundary"="administrative"]["admin_level"="8"]->.city;
way(area.city)["highway"~"^({types})$"]["name"];
out tags geom;
"""

# Property names tried, in order, when reading a GeoJSON without --name-field.
NAME_FIELDS = ("name", "NAME", "STNAME_ORD", "ORD_STNAME_CONCAT", "UNITDESC", "FULLNAME")


def fetch_osm(cache_path, refresh=False, url=OVERPASS_URL):
    """Download Seattle streets from Overpass, caching the raw response."""
    if refresh or not os.path.exists(cache_path):
        import requests

        query = OVERPASS_QUERY.format(types="|".join(HIGHWAY_TYPES))
        resp = requests.post(url, data={"data": query}, timeout=360,
                             headers={"User-Agent": "seattle_zones/0.1"})
        resp.raise_for_status()
        os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
        with open(cache_path, "w") as f:
            f.write(resp.text)
    with open(cache_path) as f:
        data = json.load(f)
    return list(_osm_streets(data))


def _osm_streets(data):
    for el in data.get("elements", []):
        name = el.get("tags", {}).get("name")
        geom = el.get("geometry")
        if el.get("type") == "way" and name and geom and len(geom) >= 2:
            yield name, [(p["lon"], p["lat"]) for p in geom]


def load_geojson(path, name_field=None):
    """Read LineString/MultiLineString features with a street-name property."""
    with open(path) as f:
        data = json.load(f)
    streets = []
    for feat in data.get("features", []):
        props = feat.get("properties") or {}
        name = props.get(name_field) if name_field else next(
            (props[k] for k in NAME_FIELDS if props.get(k)), None)
        geom = feat.get("geometry") or {}
        if not name:
            continue
        if geom.get("type") == "LineString":
            lines = [geom["coordinates"]]
        elif geom.get("type") == "MultiLineString":
            lines = geom["coordinates"]
        else:
            continue
        for line in lines:
            if len(line) >= 2:
                streets.append((name, [tuple(c[:2]) for c in line]))
    return streets
