"""Polyomino geometry: orientations, normalization, and zone-overlap tests.

A shape is a collection of (row, col) offsets. "Normalized" means shifted so
its top-left bounding-box corner is at (0, 0) and sorted, which makes shapes
comparable and de-duplicable.
"""

# The four orthogonal steps, used everywhere adjacency matters.
ORTHO = ((1, 0), (-1, 0), (0, 1), (0, -1))


def normalize(shape):
    """Shift `shape` to the origin and sort it, so equal shapes compare equal."""
    min_r = min(r for r, _ in shape)
    min_c = min(c for _, c in shape)
    return tuple(sorted((r - min_r, c - min_c) for r, c in shape))


def rotate(shape):
    """Rotate `shape` 90 degrees."""
    return tuple((-c, r) for r, c in shape)


def get_orientations(shape):
    """All distinct rotations of `shape` (reflections are not used)."""
    seen = set()
    current = shape
    for _ in range(4):
        seen.add(normalize(current))
        current = rotate(current)
    return list(seen)


def plus_at(center):
    """The 5 cells of a symmetric plus sign centered on `center`."""
    r, c = center
    return frozenset({(r, c), (r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)})


def touches_zone(cells, r0, r1, c0, c1):
    """True if any of `cells` falls inside the inclusive box (r0..r1, c0..c1)."""
    return any(r0 <= r <= r1 and c0 <= c <= c1 for r, c in cells)


def touches_all_zones(cells, zones):
    """True if `cells` has at least one cell in *every* box in `zones`.

    Not necessarily the same cell for each box, so a piece may straddle two
    zones and satisfy both.
    """
    return all(touches_zone(cells, *zone) for zone in zones)
