"""
Reusable pipeline: instance -> QUBO -> (exact optimum | QAOA | baselines).

Stages 1-4 each hard-coded one 4x4 instance. To measure how anything SCALES you
need to run the same pipeline on many instances, so the logic moves here and
stages 5+ import it.

Nothing in this file is new physics or new modelling. It is stages 1-4
generalised, and stage5_scaling.py re-verifies it against the frozen 4x4
numbers before trusting it on anything bigger.
"""

import itertools

import numpy as np
import pandas as pd

# Products are held fixed across every instance so that only the SIZE of the
# problem changes in the scaling study, never its economics.
PRODUCTS = pd.DataFrame({
    "product_id":       ["P1", "P2", "P3"],
    "product_name":     ["Milk & Bread", "Snacks", "Household Care"],
    "volume_per_unit":  [1.0, 1.5, 2.5],
    "profit_per_unit":  [12, 20, 35],
    "penalty_per_unit": [25, 15, 10],
})
PRODUCT_MIX = np.array([0.58, 0.29, 0.13])   # share of items, matches stage 1

RIDER_COST_PER_MIN  = 3.0
AVG_ITEMS_PER_ORDER = 5.0
AVG_SPEED_KMPH      = 20.0
HANDLING_MIN        = 3.0


# ======================================================================
# 1. INSTANCE GENERATION
#
# WHY RANDOM NUMBERS ARE USED HERE
#   Stages 1-4 used a single hand-built instance so the answer could be checked
#   by hand. A scaling study needs a FAMILY of instances, and hand-building
#   five of them would quietly bake in the author's expectations about which
#   layouts are easy. Sampling positions and demand from fixed distributions
#   removes that bias. Every generator call takes a seed, so any instance can
#   be reproduced exactly.
# ======================================================================
def make_instance(n_stores, n_areas, seed, city_km=10.0, sla_minutes=15.0,
                  capacity_slack=1.6, name=None):
    """Build a random but reproducible dark-store instance.

    capacity_slack : total capacity as a multiple of total demand volume.
                     Near 1.0 the capacity constraints bite hard; large values
                     make them irrelevant.
    """
    rng = np.random.default_rng(seed)

    store_xy = rng.uniform(0.5, city_km - 0.5, size=(n_stores, 2))
    area_xy  = rng.uniform(0.5, city_km - 0.5, size=(n_areas, 2))

    store_ids = [f"S{i+1}" for i in range(n_stores)]
    area_ids  = [f"A{i+1}" for i in range(n_areas)]

    # Demand: total items per area, split across products by a fixed mix.
    area_items = rng.integers(200, 460, size=n_areas)
    rows = []
    for i, a in enumerate(area_ids):
        for j, p in enumerate(PRODUCTS["product_id"]):
            rows.append({"area_id": a, "product_id": p,
                         "demand_units": int(round(area_items[i] * PRODUCT_MIX[j]))})
    demand = pd.DataFrame(rows).merge(
        PRODUCTS[["product_id", "volume_per_unit"]], on="product_id", how="left")
    demand["demand_volume"] = demand["demand_units"] * demand["volume_per_unit"]

    total_volume = demand["demand_volume"].sum()

    # Capacity: split the slack budget unevenly so stores differ from each other.
    share = rng.uniform(0.7, 1.3, size=n_stores)
    share = share / share.sum()
    capacity_units = np.round(share * capacity_slack * total_volume / 25) * 25
    capacity_units = np.maximum(capacity_units, 150.0)

    # Opening cost: mostly proportional to capacity, plus a location premium so
    # that "biggest" and "cheapest per unit" are not the same store.
    premium = rng.uniform(0.85, 1.2, size=n_stores)
    opening_cost = np.round(capacity_units * 11.0 * premium / 100) * 100

    stores = pd.DataFrame({
        "store_id": store_ids, "x_km": store_xy[:, 0], "y_km": store_xy[:, 1],
        "opening_cost": opening_cost, "capacity_units": capacity_units,
    })
    areas = pd.DataFrame({
        "area_id": area_ids, "x_km": area_xy[:, 0], "y_km": area_xy[:, 1],
    })

    # Distances and delivery times, exactly as in stage 1.
    diff = store_xy[:, None, :] - area_xy[None, :, :]
    dist = np.sqrt((diff ** 2).sum(axis=2))
    time = HANDLING_MIN + (dist / AVG_SPEED_KMPH) * 60.0

    # Every area must be reachable by someone, or the instance is degenerate.
    # Relax the SLA until that holds, and report what it took.
    sla = float(sla_minutes)
    while (time.min(axis=0) > sla).any():
        sla += 1.0

    links = pd.DataFrame({
        "store_id": np.repeat(store_ids, n_areas),
        "area_id": np.tile(area_ids, n_stores),
        "distance_km": dist.ravel(),
        "delivery_min": time.ravel(),
    })
    links["within_sla"] = links["delivery_min"] <= sla

    return _finalise(stores, areas, demand, links, sla,
                     name or f"{n_stores}x{n_areas}")


def load_stage1_instance():
    """The frozen 4x4 instance from stages 1-4, read back off disk."""
    stores = pd.read_csv("data/stores.csv")
    areas  = pd.read_csv("data/areas.csv")
    demand = pd.read_csv("data/demand.csv")
    links  = pd.read_csv("data/store_area_links.csv")
    return _finalise(stores, areas, demand, links, 15.0, "stage1-4x4")


def _finalise(stores, areas, demand, links, sla, name, products=None):
    """Attach every derived cost the rest of the pipeline needs.

    products defaults to the fixed catalogue used by the synthetic generator.
    Pass your own table (same columns) to run a real-world dataset through the
    pipeline -- see pondicherry_adapter.py.
    """
    products = (PRODUCTS if products is None else products).copy()
    products["shortfall_per_unit"] = (products["profit_per_unit"]
                                      + products["penalty_per_unit"])

    area_volume = demand.groupby("area_id")["demand_volume"].sum()
    area_items  = demand.groupby("area_id")["demand_units"].sum()
    area_orders = np.ceil(area_items / AVG_ITEMS_PER_ORDER)

    sh = demand.merge(products[["product_id", "shortfall_per_unit"]],
                      on="product_id", how="left")
    sh["row_cost"] = sh["demand_units"] * sh["shortfall_per_unit"]
    area_shortfall = sh.groupby("area_id")["row_cost"].sum()

    links = links.copy()
    links["orders"] = links["area_id"].map(area_orders)
    links["delivery_cost"] = (RIDER_COST_PER_MIN * links["delivery_min"]
                              * links["orders"])
    pairs = links[links["within_sla"]].reset_index(drop=True)

    store_ids = stores["store_id"].tolist()
    area_ids  = areas["area_id"].tolist()
    pair_list = list(zip(pairs["store_id"], pairs["area_id"]))

    return {
        "name": name, "sla": sla,
        "stores": stores, "areas": areas, "demand": demand,
        "products": products, "links": links, "pairs": pairs,
        "store_ids": store_ids, "area_ids": area_ids, "pair_list": pair_list,
        "open_cost": dict(zip(stores["store_id"], stores["opening_cost"])),
        "capacity": dict(zip(stores["store_id"], stores["capacity_units"])),
        "vol": area_volume.to_dict(),
        "shortfall": area_shortfall.to_dict(),
        "deliver": {(s, a): c for s, a, c in zip(
            pairs["store_id"], pairs["area_id"], pairs["delivery_cost"])},
        "servers_of": {a: [s for (s, aa) in pair_list if aa == a]
                       for a in area_ids},
        "served_by": {s: [a for (ss, a) in pair_list if ss == s]
                      for s in store_ids},
    }


# ======================================================================
# 2. QUBO CONSTRUCTION  (stage 3, generalised to any degree)
# ======================================================================
def minimal_violating_subsets(inst):
    """For each store, the smallest sets of areas that overflow it."""
    out = {}
    for s in inst["store_ids"]:
        reach = inst["served_by"][s]
        minimal = []
        for r in range(1, len(reach) + 1):
            for sub in itertools.combinations(reach, r):
                load = sum(inst["vol"][a] for a in sub)
                if load > inst["capacity"][s] and not any(
                        set(m) <= set(sub) for m in minimal):
                    minimal.append(tuple(sub))
        out[s] = minimal
    return out


def build_qubo(inst, scale=1.0, include_c1=True):
    """Return Q (upper triangular), offset, variable names and diagnostics.

    include_c1=False drops the "at most one store per area" penalty. Only do
    that when something else guarantees the constraint -- stage 6 uses an
    XY-mixer that can never leave the one-hot subspace, which makes the penalty
    dead weight.

    Degree-k capacity terms with k >= 3 are reduced to degree 2 by chaining AND
    gadgets: w1 = x1 AND x2, w2 = w1 AND x3, ... Each gadget costs one qubit,
    and gadgets are memoised so two constraints sharing a prefix share a qubit.
    """
    violating = minimal_violating_subsets(inst)

    names = ([f"y[{s}]" for s in inst["store_ids"]]
             + [f"x[{s},{a}]" for s, a in inst["pair_list"]])
    idx = {n: i for i, n in enumerate(names)}

    entries = {}          # (i, j) -> coefficient, i <= j
    offset = 0.0
    and_cache = {}

    max_shortfall = max(inst["shortfall"].values())
    max_open = max(inst["open_cost"].values())
    excesses = [sum(inst["vol"][a] for a in sub) - inst["capacity"][s]
                for s in inst["store_ids"] for sub in violating[s]]
    min_excess = min(excesses) if excesses else 1.0

    L_ASSIGN = 2.0 * max_shortfall * scale
    L_OPEN   = 2.0 * max_open * scale
    L_CAP    = 2.0 * max_shortfall / min_excess * scale
    L_AND    = 4.0 * max_shortfall * scale

    def new_var(n):
        idx[n] = len(names)
        names.append(n)
        return n

    def lin(n, c):
        i = idx[n]
        entries[(i, i)] = entries.get((i, i), 0.0) + c

    def quad(n1, n2, c):
        i, j = sorted((idx[n1], idx[n2]))
        entries[(i, j)] = entries.get((i, j), 0.0) + c

    def make_and(n1, n2):
        """Add a qubit w forced to equal n1 AND n2; return its name."""
        key = frozenset((n1, n2))
        if key in and_cache:
            return and_cache[key]
        w = new_var(f"w[{n1}&{n2}]")
        lin(w, 3.0 * L_AND)
        quad(n1, n2, L_AND)
        quad(w, n1, -2.0 * L_AND)
        quad(w, n2, -2.0 * L_AND)
        and_cache[key] = w
        return w

    # --- objective ---
    for s in inst["store_ids"]:
        lin(f"y[{s}]", inst["open_cost"][s])
    for (s, a) in inst["pair_list"]:
        lin(f"x[{s},{a}]", inst["deliver"][(s, a)])
    for a in inst["area_ids"]:
        offset += inst["shortfall"][a]
        for s in inst["servers_of"][a]:
            lin(f"x[{s},{a}]", -inst["shortfall"][a])

    # --- C1: at most one store per area ---
    if include_c1:
        for a in inst["area_ids"]:
            for s1, s2 in itertools.combinations(inst["servers_of"][a], 2):
                quad(f"x[{s1},{a}]", f"x[{s2},{a}]", L_ASSIGN)

    # --- C2: no shipping from a closed store ---
    for (s, a) in inst["pair_list"]:
        lin(f"x[{s},{a}]", L_OPEN)
        quad(f"y[{s}]", f"x[{s},{a}]", -L_OPEN)

    # --- C3: capacity, only where it can actually be broken ---
    n_aux_before = len(names)
    for s in inst["store_ids"]:
        for sub in violating[s]:
            weight = L_CAP * (sum(inst["vol"][a] for a in sub)
                              - inst["capacity"][s])
            terms = [f"x[{s},{a}]" for a in sub]
            if len(terms) == 1:
                lin(terms[0], weight)
            elif len(terms) == 2:
                quad(terms[0], terms[1], weight)
            else:
                acc = terms[0]
                for t in terms[1:-1]:          # chain ANDs down to degree 2
                    acc = make_and(acc, t)
                quad(acc, terms[-1], weight)

    N = len(names)
    Q = np.zeros((N, N))
    for (i, j), c in entries.items():
        Q[i, j] += c

    return {
        "Q": Q, "offset": offset, "names": names, "n_qubits": N,
        "n_aux": N - n_aux_before + 0, "violating": violating,
        "lambdas": {"assign": L_ASSIGN, "open": L_OPEN,
                    "cap": L_CAP, "and": L_AND},
    }


# ======================================================================
# 3. FEASIBILITY AND COST, VECTORISED OVER MANY BITSTRINGS AT ONCE
# ======================================================================
def cost_of(X, qubo):
    """x^T Q x + offset for every row of X."""
    return np.einsum("ij,ij->i", X @ qubo["Q"], X) + qubo["offset"]


def feasible_mask(X, inst, qubo):
    """Boolean per row. Only y and x are read; auxiliary bits are ignored."""
    n_y = len(inst["store_ids"])
    pair_list = inst["pair_list"]
    y = X[:, :n_y]
    x = X[:, n_y:n_y + len(pair_list)]

    ok = np.ones(len(X), dtype=bool)

    # C1: at most one server per area
    for a in inst["area_ids"]:
        cols = [i for i, (s, aa) in enumerate(pair_list) if aa == a]
        if cols:
            ok &= x[:, cols].sum(axis=1) <= 1

    for si, s in enumerate(inst["store_ids"]):
        cols = [i for i, (ss, _) in enumerate(pair_list) if ss == s]
        if not cols:
            continue
        # C2: any link used requires the store to be open
        ok &= (x[:, cols].max(axis=1) <= y[:, si])
        # C3: capacity
        vols = np.array([inst["vol"][pair_list[i][1]] for i in cols])
        ok &= (x[:, cols] @ vols) <= inst["capacity"][s] + 1e-9

    return ok


def all_bitstrings(n):
    return np.array(list(itertools.product([0, 1], repeat=n)), dtype=np.int64)


# ======================================================================
# 4. EXACT OPTIMUM  (structured enumeration -- stage 2 part A, generalised)
#    Enumerates open-sets x assignments, which is far smaller than 2^n.
# ======================================================================
def exact_optimum(inst):
    best = None
    n_eval = 0
    for r in range(len(inst["store_ids"]) + 1):
        for open_tuple in itertools.combinations(inst["store_ids"], r):
            open_set = set(open_tuple)
            options = [[s for s in inst["servers_of"][a] if s in open_set] + [None]
                       for a in inst["area_ids"]]
            for choice in itertools.product(*options):
                n_eval += 1
                cost = sum(inst["open_cost"][s] for s in open_set)
                load = {s: 0.0 for s in open_set}
                for a, s in zip(inst["area_ids"], choice):
                    if s is None:
                        cost += inst["shortfall"][a]
                    else:
                        cost += inst["deliver"][(s, a)]
                        load[s] += inst["vol"][a]
                if any(load[s] > inst["capacity"][s] for s in open_set):
                    continue
                if best is None or cost < best[0]:
                    best = (cost, open_tuple, dict(zip(inst["area_ids"], choice)))
    return {"cost": best[0], "open": best[1], "assign": best[2],
            "evaluations": n_eval}


# ======================================================================
# 5. QAOA  (stage 4, generalised)
# ======================================================================
def qaoa_expectation_factory(qubo, X=None):
    """Return (expected_cost_fn, state_fn, C_rupees) for this QUBO."""
    n = qubo["n_qubits"]
    dim = 2 ** n
    if X is None:
        X = all_bitstrings(n)
    C = cost_of(X, qubo)
    C_scaled = (C - C.mean()) / C.std()
    plus = np.full(dim, 1.0 / np.sqrt(dim), dtype=np.complex128)

    def mixer(psi, beta):
        c = np.cos(beta)
        s = -1j * np.sin(beta)
        psi = psi.copy()
        for j in range(n):
            v = psi.reshape(2 ** j, 2, 2 ** (n - j - 1))
            a0 = v[:, 0, :].copy()
            a1 = v[:, 1, :].copy()
            v[:, 0, :] = c * a0 + s * a1
            v[:, 1, :] = c * a1 + s * a0
            psi = v.reshape(-1)
        return psi

    def state(params):
        p = len(params) // 2
        psi = plus.copy()
        for l in range(p):
            psi = psi * np.exp(-1j * params[l] * C_scaled)
            psi = mixer(psi, params[p + l])
        return psi

    def expected(params):
        return float((np.abs(state(params)) ** 2) @ C)

    return expected, state, C


def run_qaoa(qubo, p, restarts, maxiter, seed, X=None):
    from scipy.optimize import minimize

    expected, state, C = qaoa_expectation_factory(qubo, X)
    rng = np.random.default_rng(seed)
    best = None
    for _ in range(restarts):
        start = np.concatenate([rng.uniform(-np.pi, np.pi, p),
                                rng.uniform(0.0, np.pi, p)])
        res = minimize(expected, start, method="COBYLA",
                       options={"maxiter": maxiter, "rhobeg": 0.3})
        if best is None or res.fun < best.fun:
            best = res
    probs = np.abs(state(best.x)) ** 2
    return {"params": best.x, "expected": best.fun, "probs": probs, "C": C}


# ======================================================================
# 6. CLASSICAL BASELINES
# ======================================================================
def simulated_annealing(qubo, steps, seed, restarts=5, t_hi=None, t_lo=None):
    """Single-bit-flip Metropolis on the same QUBO the quantum circuit sees."""
    Q = qubo["Q"]
    n = qubo["n_qubits"]
    sym = Q + Q.T - np.diag(np.diag(Q))     # symmetric, diagonal counted once
    diag = np.diag(Q)
    rng = np.random.default_rng(seed)

    spread = np.abs(sym).sum(axis=1).mean()
    t_hi = t_hi if t_hi is not None else spread
    t_lo = t_lo if t_lo is not None else spread * 1e-4

    best_x, best_c = None, np.inf
    for _ in range(restarts):
        x = rng.integers(0, 2, size=n).astype(np.int64)
        c = float(x @ Q @ x) + qubo["offset"]
        for k in range(steps):
            T = t_hi * (t_lo / t_hi) ** (k / max(steps - 1, 1))
            i = int(rng.integers(n))
            # cost change from flipping bit i, computed in O(n) not O(n^2)
            delta = (1 - 2 * x[i]) * (diag[i] + sym[i] @ x - sym[i, i] * x[i])
            if delta <= 0 or rng.random() < np.exp(-delta / T):
                x[i] ^= 1
                c += delta
            if c < best_c:
                best_c, best_x = c, x.copy()
    return {"cost": float(best_c), "bits": best_x}


def greedy_business_heuristic(inst):
    """What a planner would do with a spreadsheet: open stores one at a time,
    each time picking the store that reduces total cost the most."""
    open_set = []
    remaining = set(inst["store_ids"])

    def cost_of_open_set(open_list):
        """Assign areas greedily by regret, cheapest feasible server first."""
        load = {s: 0.0 for s in open_list}
        cost = sum(inst["open_cost"][s] for s in open_list)
        order = []
        for a in inst["area_ids"]:
            opts = sorted((inst["deliver"][(s, a)], s)
                          for s in inst["servers_of"][a] if s in open_list)
            if not opts:
                order.append((0.0, a, []))
                continue
            regret = (opts[1][0] - opts[0][0]) if len(opts) > 1 else 1e9
            order.append((-regret, a, opts))
        order.sort()
        assign = {}
        for _, a, opts in order:
            placed = None
            for c, s in opts:
                if load[s] + inst["vol"][a] <= inst["capacity"][s]:
                    load[s] += inst["vol"][a]
                    cost += c
                    placed = s
                    break
            if placed is None:
                cost += inst["shortfall"][a]
            assign[a] = placed
        return cost, assign

    best_cost, best_assign = cost_of_open_set([])
    improved = True
    while improved and remaining:
        improved = False
        pick, pick_cost, pick_assign = None, best_cost, best_assign
        for s in sorted(remaining):
            c, asg = cost_of_open_set(open_set + [s])
            if c < pick_cost - 1e-9:
                pick, pick_cost, pick_assign = s, c, asg
        if pick is not None:
            open_set.append(pick)
            remaining.discard(pick)
            best_cost, best_assign = pick_cost, pick_assign
            improved = True
    return {"cost": best_cost, "open": open_set, "assign": best_assign}
