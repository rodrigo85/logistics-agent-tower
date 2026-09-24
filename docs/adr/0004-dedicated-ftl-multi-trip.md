# ADR-0004: Dedicated full-truckload, multi-trip allocation model

* **Status:** Superseded by [ADR-0006](0006-refrigerated-multi-drop-single-route.md) on 2026-09-24
* **Date:** 2026-09-24

## Context

The operation modelled here ships full truckloads to large retail customers
(supermarkets, wholesalers, department stores) in the Itajaí region. Mixing
customers in one truck (LTL / multi-drop) is not the business model, and
drivers are bound by Lei 13.103/2015 (1-hour intra-shift break, 11-hour shift).

## Decision

`FleetService.pack_orders_into_fleet` implements:

1. **One customer per trip.** A vehicle carries at most
   `MAX_DELIVERIES_PER_VEHICLE` (default 2) orders per day, each as a dedicated
   CD -> customer -> CD trip.
2. **Best-fit decreasing.** Orders sorted by weight+volume; each order goes to
   the suitable vehicle with the least leftover weight.
3. **Safe zone first, hard guard always.** Phase 1 and 2 only accept trips at
   <= 93% utilisation; a fallback accepts up to 100%; nothing ever exceeds 100%.
4. **Constraints:** refrigerated cargo only on refrigerated trucks (and vice
   versa), customer rules such as "VUC only" honoured via long-term memory.
5. **Reported utilisation is peak-per-trip,** not the daily sum, because each
   trip is unloaded before the next one starts.

The itinerary builder always inserts the 60-minute lunch after trip 1 and
reloading before trip 2.

## Consequences

* Simple, explainable allocation that dispatchers can audit.
* Orders that fit nowhere stay `PENDING` for the next cycle and are logged,
  never forced.
* Multi-drop routing (OR-Tools path) remains available for loads with 3+ stops
  if the business rules change.
