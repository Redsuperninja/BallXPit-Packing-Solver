"""Builds the CP-SAT model: placements, non-overlap, density, preferences,
M's open perimeter, and the pathway-to-M flow network.

`build_model()` returns a PackingModel holding the model plus every variable
group that phases.py optimizes and render.py reads back.
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List

from ortools.sat.python import cp_model

from .geometry import ORTHO, get_orientations, touches_all_zones
from .logging_utils import log
from .pieces import ALL_PIECES, piece_index
from . import layout as L

FLOW_VALUE = 1  # one unit is enough to prove a connected corridor exists


@dataclass
class PackingModel:
    """The built model and the handles needed to optimize and render it."""

    model: cp_model.CpModel

    # (piece_idx, orientation_idx, row, col) -> (bool var, cells it covers)
    x_vars: Dict[tuple, tuple]
    # piece_idx -> that piece's placement vars
    placements_by_piece: Dict[int, List]
    # label -> {cell -> placement vars of that piece covering the cell}
    label_cell_vars: Dict[str, Dict[tuple, List]]
    # cell -> every var that would occupy it (placements + center marker)
    cell_index: Dict[tuple, List]

    # The Zone 1 center marker block: exactly one orientation is chosen.
    center_var_h: cp_model.IntVar
    center_var_v: cp_model.IntVar

    covered_zone1: List          # one bool per Zone 1 cell: is it filled?
    covered_zone2: List          # one bool per Zone 2 cell: is it filled?

    preference_bonuses: Dict[str, cp_model.IntVar]
    bonus_total: cp_model.IntVar

    exposure_cell_vars: List     # one bool per cell touching M: is it empty?
    exposure_score: cp_model.IntVar

    flow_arcs: Dict = field(repr=False, default_factory=dict)
    source_arcs: Dict = field(repr=False, default_factory=dict)
    sink_arcs: Dict = field(repr=False, default_factory=dict)

    def label_of_piece(self, piece_idx):
        return ALL_PIECES[piece_idx].label


def build_model():
    t0 = time.time()
    log("Building model...")

    model = cp_model.CpModel()
    builder = _Builder(model)

    builder.add_all_placements()
    builder.add_center_marker()
    builder.index_cells()
    builder.add_non_overlap()
    builder.add_zone_coverage()
    builder.add_adjacency_preferences()
    builder.add_exposure_score()
    builder.add_pathway_flow()

    log(f"Model built in {time.time() - t0:.2f}s")
    return builder.finish()


class _Builder:
    """Step-by-step construction of the model. Each method logs its stage."""

    def __init__(self, model):
        self.model = model
        self.x_vars = {}
        self.placements_by_piece = {}
        # label_cell_vars[label][(r, c)] = placement vars of that piece which
        # would cover (r, c). Used for cheap adjacency/exposure bookkeeping.
        self.label_cell_vars = {p.label: {} for p in ALL_PIECES}
        self.cell_index = {}
        self._orientation_cache = {}

    # -- placements ---------------------------------------------------------

    def add_all_placements(self):
        for p_idx, piece in enumerate(ALL_PIECES):
            zones = L.PIECE_REQUIRED_ZONES[piece.label]
            fixed = L.PIECE_FIXED_CELLS.get(piece.label)
            n_orient, n_cand = self._add_piece_candidates(p_idx, piece, zones, fixed)
            tag = f" [centered on Zone 2 center {L.ZONE2_CENTER}]" if fixed else ""
            log(f"  Piece {piece.label:>2} ({piece.name:<14}): {n_orient} orientation(s), "
                f"{n_cand} candidate placements{tag}")
            assert n_cand > 0, (
                f"piece {piece.label} has no legal placement -- model is infeasible"
            )

        log(f"Total placement variables: {len(self.x_vars)}")
        self._assert_center_piece_is_pinned()

        log("Adding 'exactly one placement per piece' constraints...")
        for p_idx in range(len(ALL_PIECES)):
            self.model.AddExactlyOne(self.placements_by_piece[p_idx])

    def _add_piece_candidates(self, p_idx, piece, required_zones, fixed_cells):
        if piece.cells not in self._orientation_cache:
            self._orientation_cache[piece.cells] = get_orientations(piece.cells)
        orientations = self._orientation_cache[piece.cells]

        count = 0
        for o_idx, shape in enumerate(orientations):
            max_r = max(r for r, _ in shape)
            max_c = max(c for _, c in shape)
            for r in range(L.BOARD_SIZE - max_r):
                for c in range(L.BOARD_SIZE - max_c):
                    placed_cells = [(r + dr, c + dc) for dr, dc in shape]
                    # An exact cell set, not just "must cover": this is what
                    # actually centers M rather than letting one of its arms
                    # land on the center cell.
                    if fixed_cells is not None and set(placed_cells) != fixed_cells:
                        continue
                    if not touches_all_zones(placed_cells, required_zones):
                        continue

                    v = self.model.NewBoolVar(f"x_{p_idx}_{o_idx}_{r}_{c}")
                    self.x_vars[(p_idx, o_idx, r, c)] = (v, placed_cells)
                    self.placements_by_piece.setdefault(p_idx, []).append(v)
                    for cell in placed_cells:
                        self.label_cell_vars[piece.label].setdefault(cell, []).append(v)
                    count += 1

        return len(orientations), count

    def _assert_center_piece_is_pinned(self):
        """M must have exactly one placement: the plus centered on Zone 2."""
        m_idx = piece_index(L.CENTER_PIECE_LABEL)
        placements = self.placements_by_piece[m_idx]
        assert len(placements) == 1, (
            f"{L.CENTER_PIECE_LABEL} should have exactly one (centered) placement, "
            f"got {len(placements)}"
        )
        assert set(self.label_cell_vars[L.CENTER_PIECE_LABEL]) == set(L.M_CELLS)
        log(f"  {L.CENTER_PIECE_LABEL} is locked to Zone 2's center: "
            f"cells {sorted(L.M_CELLS)}")

    # -- center marker block ------------------------------------------------

    def add_center_marker(self):
        self.center_var_h = self.model.NewBoolVar("center_h")
        self.center_var_v = self.model.NewBoolVar("center_v")
        self.model.AddExactlyOne([self.center_var_h, self.center_var_v])

    # -- occupancy ----------------------------------------------------------

    def index_cells(self):
        log("Indexing cell coverage...")
        for _, (v, cells) in self.x_vars.items():
            for cell in cells:
                self.cell_index.setdefault(cell, []).append(v)
        for cell in L.CENTER_CELLS_H:
            self.cell_index.setdefault(cell, []).append(self.center_var_h)
        for cell in L.CENTER_CELLS_V:
            self.cell_index.setdefault(cell, []).append(self.center_var_v)

    def add_non_overlap(self):
        log("Adding non-overlap constraints...")
        for r in range(L.BOARD_SIZE):
            for c in range(L.BOARD_SIZE):
                cell_vars = self.cell_index.get((r, c))
                if cell_vars:
                    self.model.Add(sum(cell_vars) <= 1)

    def empty_expr(self, cell):
        """Linear expression: 1 if nothing covers `cell`, 0 otherwise."""
        vs = self.cell_index.get(cell)
        if not vs:
            return 1
        return 1 - sum(vs)

    # -- density ------------------------------------------------------------

    def add_zone_coverage(self):
        log("Adding coverage constraints for Zone 1 (7x7)...")
        self.covered_zone1 = self._coverage_vars(L.ZONE1_BOUNDS, "cov1")
        log("Adding coverage constraints for Zone 2 (M's 7x7)...")
        self.covered_zone2 = self._coverage_vars(L.ZONE2_BOUNDS, "cov2")

    def _coverage_vars(self, bounds, prefix):
        r0, r1, c0, c1 = bounds
        covered = []
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                cov = self.model.NewBoolVar(f"{prefix}_{r}_{c}")
                self.model.Add(sum(self.cell_index.get((r, c), [])) == cov)
                covered.append(cov)
        return covered

    # -- soft adjacency preferences (cell-edge formulation, cheap) ----------

    def add_adjacency_preferences(self):
        log("Building adjacency-preference bonus variables...")

        bonus_plus_pent, n = self._adjacency_bonus(
            L.PLUS_SIGN_LABELS, L.P_PENTOMINO_LABELS, "plus_pent")
        log(f"  Plus-sign <-> P-pentomino: {n} candidate adjacency edges")

        bonus_bar_square, n = self._adjacency_bonus(
            [L.BAR_LABEL], [L.SQUARE2x2_LABEL], "bar_square")
        log(f"  1x3 Bar <-> 2x2 Square: {n} candidate adjacency edges")

        adj_to_q, adj_to_u = {}, {}
        for lbl in L.L_TROMINO_LABELS:
            adj_to_q[lbl], nq = self._adjacency_bonus(
                [lbl], [L.T_TETROMINO_LABEL], f"{lbl}_adjQ")
            adj_to_u[lbl], nu = self._adjacency_bonus(
                [lbl], [L.U_PENTOMINO_LABEL], f"{lbl}_adjU")
            log(f"  L-tromino {lbl} <-> T-tetromino: {nq} edges, "
                f"<-> U-pentomino: {nu} edges")

        # Each L-tromino may serve as at most one of the two partners, so the
        # two bonuses below have to be earned by *different* trominoes.
        is_t_partner, is_u_partner = {}, {}
        for lbl in L.L_TROMINO_LABELS:
            t_var = self.model.NewBoolVar(f"{lbl}_is_T_partner")
            u_var = self.model.NewBoolVar(f"{lbl}_is_U_partner")
            self.model.Add(t_var <= adj_to_q[lbl])
            self.model.Add(u_var <= adj_to_u[lbl])
            self.model.Add(t_var + u_var <= 1)
            is_t_partner[lbl] = t_var
            is_u_partner[lbl] = u_var

        bonus_t_tromino = self.model.NewBoolVar("bonus_T_tromino")
        self.model.Add(bonus_t_tromino <= sum(is_t_partner.values()))
        bonus_u_tromino = self.model.NewBoolVar("bonus_U_tromino")
        self.model.Add(bonus_u_tromino <= sum(is_u_partner.values()))

        self.preference_bonuses = {
            "Plus sign next to a P-pentomino": bonus_plus_pent,
            "1x3 Bar next to the 2x2 Square": bonus_bar_square,
            "T-tetromino next to an L-tromino": bonus_t_tromino,
            "A different L-tromino next to the U-pentomino": bonus_u_tromino,
        }
        self.bonus_total = self.model.NewIntVar(
            0, len(self.preference_bonuses), "bonus_total")
        self.model.Add(self.bonus_total == sum(self.preference_bonuses.values()))

    def _group_cell_occupancy(self, labels):
        occ = {}
        for lbl in labels:
            for cell, vars_ in self.label_cell_vars.get(lbl, {}).items():
                occ.setdefault(cell, []).extend(vars_)
        return occ

    def _adjacency_bonus(self, labels_a, labels_b, name):
        """A bool that can only be 1 if some cell of group A ends up next to
        some cell of group B. Returns (bonus var, #candidate edges)."""
        occ_a = self._group_cell_occupancy(labels_a)
        occ_b = self._group_cell_occupancy(labels_b)

        edge_vars = []
        for (r, c) in set(occ_a) | set(occ_b):
            for dr, dc in ((1, 0), (0, 1)):   # each edge visited once
                nb = (r + dr, c + dc)
                if nb[0] >= L.BOARD_SIZE or nb[1] >= L.BOARD_SIZE:
                    continue
                for here, there, suffix in (
                    (occ_a.get((r, c)), occ_b.get(nb), "fwd"),
                    (occ_b.get((r, c)), occ_a.get(nb), "rev"),
                ):
                    if here and there:
                        e = self.model.NewBoolVar(f"{name}_e_{r}_{c}_{suffix}")
                        self.model.Add(e <= sum(here))
                        self.model.Add(e <= sum(there))
                        edge_vars.append(e)

        bonus = self.model.NewBoolVar(f"{name}_bonus")
        if edge_vars:
            self.model.Add(bonus <= sum(edge_vars))
        else:
            self.model.Add(bonus == 0)
        return bonus, len(edge_vars)

    # -- M's open perimeter -------------------------------------------------

    def add_exposure_score(self):
        """How many of the 8 cells orthogonally touching M are left empty.

        Higher = more of M's perimeter open rather than walled in by buildings.
        Counted per *cell*, not per shared edge, so the score reads out of 8
        (an edge count would score the four diagonal-corner cells twice each).
        """
        log("Building M exposure-score variables...")
        # M is pinned to one placement, so its cells and neighbours are static.
        assert set(self.label_cell_vars[L.CENTER_PIECE_LABEL]) == set(L.M_CELLS)

        self.exposure_cell_vars = []
        for cell in sorted(L.M_ADJACENT_CELLS):
            e = self.model.NewBoolVar(f"expose_{cell[0]}_{cell[1]}")
            self.model.Add(e <= self.empty_expr(cell))
            self.exposure_cell_vars.append(e)

        self.exposure_score = self.model.NewIntVar(
            0, len(self.exposure_cell_vars), "exposure_score")
        self.model.Add(self.exposure_score == sum(self.exposure_cell_vars))
        log(f"  M exposure: {len(self.exposure_cell_vars)} perimeter cells around "
            f"{L.ZONE2_CENTER}")

    # -- pathway to M (hard constraint) -------------------------------------

    def add_pathway_flow(self):
        """A unit of flow must travel from a cell touching M, through only
        empty cells, all the way to the outer edge of the board.

        Modeled as an s-t flow of value 1 over the grid graph where an arc can
        only carry flow if both endpoints are empty. Because flow is integral
        with unit capacities, a feasible flow of value 1 necessarily contains a
        real connected empty-cell path from M to the boundary (the standard
        flow-for-connectivity technique) -- it is not merely "M has one free
        neighbor", it is a corridor all the way out.

        Caveat: the flow only *proves* a corridor exists. The solver is free to
        also set arcs along empty-cell cycles, which satisfy conservation and
        cost nothing, so the flow variables are not a usable picture of the
        route. render.py re-derives the actual corridor by BFS instead.
        """
        log("Building pathway-to-boundary flow network for M...")

        # Directed arcs between orthogonally-adjacent cells, capacity 1, usable
        # only if BOTH endpoints are empty.
        self.flow_arcs = {}
        for r in range(L.BOARD_SIZE):
            for c in range(L.BOARD_SIZE):
                for dr, dc in ORTHO:
                    nr, nc = r + dr, c + dc
                    if not L.on_board((nr, nc)):
                        continue
                    a = self.model.NewBoolVar(f"flow_{r}_{c}_to_{nr}_{nc}")
                    self.model.Add(a <= self.empty_expr((r, c)))
                    self.model.Add(a <= self.empty_expr((nr, nc)))
                    self.flow_arcs[((r, c), (nr, nc))] = a

        # Source arcs: from S into any empty cell touching M. (M's own cells are
        # never empty, so they are never corridor starts.)
        self.source_arcs = {}
        for cell in sorted(L.M_ADJACENT_CELLS):
            a = self.model.NewBoolVar(f"src_to_{cell[0]}_{cell[1]}")
            self.model.Add(a <= self.empty_expr(cell))
            self.source_arcs[cell] = a

        # Sink arcs: from any empty boundary cell into T.
        self.sink_arcs = {}
        for r in range(L.BOARD_SIZE):
            for c in range(L.BOARD_SIZE):
                if L.on_boundary(r, c):
                    a = self.model.NewBoolVar(f"sink_from_{r}_{c}")
                    self.model.Add(a <= self.empty_expr((r, c)))
                    self.sink_arcs[(r, c)] = a

        self.model.Add(sum(self.source_arcs.values()) == FLOW_VALUE)
        self.model.Add(sum(self.sink_arcs.values()) == FLOW_VALUE)

        # Conservation at every cell (inflow == outflow, counting S/T arcs).
        inflow, outflow = {}, {}
        for (u, v), a in self.flow_arcs.items():
            outflow.setdefault(u, []).append(a)
            inflow.setdefault(v, []).append(a)
        for cell, a in self.source_arcs.items():
            inflow.setdefault(cell, []).append(a)
        for cell, a in self.sink_arcs.items():
            outflow.setdefault(cell, []).append(a)
        for cell in set(inflow) | set(outflow):
            self.model.Add(sum(inflow.get(cell, [])) == sum(outflow.get(cell, [])))

        log(f"  Pathway network: {len(self.flow_arcs)} grid arcs, "
            f"{len(self.source_arcs)} source arcs, {len(self.sink_arcs)} sink arcs "
            "(hard constraint: flow value = 1 always required)")

    # -- assembly -----------------------------------------------------------

    def finish(self):
        return PackingModel(
            model=self.model,
            x_vars=self.x_vars,
            placements_by_piece=self.placements_by_piece,
            label_cell_vars=self.label_cell_vars,
            cell_index=self.cell_index,
            center_var_h=self.center_var_h,
            center_var_v=self.center_var_v,
            covered_zone1=self.covered_zone1,
            covered_zone2=self.covered_zone2,
            preference_bonuses=self.preference_bonuses,
            bonus_total=self.bonus_total,
            exposure_cell_vars=self.exposure_cell_vars,
            exposure_score=self.exposure_score,
            flow_arcs=self.flow_arcs,
            source_arcs=self.source_arcs,
            sink_arcs=self.sink_arcs,
        )
