"""End-to-end check on a synthetic street grid with known zones."""

import json
import os
import tempfile
import unittest

from shapely.geometry import Point, shape

from seattle_zones import zones
from seattle_zones.__main__ import main

LON0, LON1 = -122.42, -122.26
LAT0, LAT1 = 47.52, 47.72
LAKE = (-122.30, -122.27, 47.55, 47.60)  # a hole with no streets


def expected_zone(lon, lat):
    if lat > 47.64:
        return "NW" if lon < -122.36 else ("N" if lon < -122.32 else "NE")
    if lat > 47.60:
        return "none" if lon < -122.32 else "E"
    return "SW" if lon < -122.36 else "S"


def in_lake(lon, lat):
    return LAKE[0] < lon < LAKE[1] and LAKE[2] < lat < LAKE[3]


def synthetic_streets(step=0.003):
    """Short street segments on a grid, named the Seattle way."""
    streets = []
    lat = LAT0
    while lat < LAT1:
        lon = LON0
        while lon < LON1:
            zone = expected_zone(lon, lat)
            for end in ((lon + step, lat), (lon, lat + step)):
                if in_lake(lon, lat) or in_lake(*end):
                    continue
                if zone == "none":
                    name = "Pike Street"
                elif end[1] == lat:  # east-west: prefix
                    name = f"{zone} 45th St"
                else:  # north-south: suffix
                    name = f"15th Ave {zone}"
                streets.append((name, [(lon, lat), end]))
            lon += step
        lat += step
    return streets


class BuildZonesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.labelled = zones.label_streets(synthetic_streets())
        cls.features = {f["properties"]["zone"]: shape(f["geometry"])
                        for f in zones.build_zones(cls.labelled)}

    def test_every_zone_found(self):
        self.assertEqual(set(self.features), {"NW", "N", "NE", "none", "E", "SW", "S"})

    def test_zone_interiors(self):
        probes = {
            "NW": (-122.39, 47.68), "N": (-122.34, 47.68), "NE": (-122.29, 47.68),
            "none": (-122.37, 47.62), "E": (-122.29, 47.62),
            "SW": (-122.39, 47.56), "S": (-122.34, 47.56),
        }
        for zone, (lon, lat) in probes.items():
            with self.subTest(zone=zone):
                self.assertTrue(self.features[zone].contains(Point(lon, lat)))

    def test_lake_left_empty(self):
        centre = Point((LAKE[0] + LAKE[1]) / 2, (LAKE[2] + LAKE[3]) / 2)
        for zone, geom in self.features.items():
            self.assertFalse(geom.contains(centre), zone)

    def test_zones_do_not_overlap_much(self):
        names = list(self.features)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                overlap = self.features[a].intersection(self.features[b]).area
                self.assertLess(overlap, 0.02 * min(self.features[a].area, self.features[b].area),
                                f"{a}/{b}")


class CliTest(unittest.TestCase):
    def test_geojson_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "streets.geojson")
            with open(src, "w") as f:
                json.dump({"type": "FeatureCollection", "features": [
                    {"type": "Feature", "properties": {"STNAME_ORD": name},
                     "geometry": {"type": "LineString", "coordinates": coords}}
                    for name, coords in synthetic_streets()]}, f)
            out = os.path.join(tmp, "out")
            main(["--geojson", src, "--out", out])
            with open(os.path.join(out, "zones.geojson")) as f:
                fc = json.load(f)
            self.assertIn("SW", {feat["properties"]["zone"] for feat in fc["features"]})
            with open(os.path.join(out, "map.html")) as f:
                self.assertIn("leaflet", f.read())


if __name__ == "__main__":
    unittest.main()
