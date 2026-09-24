# ADR-0006: Refrigerated multi-drop routes, one route per vehicle per day

* **Status:** Accepted (supersedes ADR-0004)
* **Date:** 2026-09-24

## Context

The operation changed from dedicated full truckloads to cold-chain distribution
for food retail: supermarkets, wholesalers, grocery stores, mini-markets,
bakeries, butchers, fishmongers, greengrocers and convenience stores. Orders are
small (40 kg to 1.5 t), there are many of them per day (40+), and every customer
expects delivery inside its receiving window. Drivers remain bound by
Lei 13.103/2015 (60-minute intra-shift break, 11-hour shift).

## Decision

1. **Fleet:** five refrigerated trucks (2 VUC, 2 Toco, 1 Truck). Only
   refrigerated cargo is accepted; `cargo_type` must match the vehicle.
2. **One route per vehicle per day.** Loading starts at 05:00 and the truck
   departs at 06:00 (`DOCK_START_TIME`, `LOADING_TIME_MINUTES`). There is no
   second trip; whatever does not fit stays `PENDING` and is surfaced to the
   dispatcher as an `UNALLOCATED` warning.
3. **Cluster-first allocation** (`FleetService.pack_orders_into_fleet`):
   a two-pass geographic sweep (orders restricted to VUC over the VUC trucks
   first, everything else over the large trucks and then the remaining VUC
   capacity), sorted by polar angle around the CD and filling one vehicle at a
   time until weight, volume or `MAX_STOPS_PER_VEHICLE` (12) is hit; leftovers go
   to the nearest eligible route; then a few k-means-style iterations move a stop
   to another eligible route when its centroid is at least 20% closer. On the
   seed dataset this refinement cut planned distance from 604 km to 387 km and
   late stops from 9 to 1. Nothing ever exceeds 100% of weight or volume.
4. **Sequencing by OR-Tools** (`GoogleORToolsVRPTSolver.plan_route`): a
   single-vehicle TSP with time windows. Windows are hard on the lower bound
   (the truck waits) and soft on the upper bound (late arrival is penalised, then
   reported as `SLA_BREACH`). Distance is the arc cost; Guided Local Search runs
   for routes with more than 8 stops.
5. **Timeline:** 20-minute service per stop; the lunch break is inserted after
   the first stop completed at or after 11:30 (or at the CD after the return
   when the route ends earlier). The solver's planning horizon is the rest of
   the day; the 11 h legal limit is audited afterwards and raises `SHIFT_LIMIT`
   instead of forcing a greedy fallback.
6. **Travel times:** Google Routes API v2 per leg when a key is configured
   (cached), otherwise haversine x 1.35 at 32 km/h. The OR-Tools matrix always
   uses haversine to avoid N² API calls.

## Consequences

* Explainable clustering (a dispatcher can see why stops share a truck) with
  solver-quality sequencing inside each cluster.
* Sweep + centroid refinement is a heuristic with no optimality guarantee. A
  savings/OR-Tools multi-vehicle CVRP is the natural upgrade if fleet
  utilisation needs to be optimised globally.
* Lunch is inserted after solving, so it can push later stops outside their
  windows; those cases are flagged rather than hidden. Modelling the break inside
  OR-Tools (`SetBreakIntervalsOfVehicle`) is a follow-up.
* Orders are generated per customer segment (`db/order_factory.py`), which keeps
  demo data realistic and the seed deterministic (fixed RNG).
