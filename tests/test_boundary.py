import json
import os
import tempfile
import unittest

from shapely.geometry import Point, box, shape

from seattle_zones import sources, zones
from seattle_zones.__main__ import main
from tests.test_zones import LAT0, LAT1, LON0, LON1, synthetic_streets

# A city limit that cuts the synthetic grid: everything north of 47.70 is
# "outside the city" even though streets continue there.
CITY = box(LON0, LAT0, LON1, 47.70)


def overpass_response(streets, outline):
    """A fake Overpass reply: the boundary relation, then the street ways.

    The outer ring is split into two ways, as OSM usually stores it.
    """
    ring = [{"lon": x, "lat": y} for x, y in outline.exterior.coords]
    half = len(ring) // 2
    return {"elements": [
        {"type": "relation", "tags": {"name": "Testville"}, "members": [
            {"type": "way", "role": "outer", "geometry": ring[:half + 1]},
            {"type": "way", "role": "outer", "geometry": ring[half:]},
            {"type": "node", "role": "admin_centre", "lat": 47.6, "lon": -122.3},
        ]},
    ] + [
        {"type": "way", "tags": {"name": name},
         "geometry": [{"lon": x, "lat": y} for x, y in coords]}
        for name, coords in streets
    ]}


class BoundaryTest(unittest.TestCase):
    def test_assemble_from_split_ways(self):
        b = sources._osm_boundary(overpass_response([], CITY))
        self.assertAlmostEqual(b.area, CITY.area, places=9)

    def test_inner_ring_is_a_hole(self):
        data = overpass_response([], CITY)
        hole = box(-122.35, 47.60, -122.34, 47.61)
        data["elements"][0]["members"].append({"type": "way", "role": "inner", "geometry": [
            {"lon": x, "lat": y} for x, y in hole.exterior.coords]})
        b = sources._osm_boundary(data)
        self.assertFalse(b.contains(hole.centroid))
        self.assertTrue(b.contains(Point(-122.30, 47.65)))

    def test_zones_trimmed_to_boundary(self):
        labelled = zones.label_streets(synthetic_streets())
        trimmed = {f["properties"]["zone"]: shape(f["geometry"])
                   for f in zones.build_zones(labelled, CITY)}
        outside = box(LON0, 47.705, LON1, LAT1)
        for zone, geom in trimmed.items():
            with self.subTest(zone=zone):
                self.assertLess(geom.intersection(outside).area, 1e-9)
        self.assertTrue(trimmed["N"].contains(Point(-122.34, 47.68)))


class FetchOsmCacheTest(unittest.TestCase):
    def test_cli_with_cached_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = os.path.join(tmp, "testville.json")
            with open(cache, "w") as f:
                json.dump(overpass_response(synthetic_streets(), CITY), f)
            out = os.path.join(tmp, "out")
            main(["--place", "Testville", "--cache", cache, "--out", out])
            with open(os.path.join(out, "zones.geojson")) as f:
                fc = json.load(f)
            north = max(shape(feat["geometry"]).bounds[3] for feat in fc["features"])
            self.assertLessEqual(north, 47.70 + 1e-9)
            with open(os.path.join(out, "map.html")) as f:
                self.assertIn("<title>Testville Directional Zones</title>", f.read())

    def test_empty_download_explains(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = os.path.join(tmp, "nowhere.json")
            with open(cache, "w") as f:
                json.dump({"elements": []}, f)
            with self.assertRaises(SystemExit) as cm:
                sources.fetch_osm("Nowhere", cache_path=cache)
            self.assertIn("no streets", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
