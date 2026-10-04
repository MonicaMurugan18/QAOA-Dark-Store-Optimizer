"""
Stage 7 -- Run the corrected Puducherry dataset through the whole pipeline.

Project: QAOA for Joint Dark Store Location Selection and Inventory Allocation
         in Hyperlocal Quick Commerce.

Stages 1-6 used a hand-built 4x4 Chennai instance. This runs the same machinery
on real Puducherry geography, and produces the actual business answer: which
dark stores to open in Puducherry, and how much of each product to stock.

Two instances, because they need different tools:

  FULL   11 sites x 20 zones. Too large for exact enumeration AND too large to
         encode as a QUBO (see the qubit count printed below). Classical
         heuristics only.

  QAOA   4 sites x 4 zones, carved out of the full instance and re-sized so the
         capacity constraint still binds. 18 qubits, which a laptop can
         simulate.

Run:  python stage7_pondicherry.py
"""

import time

import numpy as np
import pandas as pd

import pondicherry_adapter as pa
import qaoa_pipeline as qp

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 40)

P_LAYERS, RESTARTS, MAXITER, SHOTS, SEED = 3, 3, 200, 500, 42

# Chosen by search over slices of the full instance: the largest non-degenerate
# slice that stays under 20 qubits. Every zone has at least 2 candidate servers,
# so there is a real assignment decision, and at least 2 stores must open.
SUB_STORES = ["DS01", "DS02", "DS03", "DS09"]
SUB_ZONES = ["Z01", "Z03", "Z10", "Z12"]


def rule(t):
    print("\n" + "=" * 84)
    print(t)
    print("=" * 84)


def inventory_table(inst, assignment):
    """Units of each product to stock at each opened store."""
    rows = []
    for a, s in assignment.items():
        if s is None:
            continue
        for _, d in inst["demand"][inst["demand"].area_id == a].iterrows():
            rows.append({"store": s, "product": d["product_id"],
                         "units": d["demand_units"]})
    if not rows:
        return pd.DataFrame()
    return (pd.DataFrame(rows).groupby(["store", "product"])["units"].sum()
            .reset_index().pivot(index="store", columns="product",
                                 values="units").fillna(0).astype(int))


# ======================================================================
# 1. THE FULL INSTANCE
# ======================================================================
rule("STEP 1 -- FULL PUDUCHERRY INSTANCE (11 sites x 20 zones)")
full = pa.load_pondicherry("data_pondicherry", name="pondy-full")

t0 = time.perf_counter()
q_full = qp.build_qubo(full)
build_sec = time.perf_counter() - t0

n_pairs = len(full["pair_list"])
n_aux = q_full["n_qubits"] - len(full["store_ids"]) - n_pairs
print(f"candidate sites            : {len(full['store_ids'])}")
print(f"demand zones               : {len(full['area_ids'])}")
print(f"products                   : {full['products']['product_id'].nunique()}")
print(f"SLA-feasible site-zone pairs: {n_pairs} of "
      f"{len(full['store_ids']) * len(full['area_ids'])}")
print(f"total demand               : {sum(full['vol'].values()):,.0f} L/day")
print(f"total capacity             : {sum(full['capacity'].values()):,.0f} L/day "
      f"({sum(full['capacity'].values()) / sum(full['vol'].values()):.2f}x)")

print(f"\nQUBO size: {len(full['store_ids'])} open + {n_pairs} assignment "
      f"+ {n_aux} auxiliary = {q_full['n_qubits']:,} qubits "
      f"(built in {build_sec:.1f}s)")
print("The auxiliary count is the story here. Every capacity constraint that")
print("involves 3 or more zones has to be reduced to degree 2 with AND gadgets,")
print("and with 11 stores reaching up to 7 zones each there are a lot of them.")
print("This is the real scaling barrier for the encoding, not the 76 pairs.")

assign_options = np.prod([len(full["servers_of"][a]) + 1
                          for a in full["area_ids"]], dtype=float)
print(f"\nExact enumeration would need {2 ** len(full['store_ids']):,} open-sets "
      f"x {assign_options:.3e} assignments.")
print("Not tractable. Simulated annealing is the reference answer at full size.")

rule("STEP 2 -- FULL INSTANCE, CLASSICAL SOLVERS")
t0 = time.perf_counter()
greedy_full = qp.greedy_business_heuristic(full)
greedy_sec = time.perf_counter() - t0

t0 = time.perf_counter()
sa_full = qp.simulated_annealing(q_full, steps=20000, seed=SEED, restarts=5)
sa_sec = time.perf_counter() - t0
# A QUBO cost only means something if the bitstring is actually feasible.
# Penalties make an infeasible state look like a huge number, not an error.
sa_full_ok = bool(qp.feasible_mask(sa_full["bits"][None, :], full, q_full)[0])

print(f"greedy heuristic     : Rs {greedy_full['cost']:>12,.2f}  "
      f"({greedy_sec:.2f}s)   opens {'+'.join(greedy_full['open'])}")
print(f"simulated annealing  : Rs {sa_full['cost']:>12,.2f}  ({sa_sec:.2f}s)   "
      f"{'FEASIBLE' if sa_full_ok else 'INFEASIBLE -- NOT A SOLUTION'}")
if not sa_full_ok:
    print(f"  Annealing cannot cope with {q_full['n_qubits']:,} variables at this "
          f"budget. Almost")
    print("  all of them are auxiliary AND-gadget bits, which have to be set")
    print("  exactly right or the penalty fires. The number above is mostly")
    print("  penalty, so it is not comparable with the greedy cost.")
    print("  At full size, greedy is the only classical method that works.")
elif sa_full["cost"] < greedy_full["cost"]:
    print(f"  -> annealing is better by Rs "
          f"{greedy_full['cost'] - sa_full['cost']:,.2f}")
else:
    print(f"  -> greedy is better by Rs "
          f"{sa_full['cost'] - greedy_full['cost']:,.2f}")

rule("STEP 3 -- THE FULL-SIZE BUSINESS ANSWER (greedy plan)")
print(f"open these dark stores : {greedy_full['open']}")
served = sum(1 for v in greedy_full["assign"].values() if v)
print(f"zones served           : {served} of {len(full['area_ids'])}")
print(f"daily cost             : Rs {greedy_full['cost']:,.2f}")
print("\nzone -> store:")
for a in full["area_ids"]:
    s = greedy_full["assign"].get(a)
    nm = full["areas"].loc[full["areas"].area_id == a, "area_name"].iloc[0]
    print(f"  {a} {nm:<20} -> {s if s else 'UNSERVED'}")

inv_full = inventory_table(full, greedy_full["assign"])
print("\ninventory to stock (units/day):")
print(inv_full.to_string())
inv_full.to_csv("data_pondicherry/solution_full_greedy.csv")


# ======================================================================
# 4. THE QAOA-SIZED SLICE
# ======================================================================
rule("STEP 4 -- QAOA SLICE (4 sites x 4 zones)")
sub = pa.slice_instance(full, SUB_STORES, SUB_ZONES, name="pondy-4x4")
q_sub = qp.build_qubo(sub)
n_sub = q_sub["n_qubits"]

print(f"sites : {SUB_STORES}")
print(f"zones : {SUB_ZONES}")
for a in sub["area_ids"]:
    nm = sub["areas"].loc[sub["areas"].area_id == a, "area_name"].iloc[0]
    print(f"  {a} {nm:<20} can be served by {sub['servers_of'][a]}")
print(f"\ndemand   : {sum(sub['vol'].values()):,.1f} L/day")
print(f"capacity : {sum(sub['capacity'].values()):,.1f} L/day "
      f"({sum(sub['capacity'].values()) / sum(sub['vol'].values()):.2f}x)")
print(f"largest store holds {max(sub['capacity'].values()):,.0f} L -> at least "
      f"{int(np.ceil(sum(sub['vol'].values()) / max(sub['capacity'].values())))}"
      f" stores must open")
print(f"qubits   : {len(SUB_STORES)} + {len(sub['pair_list'])} + "
      f"{n_sub - len(SUB_STORES) - len(sub['pair_list'])} = {n_sub}  "
      f"(2^{n_sub} = {2 ** n_sub:,} states)")

rule("STEP 5 -- SOLVING THE SLICE")
t0 = time.perf_counter()
exact = qp.exact_optimum(sub)
exact_sec = time.perf_counter() - t0
print(f"exact optimum        : Rs {exact['cost']:>11,.2f}  ({exact_sec:.3f}s, "
      f"{exact['evaluations']:,} evaluations)")

t0 = time.perf_counter()
greedy = qp.greedy_business_heuristic(sub)
print(f"greedy heuristic     : Rs {greedy['cost']:>11,.2f}  "
      f"({time.perf_counter() - t0:.3f}s)   "
      f"gap {100 * (greedy['cost'] - exact['cost']) / exact['cost']:+.2f}%")

t0 = time.perf_counter()
sa = qp.simulated_annealing(q_sub, steps=8000, seed=SEED, restarts=5)
print(f"simulated annealing  : Rs {sa['cost']:>11,.2f}  "
      f"({time.perf_counter() - t0:.3f}s)   "
      f"gap {100 * (sa['cost'] - exact['cost']) / exact['cost']:+.2f}%")

print(f"\nrunning QAOA (p={P_LAYERS}, {RESTARTS} restarts) on "
      f"{2 ** n_sub:,} states -- this is the slow part...")
t0 = time.perf_counter()
X = qp.all_bitstrings(n_sub)
res = qp.run_qaoa(q_sub, p=P_LAYERS, restarts=RESTARTS, maxiter=MAXITER,
                  seed=SEED, X=X)
probs = res["probs"] / res["probs"].sum()
C = res["C"]
feas = qp.feasible_mask(X, sub, q_sub)
rng = np.random.default_rng(20260911)
shots = rng.choice(len(probs), size=SHOTS, p=probs)
shot_ok = qp.feasible_mask(X[shots], sub, q_sub)
qaoa_cost = float(C[shots][shot_ok].min()) if shot_ok.any() else np.nan
qaoa_sec = time.perf_counter() - t0

print(f"QAOA                 : Rs {qaoa_cost:>11,.2f}  ({qaoa_sec:.1f}s)   "
      f"gap {100 * (qaoa_cost - exact['cost']) / exact['cost']:+.2f}%")
print(f"\n  expected cost       : Rs {res['expected']:,.2f}")
print(f"  blind guessing      : Rs {C.mean():,.2f}")
print(f"  approximation ratio : "
      f"{(C.mean() - res['expected']) / (C.mean() - C.min()):.4f}")
print(f"  P(feasible)         : {probs[feas].sum():.4f}  "
      f"(random would be {feas.mean():.4f})")
print(f"  P(exact optimum)    : {probs[int(C.argmin())]:.6f}  "
      f"(random would be {1 / len(probs):.2e})")
print(f"  feasible shots      : {int(shot_ok.sum())} of {SHOTS}")


# ======================================================================
# 6. THE ANSWER
# ======================================================================
rule("STEP 6 -- THE PUDUCHERRY DECISION (from the exact optimum)")
print(f"open these dark stores : {list(exact['open'])}")
for s in exact["open"]:
    nm = sub["stores"].loc[sub["stores"].store_id == s, "store_name"].iloc[0]
    load = sum(sub["vol"][a] for a, ss in exact["assign"].items() if ss == s)
    print(f"  {s} {nm:<24} {load:>7,.1f} / {sub['capacity'][s]:,.0f} L "
          f"({100 * load / sub['capacity'][s]:.1f}% full)   "
          f"opening Rs {sub['open_cost'][s]:,.0f}/day")

print("\nserve zones as follows:")
for a in sub["area_ids"]:
    s = exact["assign"][a]
    nm = sub["areas"].loc[sub["areas"].area_id == a, "area_name"].iloc[0]
    if s is None:
        print(f"  {a} {nm:<20} -> UNSERVED")
    else:
        mins = sub["links"].loc[(sub["links"].store_id == s)
                                & (sub["links"].area_id == a),
                                "delivery_min"].iloc[0]
        print(f"  {a} {nm:<20} -> {s}   {mins:.1f} min   "
              f"Rs {sub['deliver'][(s, a)]:,.0f}/day")

inv = inventory_table(sub, exact["assign"])
print("\ninventory to stock each day (units):")
names = dict(zip(sub["products"]["product_id"], sub["products"]["product_name"]))
inv_named = inv.rename(columns=names)
print(inv_named.to_string())
inv.to_csv("data_pondicherry/solution_sub_optimal.csv")

print(f"\ntotal daily cost : Rs {exact['cost']:,.2f}")

rule("SUMMARY")
summary = pd.DataFrame([
    {"instance": "full 11x20", "qubits": q_full["n_qubits"],
     "method": "greedy", "cost": greedy_full["cost"]},
    {"instance": "full 11x20", "qubits": q_full["n_qubits"],
     "method": "annealing" + ("" if sa_full_ok else " (INFEASIBLE)"),
     "cost": sa_full["cost"]},
    {"instance": "slice 4x4", "qubits": n_sub, "method": "exact",
     "cost": exact["cost"]},
    {"instance": "slice 4x4", "qubits": n_sub, "method": "greedy",
     "cost": greedy["cost"]},
    {"instance": "slice 4x4", "qubits": n_sub, "method": "annealing",
     "cost": sa["cost"]},
    {"instance": "slice 4x4", "qubits": n_sub, "method": "QAOA",
     "cost": qaoa_cost},
])
print(summary.to_string(index=False,
                        formatters={"cost": lambda v: f"Rs {v:,.2f}"}))
summary.to_csv("data_pondicherry/stage7_summary.csv", index=False)

rule("SAVED")
for f in ["data_pondicherry/solution_full_greedy.csv",
          "data_pondicherry/solution_sub_optimal.csv",
          "data_pondicherry/stage7_summary.csv"]:
    print(f"  {f}")
