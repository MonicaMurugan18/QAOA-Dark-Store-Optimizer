# QAOA Dark-Store Location & Inventory Optimization — Backend

Joint optimization of **which dark stores to open** and **how much of each SKU to
stock in each opened store**, for hyperlocal quick commerce. The same problem
instance is solved two ways — QAOA on a quantum simulator and a classical
MILP — and the results are compared objectively.

Backend only. No frontend.

---

## 1. Project overview

The system answers two coupled questions at once:

1. **Location** — which of the candidate dark stores should be opened?
2. **Inventory** — how many units of each product should each opened store hold?

Both solvers receive an identical instance and encode identical constraints.
Both solutions are then checked by an **independent validator** that re-derives
every constraint from the raw data and reads neither the QUBO nor the solver's
own verdict.

### Honest-reporting rules this codebase follows

* QAOA **does not** enumerate the search space and carries **no optimality
  guarantee**. It samples a biased distribution. Low circuit depth returns
  feasible but suboptimal plans, and the API reports that rather than hiding it.
* An **optimality gap** is published **only** when a solver provided a proven
  optimum for that instance (PuLP/CBC status `Optimal`). Otherwise the field is
  `null`.
* The word **"accuracy"** is never used for optimization performance. These are
  objective values, not predictions.
* Nothing claims QAOA is better than classical optimization.

---

## 2. Architecture

```
backend/
├── app/
│   ├── main.py                     FastAPI app, /docs, error handlers
│   ├── config.py                   settings from environment (no credentials)
│   ├── database.py                 engine, session, init, health check
│   ├── models/                     SQLAlchemy ORM (5 tables)
│   │   ├── store.py  product.py  demand.py  optimization.py
│   ├── schemas/                    Pydantic request/response + validation
│   │   ├── store.py  product.py  demand.py  optimization.py
│   ├── routers/                    HTTP only — no optimization logic
│   │   ├── stores.py  products.py  demand.py  optimization.py
│   ├── services/
│   │   ├── data_service.py         seed loading + the shared instance builder
│   │   │                           (the full model is documented at the top)
│   │   ├── qubo_service.py         QUBO formulation, two encodings
│   │   ├── qaoa_service.py         QAOA on Qiskit primitives
│   │   ├── classical_service.py    PuLP + CBC baseline
│   │   ├── validation_service.py   independent constraint checking
│   │   └── comparison_service.py   orchestration + comparison
│   └── utils/helpers.py            haversine, circuity, delivery time
├── data/
│   ├── seed_data.csv               6 candidate stores (Puducherry)
│   ├── demo_products.csv           6 products
│   └── demo_demand.csv             demand per area per product
├── tests/                          60 tests
├── requirements.txt
├── .env.example
└── README.md
```

**Dependency direction:** `routers → comparison_service → {data, qubo, qaoa,
classical, validation}_service`. Routers never import a solver directly and
never contain optimization logic.

### The optimization model

Stated in full at the top of `app/services/data_service.py`. In brief:

```
Decision variables
  x_i      = 1 if candidate store i is opened
  s_{i,a}  = 1 if area a is served by store i   (only for service-feasible links)

Inventory allocation (derived, not searched)
  inv_{i,j} = sum_a s_{i,a} * d_{a,j}

Objective (MAXIMISE)
  sum rev_a * s_{i,a}              margin on demand actually served
  - sum f_i * x_i                  opening cost
  - sum deliv_{i,a} * s_{i,a}      rider cost

Constraints
  C1 single sourcing          sum_i s_{i,a} <= 1
  C2 store-inventory coupling s_{i,a} <= x_i        ← joins the two halves
  C3 storage capacity         sum_a vol_a*s_{i,a} <= cap_i * x_i
  C4 budget                   sum_i f_i*x_i <= B
  C5 delivery / service       structural — infeasible links are never created
```

**Why inventory is derived.** Once you know which store serves which area, the
stock that store must carry follows exactly. Encoding inventory as free integer
variables would need a binary expansion per store-product pair and push the
register far past what a statevector simulator can hold. This is a deliberate
trade-off, listed again under Limitations.

### The two QUBO encodings

| encoding | qubits (3×3×3 instance) | note |
|---|---|---|
| `slack` | **58** (10 decision + 48 slack) | textbook; qiskit-optimization adds an integer slack per inequality. Correct but unusable on a simulator. |
| `compact` *(default)* | **11** (10 decision + 1 aux) | penalises each constraint's *minimal violating subsets*; AND gadgets reduce degree ≥3 terms. |

Both describe the same feasible set — they differ only in how infeasible points
are priced.

---

## 3. Installation

Requires **Python 3.11+** (verified on 3.14, Windows).

```bash
cd backend
python -m venv .venv
```

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

On macOS/Linux use `.venv/bin/python` instead.

### Two pinned dependencies worth knowing about

* **`PuLP>=2.8,<3.0`** — pinned deliberately. PuLP 4.x is a Rust rewrite with a
  different API *and* ships **no bundled solver**
  (`listSolvers(onlyAvailable=True)` returns `[]`). Version 2.9 bundles CBC, so
  no separate solver install is needed.
* **`qiskit-algorithms`** is installed for interop but its `QAOA` class is
  **not used**. It was measured to scale pathologically on this version
  combination — see §8.

---

## 4. PostgreSQL setup

```sql
CREATE DATABASE darkstore;
CREATE USER darkstore_app WITH PASSWORD 'choose-your-own';
GRANT ALL PRIVILEGES ON DATABASE darkstore TO darkstore_app;
```

Then set `DATABASE_URL` in `.env` (§5). Tables are created automatically on
startup; no migration tool is required for this schema.

`GET /health` reports database connectivity and the active dialect.

**SQLite fallback.** If `DATABASE_URL` is unset, the app falls back to a local
SQLite file. That is how the test suite runs, so the tests need no database
credentials. PostgreSQL is the intended target; point `DATABASE_URL` at a real
server to use it.

---

## 5. Environment variables

Copy `.env.example` to `.env` and edit. **Never commit `.env`.** No password is
hardcoded anywhere in the source.

| variable | default | meaning |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./darkstore.db` | SQLAlchemy URL |
| `SQL_ECHO` | `false` | log every SQL statement |
| `DEBUG` | `false` | verbose logging |
| `GROSS_MARGIN` | `0.18` | margin per rupee of demand value served |
| `RIDER_COST_PER_MIN` | `3.0` | rider cost per minute |
| `AVG_ITEMS_PER_ORDER` | `5.0` | basket size, converts units → trips |
| `DEFAULT_DELIVERY_TIME_LIMIT` | `15.0` | fallback service promise (minutes) |
| `QAOA_MAX_QUBITS` | `20` | reject above this; 2^n amplitudes |
| `QAOA_DEFAULT_REPS` | `3` | circuit depth p |
| `QAOA_DEFAULT_MAXITER` | `200` | classical optimizer iterations |
| `QAOA_DEFAULT_SHOTS` | `2048` | shots per circuit evaluation |
| `CLASSICAL_TIME_LIMIT_SEC` | `60` | CBC time limit |

---

## 6. Running FastAPI

```bash
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

* Swagger UI — <http://127.0.0.1:8000/docs>
* ReDoc — <http://127.0.0.1:8000/redoc>
* Health — <http://127.0.0.1:8000/health>

---

## 7. Loading seed data

```bash
.venv\Scripts\python.exe -c "from app.database import init_db, SessionLocal; from app.services.data_service import seed_database; init_db(); db=SessionLocal(); print(seed_database(db, reset=True)); db.close()"
```

Loads 6 stores, 6 products and 12 demand rows. Idempotent — re-running updates
rows rather than duplicating them.

### Data provenance — read this before quoting any number

The **areas and store counts are from the project owner**: Venkata Nagar (3),
Lawspet (1), Marie Oulgaret (1), Krishna Nagar (1) — 6 mapped dark stores.

Everything else is **not** real operator data, and every row says so in its
`data_source` and `notes` columns:

* **Coordinates** are `APPROX_AREA_CENTROID` — approximate area centroids, not
  surveyed addresses.
* **Opening costs, storage capacities, demand quantities, product prices** are
  `DEMO_ASSUMPTION` — illustrative values chosen so the optimization is
  non-degenerate.

Replace them with measured values before drawing any operational conclusion.
Nothing invented is presented as real.

---

## 8. Running QAOA

```bash
curl -X POST http://127.0.0.1:8000/api/optimization/qaoa \
  -H "Content-Type: application/json" \
  -d '{"budget":20000,"delivery_time_limit":15,
       "store_ids":[1,4,5],"product_ids":[1,2,3],
       "areas":["Lawspet","Marie Oulgaret","Venkata Nagar"],
       "options":{"reps":3,"maxiter":150,"shots":2048,"seed":42}}'
```

Flow: `instance → QUBO → Ising → QAOAAnsatz → StatevectorSampler → angle
optimisation → measure → decode → validate`.

### Depth matters, and the API does not hide it

On the 3×3×3 demo instance (11 qubits):

| reps (p) | maxiter | shots | runtime | objective | feasible | service |
|---|---|---|---|---|---|---|
| 1 | 5 | 256 | 0.28s | ₹10,846.00 | yes | 71.7% |
| 1 | 30 | 512 | 0.46s | ₹10,846.00 | yes | 71.7% |
| 2 | 60 | 1024 | 1.01s | ₹10,846.00 | yes | 71.7% |
| **3** | **150** | **2048** | **1.38s** | **₹14,716.14** | **yes** | **100%** |

`p=1` and `p=2` return **valid but suboptimal** plans. That is expected
behaviour for a sampling heuristic, not a defect.

### Two implementation decisions

**1. `qiskit_algorithms.QAOA` is not used.** It was measured first, on trivial
diagonal operators:

```
n= 3   0.18s        n= 9   12.26s
n= 5   0.20s        n=11   did not finish in 200s
n= 7   0.55s
```

~20× per two qubits where statevector growth predicts 4×. Qiskit's own
components are fine — `QAOAAnsatz` builds in 0.000s and one
`StatevectorSampler` call takes 0.064s at 11 qubits. So the high-level wrapper
is replaced by an explicit loop over those same primitives (`QAOAAnsatz` →
`StatevectorSampler` → scipy COBYLA). Same algorithm, same library.

**2. The cost Hamiltonian is normalised.** Raw coefficients reach |c| ≈ 91,500,
so γ = 0.001 would spin phases through ~90 radians — about 14 full turns — and
the angle landscape becomes noise at any step size the optimiser can take. The
operator is divided by its largest coefficient. This is **order-preserving**:
division by a positive constant is monotone, so the ranking of every solution
and the location of the optimum are unchanged, and it is exactly equivalent to
reparametrising γ. The identity term is dropped (global phase, unobservable).
**All reported rupee values use the original unscaled QUBO.**

---

## 9. Running classical OR

```bash
curl -X POST http://127.0.0.1:8000/api/optimization/classical \
  -H "Content-Type: application/json" \
  -d '{"budget":20000,"delivery_time_limit":15,
       "store_ids":[1,4,5],"product_ids":[1,2,3],
       "areas":["Lawspet","Marie Oulgaret","Venkata Nagar"],
       "options":{"time_limit_sec":30}}'
```

PuLP + CBC branch and bound on the same model, with C1–C4 as **hard** linear
constraints instead of penalties.

When CBC reports `Optimal`, `solver_details.proven_optimal` is `true` and the
result becomes the reference for optimality gaps. If CBC hits its time limit,
`proven_optimal` is `false`, the value is only the best found so far, and **no
gap is published**.

Capacity and budget use the same integerised coefficients as the QUBO (slack
encoding requires integer coefficients). Rounding is always in the
**conservative** direction — required volume up, available capacity down — so a
plan feasible in the rounded model is feasible in the true one.

---

## 10. Comparing results

```bash
curl http://127.0.0.1:8000/api/optimization/5/comparison
```

```json
{
  "run_id": 5,
  "qaoa":      {"objective_value": 14716.14, "customers_served": 6800.0,
                "budget_used": 17000.0, "runtime": 2.026, "feasible": true},
  "classical": {"objective_value": 14716.14, "customers_served": 6800.0,
                "budget_used": 17000.0, "runtime": 0.019, "feasible": true},
  "reference_solver": "classical",
  "reference_objective": 14716.14,
  "optimality_gap_percent": {"qaoa": 0.0, "classical": 0.0}
}
```

Compared on: objective value, demand served, service level, budget used,
storage utilization, constraint violations, runtime, and optimality gap where a
proven reference exists.

### Verified agreement on the demo instance

Four independent routes:

```
brute-force QUBO (2,048 states)   Rs 14,716.14
PuLP/CBC (proven optimal)         Rs 14,716.14
QAOA p=3                          Rs 14,716.14
API /optimization/run (both)      Rs 14,716.14
```

**This value is nowhere hardcoded.** Every number comes from an actual solver
call; the tests assert that the routes agree with each other.

---

## 11. API endpoints

| method | path | purpose |
|---|---|---|
| GET | `/` | service metadata |
| GET | `/health` | liveness + database check |
| GET | `/docs` | Swagger UI |
| GET | `/api/stores` | list stores (`area`, `candidates_only`, paging) |
| GET | `/api/stores/{id}` | one store |
| POST | `/api/stores` | create |
| PUT | `/api/stores/{id}` | update |
| DELETE | `/api/stores/{id}` | delete |
| GET | `/api/products` | list products |
| GET | `/api/products/{id}` | one product |
| POST | `/api/products` | create |
| PUT | `/api/products/{id}` | update |
| DELETE | `/api/products/{id}` | delete (cascades its demand rows) |
| GET | `/api/demand` | list demand (`area`, `product_id`, paging) |
| GET | `/api/demand/{id}` | one demand row |
| POST | `/api/demand` | create or replace one row (idempotent) |
| POST | `/api/demand/bulk` | many rows; all-or-nothing |
| PUT | `/api/demand/{id}` | update |
| DELETE | `/api/demand/{id}` | delete |
| POST | `/api/optimization/preview` | size an instance without solving |
| POST | `/api/optimization/run` | QAOA and/or classical (`method`) |
| POST | `/api/optimization/qaoa` | QAOA only |
| POST | `/api/optimization/classical` | classical only |
| GET | `/api/optimization/runs` | list stored runs |
| GET | `/api/optimization/{run_id}` | stored run + all solver results |
| GET | `/api/optimization/{run_id}/comparison` | compare the solvers |

### Rejected inputs

| input | response |
|---|---|
| negative demand / inventory / cost / budget | `422` naming the field |
| `unit_volume <= 0` | `422` |
| unknown store or product id | `422` listing the bad ids |
| inventory assigned to a non-selected store | reported as a **C2 violation** |
| budget below the cheapest store | `422` — no store can be opened |
| instance above `QAOA_MAX_QUBITS` | `500` with the qubit count and how to fix it |
| every requested solver failed | `500` naming the solver and the error |

Errors always say what went wrong. No failure is dressed up as success.

---

## 12. Testing

```bash
.venv\Scripts\python.exe -m pytest tests -q
```

**60 tests, all passing.** Coverage by area:

| area | what is checked |
|---|---|
| database connection | connectivity, all 5 tables, seed loaded, provenance labelled |
| store API | CRUD, filters, 404, negative cost/capacity, bad latitude |
| product API | CRUD, zero volume rejected, negative cost rejected |
| demand API | CRUD, negative demand, zero time limit, unknown product, bulk atomicity |
| QUBO generation | 11-qubit compact size, slack is larger, all constraints present, penalty exceeds max gain |
| classical solver | proven optimum, budget respected, capacity respected, tight budget changes plan |
| QAOA execution | runs in seconds, feasible, reaches optimum at p=3, suboptimal-but-feasible at p=1, rejects oversized instance |
| constraint validation | catches C1 double assignment, C2 inventory in unopened store, C3 overflow, C4 budget, unknown store id |
| optimization API | all endpoints, persistence round-trip, comparison, optimality gap, every error path |

---

## 13. Limitations

Stated plainly, because a reviewer will find them anyway.

1. **No quantum advantage, and none claimed.** On this instance the classical
   MILP is ~100× faster than the QAOA simulation and carries a proven-optimality
   guarantee that QAOA cannot offer. QAOA matching it is a *correctness* result,
   not a performance one.
2. **Simulation, not hardware.** Statevector simulation holds 2^n amplitudes;
   `QAOA_MAX_QUBITS` defaults to 20. No noise model, no hardware queue, no
   transpilation to a real coupling map.
3. **Inventory is derived from the assignment**, not an independent integer
   variable. Realistic, but it does mean the model cannot split one area's
   demand across two stores.
4. **Single sourcing (C1).** Each area is served by at most one store.
5. **Operational values are demo assumptions.** Only the areas and store counts
   come from the project owner. See §7.
6. **Area locations are approximated** by the centroid of the stores sharing the
   area name; areas have no coordinates of their own.
7. **Constraint coefficients are integerised** for the slack encoding. Rounding
   is conservative, so a plan may be discarded for only just fitting.
8. **QAOA quality depends on depth, shots and iterations**, and low settings
   return suboptimal plans. There is no guarantee that increasing depth helps
   monotonically.
9. **Penalty weights are derived from the instance**, not tuned per run. A very
   large penalty would flatten the angle landscape; a very small one would make
   violating a constraint profitable.
10. **CORS is wide open** (`allow_origins=["*"]`) for local development. Lock it
    down before any deployment.
11. **No authentication.** Every endpoint is public.
12. **Tests run on SQLite.** The models are PostgreSQL-compatible and `/health`
    confirms the live dialect, but the suite itself does not exercise
    PostgreSQL-specific behaviour.
