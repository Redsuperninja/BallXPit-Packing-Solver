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


pieces_def = [
    ([(0, 1), (1, 1), (1, 2)], "A", "L-tromino 1"),
    ([(0, 1), (1, 1), (1, 2)], "B", "L-tromino 2"),
    ([(0, 1), (1, 1), (1, 2)], "C", "L-tromino 3"),
    ([(0, 1), (1, 1), (1, 2)], "D", "L-tromino 4"),
    ([(r, c) for r in range(3) for c in range(3)], "E", "3x3 Square"),
    ([(r, c) for r in range(2) for c in range(2)], "F", "2x2 Square"),
    ([(r, c) for r in range(3) for c in range(2)], "G", "2x3 Rectangle"),
    ([(0, 1), (1, 1), (2, 0), (2, 1), (2, 2), (3, 1)], "H", "Cross-like"),
    ([(0, 0), (0, 1), (0, 2), (1, 1), (2, 1), (3, 0), (3, 1), (3, 2)], "I", "8-cell U/I"),
    ([(0, 0), (0, 1), (1, 0), (1, 1), (2, 1)], "J", "P-pentomino 1"),
    ([(0, 0), (0, 1), (1, 0), (1, 1), (2, 1)], "K", "P-pentomino 2"),
    ([(0, 0), (0, 2), (1, 0), (1, 1), (1, 2)], "L", "U-pentomino"),
    ([(0, 1), (1, 0), (1, 1), (1, 2), (2, 1)], "M", "Plus sign 1"),
    ([(0, 1), (1, 0), (1, 1), (1, 2), (2, 1)], "N", "Plus sign 2"),
    ([(0, 2), (1, 0), (1, 1), (1, 2), (2, 1)], "O", "T/Corner"),
    ([(0, 0), (0, 1), (0, 2)], "P", "1x3 Bar"),
    ([(0, 1), (1, 0), (1, 1), (1, 2)], "Q", "T-tetromino"),
    ([(0, 0), (0, 1), (0, 2), (0, 3), (0, 4), (1, 1), (1, 2), (1, 3), (2, 2)], "R", "Arrow/House"),
]

BOARD_SIZE = 17
R_START, R_END = 5, 11
C_START, C_END = 5, 11

# Adjacency preference groups (soft "if possible" preferences)
PLUS_SIGN_LABELS = ["M", "N"]
P_PENTOMINO_LABELS = ["J", "K"]
BAR_LABEL = "P"
SQUARE2x2_LABEL = "F"
T_TETROMINO_LABEL = "Q"
L_TROMINO_LABELS = ["A", "B", "C", "D"]
U_PENTOMINO_LABEL = "L"

# --- Tunable run parameters --------------------------------------------
TIME_LIMIT_COVERAGE = 60.0     # phase 1: maximize center coverage
TIME_LIMIT_PREFERENCES = 60.0  # phase 2: maximize adjacency preferences
TIME_LIMIT_PER_ALTERNATE = 30.0
NUM_ALTERNATE_SOLUTIONS = 3    # how many distinct top-scoring layouts to show
NUM_SEARCH_WORKERS = 8
# -------------------------------------------------------------------------

t0 = time.time()
log("Building model...")

model = cp_model.CpModel()
x_vars = {}
placements_by_label = {label: [] for _, label, _ in pieces_def}
# label_cell_vars[label][(r, c)] = list of placement-vars of that piece
# that would cover cell (r, c). Used for cheap adjacency bookkeeping.
label_cell_vars = {label: {} for _, label, _ in pieces_def}

orientation_cache = {}
for p_idx, (raw_shape, label, name) in enumerate(pieces_def):
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
                touches = any(
                    R_START <= pr <= R_END and C_START <= pc <= C_END
                    for pr, pc in placed_cells
                )
                if touches:
                    v = model.NewBoolVar(f"x_{p_idx}_{o_idx}_{r}_{c}")
                    x_vars[(p_idx, o_idx, r, c)] = (v, placed_cells)
                    placements_by_label[label].append((v, placed_cells))
                    for cell in placed_cells:
                        label_cell_vars[label].setdefault(cell, []).append(v)
                    piece_var_count += 1

    log(f"  Piece {label:>2} ({name:<14}): {len(orientations)} orientation(s), "
        f"{piece_var_count} candidate placements")

log(f"Total placement variables: {len(x_vars)}")

log("Adding 'exactly one placement per piece' constraints...")
for p_idx in range(len(pieces_def)):
    p_vars = [v for (p, o, r, c), (v, cells) in x_vars.items() if p == p_idx]
    model.AddExactlyOne(p_vars)

center_var_h = model.NewBoolVar("center_h")
center_var_v = model.NewBoolVar("center_v")
model.AddExactlyOne([center_var_h, center_var_v])

center_cells_h = [(8, 7), (8, 8), (8, 9)]
center_cells_v = [(7, 8), (8, 8), (9, 8)]

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

log("Adding coverage constraints for the 7x7 center...")
covered_grid_vars = []
for gr in range(R_START, R_END + 1):
    for gc in range(C_START, C_END + 1):
        c_vars = cell_index.get((gr, gc), [])
        cov = model.NewBoolVar(f"cov_{gr}_{gc}")
        model.Add(sum(c_vars) == cov)
        covered_grid_vars.append(cov)

# ---------------------------------------------------------------------------
# Soft adjacency preferences (cell-edge formulation - cheap)
# ---------------------------------------------------------------------------
log("Building adjacency-preference bonus variables...")


def group_cell_occupancy(labels):
    occ = {}
    for lbl in labels:
        for cell, vars_ in label_cell_vars.get(lbl, {}).items():
            occ.setdefault(cell, []).extend(vars_)
    return occ


def build_adjacency_bonus(model, labels_a, labels_b, name):
    """Returns (bonus_bool, num_edge_vars).

    Walks every orthogonal edge of the board once. For each edge between
    cell u and cell v, adds a small boolean capturing "group A occupies u
    AND group B occupies v" (and the mirrored case). bonus_bool can only be
    pushed to 1 by the solver if some such edge is actually realized.
    This is O(cells) rather than O(placements_a * placements_b), which is
    what made the naive pairwise version blow up.
    """
    occ_a = group_cell_occupancy(labels_a)
    occ_b = group_cell_occupancy(labels_b)

    edge_vars = []
    relevant_cells = set(occ_a) | set(occ_b)
    for (r, c) in relevant_cells:
        for dr, dc in ((1, 0), (0, 1)):  # each undirected edge visited once
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

# Each L-tromino may only be "credited" toward ONE of the two relationships,
# so the piece next to the T-tetromino is guaranteed to be a DIFFERENT
# physical L-tromino from the one next to the U-pentomino.
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

log(f"Model built in {time.time() - t0:.2f}s ({len(x_vars) + 2} placement/center vars)")

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


def render_grid(solver, title=""):
    grid = [["." for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
    if solver.Value(center_var_h):
        for r, c in center_cells_h:
            grid[r][c] = "Z"
    else:
        for r, c in center_cells_v:
            grid[r][c] = "Z"

    for (p, o, r, c), (v, cells) in x_vars.items():
        if solver.Value(v):
            lbl = pieces_def[p][1]
            for pr, pc in cells:
                grid[pr][pc] = lbl

    colors = {
        "Z": "\033[93m", "A": "\033[91m", "B": "\033[92m", "C": "\033[94m",
        "D": "\033[95m", "E": "\033[96m", "F": "\033[97m", "G": "\033[31m",
        "H": "\033[32m", "I": "\033[33m", "J": "\033[34m", "K": "\033[35m",
        "L": "\033[36m", "M": "\033[90m", "N": "\033[91m", "O": "\033[92m",
        "P": "\033[94m", "Q": "\033[95m", "R": "\033[96m", ".": "\033[0m",
    }
    reset = "\033[0m"

    covered_count = sum(solver.Value(cov) for cov in covered_grid_vars)
    print()
    if title:
        print(f"=== {title} ===")
    print(f"7x7 Grid Density: {covered_count} / 49 cells filled")
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
            if R_START <= r <= R_END and C_START <= c <= C_END and val == ".":
                row_str += "\033[100m . \033[0m"
            else:
                row_str += f"{col} {val} {reset}"
        print(row_str)

    print("\nPiece Legend:")
    print(f"{colors['Z']}[ Z ]{reset} = Center 1x3 Block")
    for raw_shape, lbl, name in pieces_def:
        col = colors.get(lbl, reset)
        print(f"{col}[ {lbl} ]{reset} = {name}")


# ---------------------------------------------------------------------------
# Phase 1: maximize center coverage
# ---------------------------------------------------------------------------
solver = cp_model.CpSolver()
solver.parameters.num_search_workers = NUM_SEARCH_WORKERS
solver.parameters.log_search_progress = False
solver.parameters.cp_model_presolve = True
solver.parameters.linearization_level = 2

model.Maximize(sum(covered_grid_vars))
solver.parameters.max_time_in_seconds = TIME_LIMIT_COVERAGE

log("PHASE 1/3: maximizing center coverage...")
printer1 = ProgressPrinter(
    "coverage",
    lambda cb: f"{sum(cb.Value(v) for v in covered_grid_vars)}/49 covered",
)
status = solver.Solve(model, printer1)
if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
    log(f"Phase 1 failed with status {solver.StatusName(status)}. Aborting.")
    sys.exit(1)

best_coverage = sum(solver.Value(v) for v in covered_grid_vars)
log(f"PHASE 1 done: best coverage = {best_coverage}/49 "
    f"(status={solver.StatusName(status)})")

model.Add(sum(covered_grid_vars) == best_coverage)

# ---------------------------------------------------------------------------
# Phase 2: with coverage locked in, maximize satisfied adjacency preferences
# ---------------------------------------------------------------------------
model.Maximize(bonus_total)
solver.parameters.max_time_in_seconds = TIME_LIMIT_PREFERENCES

log("PHASE 2/3: maximizing satisfied adjacency preferences "
    f"(coverage locked at {best_coverage}/49)...")
printer2 = ProgressPrinter(
    "preferences",
    lambda cb: f"{cb.Value(bonus_total)}/{len(PREFERENCE_BONUSES)} preferences satisfied",
)
status = solver.Solve(model, printer2)
if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
    log(f"Phase 2 failed with status {solver.StatusName(status)}. "
        "Falling back to phase-1 solution only.")
    best_bonus = 0
else:
    best_bonus = solver.Value(bonus_total)
    log(f"PHASE 2 done: best preference score = {best_bonus}/{len(PREFERENCE_BONUSES)} "
        f"(status={solver.StatusName(status)})")
    model.Add(bonus_total == best_bonus)

# ---------------------------------------------------------------------------
# Phase 3: collect several distinct top-scoring layouts
# ---------------------------------------------------------------------------
log(f"PHASE 3/3: searching for up to {NUM_ALTERNATE_SOLUTIONS} distinct "
    f"layout(s) at coverage={best_coverage}, preferences={best_bonus}...")

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
    # No-good cut: forbid this exact combination of placements from recurring.
    model.Add(sum(active_vars) <= len(active_vars) - 1)

log(f"\nDone. Found {solutions_found} distinct top-scoring layout(s) "
    f"(coverage={best_coverage}/49, preferences={best_bonus}/{len(PREFERENCE_BONUSES)}).")