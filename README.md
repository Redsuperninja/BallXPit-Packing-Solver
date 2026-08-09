# BallXPit Packing Solver

A constraint solver for BallXPit building layouts. It packs 28 polyomino-shaped buildings into two 7×7 zones so that the **Iron Fortress sits dead center of Zone 2**, both zones are filled as densely as possible, and a walkable corridor still reaches the Fortress from outside.

Built on Google OR-Tools [CP-SAT](https://developers.google.com/optimization/cp).

```
       0  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16 17 18 19 20 21 22
 4 |  .  .  .  .  .  .  .  .  Z  Z  Z  P  I  .  .  I  .  .  .  .  .  .  .
 5 |  .  .  .  .  .  J  C  C  Z  Z  Z  P  I  I  I  I  .  .  .  .  .  .  .
 6 |  .  .  .  .  .  J  J  C  Z  D  Z  P  I  K  K  I  .  .  .  .  .  .  .
 7 |  .  .  .  .  .  J  J  Q  D  D  F  F  K  K  K  W  W  .  .  .  .  .  .
 8 |  .  .  .  .  .  N  Q  Q  Q  @  F  F  L  L  W  W  W  .  .  .  .  .  .
 9 |  .  .  .  .  N  N  N  G  G  @  H  B  B  L  W  W  W  .  .  .  .  .  .
10 |  .  .  .  .  .  N  O  G  G  @  H  B  L  L  W  T  T  .  .  .  .  .  .
11 |  .  .  .  .  O  O  O  G  G  H  H  H  A  A  T  T  T  T  .  .  .  .  .
12 |  .  .  .  .  .  O  R  E  E  E  H  Y  A  M  T  T  T  T  .  .  .  .  .
13 |  .  .  .  .  .  R  R  E  E  E  U  Y  M  M  M  S  S  S  .  .  .  .  .
14 |  .  .  .  .  R  R  R  E  E  E  U  Y  Y  M  S  S  S  S  .  .  .  .  .
15 |  .  .  .  .  .  R  R  U  U  U  U  Y  Y  *  X  S  S  S  X  .  .  .  .
16 |  .  .  .  .  .  .  R  U  U  U  U  V  V  *  X  X  X  X  X  .  .  .  .
17 |  .  .  .  .  .  .  .  .  .  V  V  V  V  *  .  X  X  X  .  .  .  .  .
18 |  .  .  .  .  .  .  .  .  .  V  V  V  V  *  .  .  .  .  .  .  .  .  .
19 |  .  .  .  .  .  .  .  .  .  .  .  .  .  *  .  .  .  .  .  .  .  .  .
                                       (rows 20-22: the corridor continues out)

M (M) centered on Zone 2 center (13, 13): OK
Zone 1 (@) density: 49 / 49 cells filled
Zone 2 (M) density: 47 / 49 cells filled
Pathway to M: OK -- 8 empty cells from the board edge at (22, 13) to M's perimeter at (15, 13)
M exposure score: 1 / 8 open perimeter cells
Adjacency preferences satisfied (4/4)
```

`M` is the Iron Fortress, pinned to (13, 13). `*` is the corridor out to the board edge. `@` is Zone 1's center marker block. In a real terminal every building gets its own color.

## Quick start

```bash
pip install -r requirements.txt

python solve.py                 # defaults: 60s per phase, 5 distinct layouts
python solve.py --quick         # 10s per phase, 1 layout -- fast sanity run
python solve.py --layouts 3 --time-limit 120
```

Options: `--time-limit` (seconds per optimization phase), `--alternate-time-limit`, `--layouts`, `--workers`, `--quick`. Defaults live in [`ballxpit/config.py`](ballxpit/config.py).

## The problem

28 buildings, each a fixed polyomino that may be rotated but not reflected, are placed on a 23×23 board. No two may overlap. Two 7×7 zones are marked out:

| | Rows / cols | Contents |
|---|---|---|
| **Zone 1** | 6–12 | 21 buildings (labels `A`–`R`, `Y`, `Z`) plus a 1×3 center marker block (`@`) |
| **Zone 2** | 10–16 | 6 large buildings (`S`–`X`) packed around the Iron Fortress (`M`) |

The zones deliberately **overlap** in the 3×3 block at rows/cols 10–12. That overlap is load-bearing — see [Why the zones overlap](#why-the-zones-overlap).

### Hard requirements (always satisfied)

1. **Zone membership** — every Zone 1 building has at least one cell inside Zone 1's box; every Zone 2 building has at least one cell inside Zone 2's box. Buildings may sprawl outside their zone, they just have to touch it.
2. **M is the center of Zone 2** — the Iron Fortress is a symmetric plus sign, and its *middle* cell must sit on Zone 2's center cell (13, 13). This leaves it exactly one legal placement.
3. **M is reachable** — an unbroken corridor of empty cells runs from a cell touching M all the way to the outer edge of the board. Not "M has a free neighbor" — a real path out.
4. **No overlaps** and exactly one placement per building.

### Soft objectives (maximized, in priority order)

1. **Zone 1 density** — fill all 49 cells of Zone 1.
2. **Zone 2 density** — pack the six buildings as tightly as possible around M.
3. **Adjacency preferences** — four "if possible" pairings:
   - a plus sign next to a P-pentomino
   - the 1×3 bar next to the 2×2 square
   - the T-tetromino next to an L-tromino
   - a *different* L-tromino next to the U-pentomino
4. **M's open perimeter** — of the 8 cells touching M, leave as many empty as the packing allows.

Zone 2 tops out at 47/49 rather than 49/49: requirement 3 forces at least two cells of the corridor to stay empty inside the zone.

## How it works

### Staged optimization

The four soft objectives are ranked, not summed. Each phase maximizes one objective, then **locks its result in** with an equality constraint before the next phase runs, so a later phase can never trade away a higher-priority score:

```
Phase 1  maximize Zone 1 density          -> lock at best
Phase 2  maximize Zone 2 density          -> lock at best
Phase 3  maximize adjacency preferences   -> lock at best
Phase 4  maximize M's open perimeter      -> lock at best
Phase 5  enumerate distinct layouts that all hit those scores
```

Phase 5 finds alternates by adding a *no-good cut* after each layout: the exact set of placements just used is forbidden, so the next solve must differ somewhere.

Each phase has its own time limit. The log prints whether a phase proved `OPTIMAL` or merely ran out of time at `FEASIBLE` — if you see `FEASIBLE`, raise `--time-limit` to get a better answer.

### Pinning M to the center

The subtle part. A plus sign has five cells, so requiring it to merely *cover* (13, 13) allows five placements — four of which put one of the plus's **arms** on the center cell and hang the body off to one side:

```
    arm on center            centered (the one we want)
      . M . .                    . . . .
      M M M .                    . M . .
      . X . .   <- (13,13)       M X M .   <- (13,13)
      . . . .                    . M . .
```

So the model pins the whole **cell set** — the exact five cells of the plus centered on (13, 13) — leaving exactly one legal placement. Build-time assertions verify that M really is a symmetric plus (otherwise "centered" is meaningless), that Zone 2 is odd-sized and square (otherwise it has no single center cell), and that the pinned piece ends up with exactly one candidate placement.

### Proving the corridor exists

"There is a path of empty cells from M to the board edge" is a connectivity constraint, which CP-SAT can't express directly. The model encodes it as a **unit flow problem** instead:

- one directed arc between each pair of orthogonally adjacent cells, usable only if **both** endpoints end up empty;
- a super-source feeding the 8 cells that touch M, a super-sink draining every cell on the board's boundary;
- flow conservation everywhere, and total flow forced to exactly 1.

Because the flow is integral with unit capacities, any feasible solution must contain a genuine connected empty-cell path from M to the boundary. This is a standard flow-for-connectivity encoding, and it is a hard constraint in every phase — never relaxed.

One caveat worth knowing: the flow only *proves* a corridor exists. The solver is free to also switch on arcs around empty-cell cycles, which satisfy conservation and cost nothing, so the flow variables are **not** a usable picture of the route (early on they lit up 282 cells across the board). The renderer therefore re-derives the corridor by breadth-first search over the finished grid. That doubles as an independent check: `render.py` verifies M's centering and the pathway from what was actually drawn, not from the model's own variables, so a broken constraint prints `FAILED` on screen instead of passing silently.

### Why the zones overlap

Zone 2's center is three cells deep into the zone. With M locked there, a Zone 1 building can only reach the cells beside M if Zone 1's box extends far enough — which the 3×3 overlap provides. Separate the zones and the "plus sign next to a P-pentomino" preference becomes physically impossible, capping the score at 3/4.

## Repository layout

```
solve.py                 CLI entry point
ballxpit/
  geometry.py            polyomino rotation/normalization, zone-overlap tests
  pieces.py              the building catalogue: shapes, labels, display names
  layout.py              board size, zone boxes, M's pinned placement, preference groups
  config.py              tunable run parameters
  model.py               builds the CP-SAT model and all its variables
  phases.py              the staged optimization pipeline
  render.py              terminal grid, score summary, independent requirement checks
  logging_utils.py       timestamped logging
```

Read them in that order — each file only depends on the ones above it.

## Customizing

**Add a building.** Append a `_piece([...cells...], "LABEL", "Display Name")` to `ZONE_1_PIECES` or `ZONE_2_PIECES` in `pieces.py`, and add a color for its label in `COLORS` in `render.py`. Zone membership follows automatically from which list it is in.

**Move or resize a zone.** Edit the bounds in `layout.py`. Zone 2 must stay an odd-sized square so it has a single center cell; assertions will tell you if you break that.

**Change what sits at the center.** Set `CENTER_PIECE_LABEL` in `layout.py`. The piece has to be a symmetric plus sign for the centering assertion to hold; centering a different shape means deciding what its "middle" is and generalizing `plus_at()`.

**Change the preferences.** The label groups near the bottom of `layout.py` define which pieces participate. `Y` and `Z` are in no group yet — e.g. `P_PENTOMINO_LABELS.append("Y")` puts the Falconry Hut in the plus-sign pairing. To add a whole new preference, build it with `_adjacency_bonus()` in `model.py` and register it in `preference_bonuses`.

**Re-prioritize the objectives.** Reorder the `_optimize(...)` calls in `phases.py::run`. Since each phase locks in its result, the call order *is* the priority order.

## Performance notes

The model has roughly 12,000 variables and 11,700 constraints, of which ~6,600 are placement candidates and ~2,000 are corridor flow arcs. It builds in well under a second.

With the default 60s limits, all four optimization phases prove `OPTIMAL` in about 25 seconds total on a modern laptop — they do not need the full budget. The scores above (49/49, 47/49, 4/4, 1/8) are therefore *proven optimal*, not just the best found so far. Phase 5's enumeration of alternate layouts is the open-ended part; it is bounded by `--layouts` and `--alternate-time-limit`.
