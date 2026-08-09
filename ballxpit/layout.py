"""Board layout, zone boxes, M's pinned placement, and preference groups.

Two 7x7 zones on a 23x23 board. The board is oversized on purpose -- the zones
would fit on 17x17; the extra margin is so pieces can sprawl outside their own
zone (which is allowed) without immediately jamming against the board edge.

    Zone 1  rows/cols  6..12  -- the dense-pack zone, "@" center marker block
    Zone 2  rows/cols 10..16  -- M's zone, M locked to its exact center cell

The two boxes deliberately overlap in the 3x3 block rows/cols 10..12, and sit
symmetrically about the board center. The overlap is load-bearing: it is what
lets a Zone-1 piece physically reach the cells next to M, which keeps the
"plus sign next to a P-pentomino" preference achievable now that M is locked
to the middle of Zone 2.

Requirements the model enforces (see model.py and phases.py):
    1. Every Zone-1 piece has >=1 cell inside Zone 1's box.
    2. Every Zone-2 building has >=1 cell inside Zone 2's box.
    3. M ("Iron Fortress - Plus sign 1") is *centered* on Zone 2 -- its middle
       cell sits on ZONE2_CENTER -- so it has exactly one legal placement and
       the six buildings pack around it.
    4. M is reachable: an all-empty corridor runs from a cell touching M out
       to the edge of the board (hard constraint, never relaxed).
    5. Then, in descending priority: Zone 1 density, Zone 2 density, adjacency
       preferences, M's open perimeter.
"""

from .geometry import ORTHO, normalize, plus_at
from .pieces import ALL_PIECES, ZONE_1_PIECES, ZONE_2_PIECES

BOARD_SIZE = 23

R_START, R_END = 6, 12       # Zone 1 (rows)
C_START, C_END = 6, 12       # Zone 1 (cols)

M_R_START, M_R_END = 10, 16  # Zone 2 (rows) -- shifted +4/+4, overlaps Zone 1
M_C_START, M_C_END = 10, 16  # Zone 2 (cols) -- shared block: rows/cols 10-12

ZONE1_BOUNDS = (R_START, R_END, C_START, C_END)
ZONE2_BOUNDS = (M_R_START, M_R_END, M_C_START, M_C_END)

ZONE_CELLS = (R_END - R_START + 1) * (C_END - C_START + 1)   # 49, used as the
                                                             # density target

# Zone 2 must be an odd-sized square, otherwise "the center of Zone 2" is not a
# single cell and M cannot be centered on it.
assert (M_R_END - M_R_START) == (M_C_END - M_C_START), "Zone 2 must be square"
assert (M_R_END - M_R_START) % 2 == 0, "Zone 2 must be odd-sized (single center cell)"

# The single center cell of Zone 2's 7x7 box (10..16 -> middle index 13).
ZONE2_CENTER = ((M_R_START + M_R_END) // 2, (M_C_START + M_C_END) // 2)

# ---------------------------------------------------------------------------
# The Zone 1 center marker block: a 1x3 bar through the middle of Zone 1, laid
# either horizontally or vertically (the solver picks one).
# ---------------------------------------------------------------------------
CENTER_CELLS_H = [(9, 8), (9, 9), (9, 10)]
CENTER_CELLS_V = [(8, 9), (9, 9), (10, 9)]

# ---------------------------------------------------------------------------
# Which zone(s) each piece must touch. Every Zone-1 piece (including Y and Z)
# targets Zone 1; every building targets Zone 2.
#
# M is a Zone-2 piece: centering its plus on ZONE2_CENTER puts all five of its
# cells inside Zone 2 and entirely outside Zone 1's box (the zones only overlap
# in rows/cols 10-12, and the Zone-2 center is past that overlap), so requiring
# it to touch Zone 1 as well would be unsatisfiable. It stays eligible for the
# plus-sign/P-pentomino adjacency bonus, which only cares about which cells end
# up next to each other.
# ---------------------------------------------------------------------------
CENTER_PIECE_LABEL = "M"

PIECE_REQUIRED_ZONES = {p.label: [ZONE1_BOUNDS] for p in ZONE_1_PIECES}
PIECE_REQUIRED_ZONES[CENTER_PIECE_LABEL] = [ZONE2_BOUNDS]
for _piece in ZONE_2_PIECES:
    PIECE_REQUIRED_ZONES[_piece.label] = [ZONE2_BOUNDS]

# ---------------------------------------------------------------------------
# M is the center of Zone 2.
#
# This is an *exact cell set*, not a "must cover this cell" rule. Merely
# requiring M to cover ZONE2_CENTER leaves five legal placements -- four of
# them put one of the plus's arms on the center and the body off to one side.
# Pinning the whole cell set leaves exactly one placement: the plus whose
# middle cell is ZONE2_CENTER.
# ---------------------------------------------------------------------------
M_CELLS = plus_at(ZONE2_CENTER)

_m_piece = next(p for p in ALL_PIECES if p.label == CENTER_PIECE_LABEL)
assert normalize(_m_piece.cells) == normalize(M_CELLS), (
    f"piece {CENTER_PIECE_LABEL} must be a symmetric plus sign for "
    "'centered on Zone 2' to be well defined"
)
assert all(
    M_R_START <= r <= M_R_END and M_C_START <= c <= M_C_END for r, c in M_CELLS
), "centered M does not fit inside Zone 2"

# Exact cell set a piece's placement is hard-required to occupy, beyond the
# zone checks above.
PIECE_FIXED_CELLS = {CENTER_PIECE_LABEL: M_CELLS}

# The 8 cells orthogonally touching the centered plus. Because M is pinned,
# these are known up front and are what "reach M" and "M's open perimeter" are
# measured against.
M_ADJACENT_CELLS = frozenset(
    (r + dr, c + dc)
    for r, c in M_CELLS
    for dr, dc in ORTHO
    if (r + dr, c + dc) not in M_CELLS
    and 0 <= r + dr < BOARD_SIZE
    and 0 <= c + dc < BOARD_SIZE
)
assert len(M_ADJACENT_CELLS) == 8

# ---------------------------------------------------------------------------
# Adjacency preference groups (soft "if possible" preferences).
#
# Y and Z are not part of any group yet; add them here to make them
# participate in a bonus (e.g. P_PENTOMINO_LABELS.append("Y")).
# ---------------------------------------------------------------------------
PLUS_SIGN_LABELS = ["M", "N"]
P_PENTOMINO_LABELS = ["J", "K"]
BAR_LABEL = "P"
SQUARE2x2_LABEL = "F"
T_TETROMINO_LABEL = "Q"
L_TROMINO_LABELS = ["A", "B", "C", "D"]
U_PENTOMINO_LABEL = "L"


def in_zone1(r, c):
    return R_START <= r <= R_END and C_START <= c <= C_END


def in_zone2(r, c):
    return M_R_START <= r <= M_R_END and M_C_START <= c <= M_C_END


def on_boundary(r, c):
    return r in (0, BOARD_SIZE - 1) or c in (0, BOARD_SIZE - 1)


def on_board(cell):
    return 0 <= cell[0] < BOARD_SIZE and 0 <= cell[1] < BOARD_SIZE
