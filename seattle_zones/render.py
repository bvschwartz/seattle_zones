"""Write a self-contained Leaflet map of the zones."""

import json

COLORS = {
    "N": "#1f77b4", "NE": "#2ca02c", "NW": "#17becf",
    "E": "#9467bd", "W": "#e377c2",
    "S": "#d62728", "SE": "#ff7f0e", "SW": "#8c564b",
    "none": "#7f7f7f",
}

LABELS = {"none": "No directional (downtown)"}

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
  .legend { background: #fff; padding: 8px 10px; font: 13px/1.5 system-ui, sans-serif;
            border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,.3); }
  .legend i { display: inline-block; width: 12px; height: 12px; margin-right: 6px;
              vertical-align: -1px; opacity: .8; }
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
  style: f => ({ color: color(f.properties.zone), weight: 2, fillOpacity: 0.35 }),
  onEachFeature: (f, l) => l.bindTooltip(
    `${labels[f.properties.zone] || f.properties.zone} &middot; ${f.properties.area_km2} km&sup2;`,
    { sticky: true })
}).addTo(map);
const streetLayer = L.geoJSON(streets, {
  style: f => ({ color: color(f.properties.zone), weight: 1.5, opacity: 0.9 }),
  onEachFeature: (f, l) => l.bindTooltip(f.properties.name, { sticky: true })
});
map.fitBounds(zoneLayer.getBounds());
L.control.layers(null, { "Zones": zoneLayer, "Streets (by suffix)": streetLayer },
                 { collapsed: false }).addTo(map);

const legend = L.control({ position: "bottomright" });
legend.onAdd = () => {
  const div = L.DomUtil.create("div", "legend");
  div.innerHTML = zones.features.map(f =>
    `<div><i style="background:${color(f.properties.zone)}"></i>` +
    `${labels[f.properties.zone] || f.properties.zone}</div>`).join("");
  return div;
};
legend.addTo(map);
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
