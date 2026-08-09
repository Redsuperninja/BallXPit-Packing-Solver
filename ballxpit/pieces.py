"""The building catalogue.

Every piece is a polyomino given as (row, col) offsets, a single-character
label used on the printed grid, and a display name. Row 0 is the top row, so
the literals below read the same way the shapes look on screen.
"""

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class Piece:
    cells: Tuple[Tuple[int, int], ...]
    label: str
    name: str

    def __len__(self):
        return len(self.cells)


def _piece(cells, label, name):
    return Piece(tuple(cells), label, name)


# ---------------------------------------------------------------------------
# Zone 1 pieces (labels A-R, plus Y and Z).
#
# Note "M" (Iron Fortress) is listed here for historical reasons but is
# treated as a Zone 2 piece -- see layout.py, which pins it to the center of
# Zone 2.
# ---------------------------------------------------------------------------
ZONE_1_PIECES = [
    _piece([(0, 1), (1, 1), (1, 2)], "A", "Haunted House - L-tromino 1"),
    _piece([(0, 1), (1, 1), (1, 2)], "B", "Sheriff's Office - L-tromino 2"),
    _piece([(0, 1), (1, 1), (1, 2)], "C", "Campground - L-tromino 3"),
    _piece([(0, 1), (1, 1), (1, 2)], "D", "Single Family Home - L-tromino 4"),
    _piece([(r, c) for r in range(3) for c in range(3)], "E", "Ball House - 3x3 Square"),
    _piece([(r, c) for r in range(2) for c in range(2)], "F", "Rocky Hill - 2x2 Square"),
    _piece([(r, c) for r in range(3) for c in range(2)], "G", "Mausoleum - 2x3 Rectangle"),
    _piece([(0, 1), (1, 1), (2, 0), (2, 1), (2, 2), (3, 1)], "H", "Monastery - Cross-like"),
    _piece([(0, 0), (0, 1), (0, 2), (1, 1), (2, 1), (3, 0), (3, 1), (3, 2)], "I", "Stone Domain - 8-cell I"),
    _piece([(0, 0), (0, 1), (1, 0), (1, 1), (2, 1)], "J", "Captian's Quarters - P-pentomino 1"),
    _piece([(0, 0), (0, 1), (1, 0), (1, 1), (2, 1)], "K", "Party House - P-pentomino 2"),
    _piece([(0, 0), (0, 2), (1, 0), (1, 1), (1, 2)], "L", "Villa - U-pentomino"),
    _piece([(0, 1), (1, 0), (1, 1), (1, 2), (2, 1)], "M", "Iron Fortress - Plus sign 1"),
    _piece([(0, 1), (1, 0), (1, 1), (1, 2), (2, 1)], "N", "Unstable Tower - Plus sign 2"),
    _piece([(0, 2), (1, 0), (1, 1), (1, 2), (2, 1)], "O", "Laboratory - T/Corner"),
    _piece([(0, 0), (0, 1), (0, 2)], "P", "Theater - 1x3 Bar"),
    _piece([(0, 1), (1, 0), (1, 1), (1, 2)], "Q", "Cozy Home - T-tetromino"),
    _piece([(0, 0), (0, 1), (0, 2), (0, 3), (0, 4), (1, 1), (1, 2), (1, 3), (2, 2)], "R", "Mansion - Arrow/House"),
    _piece([(0, 0), (0, 1), (1, 0), (1, 1), (2, 1), (3, 1)], "Y", "Falconry Hut - Longer P-pentomino 3"),
    _piece([(0, 0), (0, 2), (1, 0), (1, 1), (1, 2), (2, 0), (2, 1), (2, 2)], "Z", "Hidden Temple - U-pentomino"),
]

# ---------------------------------------------------------------------------
# Zone 2 pieces: the six large buildings that pack around M.
# ---------------------------------------------------------------------------
ZONE_2_PIECES = [
    _piece([(0, 0), (0, 1), (0, 2),
            (1, 0), (1, 1), (1, 2),
            (2, 0), (2, 1), (2, 2),
            (3, 1)], "S", "Capitolium"),
    _piece([(0, 0), (0, 1), (0, 2), (0, 3),
            (1, 0), (1, 1), (1, 2), (1, 3),
            (2, 1), (2, 2)], "T", "Warrior's Guild"),
    _piece([(0, 0), (0, 1), (0, 2), (0, 3),
            (1, 0), (1, 1), (1, 2), (1, 3),
            (2, 0),
            (3, 0)], "U", "Hospital"),
    _piece([(0, 0), (0, 1), (0, 2), (0, 3),
            (1, 0), (1, 1), (1, 2), (1, 3),
            (2, 0), (2, 1)], "V", "Wagon Factory"),
    _piece([(0, 0), (0, 1), (0, 2),
            (1, 0), (1, 1), (1, 2),
            (2, 1), (2, 2), (2, 3)], "W", "Marksman's Guild"),
    _piece([(0, 1), (0, 2),
            (1, 0), (1, 1),
            (2, 0), (2, 1),
            (3, 0), (3, 1),
            (4, 1), (4, 2)], "X", "Grand Museum"),
]

ALL_PIECES = ZONE_1_PIECES + ZONE_2_PIECES
ALL_LABELS = [p.label for p in ALL_PIECES]

# The character used for the Zone 1 center marker block. It is deliberately
# not a letter: "Z" used to serve this role and became ambiguous the moment a
# real "Z" piece (Hidden Temple) was added.
CENTER_MARKER = "@"

# --- Catalogue sanity checks -----------------------------------------------
assert sum(len(p) for p in ZONE_2_PIECES) == 59, "building cell count changed"
assert len(ALL_LABELS) == len(set(ALL_LABELS)), "duplicate piece label"
assert CENTER_MARKER not in ALL_LABELS, f"'{CENTER_MARKER}' is reserved for the center marker"


def piece_index(label):
    """Index of `label` in ALL_PIECES (the solver's piece numbering)."""
    return ALL_LABELS.index(label)
