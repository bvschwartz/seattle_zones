"""Command line entry point: python -m seattle_zones"""

import argparse
import json
import os

from shapely.geometry import mapping

from . import render, sources, zones

# Above this many segments the street layer makes map.html slow to open.
MAX_MAP_STREETS = 60_000


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="seattle_zones",
        description="Map the extent of the N/NE/NW/E/W/S/SE/SW street-name zones "
                    "of Seattle, or any other Washington city or county.")
    p.add_argument("--place", action="append",
                   help='city or county name as OpenStreetMap has it, e.g. "Snohomish County". '
                   "Repeat to put several places on one map; where they overlap (a city "
                   "inside a county) the smaller place wins. Default: Seattle")
    p.add_argument("--admin-level", type=int,
                   help="OpenStreetMap admin_level: 8 for a city, 6 for a county "
                   "(default: 6 if the name ends in County, else 8; single --place only)")
    p.add_argument("--state", default="US-WA", help="ISO code of the state the place is in")
    p.add_argument("--geojson", help="read street centerlines from this GeoJSON "
                   "instead of downloading from OpenStreetMap")
    p.add_argument("--name-field", help="street-name property in --geojson "
                   f"(default: first of {', '.join(sources.NAME_FIELDS)})")
    p.add_argument("--cache", help="where to cache the OpenStreetMap download "
                   "(default: data/<place>.json)")
    p.add_argument("--boundary", help="GeoJSON polygon to trim zones to (with --geojson; "
                   "the OpenStreetMap download includes the boundary)")
    p.add_argument("--no-clip", action="store_true",
                   help="don't trim zones to the place boundary")
    p.add_argument("--refresh", action="store_true", help="re-download OSM data")
    p.add_argument("--out", help="output directory (default: output/<place>, "
                   "or output/combined for several places)")
    p.add_argument("--cell", type=float, default=50.0, help="grid cell size in metres")
    p.add_argument("--radius", type=float, default=250.0,
                   help="how far a street influences the zone vote, in metres")
    p.add_argument("--reach", type=float, default=150.0,
                   help="cells further than this from any street are left blank")
    p.add_argument("--unlabeled-weight", type=float, default=0.5,
                   help="vote weight for streets with no directional")
    p.add_argument("--fill-area", type=float, default=0.8,
                   help="drop zone specks and fill holes smaller than this, in km² "
                   "(0 keeps them all)")
    p.add_argument("--no-streets", action="store_true",
                   help="leave the street layer out of the HTML map (smaller file)")
    p.add_argument("--streets", action="store_true",
                   help=f"keep the street layer in the HTML map even above "
                   f"{MAX_MAP_STREETS} segments")
    args = p.parse_args(argv)

    places = args.place or ["Seattle"]
    if len(places) > 1 and (args.geojson or args.cache or args.admin_level):
        p.error("--geojson, --cache and --admin-level work with a single --place only")
    args.out = args.out or os.path.join(
        "output", sources.slug(places[0]) if len(places) == 1 else "combined")

    # Load everything first: overlaps are resolved smallest place first.
    loaded = []
    for place in places:
        if args.geojson:
            raw = sources.load_geojson(args.geojson, args.name_field)
            boundary = sources.load_boundary(args.boundary) if args.boundary else None
        else:
            level = args.admin_level or (6 if place.lower().endswith(" county") else 8)
            raw, boundary = sources.fetch_osm(place, level, args.state, args.cache,
                                              refresh=args.refresh)
            if boundary is None:
                print(f"warning: no boundary for {place} in OpenStreetMap; "
                      "its zones won't be trimmed")
        labelled = zones.label_streets(raw)
        if not labelled:
            p.error(f"no named streets found for {place}")
        loaded.append((place, labelled, None if args.no_clip else boundary))
    loaded.sort(key=lambda x: x[2].area if x[2] is not None else float("inf"))

    features, boundaries, all_streets = [], [], []
    covered = None
    for place, labelled, boundary in loaded:
        print(f"{place}: {len(labelled)} named street segments")
        for zone, n in sorted(zones.zone_counts(labelled).items()):
            print(f"  {zone:>4}: {n}")
        clip = boundary
        if boundary is not None:
            boundaries.append({"type": "Feature", "properties": {"place": place},
                               "geometry": mapping(boundary)})
            if covered is not None:
                clip = boundary.difference(covered)
            covered = boundary if covered is None else covered.union(boundary)
        place_features = zones.build_zones(
            labelled, clip, cell=args.cell, radius=args.radius, reach=args.reach,
            unlabeled_weight=args.unlabeled_weight, fill_area=args.fill_area * 1e6)
        for feat in place_features:
            feat["properties"]["place"] = place
            print(f"  {feat['properties']['zone']:>4}: {feat['properties']['area_km2']} km²")
        features.extend(place_features)
        all_streets.extend(labelled)

    zone_fc = {"type": "FeatureCollection", "features": features}
    street_fc = zones.streets_geojson(all_streets)
    boundary_fc = {"type": "FeatureCollection", "features": boundaries}

    os.makedirs(args.out, exist_ok=True)
    for name, fc in (("zones", zone_fc), ("streets", street_fc), ("boundaries", boundary_fc)):
        with open(os.path.join(args.out, name + ".geojson"), "w") as f:
            json.dump(fc, f)

    map_streets = not args.no_streets
    if map_streets and not args.streets and len(all_streets) > MAX_MAP_STREETS:
        print(f"note: {len(all_streets)} street segments is too many for a smooth map; "
              "leaving the street layer out (use --streets to keep it)")
        map_streets = False
    title = (places[0] if len(places) == 1 else " + ".join(places)) + " Directional Zones"
    render.write_map(os.path.join(args.out, "map.html"), zone_fc,
                     street_fc if map_streets else None, title=title, boundaries=boundary_fc)
    print(f"wrote {args.out}/zones.geojson, streets.geojson, boundaries.geojson, map.html")


if __name__ == "__main__":
    main()
