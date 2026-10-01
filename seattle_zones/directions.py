"""Parse the directional designator out of a Seattle street name.

Seattle names look like "NE 45th St" / "Northeast 45th Street" (prefix, used
mostly on east-west streets) or "15th Ave NE" / "Aurora Avenue North" (suffix,
used mostly on north-south avenues). A few names carry both, e.g.
"East Marginal Way South", where the prefix is part of the proper name and the
suffix is the zone, so the suffix wins.
"""

import re

DIRECTIONS = {
    "n": "N", "north": "N",
    "s": "S", "south": "S",
    "e": "E", "east": "E",
    "w": "W", "west": "W",
    "ne": "NE", "northeast": "NE",
    "nw": "NW", "northwest": "NW",
    "se": "SE", "southeast": "SE",
    "sw": "SW", "southwest": "SW",
}

# Zone label used for named streets that carry no directional (mostly downtown).
NONE = "none"

# Words that, following a leading direction word, mean the direction is part of
# a place name rather than a zone designator ("West Seattle Bridge").
_PLACE_WORDS = {"seattle", "lake", "park", "point", "beach", "end", "bay"}

_SPLIT = re.compile(r"[\s,]+")


def parse_direction(name):
    """Return the zone code ("NE", "S", ...) for a street name, or NONE.

    Returns None when name is empty.
    """
    if not name:
        return None
    tokens = [t for t in _SPLIT.split(name.replace(".", "").strip()) if t]
    if len(tokens) < 2:
        return NONE
    words = [t.lower() for t in tokens]

    suffix = DIRECTIONS.get(words[-1])
    if suffix:
        return suffix

    prefix = DIRECTIONS.get(words[0])
    if prefix and len(words) >= 3 and words[1] not in _PLACE_WORDS:
        return prefix
    return NONE
