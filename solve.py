#!/usr/bin/env python3
"""BallXPit packing solver -- command-line entry point.

Usage:
    python solve.py                      # defaults (60s per phase, 5 layouts)
    python solve.py --quick              # short time limits, 1 layout
    python solve.py --layouts 3 --time-limit 120
"""

import argparse

from ballxpit.config import RunConfig
from ballxpit.model import build_model
from ballxpit.phases import run
from ballxpit.render import render_layout


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Pack BallXPit buildings into two zones with M at the "
                    "center of Zone 2.")
    parser.add_argument(
        "--time-limit", type=float, metavar="SECONDS",
        help="time limit for each of the four optimization phases (default: 60)",
    )
    parser.add_argument(
        "--alternate-time-limit", type=float, metavar="SECONDS",
        help="time limit per alternate layout in phase 5 (default: 30)",
    )
    parser.add_argument(
        "--layouts", type=int, metavar="N",
        help="how many distinct top-scoring layouts to print (default: 5)",
    )
    parser.add_argument(
        "--workers", type=int, metavar="N",
        help="CP-SAT search workers (default: 12)",
    )
    parser.add_argument(
        "--quick", action="store_true",
        help="10s per phase and a single layout -- for a fast sanity run",
    )
    return parser.parse_args(argv)


def config_from_args(args):
    config = RunConfig()

    if args.quick:
        config.time_limit_zone1 = 10.0
        config.time_limit_zone2 = 10.0
        config.time_limit_preferences = 10.0
        config.time_limit_exposure = 10.0
        config.time_limit_per_alternate = 10.0
        config.num_alternate_solutions = 1

    if args.time_limit is not None:
        config.time_limit_zone1 = args.time_limit
        config.time_limit_zone2 = args.time_limit
        config.time_limit_preferences = args.time_limit
        config.time_limit_exposure = args.time_limit
    if args.alternate_time_limit is not None:
        config.time_limit_per_alternate = args.alternate_time_limit
    if args.layouts is not None:
        config.num_alternate_solutions = args.layouts
    if args.workers is not None:
        config.num_search_workers = args.workers

    return config


def main(argv=None):
    config = config_from_args(parse_args(argv))
    pm = build_model()
    run(pm, config, on_layout=lambda solver, index: render_layout(
        pm, solver, title=f"Layout {index}"))


if __name__ == "__main__":
    main()
