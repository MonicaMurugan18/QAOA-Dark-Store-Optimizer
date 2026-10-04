"""
Stage 6 -- Constraint-preserving QAOA (XY-mixer) and warm starts.

Project: QAOA for Joint Dark Store Location Selection and Inventory Allocation
         in Hyperlocal Quick Commerce.

Stage 5 found the failure mode: as instances grow, the fraction of bitstrings
that are valid business plans collapses (16% -> 0.27%), and the standard mixer
spends nearly all its amplitude on garbage. This stage attacks that directly.

THE IDEA
  The standard mixer exp(-i beta sum_j X_j) can move the state ANYWHERE in the
  2^n space, so "at most one store per area" has to be bribed with a penalty
  and is only ever satisfied approximately.

  Instead, give each area a one-hot register over {its reachable stores} plus
  one extra slot meaning "unserved", and mix it with an XY-mixer

      H_XY = sum_{i<j} (X_i X_j + Y_i Y_j) / 2

  which only ever HOPS the single excitation between slots. It cannot create or
  destroy one, so exactly-one-choice-per-area holds by construction, at every
  depth, forever. The C1 penalty is then dead weight and is deleted.

WHAT THIS DOES AND DOES NOT FIX
  C1 (one store per area)      -> guaranteed by the mixer. No penalty needed.
  C2 (no shipping from closed) -> still a penalty.
  C3 (capacity)                -> still a penalty.
  So feasibility is not automatically 1. It should be much higher.

SIMULATION NOTE
  Because the state can never leave the one-hot subspace, we simulate INSIDE
  that subspace instead of the full 2^n space. Restricted to one-hot states,
  H_XY is the adjacency matrix of the complete graph, so the mixer on a block
  of size k is the exact k x k matrix

      M = e^{i beta} [ I + ((e^{-i beta k} - 1) / k) * ones ]

  This is why stage 6 runs faster than stage 5 despite solving more.

Run:  python stage6_constrained.py
"""

import itertools
import time

import numpy as np
import pandas as pd
from scipy.optimize import minimize

import qaoa_pipeline as qp

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 60)


def rule(title):
    print("\n" + "=" * 96)
    print(title)
    print("=" * 96)


P_LAYERS  = 4
RESTARTS  = 5
MAXITER   = 300
SHOTS     = 500
SEED      = 42
WARM_BIAS = 0.6          # how strongly the warm start leans on the greedy plan


# ======================================================================
# 1. THE REDUCED (ONE-HOT) BASIS
# ======================================================================
def build_reduced_basis(inst, qubo):
    """Enumerate only the states the XY-mixer can ever reach.

    Axes are, in order:
        one binary axis per y[s]        (open/closed, standard X mixer)
        one binary axis per auxiliary w (AND gadget, standard X mixer)
        one block axis per area         (size = reachable stores + 1, XY mixer)

    Returns the axis sizes, the full bitstring for every reduced index, and a
    label for what each area axis position means.
    """
    names = qubo["names"]
    idx = {n: i for i, n in enumerate(names)}
    n_bits = qubo["n_qubits"]

    y_names = [f"y[{s}]" for s in inst["store_ids"]]
    w_names = [n for n in names if n.startswith("w[")]

    # For each area: the choices are its reachable stores, then "unserved".
    area_choices = {a: inst["servers_of"][a] + [None] for a in inst["area_ids"]}

    dims = ([2] * len(y_names) + [2] * len(w_names)
            + [len(area_choices[a]) for a in inst["area_ids"]])

    ranges = [range(d) for d in dims]
    rows = []
    for combo in itertools.product(*ranges):
        bits = np.zeros(n_bits, dtype=np.int64)
        pos = 0
        for name in y_names:
            bits[idx[name]] = combo[pos]
            pos += 1
        for name in w_names:
            bits[idx[name]] = combo[pos]
            pos += 1
        for a in inst["area_ids"]:
            s = area_choices[a][combo[pos]]
            if s is not None:
                bits[idx[f"x[{s},{a}]"]] = 1
            pos += 1
        rows.append(bits)

    return {
        "dims": dims, "bits": np.array(rows), "area_choices": area_choices,
        "n_binary": len(y_names) + len(w_names),
        "y_names": y_names, "w_names": w_names,
    }


# ======================================================================
# 2. SIMULATOR ON THE REDUCED BASIS
#    One helper applies any matrix along any axis, so the binary mixer and
#    the XY block mixer share the same code path.
# ======================================================================
def apply_axis(psi, M, ax):
    """Multiply the state by matrix M acting on a single tensor axis."""
    out = np.tensordot(M, psi, axes=([1], [ax]))
    return np.moveaxis(out, 0, ax)


def rx_matrix(beta):
    """exp(-i beta X) for one qubit."""
    c, s = np.cos(beta), -1j * np.sin(beta)
    return np.array([[c, s], [s, c]], dtype=np.complex128)


def xy_block_matrix(beta, k):
    """exp(-i beta H_XY) restricted to the k one-hot states of a block.

    On that subspace H_XY is the complete-graph adjacency matrix J - I, and
    J = k * (projector onto uniform), which gives the closed form below.
    """
    if k == 1:
        return np.array([[np.exp(1j * beta)]], dtype=np.complex128)
    M = np.eye(k, dtype=np.complex128)
    M += ((np.exp(-1j * beta * k) - 1.0) / k) * np.ones((k, k), dtype=np.complex128)
    return np.exp(1j * beta) * M


def make_constrained_qaoa(basis, C):
    """Return (expected_cost_fn, state_fn) for the XY-mixed circuit."""
    dims = basis["dims"]
    nb = basis["n_binary"]
    shape = tuple(dims)
    C_t = C.reshape(shape)
    C_scaled = ((C - C.mean()) / C.std()).reshape(shape)

    def mixer(psi, beta):
        for ax in range(len(dims)):
            M = rx_matrix(beta) if ax < nb else xy_block_matrix(beta, dims[ax])
            psi = apply_axis(psi, M, ax)
        return psi

    def state(params, psi0):
        p = len(params) // 2
        psi = psi0.copy()
        for l in range(p):
            psi = psi * np.exp(-1j * params[l] * C_scaled)
            psi = mixer(psi, params[p + l])
        return psi

    def expected(params, psi0):
        return float((np.abs(state(params, psi0)) ** 2 * C_t).sum())

    return expected, state, C_t


def uniform_start(basis):
    """Uniform over the whole reduced basis.

    On the binary axes this is |+>; on each block it is the equal-weight W
    state. Both are ground states of their mixer, which is what the QAOA
    construction requires.
    """
    D = int(np.prod(basis["dims"]))
    return np.full(tuple(basis["dims"]), 1.0 / np.sqrt(D), dtype=np.complex128)


def warm_start(basis, inst, greedy, bias=WARM_BIAS):
    """Bias the start toward the greedy plan, staying inside the subspace.

    Each axis gets probability `bias` on the greedy choice, with the remaining
    (1 - bias) spread evenly. bias = 0 recovers the uniform start.
    """
    vectors = []
    for name in basis["y_names"]:
        s = name[2:-1]
        want = 1 if s in greedy["open"] else 0
        p = np.full(2, (1 - bias) / 2)
        p[want] += bias
        vectors.append(np.sqrt(p))
    for _ in basis["w_names"]:
        vectors.append(np.sqrt(np.full(2, 0.5)))     # no greedy value for aux
    for a in inst["area_ids"]:
        choices = basis["area_choices"][a]
        k = len(choices)
        want = choices.index(greedy["assign"].get(a))
        p = np.full(k, (1 - bias) / k)
        p[want] += bias
        vectors.append(np.sqrt(p))

    psi = vectors[0]
    for v in vectors[1:]:
        psi = np.multiply.outer(psi, v)
    return psi.astype(np.complex128)


def optimise(expected, psi0, p, restarts, maxiter, seed):
    rng = np.random.default_rng(seed)
    best = None
    for _ in range(restarts):
        start = np.concatenate([rng.uniform(-np.pi, np.pi, p),
                                rng.uniform(0.0, np.pi, p)])
        res = minimize(lambda t: expected(t, psi0), start, method="COBYLA",
                       options={"maxiter": maxiter, "rhobeg": 0.3})
        if best is None or res.fun < best.fun:
            best = res
    return best


# ======================================================================
# 3. INSTANCES
# ======================================================================
base = qp.load_stage1_instance()
INSTANCES = [("stage1-4x4", base)]
for ns, na in [(4, 5), (5, 5), (5, 6), (6, 6)]:
    INSTANCES.append((f"{ns}x{na}", qp.make_instance(ns, na, 42, capacity_slack=1.5)))

# Head-to-head against the standard mixer is only affordable where 2^n is small.
STANDARD_LIMIT = 16


# ======================================================================
# 4. CORRECTNESS CHECKS ON THE REDUCED BASIS
# ======================================================================
rule("STEP 1 -- IS THE REDUCED BASIS THE RIGHT ONE?")
q_full = qp.build_qubo(base, include_c1=True)
q_noc1 = qp.build_qubo(base, include_c1=False)
b = build_reduced_basis(base, q_noc1)

C_noc1 = qp.cost_of(b["bits"], q_noc1)
C_full = qp.cost_of(b["bits"], q_full)
exact = qp.exact_optimum(base)

n_y = len(base["store_ids"])
x_cols = slice(n_y, n_y + len(base["pair_list"]))
per_area_counts = []
for a in base["area_ids"]:
    cols = [n_y + i for i, (s, aa) in enumerate(base["pair_list"]) if aa == a]
    per_area_counts.append(b["bits"][:, cols].sum(axis=1))
c1_ok = np.all(np.array(per_area_counts) <= 1)

checks = [
    ("every reduced state satisfies C1", bool(c1_ok)),
    ("dropping the C1 penalty changes nothing on this basis",
     float(np.abs(C_noc1 - C_full).max()) < 1e-9),
    ("the known optimum is inside the reduced basis",
     abs(C_noc1.min() - exact["cost"]) < 1e-6),
]
for label, ok in checks:
    print(f"  [{'PASS' if ok else 'FAIL'}]  {label}")
if not all(ok for _, ok in checks):
    raise SystemExit("reduced basis is wrong; stopping.")
print(f"\n  full space  2^{q_full['n_qubits']} = {2 ** q_full['n_qubits']:,}")
print(f"  reduced basis dimension = {len(b['bits']):,}  "
      f"({100 * len(b['bits']) / 2 ** q_full['n_qubits']:.2f}% of it)")


# ======================================================================
# 5. THE EXPERIMENT
# ======================================================================
rule("STEP 2 -- SEARCH SPACE: STANDARD MIXER VS XY MIXER")
print(f"{'instance':>12} {'qubits':>7} {'2^n (standard)':>16} "
      f"{'reduced (XY)':>14} {'shrink':>9}")
prepared = []
for name, inst in INSTANCES:
    qf = qp.build_qubo(inst, include_c1=True)
    qn = qp.build_qubo(inst, include_c1=False)
    bs = build_reduced_basis(inst, qn)
    D = len(bs["bits"])
    print(f"{name:>12} {qf['n_qubits']:>7} {2 ** qf['n_qubits']:>16,} "
          f"{D:>14,} {2 ** qf['n_qubits'] / D:>8.0f}x")
    prepared.append((name, inst, qf, qn, bs))

rule("STEP 3 -- RUNNING THE THREE VARIANTS")
rows = []
rng_shots = np.random.default_rng(20260909)

for name, inst, qf, qn, bs in prepared:
    n = qf["n_qubits"]
    exact = qp.exact_optimum(inst)
    greedy = qp.greedy_business_heuristic(inst)
    rec = {"instance": name, "qubits": n, "reduced_dim": len(bs["bits"]),
           "exact_cost": exact["cost"], "greedy_cost": greedy["cost"]}

    # ---- variant 1: standard X mixer, all penalties on ----------------
    if 2 ** n <= 2 ** STANDARD_LIMIT:
        t0 = time.perf_counter()
        X = qp.all_bitstrings(n)
        res = qp.run_qaoa(qf, p=P_LAYERS, restarts=RESTARTS,
                          maxiter=MAXITER, seed=SEED, X=X)
        probs = res["probs"] / res["probs"].sum()
        C = res["C"]
        feas = qp.feasible_mask(X, inst, qf)
        shots = rng_shots.choice(len(probs), size=SHOTS, p=probs)
        sf = qp.feasible_mask(X[shots], inst, qf)
        rec["std_P_feasible"] = float(probs[feas].sum())
        rec["std_P_opt"] = float(probs[int(C.argmin())])
        rec["std_cost"] = float(C[shots][sf].min()) if sf.any() else np.nan
        rec["std_sec"] = time.perf_counter() - t0
    else:
        for k in ["std_P_feasible", "std_P_opt", "std_cost", "std_sec"]:
            rec[k] = np.nan

    # ---- variants 2 and 3: XY mixer, cold and warm start ---------------
    C_red = qp.cost_of(bs["bits"], qn)
    feas_red = qp.feasible_mask(bs["bits"], inst, qn)
    expected, state, C_t = make_constrained_qaoa(bs, C_red)
    opt_flat = int(C_red.argmin())

    for tag, psi0 in [("xy", uniform_start(bs)),
                      ("warm", warm_start(bs, inst, greedy))]:
        t0 = time.perf_counter()
        best = optimise(expected, psi0, P_LAYERS, RESTARTS, MAXITER, SEED)
        probs = np.abs(state(best.x, psi0)) ** 2
        probs = (probs / probs.sum()).ravel()
        shots = rng_shots.choice(len(probs), size=SHOTS, p=probs)
        sf = feas_red[shots]
        rec[f"{tag}_P_feasible"] = float(probs[feas_red].sum())
        rec[f"{tag}_P_opt"] = float(probs[opt_flat])
        rec[f"{tag}_cost"] = (float(C_red[shots][sf].min()) if sf.any()
                              else np.nan)
        rec[f"{tag}_sec"] = time.perf_counter() - t0

    rows.append(rec)
    print(f"  {name:>12} n={n:>2}  exact Rs {exact['cost']:>10,.0f}   "
          f"std {rec['std_cost'] if rec['std_cost'] == rec['std_cost'] else float('nan'):>10,.0f}   "
          f"xy {rec['xy_cost']:>10,.0f}   warm {rec['warm_cost']:>10,.0f}")

df = pd.DataFrame(rows)
for tag in ["std", "xy", "warm", "greedy"]:
    df[f"{tag}_gap_pct"] = 100 * (df[f"{tag}_cost"] - df["exact_cost"]) / df["exact_cost"]
df.to_csv("data/stage6_constrained.csv", index=False)


# ======================================================================
# 6. RESULTS
# ======================================================================
def fmt_pct(v):
    return f"{v:+.2f}%" if v == v else "n/a"


def fmt_p(v):
    return f"{v:.4f}" if v == v else "n/a"


rule("RESULT 1 -- PROBABILITY THE MEASURED STATE IS A VALID PLAN")
print(df[["instance", "qubits", "std_P_feasible", "xy_P_feasible",
          "warm_P_feasible"]].to_string(index=False, formatters={
    "std_P_feasible": fmt_p, "xy_P_feasible": fmt_p, "warm_P_feasible": fmt_p}))

rule("RESULT 2 -- PROBABILITY OF THE EXACT OPTIMUM")
print(df[["instance", "qubits", "std_P_opt", "xy_P_opt",
          "warm_P_opt"]].to_string(index=False, formatters={
    "std_P_opt": lambda v: f"{v:.6f}" if v == v else "n/a",
    "xy_P_opt": lambda v: f"{v:.6f}",
    "warm_P_opt": lambda v: f"{v:.6f}"}))

rule("RESULT 3 -- BEST PLAN FOUND IN %d SHOTS (gap to exact optimum)" % SHOTS)
print(df[["instance", "qubits", "exact_cost", "greedy_gap_pct", "std_gap_pct",
          "xy_gap_pct", "warm_gap_pct"]].to_string(index=False, formatters={
    "exact_cost": lambda v: f"Rs {v:,.0f}",
    "greedy_gap_pct": fmt_pct, "std_gap_pct": fmt_pct,
    "xy_gap_pct": fmt_pct, "warm_gap_pct": fmt_pct}))

rule("RESULT 4 -- SIMULATION TIME (seconds)")
print(df[["instance", "qubits", "std_sec", "xy_sec", "warm_sec"]].to_string(
    index=False, formatters={c: (lambda v: f"{v:.1f}" if v == v else "n/a")
                             for c in ["std_sec", "xy_sec", "warm_sec"]}))

rule("SUMMARY")
n_inst = len(df)
print(f"instances                                   : {n_inst}")
print(f"exact optimum found -- standard mixer       : "
      f"{int((df['std_gap_pct'].abs() < 1e-6).sum())} / "
      f"{int(df['std_cost'].notna().sum())}")
print(f"exact optimum found -- XY mixer             : "
      f"{int((df['xy_gap_pct'].abs() < 1e-6).sum())} / {n_inst}")
print(f"exact optimum found -- XY + warm start      : "
      f"{int((df['warm_gap_pct'].abs() < 1e-6).sum())} / {n_inst}")
print(f"exact optimum found -- greedy heuristic     : "
      f"{int((df['greedy_gap_pct'].abs() < 1e-6).sum())} / {n_inst}")
print(f"\nmean P(feasible)  standard : "
      f"{df['std_P_feasible'].mean():.4f}")
print(f"mean P(feasible)  XY       : {df['xy_P_feasible'].mean():.4f}")
print(f"mean P(feasible)  XY+warm  : {df['warm_P_feasible'].mean():.4f}")

rule("SAVED")
print("  data/stage6_constrained.csv")
