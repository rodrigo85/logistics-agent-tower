# ADR-0002: Google OR-Tools as the routing engine

* **Status:** Accepted
* **Date:** 2026-09-24

## Context

Route sequencing with time windows and capacity constraints is a
capacitated vehicle routing problem with time windows (CVRPTW). Hand-written
greedy heuristics are easy to start with but degrade quickly as the number of
stops grows and give no optimality guarantees.

## Decision

Use Google OR-Tools' constraint-programming routing solver
(`pywrapcp.RoutingModel`) for any load with more than two stops, with
`PATH_CHEAPEST_ARC` as the first solution and `GUIDED_LOCAL_SEARCH` as the
metaheuristic under a 2-second time limit. Loads with one or two dedicated trips
(the FTL default) are timed analytically because there is nothing to sequence.

Keep a greedy fallback (`_heuristic_fallback`) for the rare case where the
solver finds no feasible solution under strict windows.

## Consequences

* Industrial-grade solver with soft time windows and pluggable cost callbacks.
* OR-Tools ships native wheels (~100 MB) and emits SWIG deprecation warnings on
  import; both are accepted and the warning is filtered in pytest.
* Travel times come from a distance matrix. Without Google Maps we use
  haversine x 1.35 circuity at 32 km/h; with a key, live traffic durations.
