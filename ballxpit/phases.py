"""The staged optimization pipeline.

Requirements are optimized in descending priority. After each phase its result
is *locked in* with an equality constraint, so later phases can only improve
lower-priority scores and can never trade away a higher-priority one:

    1. Zone 1 density          -- fill Zone 1's 49 cells
    2. Zone 2 density          -- pack the buildings tight around M
    3. Adjacency preferences   -- the soft "if possible" pairings
    4. M's open perimeter      -- leave M as unwalled as the packing allows
    5. Alternates              -- several distinct layouts at those scores

The pathway to M and M's centering are hard constraints in the model itself, so
they hold in every phase and are never relaxed or traded away.
"""

import sys
import time
from dataclasses import dataclass

from ortools.sat.python import cp_model

from .logging_utils import log
from . import layout as L

TOTAL_PHASES = 5
SOLVED = (cp_model.OPTIMAL, cp_model.FEASIBLE)


@dataclass
class Scores:
    """Best value found for each phase objective."""
    zone1: int = 0
    zone2: int = 0
    preferences: int = 0
    exposure: int = 0


class ProgressPrinter(cp_model.CpSolverSolutionCallback):
    """Logs each improving solution while a phase is running."""

    def __init__(self, label, describe):
        super().__init__()
        self.label = label
        self.describe = describe
        self.start_time = time.time()
        self.solution_count = 0

    def on_solution_callback(self):
        self.solution_count += 1
        elapsed = time.time() - self.start_time
        log(f"  [{self.label}] Solution #{self.solution_count} @ {elapsed:6.2f}s: "
            f"{self.describe(self)} (best bound: {self.BestObjectiveBound():.0f})")


def make_solver(config):
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = config.num_search_workers
    solver.parameters.log_search_progress = False
    solver.parameters.cp_model_presolve = True
    solver.parameters.linearization_level = 2
    return solver


def run(pm, config, on_layout):
    """Run all five phases. `on_layout(solver, index)` renders each layout."""
    solver = make_solver(config)
    scores = Scores()

    def sum_of(variables):
        return lambda reader: sum(reader.Value(v) for v in variables)

    def value_of(variable):
        return lambda reader: reader.Value(variable)

    scores.zone1 = _optimize(
        pm, solver,
        number=1,
        title="maximizing Zone 1 coverage",
        objective=sum(pm.covered_zone1),
        time_limit=config.time_limit_zone1,
        progress_label="zone1-coverage",
        read=sum_of(pm.covered_zone1),
        describe=lambda v: f"{v}/{L.ZONE_CELLS} covered",
        lock=lambda v: pm.model.Add(sum(pm.covered_zone1) == v),
        failure_note="Aborting.",
        abort_on_failure=True,
    )

    scores.zone2 = _optimize(
        pm, solver,
        number=2,
        title="maximizing Zone 2 compactness (buildings packed tight)",
        objective=sum(pm.covered_zone2),
        time_limit=config.time_limit_zone2,
        progress_label="zone2-compactness",
        read=sum_of(pm.covered_zone2),
        describe=lambda v: f"{v}/{L.ZONE_CELLS} covered",
        lock=lambda v: pm.model.Add(sum(pm.covered_zone2) == v),
        failure_note="Continuing with Zone 1 result only.",
    )

    n_prefs = len(pm.preference_bonuses)
    scores.preferences = _optimize(
        pm, solver,
        number=3,
        title="maximizing satisfied adjacency preferences",
        objective=pm.bonus_total,
        time_limit=config.time_limit_preferences,
        progress_label="preferences",
        read=value_of(pm.bonus_total),
        describe=lambda v: f"{v}/{n_prefs} preferences satisfied",
        lock=lambda v: pm.model.Add(pm.bonus_total == v),
        failure_note="Falling back to prior result only.",
    )

    n_perimeter = len(pm.exposure_cell_vars)
    scores.exposure = _optimize(
        pm, solver,
        number=4,
        title="maximizing M's exposure (pathway already guaranteed)",
        objective=pm.exposure_score,
        time_limit=config.time_limit_exposure,
        progress_label="exposure",
        read=value_of(pm.exposure_score),
        describe=lambda v: f"{v}/{n_perimeter} open perimeter cells",
        lock=lambda v: pm.model.Add(pm.exposure_score == v),
        failure_note="Falling back to prior result only.",
    )

    found = _collect_alternates(pm, solver, config, scores, on_layout)

    log(f"\nDone. Found {found} distinct top-scoring layout(s) "
        f"(zone1={scores.zone1}/{L.ZONE_CELLS}, zone2={scores.zone2}/{L.ZONE_CELLS}, "
        f"prefs={scores.preferences}/{n_prefs}, "
        f"exposure={scores.exposure}/{n_perimeter}).")
    return scores, found


def _optimize(pm, solver, *, number, title, objective, time_limit, progress_label,
              read, describe, lock, failure_note, abort_on_failure=False):
    """Maximize one objective, then pin its best value for later phases."""
    pm.model.Maximize(objective)
    solver.parameters.max_time_in_seconds = time_limit

    log(f"PHASE {number}/{TOTAL_PHASES}: {title}...")
    printer = ProgressPrinter(progress_label, lambda cb: describe(read(cb)))
    status = solver.Solve(pm.model, printer)

    if status not in SOLVED:
        log(f"Phase {number} failed with status {solver.StatusName(status)}. "
            f"{failure_note}")
        if abort_on_failure:
            sys.exit(1)
        return 0

    best = read(solver)
    log(f"PHASE {number} done: best = {describe(best)} "
        f"(status={solver.StatusName(status)})")
    lock(best)
    return best


def _collect_alternates(pm, solver, config, scores, on_layout):
    """Enumerate distinct layouts that all hit the locked-in scores."""
    log(f"PHASE {TOTAL_PHASES}/{TOTAL_PHASES}: searching for up to "
        f"{config.num_alternate_solutions} distinct layout(s) at "
        f"zone1={scores.zone1}, zone2={scores.zone2}, "
        f"prefs={scores.preferences}, exposure={scores.exposure}...")

    found = 0
    for i in range(config.num_alternate_solutions):
        solver.parameters.max_time_in_seconds = config.time_limit_per_alternate
        log(f"  Searching for layout #{i + 1}...")
        status = solver.Solve(pm.model)
        if status not in SOLVED:
            log(f"  No further distinct layouts found "
                f"(status={solver.StatusName(status)}).")
            break

        found += 1
        on_layout(solver, found)
        _forbid_current_layout(pm, solver)

    return found


def _forbid_current_layout(pm, solver):
    """No-good cut: rule this exact set of placements out of future solutions."""
    active = [var for var, _ in pm.x_vars.values() if solver.Value(var)]
    active.append(pm.center_var_h if solver.Value(pm.center_var_h)
                  else pm.center_var_v)
    pm.model.Add(sum(active) <= len(active) - 1)
