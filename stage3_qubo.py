"""
Stage 3 -- Turn the model into a QUBO matrix, then into an Ising Hamiltonian.

Project: QAOA for Joint Dark Store Location Selection and Inventory Allocation
         in Hyperlocal Quick Commerce.

Still NO quantum library. This file produces the two objects a QAOA circuit is
built from:

    QUBO   cost(x) = x^T Q x + offset          x_i in {0, 1}
    Ising  E(s)    = sum_i h_i s_i  +  sum_i<j J_ij s_i s_j  + const
                                               s_i in {+1, -1}

This script is deliberately a SECOND, INDEPENDENT implementation of the cost
function. It reloads the raw CSVs instead of importing anything from
stage2_baseline.py. If the two files agree, that is real evidence the model is
right; if stage 3 imported stage 2's code, agreement would prove nothing.

Run:  python stage3_qubo.py
"""

import itertools

import numpy as np
import pandas as pd

pd.set_option("display.width", 140)
pd.set_option("display.max_columns", 60)
pd.set_option("display.float_format", lambda v: f"{v:,.2f}")


def rule(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


# ======================================================================
# 0. REBUILD THE COST INGREDIENTS FROM THE RAW DATA
# ======================================================================
stores   = pd.read_csv("data/stores.csv")
areas    = pd.read_csv("data/areas.csv")
products = pd.read_csv("data/products.csv")
demand   = pd.read_csv("data/demand.csv")
links    = pd.read_csv("data/store_area_links.csv")

STORE_IDS = stores["store_id"].tolist()
AREA_IDS  = areas["area_id"].tolist()

RIDER_COST_PER_MIN  = 3.0
AVG_ITEMS_PER_ORDER = 5.0

area_volume = demand.groupby("area_id")["demand_volume"].sum()
area_items  = demand.groupby("area_id")["demand_units"].sum()
area_orders = np.ceil(area_items / AVG_ITEMS_PER_ORDER)

products["shortfall_per_unit"] = (products["profit_per_unit"]
                                  + products["penalty_per_unit"])
short = demand.merge(products[["product_id", "shortfall_per_unit"]],
                     on="product_id", how="left")
short["row_cost"] = short["demand_units"] * short["shortfall_per_unit"]
area_shortfall = short.groupby("area_id")["row_cost"].sum()

links["orders"] = links["area_id"].map(area_orders)
links["delivery_cost"] = RIDER_COST_PER_MIN * links["delivery_min"] * links["orders"]

pairs = links[links["within_sla"]].reset_index(drop=True)
PAIR_LIST = list(zip(pairs["store_id"], pairs["area_id"]))

open_cost  = dict(zip(stores["store_id"], stores["capacity_units"] * 0
                      + stores["opening_cost"]))
capacity   = dict(zip(stores["store_id"], stores["capacity_units"]))
vol        = area_volume.to_dict()
shortfall  = area_shortfall.to_dict()
deliver    = {(s, a): c for s, a, c in zip(pairs["store_id"], pairs["area_id"],
                                           pairs["delivery_cost"])}
servers_of = {a: [s for (s, aa) in PAIR_LIST if aa == a] for a in AREA_IDS}
served_by  = {s: [a for (ss, a) in PAIR_LIST if ss == s] for s in STORE_IDS}


# ======================================================================
# 1. PREPROCESSING -- WHICH CAPACITY CONSTRAINTS ARE REAL?
#
# A constraint that no reachable solution can violate costs qubits and buys
# nothing. For each store we enumerate every subset of the areas it can legally
# reach and keep only the MINIMAL subsets that overflow it. "Minimal" means no
# smaller subset already overflows, so we never write a redundant penalty.
# ======================================================================
violating = {}
for s in STORE_IDS:
    minimal = []
    for r in range(1, len(served_by[s]) + 1):
        for sub in itertools.combinations(served_by[s], r):
            load = sum(vol[a] for a in sub)
            if load > capacity[s] and not any(set(m) <= set(sub) for m in minimal):
                minimal.append(tuple(sub))
    violating[s] = minimal

rule("STEP 1 -- WHICH CAPACITY CONSTRAINTS CAN ACTUALLY BE BROKEN?")
for s in STORE_IDS:
    reach = sum(vol[a] for a in served_by[s])
    verdict = violating[s] if violating[s] else "NEVER BINDING -> no penalty needed"
    print(f"  {s}: reaches {served_by[s]}, total {reach:,.1f} vs cap "
          f"{capacity[s]:,.1f}  ->  {verdict}")

# Textbook alternative, for comparison in the write-up: one slack register per
# store, big enough to encode the unused capacity of that store.
slack_bits = sum(int(np.ceil(np.log2(capacity[s] + 1))) for s in STORE_IDS)
print(f"\n  textbook slack-variable encoding would add : {slack_bits} qubits")


# ======================================================================
# 2. VARIABLE LIST
#    A size-2 violating set is already quadratic -> free.
#    A size-3 violating set is CUBIC, and QUBO only accepts degree 2. We fix it
#    with one auxiliary bit w = AND(first two members), a standard Rosenberg
#    reduction, which turns x1*x2*x3 into w*x3.
# ======================================================================
names = [f"y[{s}]" for s in STORE_IDS] + [f"x[{s},{a}]" for s, a in PAIR_LIST]

aux = []                       # (aux_name, store, pair_a, pair_b, third_area)
for s in STORE_IDS:
    for sub in violating[s]:
        if len(sub) == 3:
            a1, a2, a3 = sub
            w_name = f"w[{s},{a1}&{a2}]"
            aux.append((w_name, s, a1, a2, a3))
            names.append(w_name)
        elif len(sub) > 3:
            raise NotImplementedError(
                f"{s} has a degree-{len(sub)} capacity constraint; this "
                "prototype only reduces up to degree 3."
            )

idx = {n: i for i, n in enumerate(names)}
N = len(names)

rule("STEP 2 -- VARIABLES")
for i, n in enumerate(names):
    kind = ("open store" if n.startswith("y") else
            "assignment" if n.startswith("x") else "auxiliary (AND gadget)")
    print(f"  q{i:>2}  {n:<20} {kind}")
print(f"\n  total qubits: {N}   (search space 2^{N} = {2 ** N:,})")


# ======================================================================
# 3. PENALTY WEIGHTS -- DERIVED FROM THE DATA, NOT GUESSED
#
# Rule: a penalty must be strictly larger than the biggest cost saving a
# solution could get by breaking that constraint. Bigger than that is safe for
# exact enumeration but bad for QAOA, because a huge spread between the largest
# and smallest coefficients squeezes the useful cost differences into rotation
# angles too small for the optimiser to feel.
# ======================================================================
max_shortfall = max(shortfall.values())
max_open      = max(open_cost.values())

# LAMBDA_CAP is a rate (rupees per unit of overflow), so it must be calibrated
# against the SMALLEST overflow any solution could get away with -- that is the
# cheapest way to cheat. Using the largest overflow here would leave the
# tightest constraint under-priced.
min_excess = min((sum(vol[a] for a in sub) - capacity[s])
                 for s in STORE_IDS for sub in violating[s])

LAMBDA_ASSIGN = 2.0 * max_shortfall                 # double-booking an area
LAMBDA_OPEN   = 2.0 * max_open                      # shipping from a closed store
LAMBDA_CAP    = 2.0 * max_shortfall / min_excess    # per unit of overflow
LAMBDA_AND    = 4.0 * max_shortfall                 # keeping the gadget honest

rule("STEP 3 -- PENALTY WEIGHTS")
print(f"  worst shortfall (A2)          : Rs {max_shortfall:,.0f}")
print(f"  worst opening cost (S2)       : Rs {max_open:,.0f}")
print(f"  smallest capacity overflow    : {min_excess:,.1f} units")
print(f"\n  LAMBDA_ASSIGN = {LAMBDA_ASSIGN:>10,.1f}   > any gain from double-booking")
print(f"  LAMBDA_OPEN   = {LAMBDA_OPEN:>10,.1f}   > any gain from a free store")
print(f"  LAMBDA_CAP    = {LAMBDA_CAP:>10,.1f}   per unit over capacity")
print(f"  LAMBDA_AND    = {LAMBDA_AND:>10,.1f}   > any gain from a wrong AND bit")


# ======================================================================
# 4. BUILD Q  (upper triangular; because x_i^2 = x_i, linear terms sit on the
#    diagonal and there is no separate linear vector)
# ======================================================================
Q = np.zeros((N, N))
offset = 0.0


def add_linear(name, coeff):
    Q[idx[name], idx[name]] += coeff


def add_quadratic(name_i, name_j, coeff):
    i, j = idx[name_i], idx[name_j]
    if i > j:
        i, j = j, i
    Q[i, j] += coeff


# --- 4a. objective: opening cost -------------------------------------
for s in STORE_IDS:
    add_linear(f"y[{s}]", open_cost[s])

# --- 4b. objective: delivery cost ------------------------------------
for (s, a) in PAIR_LIST:
    add_linear(f"x[{s},{a}]", deliver[(s, a)])

# --- 4c. objective: shortfall  sum_a shortfall[a] * (1 - sum_s x[s,a])
#         The "1" is a constant -> it goes into offset, not into Q.
for a in AREA_IDS:
    offset += shortfall[a]
    for s in servers_of[a]:
        add_linear(f"x[{s},{a}]", -shortfall[a])

# --- 4d. C1: at most one store per area ------------------------------
#         penalty = LAMBDA_ASSIGN * sum over unordered pairs x[s,a] x[s',a]
for a in AREA_IDS:
    for s1, s2 in itertools.combinations(servers_of[a], 2):
        add_quadratic(f"x[{s1},{a}]", f"x[{s2},{a}]", LAMBDA_ASSIGN)

# --- 4e. C2: x[s,a] <= y[s]  ->  penalty = LAMBDA_OPEN * x(1 - y)
for (s, a) in PAIR_LIST:
    add_linear(f"x[{s},{a}]", LAMBDA_OPEN)
    add_quadratic(f"y[{s}]", f"x[{s},{a}]", -LAMBDA_OPEN)

# --- 4f. C3: capacity, only for the minimal violating subsets --------
for s in STORE_IDS:
    for sub in violating[s]:
        excess = sum(vol[a] for a in sub) - capacity[s]
        weight = LAMBDA_CAP * excess
        if len(sub) == 2:
            add_quadratic(f"x[{s},{sub[0]}]", f"x[{s},{sub[1]}]", weight)
        else:                                   # degree 3, via the aux bit
            a1, a2, a3 = sub
            add_quadratic(f"w[{s},{a1}&{a2}]", f"x[{s},{a3}]", weight)

# --- 4g. the AND gadget:  LAMBDA_AND * (3w + x1 x2 - 2 w x1 - 2 w x2)
#         This expression is 0 exactly when w == x1 AND x2, and positive
#         otherwise, so the minimiser sets w correctly on its own.
for (w_name, s, a1, a2, a3) in aux:
    x1, x2 = f"x[{s},{a1}]", f"x[{s},{a2}]"
    add_linear(w_name, 3.0 * LAMBDA_AND)
    add_quadratic(x1, x2, LAMBDA_AND)
    add_quadratic(w_name, x1, -2.0 * LAMBDA_AND)
    add_quadratic(w_name, x2, -2.0 * LAMBDA_AND)

rule("STEP 4 -- THE QUBO MATRIX Q  (upper triangular, rupees)")
Qdf = pd.DataFrame(Q, index=names, columns=names)
print(Qdf.replace(0, np.nan).to_string(na_rep="."))
print(f"\noffset (constant added to every solution) : Rs {offset:,.2f}")


# ======================================================================
# 5. QUBO -> ISING
#    Substitute x_i = (1 - s_i) / 2, so s = +1 means "bit is 0" and
#    s = -1 means "bit is 1" -- the standard Pauli-Z convention where
#    |0> has eigenvalue +1.
# ======================================================================
diag = np.diag(Q).copy()
offd = Q - np.diag(diag)                    # strictly upper triangular part
sym  = offd + offd.T                        # symmetric copy, easier to sum

h = -0.5 * diag - 0.25 * sym.sum(axis=1)
J = 0.25 * offd
ising_const = 0.5 * diag.sum() + 0.25 * offd.sum() + offset

rule("STEP 5 -- ISING FORM")
print("local fields h_i (rupees):")
print(pd.Series(h, index=names))
print("\nnon-zero couplings J_ij (rupees):")
couplings = [(names[i], names[j], J[i, j])
             for i in range(N) for j in range(i + 1, N) if J[i, j] != 0]
print(pd.DataFrame(couplings, columns=["qubit_i", "qubit_j", "J_ij"]))
print(f"\nconstant : Rs {ising_const:,.2f}")


# ======================================================================
# 6. VERIFY -- three independent checks
# ======================================================================
X = np.array(list(itertools.product([0, 1], repeat=N)), dtype=np.int64)
qubo_cost = np.einsum("ij,ij->i", X @ Q, X) + offset

S = 1 - 2 * X
ising_energy = S @ h + np.einsum("ij,ij->i", S @ J, S) + ising_const

rule("STEP 6 -- VERIFICATION")

# 6a. Ising must reproduce QUBO exactly, for every one of the 2^N strings.
max_gap = np.abs(qubo_cost - ising_energy).max()
print(f"[1] max |QUBO - Ising| over all {len(X):,} strings : {max_gap:.3e}")
print(f"    identical (tolerance 1e-6)? {max_gap < 1e-6}")

# 6b. On every FEASIBLE solution, the QUBO must equal the plain cost that
#     stage2_baseline.py computed independently.
land = pd.read_csv("data/stage2_landscape.csv", dtype={"bitstring": str})
land_feas = land[land["feasible"]].reset_index(drop=True)

N13 = len(STORE_IDS) + len(PAIR_LIST)
prefix_bits = X[:, :N13]
powers = (1 << np.arange(N13 - 1, -1, -1))
prefix_key = prefix_bits @ powers

# For each 13-bit stage-2 string, take the extended string whose aux bits the
# QUBO itself prefers (the minimum) -- that is what a solver would return.
best_by_prefix = pd.DataFrame({"key": prefix_key, "cost": qubo_cost}) \
    .groupby("key")["cost"].min()

land_feas["key"] = [int(b, 2) for b in land_feas["bitstring"]]
land_feas["qubo"] = land_feas["key"].map(best_by_prefix)
err = (land_feas["qubo"] - land_feas["cost"]).abs().max()
print(f"[2] feasible solutions cross-checked vs stage 2 : {len(land_feas):,}")
print(f"    max disagreement : Rs {err:.3e}   ->  match? {err < 1e-6}")

# 6c. The global minimum of the QUBO must be the known optimum.
best_i = int(qubo_cost.argmin())
best_bits = X[best_i]
stage2_opt = land_feas["cost"].min()
print(f"[3] QUBO minimum   : Rs {qubo_cost[best_i]:,.2f}")
print(f"    stage 2 optimum: Rs {stage2_opt:,.2f}   ->  match? "
      f"{abs(qubo_cost[best_i] - stage2_opt) < 1e-6}")
print(f"    bitstring      : {''.join(map(str, best_bits))}")
print("    reads as       : "
      + ", ".join(n for n, b in zip(names, best_bits) if b))


# ======================================================================
# 7. PENALTY SWEEP -- proof that the weights are in the right window
# ======================================================================
def build_and_test(scale):
    """Rebuild Q with every penalty multiplied by `scale`, return the verdict."""
    q = np.zeros((N, N))
    off = 0.0
    la, lo = LAMBDA_ASSIGN * scale, LAMBDA_OPEN * scale
    lc, ld = LAMBDA_CAP * scale, LAMBDA_AND * scale

    def lin(n, c):
        q[idx[n], idx[n]] += c

    def quad(n1, n2, c):
        i, j = sorted((idx[n1], idx[n2]))
        q[i, j] += c

    for s in STORE_IDS:
        lin(f"y[{s}]", open_cost[s])
    for (s, a) in PAIR_LIST:
        lin(f"x[{s},{a}]", deliver[(s, a)] + lo)
        quad(f"y[{s}]", f"x[{s},{a}]", -lo)
    for a in AREA_IDS:
        off += shortfall[a]
        for s in servers_of[a]:
            lin(f"x[{s},{a}]", -shortfall[a])
        for s1, s2 in itertools.combinations(servers_of[a], 2):
            quad(f"x[{s1},{a}]", f"x[{s2},{a}]", la)
    for s in STORE_IDS:
        for sub in violating[s]:
            w = lc * (sum(vol[a] for a in sub) - capacity[s])
            if len(sub) == 2:
                quad(f"x[{s},{sub[0]}]", f"x[{s},{sub[1]}]", w)
            else:
                quad(f"w[{s},{sub[0]}&{sub[1]}]", f"x[{s},{sub[2]}]", w)
    for (w_name, s, a1, a2, a3) in aux:
        x1, x2 = f"x[{s},{a1}]", f"x[{s},{a2}]"
        lin(w_name, 3.0 * ld)
        quad(x1, x2, ld)
        quad(w_name, x1, -2.0 * ld)
        quad(w_name, x2, -2.0 * ld)

    c = np.einsum("ij,ij->i", X @ q, X) + off
    i = int(c.argmin())
    key = int(prefix_key[i])
    row = land_feas[land_feas["key"] == key]
    ok_feasible = len(row) > 0
    ok_optimal = ok_feasible and abs(row["cost"].iloc[0] - stage2_opt) < 1e-6
    spread = np.abs(q[q != 0]).max() / np.abs(q[q != 0]).min()
    return ok_feasible, ok_optimal, spread


rule("STEP 7 -- PENALTY SWEEP (why the weights above are the right ones)")
print(f"{'scale':>8} {'winner feasible':>17} {'winner optimal':>16} "
      f"{'coeff. dynamic range':>22}")
for scale in [0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 10.0, 100.0, 1000.0]:
    feas, opt, spread = build_and_test(scale)
    print(f"{scale:>8.2f} {str(feas):>17} {str(opt):>16} {spread:>21,.0f}x")
print("\n  too small -> the cheapest bitstring cheats and is infeasible")
print("  too large -> still correct here, but the real cost differences shrink")
print("               relative to the penalties, which is what makes QAOA's")
print("               optimisation landscape flat and hard to climb")


# ======================================================================
# 8. SAVE
# ======================================================================
Qdf.to_csv("data/qubo_matrix.csv")
pd.Series(h, index=names, name="h").to_csv("data/ising_h.csv")
pd.DataFrame(couplings, columns=["qubit_i", "qubit_j", "J_ij"]).to_csv(
    "data/ising_J.csv", index=False)
np.savez("data/qubo.npz", Q=Q, offset=offset, h=h, J=J,
         ising_const=ising_const, names=np.array(names))
pd.DataFrame({
    "bitstring": ["".join(map(str, row)) for row in X],
    "qubo_cost": qubo_cost,
}).to_csv("data/stage3_spectrum.csv", index=False)

rule("SAVED")
for f in ["data/qubo_matrix.csv", "data/ising_h.csv", "data/ising_J.csv",
          "data/qubo.npz", "data/stage3_spectrum.csv"]:
    print(f"  {f}")
