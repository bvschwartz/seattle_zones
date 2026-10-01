# Seattle directional zones

Most Seattle street names carry a directional: `NE 45th St`, `15th Ave NW`,
`California Ave SW`, `E Pine St`, `Aurora Ave N`. This program works out
where each zone (N, NE, NW, E, W, S, SE, SW, and the unmarked downtown core)
begins and ends, using the street names themselves as the data.

Neighbouring cities and counties (Shoreline, Bellevue, Snohomish County, ...)
have their own grids and their own zones, and the same tool maps any of them
with `--place`.

## How it works

1. **Get street centerlines with names.** By default it downloads every named
   street inside the place's limits, plus the official boundary, from
   OpenStreetMap through the Overpass API (free, no key) and caches it in
   `data/`. It can also read a
   local GeoJSON, such as the City of Seattle's Street Network Database from
   [data.seattle.gov](https://data.seattle.gov).
2. **Label each street** from its leading or trailing directional
   (`seattle_zones/directions.py`). When a name has both, the suffix wins
   (`East Marginal Way S` is in S). Place names like "West Seattle Bridge"
   are not counted as directionals.
3. **Vote on a grid.** A 50 m grid covers the city. Each cell takes a
   distance-weighted vote of nearby street labels. Cells more than 150 m from
   any street (lakes, Puget Sound, big parks) stay blank. A majority filter
   cleans up stray cells. Since zones never sit inside one another, small
   specks of one zone inside another are dropped and small holes (parks,
   ponds) are filled by the zone around them.
4. **Polygonize.** Each zone's cells are merged into smoothed polygons,
   trimmed to the city or county boundary (streets that cross the limit would
   otherwise poke out past it), and written out as GeoJSON plus an
   interactive Leaflet map.

### Why not Google Maps?

Google's APIs geocode one address at a time and their terms don't allow
building a dataset from the results. OpenStreetMap and the City's own GIS data
give you every street segment with its name in one download, which is what
this needs.

## Usage

```sh
pip install -r requirements.txt
python -m seattle_zones            # downloads OSM data on first run
open output/seattle/map.html
```

Other places, by their OpenStreetMap name:

```sh
python -m seattle_zones --place "Snohomish County"   # output/snohomish_county/
python -m seattle_zones --place Bellevue
python -m seattle_zones --place "King County"
```

Names ending in "County" are looked up as counties, anything else as a city
(override with `--admin-level`: 8 city, 6 county). `--state` defaults to
`US-WA`. A county download is much bigger than Seattle's and can take several
minutes; if Overpass times out, run it again later.

Outputs in `output/<place>/`:

- `zones.geojson`: one (multi)polygon per zone, with `zone` and `area_km2`
- `streets.geojson`: every street segment with its parsed `zone`
- `map.html`: zones and streets on an OpenStreetMap basemap; hover for names

Using City of Seattle data instead:

```sh
python -m seattle_zones --geojson Seattle_Streets.geojson --name-field STNAME_ORD \
    --boundary City_Limits.geojson
```

(Check the export's property names; `--name-field` must be the field holding
the full street name.)

Tuning options: `--cell` (grid size, m), `--radius` (how far a street's vote
reaches, m), `--reach` (max distance from a street before a cell is left blank),
`--unlabeled-weight` (vote weight of streets with no directional; lower it if
the downtown zone spreads too far), `--fill-area` (specks and holes smaller than this many
km² are merged into the surrounding zone; default 0.8, which keeps Green Lake),
`--no-clip` (skip trimming to the boundary). Run `python -m seattle_zones -h` for all.

## Tests

```sh
python -m unittest discover -s tests -t .
```

The zone tests build a synthetic city grid with known zones and a lake, then
check that each zone's polygon covers the right area and the lake stays empty.
