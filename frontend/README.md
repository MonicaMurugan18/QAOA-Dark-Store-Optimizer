# QAOA Dark Store Optimizer — Frontend

React + Vite dashboard for the joint dark-store location and inventory
optimization backend. A visualization and interaction layer only: every number
on screen comes from the FastAPI service.

---

## Running it

Two terminals.

**1. Backend** (from `backend/`):

```bash
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**2. Frontend** (from `frontend/`):

```bash
npm install
```

```bash
npm run dev
```

Open <http://127.0.0.1:5173> (or whichever port Vite reports).

The API base URL lives in `.env` and is read in exactly one place
(`src/services/api.js`):

```
VITE_API_BASE_URL=http://127.0.0.1:8000
```

**Vite reads `.env` at startup, not on reload.** After changing it, stop the dev
server and run `npm run dev` again -- editing `.env` while it is running has no
effect.

---

## Stack

| | |
|---|---|
| React 19 + Vite 8 | app shell and build |
| Tailwind CSS 4 | styling, CSS-first config in `src/index.css` |
| React Router 7 | page routing |
| Axios | one shared client |
| React Leaflet 5 + Leaflet | map |
| Recharts 3 | charts |
| lucide-react | icons |

No state library. Optimization state is held by `useOptimizationRun()` at the
page level and passed down.

---

## Structure

```
src/
├── components/
│   ├── Layout.jsx              shell: sidebar + header + outlet
│   ├── Sidebar.jsx             dark nav, collapses below lg
│   ├── Header.jsx              title + live backend status
│   ├── Primitives.jsx          Card, Table, Badge, Button, Field, Metric, Note
│   ├── StatCard.jsx            KPI tile
│   ├── OptimizationForm.jsx    constraints + QAOA parameters
│   ├── OptimizationResults.jsx result KPIs, validation, solver detail
│   ├── ComparisonCard.jsx      QAOA vs classical table + 2 charts
│   ├── Tables.jsx              SelectedStores, AssignmentTable, InventoryTable
│   ├── MapView.jsx             Leaflet map
│   ├── PreviewModal.jsx        QUBO size modal
│   ├── LoadingState.jsx
│   ├── ErrorState.jsx
│   └── EmptyState.jsx
├── pages/
│   ├── Dashboard.jsx           main single-page dashboard
│   ├── Stores.jsx   Products.jsx   Demand.jsx   History.jsx
├── services/api.js             Axios client + error normalisation
├── hooks/useOptimization.js    useFetch, useHealth, useOptimizationRun, usePreview
├── utils/formatters.js         money/pct/seconds + area centroid helper
├── App.jsx   main.jsx   index.css
```

---

## Endpoints consumed

| Endpoint | Used by |
|---|---|
| `GET /health` | header status, polled every 20s |
| `GET /api/stores` | KPI, map, Stores page, selected-store table |
| `GET /api/products` | KPI, Products page, demand chart labels |
| `GET /api/demand` | KPI, Demand page |
| `POST /api/optimization/preview` | QUBO preview modal |
| `POST /api/optimization/run` | main run (method `both`) |
| `GET /api/optimization/runs` | History list |
| `GET /api/optimization/{run_id}` | History drill-down |
| `GET /api/optimization/{run_id}/comparison` | comparison card |

Request bodies were built from the live `/openapi.json`, not guessed:

```jsonc
{
  "budget": 20000,
  "delivery_time_limit": 15,
  "store_ids": [1, 4, 5],
  "product_ids": [1, 2, 3],
  "areas": ["Lawspet", "Marie Oulgaret", "Venkata Nagar"],
  "options": { "reps": 3, "maxiter": 150, "shots": 2048, "seed": 42, "time_limit_sec": 30 },
  "method": "both"
}
```

---

## Three honesty decisions

These are worth knowing because they are deliberate, not oversights.

**1. "Storage Capacity" is read-only.** The backend request schema has **no**
storage-capacity field — storage is a per-store property from `/api/stores`, not
a run input. The field is shown as a derived sum of the selected candidates'
capacity and labelled as such, rather than faking a knob that does nothing.

**2. Demand areas on the map are marked approximate.** `/api/demand` returns no
latitude or longitude. Where an area name matches a candidate store's `area`, the
area is drawn at the centroid of those stores — the *same* approximation the
backend uses to compute delivery times (see
`backend/app/services/data_service.py`). Those markers are dashed, violet, and
their popups say so. An area with no matching store gets **no marker**, and
assignment lines are drawn only when both endpoints have a real location.

**3. No progress percentage.** The run stages ("Preparing optimization
model…", "Running QAOA…", …) are labels for the sequence the backend performs.
The API exposes no progress stream, so no fake percentage is shown.

---

## Scientific presentation

The comparison never ranks the algorithms. There is no "QAOA is better / faster /
superior" anywhere. Only measured values are displayed, plus:

* **"Matches classical reference optimum"** — shown **only** when the API reports
  a zero optimality gap against a solver that returned a *proven* optimum.
* **"QAOA solution differs from the reference optimum"** — shown when the gap is
  non-zero. Not hidden.
* **"No optimality gap reported"** — when no proven reference exists on that run.

Low circuit depth returns feasible but suboptimal plans, and the UI reports that
rather than concealing it.

---

## Verified flow

Tested against the live backend in a real browser:

```
Dashboard loads              6 stores · 4 demand areas · 6 products · Ready
Backend status               green "Backend Connected · sqlite" from GET /health
Preview QUBO                 10 decision + 1 auxiliary = 11 qubits, 7 feasible links
Run Optimization             stages shown, button disabled while running
Result                       ₹14,716.14 · 100.0% coverage · 0.00% gap · 2 stores
                             budget ₹17,000/₹20,000 · storage 5,912.5/8,000.0
Selected stores              Venkata Nagar Hub 1, Lawspet Hub
Assignments                  3/3 served with delivery times
Inventory                    per-store product breakdown + grouped bar chart
Comparison                   QAOA vs Classical table + runtime & objective charts
Map                          selected stores highlighted, assignment lines drawn
History                      7 runs listed; clicking one reloads its full result
Invalid budget (₹500)        blocked client-side with the cheapest-store reason
Backend stopped              red "Backend Offline", actionable banner, zeroed KPIs
Backend restarted            "Try again" restores everything
Tablet (768px)               sidebar collapses to hamburger, KPIs reflow
```

---

## Known limitations

1. **Bundle is ~915 kB** (276 kB gzipped) in one chunk — Leaflet and Recharts
   dominate. Fine for a local demo; code-split before any real deployment.
2. **Read-only.** The backend exposes POST/PUT/DELETE for stores, products and
   demand, but this UI does not write to them. Use `/docs` for that.
3. **Mobile below 640px works but is not tuned** — tables scroll horizontally.
   Laptop and tablet were the priority.
4. **Health poll is every 20s**, so an offline backend can take up to 20 seconds
   to show in the header unless you click the status badge to re-check.
5. **The dashboard always runs `method: "both"`.** The backend also supports
   `qaoa` and `classical` alone; those are reachable via `/docs`.
