"""Load named street centerlines as (name, [(lon, lat), ...]) pairs, and the
place boundary to trim zones to.

Two sources are supported:

* OpenStreetMap via the Overpass API (default, no key needed), for any city
  or county by name, along with its official boundary.
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

# One request returns the place's boundary relation (with geometry) followed by
# its named streets. The state filter keeps e.g. King County, WA apart from
# King County, TX.
OVERPASS_QUERY = """
[out:json][timeout:600];
area["ISO3166-2"="{state}"]["admin_level"="4"]->.state;
rel(area.state)["boundary"="administrative"]["admin_level"="{admin_level}"]["name"="{place}"]->.rel;
.rel out geom;
.rel map_to_area->.place;
way(area.place)["highway"~"^({types})$"]["name"];
out tags geom;
"""

# Property names tried, in order, when reading a GeoJSON without --name-field.
NAME_FIELDS = ("name", "NAME", "STNAME_ORD", "ORD_STNAME_CONCAT", "UNITDESC", "FULLNAME")


def slug(place):
    return "".join(c if c.isalnum() else "_" for c in place.lower()).strip("_")


def fetch_osm(place="Seattle", admin_level=8, state="US-WA", cache_path=None,
              refresh=False, url=OVERPASS_URL):
    """Download a place's named streets and boundary from Overpass.

    admin_level is OSM's: 8 for a city, 6 for a county. The raw response is
    cached in cache_path (default data/<place>.json).

    Returns (streets, boundary) where boundary is a shapely (Multi)Polygon in
    lon/lat, or None if OSM has no boundary for the place.
    """
    cache_path = cache_path or os.path.join("data", slug(place) + ".json")
    if refresh or not os.path.exists(cache_path):
        import requests

        query = OVERPASS_QUERY.format(place=place, admin_level=admin_level, state=state,
                                      types="|".join(HIGHWAY_TYPES))
        print(f"Downloading {place} streets from OpenStreetMap "
              "(first run only; this can take a few minutes)...", flush=True)
        resp = requests.post(url, data={"data": query}, timeout=660,
                             headers={"User-Agent": "seattle_zones/0.1"})
        resp.raise_for_status()
        os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
        with open(cache_path, "w") as f:
            f.write(resp.text)
    with open(cache_path) as f:
        data = json.load(f)
    streets = list(_osm_streets(data))
    if not streets:
        raise SystemExit(f"OpenStreetMap returned no streets for {place!r} "
                         f"(admin_level {admin_level}, {state}). Check the spelling, "
                         f"or delete {cache_path} and retry if the download was cut short.")
    return streets, _osm_boundary(data)


def _osm_streets(data):
    for el in data.get("elements", []):
        name = el.get("tags", {}).get("name")
        geom = el.get("geometry")
        if el.get("type") == "way" and name and geom and len(geom) >= 2:
            yield name, [(p["lon"], p["lat"]) for p in geom]


def _osm_boundary(data):
    """Assemble the boundary relation's outer/inner ways into polygons."""
    from shapely import union_all
    from shapely.geometry import LineString
    from shapely.ops import polygonize

    rings = {"outer": [], "inner": []}
    for el in data.get("elements", []):
        if el.get("type") != "relation":
            continue
        for m in el.get("members", []):
            if m.get("type") == "way" and m.get("geometry") and m.get("role") in rings:
                rings[m["role"]].append(LineString([(p["lon"], p["lat"]) for p in m["geometry"]]))
    if not rings["outer"]:
        return None
    outer = union_all(list(polygonize(rings["outer"])))
    if rings["inner"]:
        outer = outer.difference(union_all(list(polygonize(rings["inner"]))))
    return None if outer.is_empty else outer


def load_boundary(path):
    """Union of all polygons in a GeoJSON file."""
    from shapely import union_all
    from shapely.geometry import shape

    with open(path) as f:
        data = json.load(f)
    feats = data["features"] if data.get("type") == "FeatureCollection" else [data]
    return union_all([shape(f.get("geometry", f)) for f in feats])


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
