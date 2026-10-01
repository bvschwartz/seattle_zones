"""Command line entry point: python -m seattle_zones"""

import argparse
import json
import os

from . import render, sources, zones


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="seattle_zones",
        description="Map the extent of the N/NE/NW/E/W/S/SE/SW street-name zones "
                    "of Seattle, or any other Washington city or county.")
    p.add_argument("--place", default="Seattle",
                   help='city or county name as OpenStreetMap has it, e.g. "Snohomish County"')
    p.add_argument("--admin-level", type=int,
                   help="OpenStreetMap admin_level: 8 for a city, 6 for a county "
                   "(default: 6 if the name ends in County, else 8)")
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
    p.add_argument("--out", help="output directory (default: output/<place>)")
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
    args = p.parse_args(argv)

    if args.admin_level is None:
        args.admin_level = 6 if args.place.lower().endswith(" county") else 8
    args.out = args.out or os.path.join("output", sources.slug(args.place))

    if args.geojson:
        raw = sources.load_geojson(args.geojson, args.name_field)
        boundary = sources.load_boundary(args.boundary) if args.boundary else None
    else:
        raw, boundary = sources.fetch_osm(args.place, args.admin_level, args.state,
                                          args.cache, refresh=args.refresh)
        if boundary is None:
            print("warning: no boundary found in OpenStreetMap; zones won't be trimmed")
    if args.no_clip:
        boundary = None
    labelled = zones.label_streets(raw)
    if not labelled:
        p.error("no named streets found in the input")
    print(f"{len(labelled)} named street segments")
    for zone, n in sorted(zones.zone_counts(labelled).items()):
        print(f"  {zone:>4}: {n}")

    features = zones.build_zones(labelled, boundary, cell=args.cell, radius=args.radius,
                                 reach=args.reach, unlabeled_weight=args.unlabeled_weight,
                                 fill_area=args.fill_area * 1e6)
    zone_fc = {"type": "FeatureCollection", "features": features}
    street_fc = zones.streets_geojson(labelled)

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "zones.geojson"), "w") as f:
        json.dump(zone_fc, f)
    with open(os.path.join(args.out, "streets.geojson"), "w") as f:
        json.dump(street_fc, f)
    render.write_map(os.path.join(args.out, "map.html"), zone_fc,
                     None if args.no_streets else street_fc,
                     title=f"{args.place} Directional Zones")

    print("zone areas:")
    for feat in features:
        print(f"  {feat['properties']['zone']:>4}: {feat['properties']['area_km2']} km²")
    print(f"wrote {args.out}/zones.geojson, streets.geojson, map.html")


if __name__ == "__main__":
    main()
