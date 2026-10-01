"""Command line entry point: python -m seattle_zones"""

import argparse
import json
import os

from . import render, sources, zones


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="seattle_zones",
        description="Map the extent of Seattle's N/NE/NW/E/W/S/SE/SW street-name zones.")
    p.add_argument("--geojson", help="read street centerlines from this GeoJSON "
                   "instead of downloading from OpenStreetMap")
    p.add_argument("--name-field", help="street-name property in --geojson "
                   f"(default: first of {', '.join(sources.NAME_FIELDS)})")
    p.add_argument("--cache", default="data/osm_streets.json",
                   help="where to cache the OpenStreetMap download")
    p.add_argument("--refresh", action="store_true", help="re-download OSM data")
    p.add_argument("--out", default="output", help="output directory")
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

    if args.geojson:
        raw = sources.load_geojson(args.geojson, args.name_field)
    else:
        raw = sources.fetch_osm(args.cache, refresh=args.refresh)
    labelled = zones.label_streets(raw)
    if not labelled:
        p.error("no named streets found in the input")
    print(f"{len(labelled)} named street segments")
    for zone, n in sorted(zones.zone_counts(labelled).items()):
        print(f"  {zone:>4}: {n}")

    features = zones.build_zones(labelled, cell=args.cell, radius=args.radius,
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
                     None if args.no_streets else street_fc)

    print("zone areas:")
    for feat in features:
        print(f"  {feat['properties']['zone']:>4}: {feat['properties']['area_km2']} km²")
    print(f"wrote {args.out}/zones.geojson, streets.geojson, map.html")


if __name__ == "__main__":
    main()
