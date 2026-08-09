"""Terminal output: the ASCII/ANSI grid, the score summary, and the legend.

The summary lines double as independent checks. Rather than trusting the model,
`render_layout` re-derives M's centering and the corridor out to the board edge
from the finished grid, so a broken constraint shows up as FAILED on screen.
"""

from .geometry import ORTHO
from .pieces import ALL_PIECES, CENTER_MARKER, ZONE_1_PIECES, ZONE_2_PIECES
from . import layout as L

EMPTY = "."
PATH = "*"

RESET = "\033[0m"
ZONE_SHADING = "\033[100m"   # grey background on empty in-zone cells

COLORS = {
    CENTER_MARKER: "\033[93m",  # center 1x3 marker block (Zone 1)
    PATH: "\033[1;92m",         # corridor from M out to the board edge
    "A": "\033[91m", "B": "\033[92m", "C": "\033[94m",
    "D": "\033[95m", "E": "\033[96m", "F": "\033[97m", "G": "\033[31m",
    "H": "\033[32m", "I": "\033[33m", "J": "\033[34m", "K": "\033[35m",
    "L": "\033[36m", "M": "\033[1;97;41m", "N": "\033[91m", "O": "\033[92m",
    "P": "\033[94m", "Q": "\033[95m", "R": "\033[96m",
    "S": "\033[31m", "T": "\033[32m", "U": "\033[33m", "V": "\033[34m",
    "W": "\033[35m", "X": "\033[36m",
    "Y": "\033[1;33m", "Z": "\033[1;36m",
    EMPTY: RESET,
}


def build_grid(pm, solver):
    """The solved board as a grid of label characters ("." where empty)."""
    grid = [[EMPTY for _ in range(L.BOARD_SIZE)] for _ in range(L.BOARD_SIZE)]

    marker_cells = (L.CENTER_CELLS_H if solver.Value(pm.center_var_h)
                    else L.CENTER_CELLS_V)
    for r, c in marker_cells:
        grid[r][c] = CENTER_MARKER

    for (p_idx, _, _, _), (var, cells) in pm.x_vars.items():
        if solver.Value(var):
            label = ALL_PIECES[p_idx].label
            for r, c in cells:
                grid[r][c] = label

    return grid


def shortest_path_out(grid):
    """Shortest route of empty cells from M's perimeter to the board edge.

    Returns the cells in order (M-perimeter end first, boundary cell last), or
    [] if M is walled in. This verifies the pathway requirement from the
    rendered grid, independently of the flow network that enforces it -- and
    unlike the flow variables it yields one clean route rather than every empty
    cell the solver happened to light up.
    """
    starts = [cell for cell in sorted(L.M_ADJACENT_CELLS)
              if grid[cell[0]][cell[1]] == EMPTY]
    came_from = {cell: None for cell in starts}
    frontier = list(starts)
    goal = None

    while frontier and goal is None:
        next_frontier = []
        for cell in frontier:
            r, c = cell
            if L.on_boundary(r, c):
                goal = cell
                break
            for dr, dc in ORTHO:
                nb = (r + dr, c + dc)
                if not L.on_board(nb):
                    continue
                if nb in came_from or grid[nb[0]][nb[1]] != EMPTY:
                    continue
                came_from[nb] = cell
                next_frontier.append(nb)
        frontier = next_frontier

    if goal is None:
        return []

    route = []
    cell = goal
    while cell is not None:
        route.append(cell)
        cell = came_from[cell]
    route.reverse()          # M-perimeter first, boundary cell last
    return route


def render_layout(pm, solver, title=""):
    grid = build_grid(pm, solver)

    path = shortest_path_out(grid)
    for r, c in path:
        grid[r][c] = PATH

    _print_summary(pm, solver, grid, path, title)
    _print_grid(grid)
    _print_legend()


def _print_summary(pm, solver, grid, path, title):
    covered1 = sum(solver.Value(v) for v in pm.covered_zone1)
    covered2 = sum(solver.Value(v) for v in pm.covered_zone2)

    m_cells_drawn = {
        (r, c)
        for r in range(L.BOARD_SIZE)
        for c in range(L.BOARD_SIZE)
        if grid[r][c] == L.CENTER_PIECE_LABEL
    }
    centered_ok = m_cells_drawn == set(L.M_CELLS)

    print()
    if title:
        print(f"=== {title} ===")

    print(f"M ({L.CENTER_PIECE_LABEL}) centered on Zone 2 center {L.ZONE2_CENTER}: "
          f"{'OK' if centered_ok else 'FAILED -> ' + str(sorted(m_cells_drawn))}")
    print(f"Zone 1 ({CENTER_MARKER}) density: {covered1} / {L.ZONE_CELLS} cells filled")
    print(f"Zone 2 (M) density: {covered2} / {L.ZONE_CELLS} cells filled")
    if path:
        print(f"Pathway to M: OK -- {len(path)} empty cells from the board edge "
              f"at {path[-1]} to M's perimeter at {path[0]} (marked {PATH})")
    else:
        print("Pathway to M: FAILED -- M is walled in")
    print(f"M exposure score: {solver.Value(pm.exposure_score)} / "
          f"{len(pm.exposure_cell_vars)} open perimeter cells")

    satisfied = sum(1 for b in pm.preference_bonuses.values() if solver.Value(b))
    print(f"Adjacency preferences satisfied ({satisfied}/{len(pm.preference_bonuses)}):")
    for name, bonus in pm.preference_bonuses.items():
        mark = "YES" if solver.Value(bonus) else "no "
        print(f"  [{mark}] {name}")


def _print_grid(grid):
    print("     " + "".join(f"{c:3}" for c in range(L.BOARD_SIZE)))
    for r in range(L.BOARD_SIZE):
        row = f"{r:2} | "
        for c in range(L.BOARD_SIZE):
            val = grid[r][c]
            if val == EMPTY and (L.in_zone1(r, c) or L.in_zone2(r, c)):
                row += f"{ZONE_SHADING} {EMPTY} {RESET}"
            else:
                row += f"{COLORS.get(val, RESET)} {val} {RESET}"
        print(row)


def _print_legend():
    print("\nPiece Legend:")
    print(f"{COLORS[CENTER_MARKER]}[ {CENTER_MARKER} ]{RESET} = Center 1x3 Block (Zone 1)")
    print(f"{COLORS[PATH]}[ {PATH} ]{RESET} = Pathway to M (empty cells, M -> board edge)")
    for piece in ZONE_1_PIECES:
        tag = (f" <- CENTER OF ZONE 2 at {L.ZONE2_CENTER}"
               if piece.label == L.CENTER_PIECE_LABEL else "")
        print(f"{COLORS.get(piece.label, RESET)}[ {piece.label} ]{RESET} = {piece.name}{tag}")
    for piece in ZONE_2_PIECES:
        print(f"{COLORS.get(piece.label, RESET)}[ {piece.label} ]{RESET} = {piece.name} (Zone 2)")
