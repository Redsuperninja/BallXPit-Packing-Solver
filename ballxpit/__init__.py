"""BallXPit packing solver.

A CP-SAT model that packs the game's buildings into two 7x7 zones on a 23x23
board, with the Iron Fortress ("M") locked to the exact center of Zone 2.

Module map:
    geometry.py  -- polyomino rotation/normalization and zone-overlap tests
    pieces.py    -- the building catalogue (shapes, labels, display names)
    layout.py    -- board size, zone boxes, M's pinned placement, preferences
    config.py    -- tunable run parameters (time limits, workers, #layouts)
    model.py     -- builds the CP-SAT model and all its variables
    phases.py    -- the staged optimization pipeline that drives the solver
    render.py    -- ASCII/ANSI grid output and independent requirement checks
"""
