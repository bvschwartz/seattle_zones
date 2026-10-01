"""Turn labelled street lines into one polygon per directional zone.

Method:
1. Project lon/lat to local metres and sample a point every few metres along
   every street, tagged with that street's zone.
2. Lay a grid over the city. Each cell takes a distance-weighted vote of the
   street points near it; cells far from any street (lakes, the Sound, big
   parks) stay empty.
3. A majority filter removes speckle, then each zone's cells are merged into
   polygons, smoothed, and projected back to lon/lat.
"""

import math
from collections import Counter

import numpy as np
from scipy.ndimage import generic_filter
from scipy.spatial import cKDTree
from shapely import box, union_all
from shapely.geometry import Polygon, mapping
from shapely.ops import polylabel, transform

from .directions import NONE, parse_direction

M_PER_DEG_LAT = 110_540.0
M_PER_DEG_LON_EQ = 111_320.0


class Projection:
    """Equirectangular projection to metres; accurate enough for one city."""

    def __init__(self, lon0, lat0):
        self.lon0, self.lat0 = lon0, lat0
        self.kx = M_PER_DEG_LON_EQ * math.cos(math.radians(lat0))

    def forward(self, lon, lat):
        return (np.asarray(lon) - self.lon0) * self.kx, (np.asarray(lat) - self.lat0) * M_PER_DEG_LAT

    def inverse(self, x, y):
        return np.asarray(x) / self.kx + self.lon0, np.asarray(y) / M_PER_DEG_LAT + self.lat0


def label_streets(streets):
    """[(name, coords)] -> [(name, zone, coords)], dropping unnamed streets."""
    out = []
    for name, coords in streets:
        zone = parse_direction(name)
        if zone:
            out.append((name, zone, coords))
    return out


def _sample(coords, proj, step):
    x, y = proj.forward([c[0] for c in coords], [c[1] for c in coords])
    pts = [(x[0], y[0])]
    for i in range(1, len(x)):
        dx, dy = x[i] - x[i - 1], y[i] - y[i - 1]
        n = max(1, int(math.hypot(dx, dy) // step))
        for k in range(1, n + 1):
            pts.append((x[i - 1] + dx * k / n, y[i - 1] + dy * k / n))
    return pts


def _mode(values):
    vals = values[values >= 0].astype(int)
    if len(vals) == 0:
        return -1
    centre = values[len(values) // 2]
    counts = np.bincount(vals)
    best = counts.argmax()
    # Keep the centre cell unless another label clearly dominates.
    if centre >= 0 and counts[int(centre)] * 2 >= counts[best]:
        return centre
    return best


def build_zones(labelled, boundary=None, cell=50.0, step=20.0, radius=250.0, reach=150.0,
                k=24, unlabeled_weight=0.5, smooth_passes=2, fill_area=0.8e6,
                label_area=3e6):
    """Compute zone polygons.

    labelled: output of label_streets.
    boundary: optional shapely (Multi)Polygon in lon/lat; zones are trimmed to
    it. Streets that cross the city limit otherwise poke out past it.
    cell: grid cell size (m). step: sampling interval along streets (m).
    radius: how far a street point can vote (m). reach: a cell further than
    this from every street is treated as not-land/no-street and left empty.
    unlabeled_weight: vote weight for streets with no directional.
    fill_area: separate pieces of a zone smaller than this (m^2) are dropped,
    and holes smaller than this are filled by the zone around them. Zones never
    nest, so a speck of one zone inside another just becomes part of the other.
    Bigger holes (Green Lake, about 1 km^2) are left open.
    label_area: besides the largest piece, pieces at least this big (m^2) get
    their own label point.

    Returns a list of GeoJSON features, one per zone.
    """
    all_lon = [c[0] for _, _, cs in labelled for c in cs]
    all_lat = [c[1] for _, _, cs in labelled for c in cs]
    proj = Projection((min(all_lon) + max(all_lon)) / 2, (min(all_lat) + max(all_lat)) / 2)

    zones = sorted({z for _, z, _ in labelled}, key=lambda z: (z == NONE, z))
    zone_idx = {z: i for i, z in enumerate(zones)}

    pts, lab = [], []
    for _, zone, coords in labelled:
        s = _sample(coords, proj, step)
        pts.extend(s)
        lab.extend([zone_idx[zone]] * len(s))
    pts = np.array(pts)
    lab = np.array(lab)
    weight = np.where(lab == zone_idx.get(NONE, -1), unlabeled_weight, 1.0)
    tree = cKDTree(pts)

    xmin, ymin = pts.min(axis=0) - reach
    xmax, ymax = pts.max(axis=0) + reach
    nx = int(math.ceil((xmax - xmin) / cell))
    ny = int(math.ceil((ymax - ymin) / cell))
    gx = xmin + (np.arange(nx) + 0.5) * cell
    gy = ymin + (np.arange(ny) + 0.5) * cell
    cx, cy = np.meshgrid(gx, gy)
    centres = np.column_stack([cx.ravel(), cy.ravel()])

    # Only cells near a street vote; on a county-sized grid most cells are
    # forest or water, so this keeps memory and time down.
    nearest, _ = tree.query(centres, distance_upper_bound=reach)
    on_land = np.isfinite(nearest)
    # A list k always yields 2-D results, even when only one neighbour fits.
    dist, idx = tree.query(centres[on_land], k=list(range(1, min(k, len(pts)) + 1)),
                           distance_upper_bound=radius)
    valid = np.isfinite(dist)
    safe_idx = np.where(valid, idx, 0)
    w = np.where(valid, weight[safe_idx] / (dist + 25.0), 0.0)
    votes = np.zeros((len(dist), len(zones)))
    for z in range(len(zones)):
        votes[:, z] = np.where(lab[safe_idx] == z, w, 0.0).sum(axis=1)

    grid = np.full(len(centres), -1.0)
    grid[on_land] = votes.argmax(axis=1)
    grid = grid.reshape(ny, nx)

    for _ in range(smooth_passes):
        smoothed = generic_filter(grid, _mode, size=3, mode="constant", cval=-1)
        grid = np.where(grid >= 0, smoothed, -1)

    if boundary is not None:
        boundary = transform(lambda x, y, z=None: proj.forward(x, y), boundary)

    features = []
    for z, name in enumerate(zones):
        geom = _cells_to_polygon(grid == z, xmin, ymin, cell)
        if geom.is_empty:
            continue
        geom = geom.buffer(cell * 0.6, join_style="round").buffer(-cell * 0.6).simplify(cell / 2)
        if boundary is not None:
            geom = _polygons_only(geom.intersection(boundary))
            if geom.is_empty:
                continue
        geom = _drop_specks_and_fill_holes(geom, fill_area)
        area = geom.area
        labels = _label_points(geom, label_area, fill_area, cell)
        geom = transform(lambda x, y, z=None: proj.inverse(x, y), geom)
        features.append({
            "type": "Feature",
            "properties": {
                "zone": name,
                "area_km2": round(area / 1e6, 2),
                "label_points": [[round(float(c), 6) for c in proj.inverse(x, y)]
                                 for x, y in labels],
            },
            "geometry": mapping(geom),
        })
    return features


def _polygons_only(geom):
    """Clipping can leave stray lines/points along shared edges; keep areas."""
    parts = getattr(geom, "geoms", [geom])
    return union_all([p for p in parts if p.geom_type in ("Polygon", "MultiPolygon")])


def _drop_specks_and_fill_holes(geom, fill_area):
    """Remove small separate pieces (always keeping the largest) and fill
    small holes."""
    parts = sorted(getattr(geom, "geoms", [geom]), key=lambda p: p.area, reverse=True)
    parts = parts[:1] + [p for p in parts[1:] if p.area >= fill_area]
    return union_all([
        Polygon(p.exterior, [h for h in p.interiors if Polygon(h).area >= fill_area])
        for p in parts
    ])


def _label_points(geom, label_area, min_area, tolerance):
    """Interior points far from the edges: the largest piece, plus big ones.

    A zone whose largest piece is under min_area is a sliver (e.g. where a
    city boundary clips the edge of a zone) and gets no label.
    """
    parts = sorted(getattr(geom, "geoms", [geom]), key=lambda p: p.area, reverse=True)
    parts = [p for p in parts[:1] if p.area >= min_area] + \
            [p for p in parts[1:] if p.area >= label_area]
    return [polylabel(p, tolerance).coords[0] for p in parts]


def _cells_to_polygon(mask, xmin, ymin, cell):
    """Union grid cells, merging horizontal runs first to keep it fast."""
    boxes = []
    for r in range(mask.shape[0]):
        row = mask[r]
        if not row.any():
            continue
        padded = np.concatenate([[False], row, [False]])
        edges = np.flatnonzero(padded[1:] != padded[:-1])
        y0 = ymin + r * cell
        for start, end in zip(edges[::2], edges[1::2]):
            boxes.append(box(xmin + start * cell, y0, xmin + end * cell, y0 + cell))
    return union_all(boxes)


def streets_geojson(labelled):
    return {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"name": name, "zone": zone},
            "geometry": {"type": "LineString", "coordinates": [list(c) for c in coords]},
        } for name, zone, coords in labelled],
    }


def zone_counts(labelled):
    return Counter(zone for _, zone, _ in labelled)
