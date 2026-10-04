"""
Stage 2 -- Write the optimisation model down, and solve it by brute force.

Project: QAOA for Joint Dark Store Location Selection and Inventory Allocation
         in Hyperlocal Quick Commerce.

Still NO quantum code. The purpose of this file is to produce the *known
correct answer* that QAOA will later be judged against.

Run:  python stage2_baseline.py
"""

import itertools

import numpy as np
import pandas as pd

pd.set_option("display.width", 130)
pd.set_option("display.max_columns", 50)
pd.set_option("display.float_format", lambda v: f"{v:,.2f}")


# ======================================================================
# 0. LOAD THE STAGE 1 DATA
# ======================================================================
stores   = pd.read_csv("data/stores.csv")
areas    = pd.read_csv("data/areas.csv")
products = pd.read_csv("data/products.csv")
demand   = pd.read_csv("data/demand.csv")
links    = pd.read_csv("data/store_area_links.csv")

STORE_IDS   = stores["store_id"].tolist()
AREA_IDS    = areas["area_id"].tolist()
PRODUCT_IDS = products["product_id"].tolist()


# ======================================================================
# 1. ECONOMIC PARAMETERS  (hand-chosen, not random)
# ======================================================================
RIDER_COST_PER_MIN  = 3.0   # rupees paid to the rider per minute of a trip
AVG_ITEMS_PER_ORDER = 5.0   # a typical quick-commerce basket


# ======================================================================
# 2. DERIVED COST TABLES
# ======================================================================

# 2a. Volume demanded by each area (the thing capacity has to hold).
area_volume = demand.groupby("area_id")["demand_volume"].sum()

# 2b. Number of rider trips each area generates per day.
area_items  = demand.groupby("area_id")["demand_units"].sum()
area_orders = np.ceil(area_items / AVG_ITEMS_PER_ORDER)

# 2c. Cost of NOT serving one item: you lose the margin you would have earned
#     (profit_per_unit) AND you pay the churn cost (penalty_per_unit).
products = products.copy()
products["shortfall_per_unit"] = (
    products["profit_per_unit"] + products["penalty_per_unit"]
)

# 2d. Cost of leaving a whole area unserved for a day.
short = demand.merge(
    products[["product_id", "shortfall_per_unit"]], on="product_id", how="left"
)
short["row_cost"] = short["demand_units"] * short["shortfall_per_unit"]
area_shortfall = short.groupby("area_id")["row_cost"].sum()

# 2e. Cost of serving area a from store s for one day.
links = links.copy()
links["orders"] = links["area_id"].map(area_orders)
links["delivery_cost"] = (
    RIDER_COST_PER_MIN * links["delivery_min"] * links["orders"]
)

# Only the SLA-feasible pairs are real decisions. The rest are deleted, not
# penalised -- a 40-minute delivery is not a bad option, it is not an option.
pairs = links[links["within_sla"]].reset_index(drop=True)
PAIR_LIST = list(zip(pairs["store_id"], pairs["area_id"]))

# Fast lookup dictionaries (plain Python -- easier to read than .loc chains).
open_cost  = dict(zip(stores["store_id"], stores["opening_cost"]))
capacity   = dict(zip(stores["store_id"], stores["capacity_units"]))
vol        = area_volume.to_dict()
shortfall  = area_shortfall.to_dict()
deliver    = {(s, a): c for s, a, c in
              zip(pairs["store_id"], pairs["area_id"], pairs["delivery_cost"])}
servers_of = {a: [s for (s, aa) in PAIR_LIST if aa == a] for a in AREA_IDS}

pairs[["store_id", "area_id", "distance_km", "delivery_min",
       "orders", "delivery_cost"]].to_csv("data/derived_costs.csv", index=False)


# ======================================================================
# 3. THE MODEL, IN WORDS AND THEN IN CODE
# ======================================================================
#
# DECISIONS
#   y[s]    = 1 if we open dark store s              (4 binary variables)
#   x[s,a]  = 1 if area a is served by store s       (9 binary variables,
#                                                     SLA-feasible pairs only)
#   I[s,p]  = units of product p stocked at store s  (NOT a free decision --
#             it is forced by x, see below)
#
# INVENTORY ALLOCATION IS DERIVED, NOT SEARCHED
#   If store s serves area a, it must stock everything that area orders:
#       I[s,p] = sum over a of  x[s,a] * demand[a,p]
#   So allocation costs zero extra qubits. This is the modelling choice that
#   keeps the problem small enough for a real QAOA run.
#
# CONSTRAINTS
#   C1  each area is served by at most one store   sum_s x[s,a] <= 1
#   C2  cannot serve from a closed store           x[s,a] <= y[s]
#   C3  capacity                                   sum_a x[s,a]*vol[a] <= cap[s]
#
# OBJECTIVE (minimise rupees per day)
#   opening   sum_s  open_cost[s] * y[s]
# + delivery  sum_sa deliver[s,a] * x[s,a]
# + shortfall sum_a  shortfall[a] * (1 - sum_s x[s,a])
#
# NOTE ON THE SHORTFALL TERM
#   Revenue does not appear as its own term. Total demand is fixed, so
#   "profit earned" = "total possible profit" - "profit lost". The first part
#   is a constant, and a constant never changes which solution is best -- so
#   it is folded into shortfall_per_unit and dropped. This matters later:
#   QAOA also only ever sees differences between solutions, never absolutes.
# ======================================================================


def evaluate(open_set, assignment):
    """Cost of one candidate solution, plus a feasibility verdict.

    open_set   : set of store_ids we decide to open
    assignment : dict area_id -> store_id, or None if the area is unserved
    """
    cost = sum(open_cost[s] for s in open_set)

    load = {s: 0.0 for s in open_set}
    for a, s in assignment.items():
        if s is None:
            cost += shortfall[a]          # nobody serves this area today
            continue
        cost += deliver[(s, a)]
        load[s] += vol[a]

    feasible = all(load[s] <= capacity[s] for s in open_set)
    return cost, feasible, load


# ======================================================================
# 4. PART A -- STRUCTURED BRUTE FORCE (the trustworthy answer)
#    Loop over every subset of stores; for each, try every way of pointing
#    each area at an open store that can reach it (or at nobody).
# ======================================================================
rows = []
best = None

for r in range(len(STORE_IDS) + 1):
    for open_tuple in itertools.combinations(STORE_IDS, r):
        open_set = set(open_tuple)

        # For each area: the stores that are open AND within SLA, plus None.
        options = [
            [s for s in servers_of[a] if s in open_set] + [None]
            for a in AREA_IDS
        ]

        best_here = None
        for choice in itertools.product(*options):
            assignment = dict(zip(AREA_IDS, choice))
            cost, feasible, load = evaluate(open_set, assignment)
            if not feasible:
                continue
            if best_here is None or cost < best_here[0]:
                best_here = (cost, assignment, load)

        if best_here is None:
            continue

        cost, assignment, load = best_here
        rows.append({
            "stores_open": "+".join(open_tuple) if open_tuple else "(none)",
            "n_open": r,
            "opening_cost": sum(open_cost[s] for s in open_set),
            "unserved": sum(1 for v in assignment.values() if v is None),
            "total_cost": cost,
        })
        if best is None or cost < best[0]:
            best = (cost, open_set, assignment, load)

subset_table = (pd.DataFrame(rows)
                .sort_values("total_cost")
                .reset_index(drop=True))

best_cost, best_open, best_assign, best_load = best


def rule(title):
    print("\n" + "=" * 74)
    print(title)
    print("=" * 74)


rule("COST INGREDIENTS")
ingredients = pd.DataFrame({
    "demand_volume": area_volume,
    "items_per_day": area_items,
    "rider_trips": area_orders,
    "cost_if_unserved": area_shortfall,
})
print(ingredients)

rule("DELIVERY COST OF EACH SLA-FEASIBLE PAIR (rupees/day)")
print(pairs.pivot(index="store_id", columns="area_id", values="delivery_cost"))

rule("PART A -- ALL STORE COMBINATIONS, BEST ACHIEVABLE COST EACH")
print(subset_table)

rule("OPTIMAL SOLUTION")
print(f"open stores      : {sorted(best_open)}")
print(f"total daily cost : Rs {best_cost:,.2f}")
print("\nassignment:")
for a in AREA_IDS:
    s = best_assign[a]
    if s is None:
        print(f"  {a} -> UNSERVED  (cost Rs {shortfall[a]:,.0f})")
    else:
        print(f"  {a} -> {s}   delivery Rs {deliver[(s, a)]:,.2f}")

print("\ncapacity usage:")
for s in sorted(best_open):
    print(f"  {s}: {best_load[s]:,.1f} / {capacity[s]:,.1f} units "
          f"({100 * best_load[s] / capacity[s]:.1f}%)")

rule("INVENTORY ALLOCATION IMPLIED BY THE OPTIMAL ASSIGNMENT")
alloc_rows = []
for a, s in best_assign.items():
    if s is None:
        continue
    for _, d in demand[demand["area_id"] == a].iterrows():
        alloc_rows.append({"store_id": s, "product_id": d["product_id"],
                           "units": d["demand_units"]})
allocation = (pd.DataFrame(alloc_rows)
              .groupby(["store_id", "product_id"])["units"].sum()
              .reset_index())
print(allocation.pivot(index="store_id", columns="product_id", values="units"))
allocation.to_csv("data/stage2_allocation.csv", index=False)


# ======================================================================
# 5. PART B -- THE SEARCH SPACE QAOA WILL ACTUALLY SEE
#    Every constraint becomes a penalty added to the cost, and we scan all
#    2^13 = 8192 bitstrings. This is the exact shape of the QUBO in Stage 3.
# ======================================================================
N_Y = len(STORE_IDS)
N_X = len(PAIR_LIST)
N_BITS = N_Y + N_X

LAMBDA_ASSIGN = 20000.0   # per double-assigned area   (> worst shortfall)
LAMBDA_OPEN   = 20000.0   # per link out of a closed store
LAMBDA_CAP    = 100.0     # per unit of volume over capacity


def penalised_cost(bits):
    """Cost of a raw bitstring, with constraints charged instead of enforced."""
    y = {s: bits[i] for i, s in enumerate(STORE_IDS)}
    x = {p: bits[N_Y + i] for i, p in enumerate(PAIR_LIST)}

    cost = sum(open_cost[s] * y[s] for s in STORE_IDS)
    cost += sum(deliver[p] * x[p] for p in PAIR_LIST)

    for a in AREA_IDS:                                    # shortfall + C1
        served = sum(x[(s, a)] for s in servers_of[a])
        cost += shortfall[a] * (1 - served)
        if served > 1:
            cost += LAMBDA_ASSIGN * (served - 1)

    for s in STORE_IDS:                                   # C2 + C3
        load = 0.0
        for (ss, a) in PAIR_LIST:
            if ss == s and x[(ss, a)]:
                load += vol[a]
                if not y[s]:
                    cost += LAMBDA_OPEN
        if load > capacity[s]:
            cost += LAMBDA_CAP * (load - capacity[s])

    return cost


def is_feasible(bits):
    y = {s: bits[i] for i, s in enumerate(STORE_IDS)}
    x = {p: bits[N_Y + i] for i, p in enumerate(PAIR_LIST)}
    for a in AREA_IDS:
        if sum(x[(s, a)] for s in servers_of[a]) > 1:
            return False
    for s in STORE_IDS:
        load = 0.0
        for (ss, a) in PAIR_LIST:
            if ss == s and x[(ss, a)]:
                if not y[s]:
                    return False
                load += vol[a]
        if load > capacity[s]:
            return False
    return True


# int64, not int8: the bits get multiplied by rupee costs in the thousands,
# and a small dtype would silently overflow.
all_bits = np.array(list(itertools.product([0, 1], repeat=N_BITS)), dtype=np.int64)
scan = pd.DataFrame({
    "cost": [penalised_cost(b) for b in all_bits],
    "feasible": [is_feasible(b) for b in all_bits],
})

rule("PART B -- THE FULL 2^13 SEARCH SPACE")
print(f"variables (qubits)          : {N_BITS}  ({N_Y} open + {N_X} assignment)")
print(f"bitstrings enumerated       : {len(scan):,}")
print(f"feasible bitstrings         : {int(scan['feasible'].sum()):,} "
      f"({100 * scan['feasible'].mean():.1f}%)")
print(f"cheapest penalised cost     : Rs {scan['cost'].min():,.2f}")
print(f"Part A optimum              : Rs {best_cost:,.2f}")
print(f"do they agree?              : {abs(scan['cost'].min() - best_cost) < 1e-6}")

argmin = int(scan["cost"].idxmin())
print(f"argmin is feasible?         : {bool(scan.loc[argmin, 'feasible'])}")
print(f"winning bitstring           : "
      f"{''.join(str(int(b)) for b in all_bits[argmin])}")
print(f"  bit order                 : y{STORE_IDS} then "
      f"x{[s + '->' + a for s, a in PAIR_LIST]}")

print(f"\nrandom-guess cost (mean)    : Rs {scan['cost'].mean():,.2f}")
print(f"worst cost                  : Rs {scan['cost'].max():,.2f}")
gap = scan["cost"].mean() - scan["cost"].min()
print(f"headroom QAOA must close    : Rs {gap:,.2f}")
print("\nhow many solutions are within X% of optimal (the target QAOA must hit):")
for pct in [0, 1, 5, 10]:
    thresh = best_cost * (1 + pct / 100)
    n = int((scan["cost"] <= thresh + 1e-9).sum())
    print(f"  within {pct:>2}% : {n:>5} of {len(scan):,} "
          f"({100 * n / len(scan):.3f}%)")

pd.DataFrame({
    "bitstring": ["".join(str(int(b)) for b in row) for row in all_bits],
    "cost": scan["cost"],
    "feasible": scan["feasible"],
}).to_csv("data/stage2_landscape.csv", index=False)

rule("SAVED")
for f in ["data/derived_costs.csv", "data/stage2_allocation.csv",
          "data/stage2_landscape.csv"]:
    print(f"  {f}")
