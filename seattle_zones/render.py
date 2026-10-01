"""Write a self-contained Leaflet map of the zones."""

import json

COLORS = {
    "N": "#1f77b4", "NE": "#2ca02c", "NW": "#17becf",
    "E": "#9467bd", "W": "#e377c2",
    "S": "#d62728", "SE": "#ff7f0e", "SW": "#8c564b",
    "none": "#7f7f7f",
}

LABELS = {"none": "no direction"}

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Seattle Directional Zones</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>
  html, body, #map { height: 100%; margin: 0; }
  .zone-label { color: #000; font: bold 18px/20px system-ui, sans-serif; white-space: nowrap;
                text-align: center; pointer-events: none;
                text-shadow: 0 0 3px #fff, 0 0 3px #fff, 0 0 3px #fff; }
  .zone-label.small { font-size: 13px; font-weight: 600; }
</style>
</head>
<body>
<div id="map"></div>
<script>
const zones = __ZONES__;
const streets = __STREETS__;
const colors = __COLORS__;
const labels = __LABELS__;

const map = L.map("map");
// CARTO tiles load from file:// pages; openstreetmap.org tiles need a Referer.
L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
  maxZoom: 20, subdomains: "abcd",
  attribution: "&copy; OpenStreetMap contributors &copy; CARTO"
}).addTo(map);

const color = z => colors[z] || "#000";
const zoneLayer = L.geoJSON(zones, {
  // The no-direction (downtown) zone is outlined only: no fill, no label.
  style: f => f.properties.zone === "none"
    ? { color: color("none"), weight: 1.5, fill: false }
    : { color: color(f.properties.zone), weight: 2, fillOpacity: 0.35 },
  onEachFeature: (f, l) => l.bindTooltip(
    `${labels[f.properties.zone] || f.properties.zone} &middot; ${f.properties.area_km2} km&sup2;`,
    { sticky: true })
}).addTo(map);
const streetLayer = L.geoJSON(streets, {
  style: f => ({ color: color(f.properties.zone), weight: 1.5, opacity: 0.9 }),
  onEachFeature: (f, l) => l.bindTooltip(f.properties.name, { sticky: true })
});
// Zone names at a point well inside each region (computed in zones.py).
const labelLayer = L.layerGroup(zones.features.filter(f => f.properties.zone !== "none").flatMap(f =>
  (f.properties.label_points || []).map(([lon, lat]) => {
    const text = labels[f.properties.zone] || f.properties.zone;
    const cls = "zone-label" + (text.length > 2 ? " small" : "");
    return L.marker([lat, lon], { interactive: false, keyboard: false,
      icon: L.divIcon({ className: cls, html: text, iconSize: [120, 20], iconAnchor: [60, 10] }) });
  }))).addTo(map);

map.fitBounds(zoneLayer.getBounds());
L.control.layers(null, { "Zones": zoneLayer, "Labels": labelLayer,
                         "Streets (by suffix)": streetLayer },
                 { collapsed: false }).addTo(map);
</script>
</body>
</html>
"""


def write_map(path, zones, streets=None):
    html = (TEMPLATE
            .replace("__ZONES__", json.dumps(zones))
            .replace("__STREETS__", json.dumps(streets or {"type": "FeatureCollection", "features": []}))
            .replace("__COLORS__", json.dumps(COLORS))
            .replace("__LABELS__", json.dumps(LABELS)))
    with open(path, "w") as f:
        f.write(html)
