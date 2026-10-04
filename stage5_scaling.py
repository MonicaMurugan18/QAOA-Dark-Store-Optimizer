"""
Stage 5 -- Scaling study and classical baselines.

Project: QAOA for Joint Dark Store Location Selection and Inventory Allocation
         in Hyperlocal Quick Commerce.

Stages 1-4 produced ONE data point: a 14-qubit instance QAOA happened to solve.
That is a demo, not a result. This stage answers the two questions a reviewer
will ask first:

  A. How does the encoding SCALE?  Qubits, feasible fraction and solution
     quality as the number of stores and areas grows.
  B. Is QAOA actually BETTER than the obvious classical alternatives on the
     same problem?  Greedy heuristic, simulated annealing, random sampling.

Part B is written expecting the answer to be "no, not at this size". Reporting
that honestly is the point -- it locates where the real research question is.

Run:  python stage5_scaling.py
"""

import time

import numpy as np
import pandas as pd

import qaoa_pipeline as qp

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 60)


def rule(title):
    print("\n" + "=" * 96)
    print(title)
    print("=" * 96)


# Statevector simulation needs 2^n complex numbers. Past this, the laptop stops.
QAOA_QUBIT_LIMIT = 19
ENUM_QUBIT_LIMIT = 20        # full-spectrum statistics need 2^n rows

QAOA_P        = 3
QAOA_RESTARTS = 3
QAOA_MAXITER  = 200
SHOTS         = 500
SA_STEPS      = 4000
SA_RESTARTS   = 5
SEED          = 42


# ======================================================================
# 0. VALIDATION -- the generalised pipeline must reproduce stages 1-4
#    before it is trusted on anything new.
# ======================================================================
rule("STEP 0 -- REPLAY THE FROZEN 4x4 INSTANCE THROUGH THE NEW PIPELINE")
base = qp.load_stage1_instance()
base_q = qp.build_qubo(base)
base_opt = qp.exact_optimum(base)
base_X = qp.all_bitstrings(base_q["n_qubits"])
base_C = qp.cost_of(base_X, base_q)
base_feas = qp.feasible_mask(base_X, base, base_q)

checks = [
    ("qubits == 14", base_q["n_qubits"] == 14),
    ("offset == 45,535", abs(base_q["offset"] - 45535.0) < 1e-6),
    ("exact optimum == Rs 23,413.49", abs(base_opt["cost"] - 23413.49) < 0.01),
    ("optimum opens S1+S4", tuple(base_opt["open"]) == ("S1", "S4")),
    ("QUBO minimum == exact optimum",
     abs(base_C.min() - base_opt["cost"]) < 1e-6),
    ("feasible states == 356 x 2 (aux bit free)", int(base_feas.sum()) == 712),
]
for label, ok in checks:
    print(f"  [{'PASS' if ok else 'FAIL'}]  {label}")
if not all(ok for _, ok in checks):
    raise SystemExit("pipeline does not reproduce stages 1-4; stopping.")


# ======================================================================
# 1. THE INSTANCE LADDER
#    One seed, a systematic sweep of sizes. Qubit count is an OUTCOME, not a
#    target -- picking seeds to hit round qubit numbers would be cheating.
# ======================================================================
SIZES = [(3, 3), (3, 4), (4, 4), (4, 5), (5, 5), (5, 6), (6, 6), (6, 7)]

instances = [("stage1-4x4", base, base_q)]
for ns, na in SIZES:
    inst = qp.make_instance(ns, na, SEED, capacity_slack=1.5)
    instances.append((f"{ns}x{na}", inst, qp.build_qubo(inst)))

rule("STEP 1 -- THE INSTANCE LADDER")
print(f"{'instance':>12} {'stores':>7} {'areas':>6} {'SLA pairs':>10} "
      f"{'aux':>4} {'qubits':>7} {'2^n':>14} {'SLA min':>8}")
for name, inst, q in instances:
    ns, na = len(inst["store_ids"]), len(inst["area_ids"])
    npairs = len(inst["pair_list"])
    print(f"{name:>12} {ns:>7} {na:>6} {npairs:>10} "
          f"{q['n_qubits'] - ns - npairs:>4} {q['n_qubits']:>7} "
          f"{2 ** q['n_qubits']:>14,} {inst['sla']:>8.0f}")


# ======================================================================
# 2. RUN EVERYTHING ON EVERY INSTANCE
# ======================================================================
rng_global = np.random.default_rng(20260909)
rows = []

rule("STEP 2 -- SOLVING EACH INSTANCE (exact, QAOA, and three baselines)")

for name, inst, q in instances:
    n = q["n_qubits"]
    ns, na = len(inst["store_ids"]), len(inst["area_ids"])
    rec = {"instance": name, "stores": ns, "areas": na,
           "pairs": len(inst["pair_list"]), "qubits": n}

    # ---- exact optimum, by structured enumeration -------------------
    t0 = time.perf_counter()
    exact = qp.exact_optimum(inst)
    rec["exact_cost"] = exact["cost"]
    rec["exact_open"] = "+".join(exact["open"])
    rec["exact_evals"] = exact["evaluations"]
    rec["exact_sec"] = time.perf_counter() - t0

    # ---- greedy business heuristic ----------------------------------
    t0 = time.perf_counter()
    greedy = qp.greedy_business_heuristic(inst)
    rec["greedy_cost"] = greedy["cost"]
    rec["greedy_sec"] = time.perf_counter() - t0

    # ---- simulated annealing on the same QUBO ------------------------
    t0 = time.perf_counter()
    sa = qp.simulated_annealing(q, SA_STEPS, seed=SEED, restarts=SA_RESTARTS)
    rec["sa_cost"] = sa["cost"]
    rec["sa_sec"] = time.perf_counter() - t0

    # ---- random sampling, same shot budget as QAOA -------------------
    t0 = time.perf_counter()
    rand_bits = rng_global.integers(0, 2, size=(SHOTS, n))
    rand_feas = qp.feasible_mask(rand_bits, inst, q)
    rand_costs = qp.cost_of(rand_bits, q)
    rec["random_cost"] = (float(rand_costs[rand_feas].min())
                          if rand_feas.any() else np.nan)
    rec["random_feasible_shots"] = int(rand_feas.sum())
    rec["random_sec"] = time.perf_counter() - t0

    # ---- full spectrum statistics (only while 2^n fits in memory) ----
    if n <= ENUM_QUBIT_LIMIT:
        X = qp.all_bitstrings(n)
        C = qp.cost_of(X, q)
        feas = qp.feasible_mask(X, inst, q)
        rec["mean_cost"] = float(C.mean())
        rec["feasible_frac"] = float(feas.mean())
    else:
        X = None
        rec["mean_cost"] = np.nan
        rec["feasible_frac"] = np.nan

    # ---- QAOA --------------------------------------------------------
    if n <= QAOA_QUBIT_LIMIT:
        t0 = time.perf_counter()
        res = qp.run_qaoa(q, p=QAOA_P, restarts=QAOA_RESTARTS,
                          maxiter=QAOA_MAXITER, seed=SEED, X=X)
        probs = res["probs"] / res["probs"].sum()
        C = res["C"]
        opt_idx = int(C.argmin())

        shots = rng_global.choice(len(probs), size=SHOTS, p=probs)
        shot_feas = qp.feasible_mask(X[shots], inst, q)
        ok = C[shots][shot_feas]

        rec["qaoa_expected"] = res["expected"]
        rec["qaoa_approx_ratio"] = ((rec["mean_cost"] - res["expected"])
                                    / (rec["mean_cost"] - C.min()))
        rec["qaoa_P_opt"] = float(probs[opt_idx])
        rec["qaoa_P_feasible"] = float(probs[qp.feasible_mask(X, inst, q)].sum())
        rec["qaoa_cost"] = float(ok.min()) if len(ok) else np.nan
        rec["qaoa_feasible_shots"] = int(shot_feas.sum())
        rec["qaoa_sec"] = time.perf_counter() - t0
    else:
        for k in ["qaoa_expected", "qaoa_approx_ratio", "qaoa_P_opt",
                  "qaoa_P_feasible", "qaoa_cost", "qaoa_sec"]:
            rec[k] = np.nan
        rec["qaoa_feasible_shots"] = -1

    rows.append(rec)
    q_txt = ("skipped (2^%d too large)" % n if np.isnan(rec["qaoa_cost"])
             else f"Rs {rec['qaoa_cost']:,.0f} in {rec['qaoa_sec']:.1f}s")
    print(f"  {name:>12}  n={n:>2}  exact Rs {exact['cost']:>10,.0f}   "
          f"greedy Rs {greedy['cost']:>10,.0f}   SA Rs {sa['cost']:>10,.0f}   "
          f"QAOA {q_txt}")

df = pd.DataFrame(rows)
for col, base_col in [("greedy", "exact_cost"), ("sa", "exact_cost"),
                      ("random", "exact_cost"), ("qaoa", "exact_cost")]:
    df[f"{col}_gap_pct"] = 100 * (df[f"{col}_cost"] - df[base_col]) / df[base_col]
df.to_csv("data/stage5_scaling.csv", index=False)


# ======================================================================
# 3. PART A -- HOW THE ENCODING SCALES
# ======================================================================
rule("PART A -- SCALING OF THE ENCODING")
print(df[["instance", "stores", "areas", "pairs", "qubits",
          "feasible_frac", "exact_evals", "exact_sec"]].to_string(
              index=False,
              formatters={"feasible_frac": lambda v: f"{v:.4f}" if v == v else "n/a",
                          "exact_sec": lambda v: f"{v:.2f}s"}))

print("\nqubits vs decision variables:")
for _, r in df.iterrows():
    print(f"  {r['instance']:>12}: {r['stores']}+{r['pairs']} decision bits "
          f"+ {int(r['qubits'] - r['stores'] - r['pairs'])} auxiliary "
          f"= {int(r['qubits'])} qubits")

fit = np.polyfit(df["stores"] * df["areas"], df["qubits"], 1)
print(f"\nlinear fit: qubits ~ {fit[0]:.2f} * (stores x areas) + {fit[1]:.2f}")
print("The SLA prune is what keeps this linear rather than quadratic: only")
print("store-area pairs inside the delivery promise ever become variables.")


# ======================================================================
# 4. PART A (continued) -- SOLUTION QUALITY VS SIZE
# ======================================================================
rule("PART A -- QAOA QUALITY VS PROBLEM SIZE (p = %d)" % QAOA_P)
sub = df[df["qaoa_expected"].notna()]
print(sub[["instance", "qubits", "feasible_frac", "qaoa_P_feasible",
           "qaoa_approx_ratio", "qaoa_P_opt", "qaoa_gap_pct",
           "qaoa_sec"]].to_string(
    index=False,
    formatters={"feasible_frac": lambda v: f"{v:.4f}",
                "qaoa_P_feasible": lambda v: f"{v:.4f}",
                "qaoa_approx_ratio": lambda v: f"{v:.4f}",
                "qaoa_P_opt": lambda v: f"{v:.6f}",
                "qaoa_gap_pct": lambda v: f"{v:+.2f}%",
                "qaoa_sec": lambda v: f"{v:.1f}s"}))

print("\nfeasibility amplification (how much better than random the state is):")
for _, r in sub.iterrows():
    amp = r["qaoa_P_feasible"] / r["feasible_frac"]
    print(f"  {r['instance']:>12}: random {r['feasible_frac']:.4f} -> "
          f"QAOA {r['qaoa_P_feasible']:.4f}   ({amp:>6.1f}x)")


# ======================================================================
# 5. PART B -- BASELINES
# ======================================================================
rule("PART B -- QAOA VERSUS CLASSICAL BASELINES (gap to the exact optimum)")
show = df[["instance", "qubits", "exact_cost", "greedy_gap_pct", "sa_gap_pct",
           "qaoa_gap_pct", "random_gap_pct"]].copy()
print(show.to_string(index=False, formatters={
    "exact_cost": lambda v: f"Rs {v:,.0f}",
    "greedy_gap_pct": lambda v: f"{v:+.2f}%" if v == v else "n/a",
    "sa_gap_pct": lambda v: f"{v:+.2f}%" if v == v else "n/a",
    "qaoa_gap_pct": lambda v: f"{v:+.2f}%" if v == v else "n/a",
    "random_gap_pct": lambda v: f"{v:+.2f}%" if v == v else "n/a",
}))

rule("PART B -- WALL-CLOCK TIME (seconds)")
print(df[["instance", "qubits", "exact_sec", "greedy_sec", "sa_sec",
          "random_sec", "qaoa_sec"]].to_string(index=False, formatters={
    c: (lambda v: f"{v:.3f}" if v == v else "n/a")
    for c in ["exact_sec", "greedy_sec", "sa_sec", "random_sec", "qaoa_sec"]}))

rule("SUMMARY")
solved = df[df["qaoa_cost"].notna()]
n_qaoa_opt = int((solved["qaoa_gap_pct"].abs() < 1e-6).sum())
n_greedy_opt = int((df["greedy_gap_pct"].abs() < 1e-6).sum())
n_sa_opt = int((df["sa_gap_pct"].abs() < 1e-6).sum())
print(f"instances in the ladder                 : {len(df)}")
print(f"instances QAOA could be simulated on    : {len(solved)} "
      f"(limit {QAOA_QUBIT_LIMIT} qubits)")
print(f"exact optimum reached by QAOA           : {n_qaoa_opt} / {len(solved)}")
print(f"exact optimum reached by greedy         : {n_greedy_opt} / {len(df)}")
print(f"exact optimum reached by annealing      : {n_sa_opt} / {len(df)}")
print(f"slowest exact solve                     : {df['exact_sec'].max():.2f}s")
print(f"slowest QAOA simulation                 : {solved['qaoa_sec'].max():.1f}s")

rule("SAVED")
print("  data/stage5_scaling.csv")
