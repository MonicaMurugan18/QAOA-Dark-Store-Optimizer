# Data Sources & Provenance

Every dataset in this system, where it came from, and what it may legitimately
be claimed to represent.

**The rule this project follows:** a value is either observed, or it is labelled.
Nothing synthetic is presented as real.

---

## Summary

| Dataset | Source | Type | Date | Records |
|---|---|---|---|---|
| Candidate dark-store locations | OpenStreetMap (Overpass API) | `real_public` | 2026-10-03 (extraction) | **48** |
| Demand zones (geometry) | OpenStreetMap (Overpass API) | `real_public` | 2026-10-03 (extraction) | **163** |
| Population | Census of India 2011, via Wikidata | `official` | **2011** (Census year) | 7 places, 1 matched |
| Product catalogue | Blinkit catalogue sample export | `real_public` | **2026-09-11** | **25** |
| Road routing (store→zone) | OSRM over OpenStreetMap | `real_public` | 2026-10-03 | **7,824** |
| Demand | Population proxy model | `proxy` | derived | **1,150** |
| Store economics (cost, capacity) | Prototype assumptions | `synthetic` | — | 48 |

---

## A. Candidate dark-store locations — REAL PUBLIC

* **Source:** OpenStreetMap via Overpass API, `https://overpass-api.de/api/interpreter`
* **Licence:** ODbL 1.0, © OpenStreetMap contributors
* **Query:** `shop` in `{supermarket, convenience, general, grocery}` within the
  Puducherry mainland bounding box `(11.87, 79.74, 12.06, 79.88)`
* **Fetched 68 → accepted 48 → rejected 20** (all logged)

**Real:** name, latitude, longitude, shop type, OSM id, OSM permalink.

**NOT real:** `opening_cost` and `storage_capacity`. These are prototype
assumptions keyed to shop type. Columns `cost_source_type` and
`capacity_source_type` are set to `synthetic` on every row.

### An important correction

> **There is no "QuickCommerceMap Puducherry dark-store report" in this project.**

It was referenced in the brief, but no such file exists in the repository, the
conversation, or on disk. I searched for it. What was found instead:
`Dark store paperr.pdf` and `Abstract_QAOA_DarkStore.pdf` — both academic papers
containing no store records.

Equally: **no quick-commerce operator tags dark stores in OpenStreetMap.** A
query for Blinkit / Zepto / Instamart / BigBasket brands across Puducherry
returns zero results. Dark stores are deliberately unmarked.

So these 48 outlets are **candidate sites**, not verified operating dark stores,
and the API says so.

### The Mahé / Yanam trap

Puducherry UT includes exclaves in Kerala (Mahé, ~11.70 N 75.53 E) and Andhra
Pradesh (Yanam, ~16.73 N 82.25 E), hundreds of kilometres away. An Overpass
*area* query on "Puducherry" returns them, and they would corrupt every distance
calculation. The pipeline uses a mainland **bounding box** and rejects anything
outside it, logging the reason.

---

## B. Population — OFFICIAL, used as a PROXY

* **Source:** Census of India 2011, retrieved via Wikidata SPARQL (property
  `P1082`), `https://query.wikidata.org/sparql`
* **Source date: 2011** — the Census year, *not* the download date.

Returned 7 places with population and coordinates: Puducherry district
(950,289), Puducherry (1,394,467), Karaikal (200,222), Uzhavarkarai (300,104),
Mahé (41,816), Yanam (55,626), Auroville (3,288).

### Ward-level data could not be obtained

| Source | Result |
|---|---|
| `censusindia.gov.in` | connection timed out (also fails TLS verification) |
| `api.data.gov.in` | connection refused |

So **only 1 of 163 zones has a population figure sourced for that exact place.**
The rest are `NULL` in the database. They are never filled with a guess.

**Population is a DEMAND PROXY, never customer demand.**

---

## C. Road network & routing — REAL PUBLIC

* **Source:** OSRM (Open Source Routing Machine), `https://router.project-osrm.org`
* **Underlying data:** OpenStreetMap road geometry, ODbL
* **7,824 legs routed (48 stores × 163 zones). 0 fell back to an estimate.**

This replaces the earlier straight-line × circuity-factor guess with an actual
route over the road graph. Every row records `source`:

* `osrm` — a real route (`source_type = real_public`)
* `haversine_fallback` — the router was unreachable (`source_type = estimated`)

The optimizer and the API both surface this, so a run computed on estimates can
never be mistaken for one computed on real routes.

**Still an assumption:** the 3-minute picking/packing time added to every leg.
It lives in its own `handling_minutes` column so it can be replaced.

**Pluggable:** set `OSRM_BASE_URL` to a self-hosted instance, or implement
OpenRouteService; nothing else changes.

---

## D. Product catalogue — REAL PUBLIC

* **Source:** `quickcommerce-sample-blinkit-products-2026-09-11.xlsx`, a public
  sample export supplied with this project
* **Catalogue date: 2026-09-11** (from the file's own `Updated at` column)
* **25 products, 0 rejected**

**Real:** product id, platform, name, brand, category, subcategory, pack
quantity, MRP.

**DERIVED, labelled `estimated`:**

* `unit_volume` — parsed from the pack-size string (`"500 g"`, `"750 ml"`,
  `"1 pc"`) and converted to litres-equivalent. Solids convert at 1 g → 1 ml, a
  stated approximation. Countable items are assumed 0.4 L.
* `unit_cost` — the catalogue publishes **retail MRP**, not supplier cost. Cost
  is derived as `MRP × (1 − 0.22)`. This is an assumed retail margin, **not an
  observed wholesale price**.

### No order data

**No legitimate public source of Puducherry quick-commerce order data exists.**
Platform order histories are private commercial data and are not scraped here.
No external retail dataset was substituted, because labelling another
geography's transactions as Puducherry demand would be misleading.

---

## E. Demand — PROXY (the most important caveat)

* **Mode:** `DEMAND_MODE=population_proxy`
* **1,150 rows** across 46 zones × 25 products

### The formula (documented and configurable)

```
zone_population
  × ADOPTION_RATE          (default 0.06)   share of residents using quick commerce
  × ORDERS_PER_USER_DAY    (default 0.35)   orders per adopting resident per day
  = zone_orders_per_day

zone_orders_per_day × ITEMS_PER_ORDER (default 5.0) × product_share(p)
  = demand_units(zone, product)
```

`product_share` comes from the **real catalogue's category mix**, so the split
across products reflects a real catalogue even though the level is estimated.

Every coefficient is overridable: `DEMAND_ADOPTION_RATE`,
`DEMAND_ORDERS_PER_USER_DAY`, `DEMAND_ITEMS_PER_ORDER`.

### Which zones count, and why it matters

Of 163 OSM place nodes, **117 are excluded** from demand. Inspecting them shows
the 102 nodes tagged `neighbourhood` and 15 tagged `quarter` are almost entirely
**Auroville settlement plots** (Promesse, Udayan, Certitude, Adventure…), each
home to a handful of residents in an intentional community. The Puducherry city
areas an operator would actually serve (Lawspet, Mudaliarpet, Reddiarpalayam,
Grand Bazaar, Ariyankuppam…) are tagged `suburb`, `town` or `village`.

Spreading 244,377 municipal residents evenly across all 163 would hand ~63% of
the city to Auroville plots. So `DEMAND_ZONE_TYPES` defaults to
`suburb,town,village` → **46 zones at ~5,431 each**. Auroville itself is tagged
`town` and keeps its own sourced Census figure, so it is still represented at
its real size.

This allocation is an **estimate**, not a ward-level observation, and the API
reports how many zones were allocated this way.

### Switching to real orders

```bash
DEMAND_MODE=historical_orders
```

Currently raises a clear error explaining what is needed. Load an authorised
order dataset and implement the reader; the rest of the pipeline is ready.

---

## F. Store economics — SYNTHETIC

**These require operator data obtained with authorisation, and are not
observable from any public source:**

| Field | Status |
|---|---|
| `opening_cost` | prototype assumption, keyed to OSM shop type |
| `storage_capacity` | prototype assumption, keyed to OSM shop type |
| rider cost per minute | assumption (`RIDER_COST_PER_MIN`) |
| picking/packing time | assumption (`HANDLING_MINUTES`) |
| gross margin | assumption (`GROSS_MARGIN`) |
| actual inventory on hand | **not available at all** |

Every affected column carries `source_type = synthetic`, and the dashboard
lists them under a separate "Synthetic assumptions" heading.

---

## Running the pipeline

```bash
python ingest.py                          # all steps, using the data/raw cache
```

```bash
python ingest.py --steps stores,zones --fresh
```

```bash
python ingest.py --no-router              # skip OSRM, write labelled estimates
```

```bash
python ingest.py --status                 # provenance summary only
```

Or over HTTP (deliberately manual — these are free community endpoints, and
nothing downloads on server startup):

```
POST /api/data/refresh?steps=stores,zones&fresh=true
GET  /api/data/sources
GET  /api/data/status
GET  /api/data/ingestion-runs
```

---

## What would make this a real-business system

1. **Operator store list** — actual dark-store addresses, with capacity and
   lease/operating cost.
2. **Order history** — to replace the population proxy. Switch
   `DEMAND_MODE=historical_orders`.
3. **Inventory snapshots** — current stock per store per SKU.
4. **Rider cost data** — actual per-delivery or per-minute cost.
5. **Ward-level Census** — from `censusindia.gov.in` or `data.gov.in`, neither
   of which was reachable from this environment.

Items 1–4 require authorised business access. The schema has a place for each
and the ingestion pipeline is structured to accept them.
