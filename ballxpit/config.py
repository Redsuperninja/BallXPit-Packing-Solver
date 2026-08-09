"""Tunable run parameters.

Defaults match the original script. Raise the time limits if a phase keeps
stopping before it proves OPTIMAL (the log prints the status of each phase).
"""

from dataclasses import dataclass


@dataclass
class RunConfig:
    # Per-phase solver time limits, in seconds.
    time_limit_zone1: float = 60.0        # phase 1: maximize Zone 1 coverage
    time_limit_zone2: float = 60.0        # phase 2: maximize Zone 2 coverage
    time_limit_preferences: float = 60.0  # phase 3: maximize adjacency preferences
    time_limit_exposure: float = 60.0     # phase 4: maximize M's open perimeter
    time_limit_per_alternate: float = 30.0  # phase 5: per alternate layout

    num_alternate_solutions: int = 5      # distinct top-scoring layouts to show
    num_search_workers: int = 12
