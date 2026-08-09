import time
import sys
from ortools.sat.python import cp_model


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def normalize(shape):
    min_r = min(r for r, c in shape)
    min_c = min(c for r, c in shape)
    return tuple(sorted((r - min_r, c - min_c) for r, c in shape))


def rotate(shape):
    return tuple((-c, r) for r, c in shape)


def get_orientations(shape):
    res = set()
    cur = shape
    for _ in range(4):
        res.add(normalize(cur))
        cur = rotate(cur)
    return list(res)


# ---------------------------------------------------------------------------
# Zone 1 pieces (letters A-R, plus the newly added Y and Z).
# ---------------------------------------------------------------------------
zone_1_buildings_def = [
    ([(0, 1), (1, 1), (1, 2)], "A", "Haunted House - L-tromino 1"),
    ([(0, 1), (1, 1), (1, 2)], "B", "Sheriff's Office - L-tromino 2"),
    ([(0, 1), (1, 1), (1, 2)], "C", "Campground - L-tromino 3"),
    ([(0, 1), (1, 1), (1, 2)], "D", "Single Family Home - L-tromino 4"),
    ([(r, c) for r in range(3) for c in range(3)], "E", "Ball House - 3x3 Square"),
    ([(r, c) for r in range(2) for c in range(2)], "F", "Rocky Hill - 2x2 Square"),
    ([(r, c) for r in range(3) for c in range(2)], "G", "Mausoleum - 2x3 Rectangle"),
    ([(0, 1), (1, 1), (2, 0), (2, 1), (2, 2), (3, 1)], "H", "Monastery - Cross-like"),
    ([(0, 0), (0, 1), (0, 2), (1, 1), (2, 1), (3, 0), (3, 1), (3, 2)], "I", "Stone Domain - 8-cell I"),
    ([(0, 0), (0, 1), (1, 0), (1, 1), (2, 1)], "J", "Captian's Quarters - P-pentomino 1"),
    ([(0, 0), (0, 1), (1, 0), (1, 1), (2, 1)], "K", "Party House - P-pentomino 2"),
    ([(0, 0), (0, 2), (1, 0), (1, 1), (1, 2)], "L", "Villa - U-pentomino"),
    ([(0, 1), (1, 0), (1, 1), (1, 2), (2, 1)], "M", "Iron Fortress - Plus sign 1"),
    ([(0, 1), (1, 0), (1, 1), (1, 2), (2, 1)], "N", "Unstable Tower - Plus sign 2"),
    ([(0, 2), (1, 0), (1, 1), (1, 2), (2, 1)], "O", "Laboratory - T/Corner"),
    ([(0, 0), (0, 1), (0, 2)], "P", "Theater - 1x3 Bar"),
    ([(0, 1), (1, 0), (1, 1), (1, 2)], "Q", "Cozy Home - T-tetromino"),
    ([(0, 0), (0, 1), (0, 2), (0, 3), (0, 4), (1, 1), (1, 2), (1, 3), (2, 2)], "R", "Mansion - Arrow/House"),
    ([(0, 0), (0, 1), (1, 0), (1, 1), (2, 1), (3, 1)], "Y", "Falconry Hut - Longer P-pentomino 3"),
    ([(0, 0), (0, 2), (1, 0), (1, 1), (1, 2), (2, 0), (2, 1), (2, 2)], "Z", "Hidden Temple - U-pentomino"),
]

# ---------------------------------------------------------------------------
# Zone 2 pieces: the six "buildings" that pack around M in its own
# dedicated zone. Drawn exactly as given, row 0 = top row of the ASCII art.
# ---------------------------------------------------------------------------
zone_2_buildings_def = [
    ([(0, 0), (0, 1), (0, 2),
       (1, 0), (1, 1), (1, 2),
       (2, 0), (2, 1), (2, 2),
       (3, 1)], "S", "Capitolium"),
    ([(0, 0), (0, 1), (0, 2), (0, 3),
       (1, 0), (1, 1), (1, 2), (1, 3),
       (2, 1), (2, 2)], "T", "Warrior's Guild"),
    ([(0, 0), (0, 1), (0, 2), (0, 3),
       (1, 0), (1, 1), (1, 2), (1, 3),
       (2, 0),
       (3, 0)], "U", "Hospital"),
    ([(0, 0), (0, 1), (0, 2), (0, 3),
       (1, 0), (1, 1), (1, 2), (1, 3),
       (2, 0), (2, 1)], "V", "Wagon Factory"),
    ([(0, 0), (0, 1), (0, 2),
       (1, 0), (1, 1), (1, 2),
       (2, 1), (2, 2), (2, 3)], "W", "Marksman's Guild"),
    ([(0, 1), (0, 2),
       (1, 0), (1, 1),
       (2, 0), (2, 1),
       (3, 0), (3, 1),
       (4, 1), (4, 2)], "X", "Grand Museum"),
]

assert sum(len(s) for s, _, _ in zone_2_buildings_def) == 59, "building cell count changed"

# Sanity check: all Zone 1 piece labels must be unique, and none of them may
# collide with the reserved "@" character used for the center marker block
# (previously this was "Z", which broke the moment a real "Z" piece -
# Hidden Temple - was added below).
_zone1_labels = [lbl for _, lbl, _ in zone_1_buildings_def]
assert len(_zone1_labels) == len(set(_zone1_labels)), "duplicate Zone 1 piece label"
assert "@" not in _zone1_labels, "'@' is reserved for the center marker block"

# ---------------------------------------------------------------------------
# Board layout.
#
# Board is 23x23 -- sized for comfortable room, not because the zones need
# it (they'd fit on 17x17 too). Zone 1 (7x7 dense-pack zone) and Zone 2
# (M's zone) are allowed to physically overlap -- Zone 2 is shifted
# diagonally from Zone 1 so the two share a 3x3 overlap block, and both are
# centered symmetrically on the larger board so every piece has generous
# room to sprawl outside its own zone (as allowed) without the two zones'
# "extend-outward" pieces immediately colliding with each other along the
# edges. M is pinned to the exact center cell of Zone 2's 7x7 box (see
# ZONE2_CENTER / PIECE_REQUIRED_CELLS below), so it has exactly one legal
# placement and sits dead-center among the six Zone-2 buildings. It's still
# eligible for the plus-sign/P-pentomino adjacency bonus. The six buildings
# only need to touch Zone 2.
# ---------------------------------------------------------------------------
BOARD_SIZE = 23

R_START, R_END = 6, 12       # Zone 1 (rows)
C_START, C_END = 6, 12       # Zone 1 (cols)

M_R_START, M_R_END = 10, 16  # Zone 2 (rows) -- shifted +4/+4, overlaps Zone 1
M_C_START, M_C_END = 10, 16  # Zone 2 (cols) -- shared block: rows/cols 10-12

ZONE1_BOUNDS = (R_START, R_END, C_START, C_END)
ZONE2_BOUNDS = (M_R_START, M_R_END, M_C_START, M_C_END)

# The single center cell of Zone 2's 7x7 box (10..16 -> middle index 13).
ZONE2_CENTER = ((M_R_START + M_R_END) // 2, (M_C_START + M_C_END) // 2)

# Which zone(s) each piece's candidates must touch. Every Zone-1 piece
# (including the new Y and Z) targets Zone 1 as before; buildings only need
# to touch Zone 2.
#
# M is pinned dead-center in Zone 2 (see PIECE_REQUIRED_CELLS below): its
# plus-sign shape is exactly 3x3, so once its middle cell sits on
# ZONE2_CENTER the whole piece is automatically inside Zone 2 -- but that
# also puts it entirely outside Zone 1's box (rows/cols 6-12), since the
# two zones only overlap in rows/cols 10-12 and the Zone-2 center (13,13)
# is past that overlap. So M is no longer required to touch Zone 1; it's a
# Zone-2 piece now, still eligible for the plus-sign/P-pentomino adjacency
# bonus since that only cares about which cells end up next to each other.
PIECE_REQUIRED_ZONES = {lbl: [ZONE1_BOUNDS] for _, lbl, _ in zone_1_buildings_def}
PIECE_REQUIRED_ZONES["M"] = [ZONE2_BOUNDS]
for _, lbl, _ in zone_2_buildings_def:
    PIECE_REQUIRED_ZONES[lbl] = [ZONE2_BOUNDS]

# Cells a piece's placement is hard-required to cover, beyond the zone
# checks above. M must cover the exact center of Zone 2.
PIECE_REQUIRED_CELLS = {"M": ZONE2_CENTER}

# Adjacency preference groups (soft "if possible" preferences) -- unchanged.
# Y and Z are not part of any preference group yet; add them here if you
# want them to participate in a bonus (e.g. P_PENTOMINO_LABELS.append("Y")).
PLUS_SIGN_LABELS = ["M", "N"]
P_PENTOMINO_LABELS = ["J", "K"]
BAR_LABEL = "P"
SQUARE2x2_LABEL = "F"
T_TETROMINO_LABEL = "Q"
L_TROMINO_LABELS = ["A", "B", "C", "D"]
U_PENTOMINO_LABEL = "L"

# --- Tunable run parameters --------------------------------------------
TIME_LIMIT_COVERAGE = 60.0       # phase 1: maximize Zone 1 coverage
TIME_LIMIT_ZONE2 = 60.0          # phase 2: maximize Zone 2 (buildings) compactness
TIME_LIMIT_PREFERENCES = 60.0    # phase 3: maximize adjacency preferences
TIME_LIMIT_EXPOSURE = 60.0       # phase 4: maximize M's exposure
TIME_LIMIT_PER_ALTERNATE = 30.0
NUM_ALTERNATE_SOLUTIONS = 3      # how many distinct top-scoring layouts to show
NUM_SEARCH_WORKERS = 8
# -------------------------------------------------------------------------

t0 = time.time()
log("Building model...")

model = cp_model.CpModel()
x_vars = {}
placements_by_label = {label: [] for _, label, _ in zone_1_buildings_def}
placements_by_label.update({label: [] for _, label, _ in zone_2_buildings_def})
# label_cell_vars[label][(r, c)] = list of placement-vars of that piece
# that would cover cell (r, c). Used for cheap adjacency/exposure bookkeeping.
label_cell_vars = {label: {} for label in placements_by_label}


def touches_zone(cells, r0, r1, c0, c1):
    return any(r0 <= pr <= r1 and c0 <= pc <= c1 for pr, pc in cells)


def touches_all_zones(cells, zones):
    # Each zone in the list must have >=1 covered cell -- not necessarily
    # the *same* cell, so a piece can straddle two zones. This is how M
    # ends up required to be "in both zones" at once.
    return all(touches_zone(cells, *z) for z in zones)


orientation_cache = {}


def add_piece_candidates(p_idx, raw_shape, label, name, required_zones, required_cell=None):
    shape_key = tuple(raw_shape)
    if shape_key not in orientation_cache:
        orientation_cache[shape_key] = get_orientations(raw_shape)
    orientations = orientation_cache[shape_key]

    piece_var_count = 0
    for o_idx, shape in enumerate(orientations):
        max_r = max(r for r, c in shape)
        max_c = max(c for r, c in shape)
        for r in range(BOARD_SIZE - max_r):
            for c in range(BOARD_SIZE - max_c):
                placed_cells = [(r + dr, c + dc) for dr, dc in shape]
                if required_cell is not None and required_cell not in placed_cells:
                    continue
                if touches_all_zones(placed_cells, required_zones):
                    v = model.NewBoolVar(f"x_{p_idx}_{o_idx}_{r}_{c}")
                    x_vars[(p_idx, o_idx, r, c)] = (v, placed_cells)
                    placements_by_label[label].append((v, placed_cells))
                    for cell in placed_cells:
                        label_cell_vars[label].setdefault(cell, []).append(v)
                    piece_var_count += 1
    return len(orientations), piece_var_count


p_idx = 0
for raw_shape, label, name in zone_1_buildings_def:
    zones = PIECE_REQUIRED_ZONES[label]
    req_cell = PIECE_REQUIRED_CELLS.get(label)
    n_orient, n_cand = add_piece_candidates(p_idx, raw_shape, label, name, zones, req_cell)
    tag = f" [pinned to Zone 2 center {ZONE2_CENTER}]" if label == "M" else ""
    log(f"  Piece {label:>2} ({name:<14}): {n_orient} orientation(s), "
        f"{n_cand} candidate placements{tag}")
    p_idx += 1

for raw_shape, label, name in zone_2_buildings_def:
    zones = PIECE_REQUIRED_ZONES[label]
    req_cell = PIECE_REQUIRED_CELLS.get(label)
    n_orient, n_cand = add_piece_candidates(p_idx, raw_shape, label, name, zones, req_cell)
    log(f"  Piece {label:>2} ({name:<14}): {n_orient} orientation(s), "
        f"{n_cand} candidate placements")
    p_idx += 1

NUM_PIECES = p_idx
log(f"Total placement variables: {len(x_vars)}")

log("Adding 'exactly one placement per piece' constraints...")
for pi in range(NUM_PIECES):
    p_vars = [v for (p, o, r, c), (v, cells) in x_vars.items() if p == pi]
    model.AddExactlyOne(p_vars)

center_var_h = model.NewBoolVar("center_h")
center_var_v = model.NewBoolVar("center_v")
model.AddExactlyOne([center_var_h, center_var_v])

# The center 1x3 marker block still lives in the middle of Zone 1.
# NOTE: it is displayed/legend-labeled as "@" (not "Z") because "Z" is now
# a real piece label (Hidden Temple, added above) -- reusing "Z" for both
# would make them indistinguishable on the printed grid.
center_cells_h = [(9, 8), (9, 9), (9, 10)]
center_cells_v = [(8, 9), (9, 9), (10, 9)]

log("Indexing cell coverage...")
cell_index = {}
for (p, o, r, c), (v, cells) in x_vars.items():
    for cell in cells:
        cell_index.setdefault(cell, []).append(v)
for cell in center_cells_h:
    cell_index.setdefault(cell, []).append(center_var_h)
for cell in center_cells_v:
    cell_index.setdefault(cell, []).append(center_var_v)

log("Adding non-overlap constraints...")
for gr in range(BOARD_SIZE):
    for gc in range(BOARD_SIZE):
        cell_vars = cell_index.get((gr, gc))
        if cell_vars:
            model.Add(sum(cell_vars) <= 1)


def empty_expr(cell):
    """Linear expression: 1 if nothing covers `cell`, 0 otherwise."""
    vs = cell_index.get(cell)
    if not vs:
        return 1
    return 1 - sum(vs)


log("Adding coverage constraints for Zone 1 (7x7)...")
covered_grid_vars = []
for gr in range(R_START, R_END + 1):
    for gc in range(C_START, C_END + 1):
        c_vars = cell_index.get((gr, gc), [])
        cov = model.NewBoolVar(f"cov1_{gr}_{gc}")
        model.Add(sum(c_vars) == cov)
        covered_grid_vars.append(cov)

log("Adding coverage constraints for Zone 2 (M's 7x7)...")
covered_grid_vars2 = []
for gr in range(M_R_START, M_R_END + 1):
    for gc in range(M_C_START, M_C_END + 1):
        c_vars = cell_index.get((gr, gc), [])
        cov = model.NewBoolVar(f"cov2_{gr}_{gc}")
        model.Add(sum(c_vars) == cov)
        covered_grid_vars2.append(cov)

# ---------------------------------------------------------------------------
# Soft adjacency preferences (cell-edge formulation - cheap) -- unchanged.
# ---------------------------------------------------------------------------
log("Building adjacency-preference bonus variables...")


def group_cell_occupancy(labels):
    occ = {}
    for lbl in labels:
        for cell, vars_ in label_cell_vars.get(lbl, {}).items():
            occ.setdefault(cell, []).extend(vars_)
    return occ


def build_adjacency_bonus(model, labels_a, labels_b, name):
    occ_a = group_cell_occupancy(labels_a)
    occ_b = group_cell_occupancy(labels_b)

    edge_vars = []
    relevant_cells = set(occ_a) | set(occ_b)
    for (r, c) in relevant_cells:
        for dr, dc in ((1, 0), (0, 1)):
            nb = (r + dr, c + dc)
            if nb[0] >= BOARD_SIZE or nb[1] >= BOARD_SIZE:
                continue
            a_here = occ_a.get((r, c))
            b_there = occ_b.get(nb)
            if a_here and b_there:
                e = model.NewBoolVar(f"{name}_e_{r}_{c}_fwd")
                model.Add(e <= sum(a_here))
                model.Add(e <= sum(b_there))
                edge_vars.append(e)
            b_here = occ_b.get((r, c))
            a_there = occ_a.get(nb)
            if b_here and a_there:
                e = model.NewBoolVar(f"{name}_e_{r}_{c}_rev")
                model.Add(e <= sum(b_here))
                model.Add(e <= sum(a_there))
                edge_vars.append(e)

    bonus = model.NewBoolVar(f"{name}_bonus")
    if edge_vars:
        model.Add(bonus <= sum(edge_vars))
    else:
        model.Add(bonus == 0)
    return bonus, len(edge_vars)


bonus_plus_pent, n1 = build_adjacency_bonus(model, PLUS_SIGN_LABELS, P_PENTOMINO_LABELS, "plus_pent")
log(f"  Plus-sign <-> P-pentomino: {n1} candidate adjacency edges")

bonus_bar_square, n2 = build_adjacency_bonus(model, [BAR_LABEL], [SQUARE2x2_LABEL], "bar_square")
log(f"  1x3 Bar <-> 2x2 Square: {n2} candidate adjacency edges")

adj_to_Q = {}
adj_to_U = {}
for lbl in L_TROMINO_LABELS:
    adjQ, nq = build_adjacency_bonus(model, [lbl], [T_TETROMINO_LABEL], f"{lbl}_adjQ")
    adjU, nu = build_adjacency_bonus(model, [lbl], [U_PENTOMINO_LABEL], f"{lbl}_adjU")
    adj_to_Q[lbl] = adjQ
    adj_to_U[lbl] = adjU
    log(f"  L-tromino {lbl} <-> T-tetromino: {nq} edges, "
        f"<-> U-pentomino: {nu} edges")

is_T_partner = {}
is_U_partner = {}
for lbl in L_TROMINO_LABELS:
    t_var = model.NewBoolVar(f"{lbl}_is_T_partner")
    u_var = model.NewBoolVar(f"{lbl}_is_U_partner")
    model.Add(t_var <= adj_to_Q[lbl])
    model.Add(u_var <= adj_to_U[lbl])
    model.Add(t_var + u_var <= 1)
    is_T_partner[lbl] = t_var
    is_U_partner[lbl] = u_var

bonus_T_tromino = model.NewBoolVar("bonus_T_tromino")
model.Add(bonus_T_tromino <= sum(is_T_partner.values()))
bonus_U_tromino = model.NewBoolVar("bonus_U_tromino")
model.Add(bonus_U_tromino <= sum(is_U_partner.values()))

PREFERENCE_BONUSES = {
    "Plus sign next to a P-pentomino": bonus_plus_pent,
    "1x3 Bar next to the 2x2 Square": bonus_bar_square,
    "T-tetromino next to an L-tromino": bonus_T_tromino,
    "A different L-tromino next to the U-pentomino": bonus_U_tromino,
}

bonus_total = model.NewIntVar(0, len(PREFERENCE_BONUSES), "bonus_total")
model.Add(bonus_total == sum(PREFERENCE_BONUSES.values()))

# ---------------------------------------------------------------------------
# M's exposure score (soft, maximized) and pathway-to-boundary
# (hard constraint, always enforced).
#
# Exposure: for every edge between a cell M occupies and an orthogonally
# adjacent cell, count it if that neighbor ends up empty. More such edges
# = more of M's perimeter left open rather than boxed in by buildings.
#
# Pathway: a unit of flow must be able to travel from a cell touching M,
# through only empty cells, all the way to the outer edge of the board.
# This is modeled as an s-t flow of value 1 over the grid graph, where an
# arc can only carry flow if both endpoints are empty. Because flow is
# integral with unit capacities, a feasible flow of value 1 necessarily
# contains an actual connected empty-cell path from M to the boundary
# (standard flow-for-connectivity technique) -- it's not just "M has one
# free neighbor", it's a real corridor all the way out.
# ---------------------------------------------------------------------------
log("Building M exposure-score variables...")

occ_M = label_cell_vars["M"]  # cell -> list of M placement-vars covering it

exposure_edges = []
for (r, c), vlist in occ_M.items():
    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nb = (r + dr, c + dc)
        if not (0 <= nb[0] < BOARD_SIZE and 0 <= nb[1] < BOARD_SIZE):
            continue
        e = model.NewBoolVar(f"expose_{r}_{c}_{nb[0]}_{nb[1]}")
        model.Add(e <= sum(vlist))
        # e can only be 1 if the neighbor is empty:
        nb_vars = cell_index.get(nb)
        if nb_vars:
            model.Add(e <= 1 - sum(nb_vars))
        exposure_edges.append(e)

exposure_score = model.NewIntVar(0, len(exposure_edges), "exposure_score")
model.Add(exposure_score == sum(exposure_edges))
log(f"  M exposure: {len(exposure_edges)} candidate perimeter edges")

log("Building pathway-to-boundary flow network for M...")

FLOW_VALUE = 1  # one unit is enough to prove a connected corridor exists

# Directed arcs between every pair of orthogonally-adjacent board cells.
# Capacity 1, and an arc can only be used if BOTH endpoints are empty.
flow_arcs = {}
for r in range(BOARD_SIZE):
    for c in range(BOARD_SIZE):
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE:
                a = model.NewBoolVar(f"flow_{r}_{c}_to_{nr}_{nc}")
                model.Add(a <= empty_expr((r, c)))
                model.Add(a <= empty_expr((nr, nc)))
                flow_arcs[((r, c), (nr, nc))] = a

# Super-source arcs: from S into any empty cell orthogonally adjacent to M.
source_arcs = {}
m_neighbor_cells = set()
for (r, c) in occ_M:
    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nb = (r + dr, c + dc)
        if 0 <= nb[0] < BOARD_SIZE and 0 <= nb[1] < BOARD_SIZE:
            m_neighbor_cells.add(nb)
for cell in m_neighbor_cells:
    a = model.NewBoolVar(f"src_to_{cell[0]}_{cell[1]}")
    # Only usable if this cell is actually adjacent to an active M cell.
    adj_occ = []
    r, c = cell
    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nb = (r + dr, c + dc)
        if nb in occ_M:
            adj_occ.extend(occ_M[nb])
    if adj_occ:
        model.Add(a <= sum(adj_occ))
    else:
        model.Add(a == 0)
    model.Add(a <= empty_expr(cell))
    source_arcs[cell] = a

# Super-sink arcs: from any empty boundary cell into T.
sink_arcs = {}
for r in range(BOARD_SIZE):
    for c in range(BOARD_SIZE):
        if r in (0, BOARD_SIZE - 1) or c in (0, BOARD_SIZE - 1):
            a = model.NewBoolVar(f"sink_from_{r}_{c}")
            model.Add(a <= empty_expr((r, c)))
            sink_arcs[(r, c)] = a

model.Add(sum(source_arcs.values()) == FLOW_VALUE)
model.Add(sum(sink_arcs.values()) == FLOW_VALUE)

# Flow conservation at every grid cell (inflow == outflow, counting S/T arcs).
in_by_cell = {}
out_by_cell = {}
for (u, v), a in flow_arcs.items():
    out_by_cell.setdefault(u, []).append(a)
    in_by_cell.setdefault(v, []).append(a)
for cell, a in source_arcs.items():
    in_by_cell.setdefault(cell, []).append(a)
for cell, a in sink_arcs.items():
    out_by_cell.setdefault(cell, []).append(a)

all_flow_cells = set(in_by_cell) | set(out_by_cell)
for cell in all_flow_cells:
    model.Add(sum(in_by_cell.get(cell, [])) == sum(out_by_cell.get(cell, [])))

log(f"  Pathway network: {len(flow_arcs)} grid arcs, "
    f"{len(source_arcs)} source arcs, {len(sink_arcs)} sink arcs "
    "(hard constraint: flow value = 1 always required)")

log(f"Model built in {time.time() - t0:.2f}s")

# ---------------------------------------------------------------------------
# Shared progress-printing solution callback
# ---------------------------------------------------------------------------
class ProgressPrinter(cp_model.CpSolverSolutionCallback):
    def __init__(self, label, value_fn):
        super().__init__()
        self.label = label
        self.value_fn = value_fn
        self.start_time = time.time()
        self.solution_count = 0

    def on_solution_callback(self):
        self.solution_count += 1
        elapsed = time.time() - self.start_time
        val = self.value_fn(self)
        log(f"  [{self.label}] Solution #{self.solution_count} @ {elapsed:6.2f}s: "
            f"{val} (best bound: {self.BestObjectiveBound():.0f})")


ALL_LABELS = [lbl for _, lbl, _ in zone_1_buildings_def] + [lbl for _, lbl, _ in zone_2_buildings_def]


def render_grid(solver, title=""):
    grid = [["." for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
    if solver.Value(center_var_h):
        for r, c in center_cells_h:
            grid[r][c] = "@"
    else:
        for r, c in center_cells_v:
            grid[r][c] = "@"

    for (p, o, r, c), (v, cells) in x_vars.items():
        if solver.Value(v):
            lbl = ALL_LABELS[p]
            for pr, pc in cells:
                grid[pr][pc] = lbl

    colors = {
        "@": "\033[93m",  # center 1x3 marker block (Zone 1)
        "A": "\033[91m", "B": "\033[92m", "C": "\033[94m",
        "D": "\033[95m", "E": "\033[96m", "F": "\033[97m", "G": "\033[31m",
        "H": "\033[32m", "I": "\033[33m", "J": "\033[34m", "K": "\033[35m",
        "L": "\033[36m", "M": "\033[90m", "N": "\033[91m", "O": "\033[92m",
        "P": "\033[94m", "Q": "\033[95m", "R": "\033[96m",
        "S": "\033[31m", "T": "\033[32m", "U": "\033[33m", "V": "\033[34m",
        "W": "\033[35m", "X": "\033[36m",
        "Y": "\033[1;33m", "Z": "\033[1;36m",  # newly added pieces
        ".": "\033[0m",
    }
    reset = "\033[0m"

    covered1 = sum(solver.Value(cov) for cov in covered_grid_vars)
    covered2 = sum(solver.Value(cov) for cov in covered_grid_vars2)
    print()
    if title:
        print(f"=== {title} ===")
    print(f"Zone 1 (@) density: {covered1} / 49 cells filled")
    print(f"Zone 2 (M) density: {covered2} / 49 cells filled")
    print(f"M exposure score: {solver.Value(exposure_score)} / {len(exposure_edges)} open perimeter edges")
    satisfied = [name for name, b in PREFERENCE_BONUSES.items() if solver.Value(b)]
    print(f"Adjacency preferences satisfied ({len(satisfied)}/{len(PREFERENCE_BONUSES)}):")
    for name in PREFERENCE_BONUSES:
        mark = "YES" if solver.Value(PREFERENCE_BONUSES[name]) else "no "
        print(f"  [{mark}] {name}")

    header = "     " + "".join([f"{c:3}" for c in range(BOARD_SIZE)])
    print(header)
    for r in range(BOARD_SIZE):
        row_str = f"{r:2} | "
        for c in range(BOARD_SIZE):
            val = grid[r][c]
            col = colors.get(val, reset)
            in_zone1 = R_START <= r <= R_END and C_START <= c <= C_END
            in_zone2 = M_R_START <= r <= M_R_END and M_C_START <= c <= M_C_END
            if (in_zone1 or in_zone2) and val == ".":
                row_str += "\033[100m . \033[0m"
            else:
                row_str += f"{col} {val} {reset}"
        print(row_str)

    print("\nPiece Legend:")
    print(f"{colors['@']}[ @ ]{reset} = Center 1x3 Block (Zone 1)")
    for raw_shape, lbl, name in zone_1_buildings_def:
        col = colors.get(lbl, reset)
        tag = " (Zone 2 home)" if lbl == "M" else ""
        print(f"{col}[ {lbl} ]{reset} = {name}{tag}")
    for raw_shape, lbl, name in zone_2_buildings_def:
        col = colors.get(lbl, reset)
        print(f"{col}[ {lbl} ]{reset} = {name} (Zone 2)")


# ---------------------------------------------------------------------------
# Phase 1: maximize Zone 1 coverage
# ---------------------------------------------------------------------------
solver = cp_model.CpSolver()
solver.parameters.num_search_workers = NUM_SEARCH_WORKERS
solver.parameters.log_search_progress = False
solver.parameters.cp_model_presolve = True
solver.parameters.linearization_level = 2

model.Maximize(sum(covered_grid_vars))
solver.parameters.max_time_in_seconds = TIME_LIMIT_COVERAGE

log("PHASE 1/5: maximizing Zone 1 coverage...")
printer1 = ProgressPrinter(
    "zone1-coverage",
    lambda cb: f"{sum(cb.Value(v) for v in covered_grid_vars)}/49 covered",
)
status = solver.Solve(model, printer1)
if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
    log(f"Phase 1 failed with status {solver.StatusName(status)}. Aborting.")
    sys.exit(1)

best_coverage = sum(solver.Value(v) for v in covered_grid_vars)
log(f"PHASE 1 done: best Zone 1 coverage = {best_coverage}/49 "
    f"(status={solver.StatusName(status)})")
model.Add(sum(covered_grid_vars) == best_coverage)

# ---------------------------------------------------------------------------
# Phase 2: maximize Zone 2 (buildings around M) compactness
# ---------------------------------------------------------------------------
model.Maximize(sum(covered_grid_vars2))
solver.parameters.max_time_in_seconds = TIME_LIMIT_ZONE2

log("PHASE 2/5: maximizing Zone 2 compactness (buildings packed tight)...")
printer2 = ProgressPrinter(
    "zone2-compactness",
    lambda cb: f"{sum(cb.Value(v) for v in covered_grid_vars2)}/49 covered",
)
status = solver.Solve(model, printer2)
if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
    log(f"Phase 2 failed with status {solver.StatusName(status)}. "
        "Continuing with Zone 1 result only.")
    best_zone2 = 0
else:
    best_zone2 = sum(solver.Value(v) for v in covered_grid_vars2)
    log(f"PHASE 2 done: best Zone 2 coverage = {best_zone2}/49 "
        f"(status={solver.StatusName(status)})")
    model.Add(sum(covered_grid_vars2) == best_zone2)

# ---------------------------------------------------------------------------
# Phase 3: with coverage locked in, maximize satisfied adjacency preferences
# ---------------------------------------------------------------------------
model.Maximize(bonus_total)
solver.parameters.max_time_in_seconds = TIME_LIMIT_PREFERENCES

log("PHASE 3/5: maximizing satisfied adjacency preferences...")
printer3 = ProgressPrinter(
    "preferences",
    lambda cb: f"{cb.Value(bonus_total)}/{len(PREFERENCE_BONUSES)} preferences satisfied",
)
status = solver.Solve(model, printer3)
if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
    log(f"Phase 3 failed with status {solver.StatusName(status)}. "
        "Falling back to prior result only.")
    best_bonus = 0
else:
    best_bonus = solver.Value(bonus_total)
    log(f"PHASE 3 done: best preference score = {best_bonus}/{len(PREFERENCE_BONUSES)} "
        f"(status={solver.StatusName(status)})")
    model.Add(bonus_total == best_bonus)

# ---------------------------------------------------------------------------
# Phase 4: maximize M's exposure (pathway is a hard constraint throughout,
# already enforced in every phase above -- it never gets relaxed).
# ---------------------------------------------------------------------------
model.Maximize(exposure_score)
solver.parameters.max_time_in_seconds = TIME_LIMIT_EXPOSURE

log("PHASE 4/5: maximizing M's exposure (pathway already guaranteed)...")
printer4 = ProgressPrinter(
    "exposure",
    lambda cb: f"{cb.Value(exposure_score)}/{len(exposure_edges)} open perimeter edges",
)
status = solver.Solve(model, printer4)
if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
    log(f"Phase 4 failed with status {solver.StatusName(status)}. "
        "Falling back to prior result only.")
    best_exposure = 0
else:
    best_exposure = solver.Value(exposure_score)
    log(f"PHASE 4 done: best exposure score = {best_exposure}/{len(exposure_edges)} "
        f"(status={solver.StatusName(status)})")
    model.Add(exposure_score == best_exposure)

# ---------------------------------------------------------------------------
# Phase 5: collect several distinct top-scoring layouts
# ---------------------------------------------------------------------------
log(f"PHASE 5/5: searching for up to {NUM_ALTERNATE_SOLUTIONS} distinct "
    f"layout(s) at zone1={best_coverage}, zone2={best_zone2}, "
    f"prefs={best_bonus}, exposure={best_exposure}...")

solutions_found = 0
for i in range(NUM_ALTERNATE_SOLUTIONS):
    solver.parameters.max_time_in_seconds = TIME_LIMIT_PER_ALTERNATE
    log(f"  Searching for layout #{i + 1}...")
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        log(f"  No further distinct layouts found (status={solver.StatusName(status)}).")
        break

    solutions_found += 1
    render_grid(solver, title=f"Layout {solutions_found}")

    active_vars = [v for (p, o, r, c), (v, cells) in x_vars.items() if solver.Value(v)]
    active_vars.append(center_var_h if solver.Value(center_var_h) else center_var_v)
    model.Add(sum(active_vars) <= len(active_vars) - 1)

log(f"\nDone. Found {solutions_found} distinct top-scoring layout(s) "
    f"(zone1={best_coverage}/49, zone2={best_zone2}/49, "
    f"prefs={best_bonus}/{len(PREFERENCE_BONUSES)}, "
    f"exposure={best_exposure}/{len(exposure_edges)}).")