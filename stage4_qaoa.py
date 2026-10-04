"""
Stage 4 -- QAOA, simulated by hand with NumPy.

Project: QAOA for Joint Dark Store Location Selection and Inventory Allocation
         in Hyperlocal Quick Commerce.

This is the first file with quantum mechanics in it. There is no Qiskit and no
quantum SDK: the state is a plain complex NumPy array of 2^14 = 16,384
amplitudes, and every gate is written out. SciPy is used only for the CLASSICAL
optimiser that tunes the angles -- nothing quantum is delegated to it.

The whole algorithm:

    |psi> = U_B(beta_p) U_C(gamma_p) ... U_B(beta_1) U_C(gamma_1) |+>^n

    U_C(gamma) = exp(-i gamma C)      C is diagonal -> elementwise multiply
    U_B(beta)  = exp(-i beta sum_j X_j) -> an Rx(2 beta) on each qubit

Then measure, decode the bitstring into a business decision, and keep the best
feasible one seen.

Run:  python stage4_qaoa.py
"""

import itertools

import numpy as np
import pandas as pd
from scipy.optimize import minimize

pd.set_option("display.width", 140)
pd.set_option("display.max_columns", 60)
pd.set_option("display.float_format", lambda v: f"{v:,.4f}")


def rule(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


# ======================================================================
# 0. LOAD THE STAGE 3 HAMILTONIAN AND THE STAGE 1 DATA
# ======================================================================
qubo = np.load("data/qubo.npz", allow_pickle=True)
Q      = qubo["Q"]
offset = float(qubo["offset"])
NAMES  = [str(n) for n in qubo["names"]]
N      = len(NAMES)
DIM    = 2 ** N

stores = pd.read_csv("data/stores.csv")
areas  = pd.read_csv("data/areas.csv")
demand = pd.read_csv("data/demand.csv")
links  = pd.read_csv("data/store_area_links.csv")

STORE_IDS = stores["store_id"].tolist()
AREA_IDS  = areas["area_id"].tolist()
pairs = links[links["within_sla"]].reset_index(drop=True)
PAIR_LIST = list(zip(pairs["store_id"], pairs["area_id"]))

capacity = dict(zip(stores["store_id"], stores["capacity_units"]))
vol      = demand.groupby("area_id")["demand_volume"].sum().to_dict()

# The exact cost of every basis state, in rupees. This is the DIAGONAL of the
# cost Hamiltonian -- and because it is diagonal, we never build a matrix.
X = np.array(list(itertools.product([0, 1], repeat=N)), dtype=np.int64)
C_rupees = np.einsum("ij,ij->i", X @ Q, X) + offset

C_MIN  = C_rupees.min()
C_MEAN = C_rupees.mean()
OPT_INDEX = int(C_rupees.argmin())

rule("STEP 0 -- THE COST HAMILTONIAN")
print(f"qubits                       : {N}")
print(f"basis states (Hilbert dim)   : {DIM:,}")
print(f"cheapest state (the target)  : Rs {C_MIN:,.2f}")
print(f"mean over all states         : Rs {C_MEAN:,.2f}   <- blind guessing")
print(f"most expensive state         : Rs {C_rupees.max():,.2f}")
print(f"optimal bitstring            : "
      f"{''.join(map(str, X[OPT_INDEX]))}  (index {OPT_INDEX})")
print(f"probability of hitting it by luck : 1/{DIM:,} = {1 / DIM:.2e}")


# ======================================================================
# 1. RESCALE THE HAMILTONIAN  (this is not cosmetic -- it decides whether
#    QAOA works at all)
#
# U_C = exp(-i gamma C). If C is measured in rupees, a gamma of even 0.001
# spins the phase of a Rs 250,000 state through 250 radians -- about 40 full
# turns. The angle landscape becomes a blur of oscillations that no optimiser
# can climb. So we standardise C:
#
#     C_scaled = (C - mean) / std
#
# Subtracting the mean only adds a GLOBAL PHASE, which is physically
# undetectable. Dividing by the standard deviation is exactly the same as
# rescaling gamma. So this changes nothing about the problem -- it only puts
# the useful gamma values in a range like [-pi, pi] instead of [-1e-5, 1e-5].
# ======================================================================
C_SCALE = C_rupees.std()
C_scaled = (C_rupees - C_MEAN) / C_SCALE

print(f"\nrescaling: C_scaled = (C - {C_MEAN:,.0f}) / {C_SCALE:,.0f}")
print(f"C_scaled range               : "
      f"[{C_scaled.min():.3f}, {C_scaled.max():.3f}]")


# ======================================================================
# 2. THE QUANTUM SIMULATOR  (three functions, that is the whole thing)
# ======================================================================
PLUS_STATE = np.full(DIM, 1.0 / np.sqrt(DIM), dtype=np.complex128)


def apply_cost_layer(psi, gamma):
    """U_C(gamma) = exp(-i gamma C).

    C is diagonal, so exp(-i gamma C) is diagonal too: every amplitude just
    picks up its own phase. No matrix, no matrix product -- one multiply.
    """
    return psi * np.exp(-1j * gamma * C_scaled)


def apply_mixer_layer(psi, beta):
    """U_B(beta) = exp(-i beta sum_j X_j) = an Rx(2 beta) on every qubit.

    The X operators on different qubits commute, so the sum in the exponent
    factorises into one independent single-qubit rotation per qubit.

        Rx(2 beta) = cos(beta) I  -  i sin(beta) X

    which sends  (a0, a1) -> (cos b * a0 - i sin b * a1,
                              cos b * a1 - i sin b * a0).
    """
    c = np.cos(beta)
    s = -1j * np.sin(beta)
    psi = psi.copy()
    for j in range(N):
        # View the flat state as (everything above qubit j, qubit j, everything
        # below). Then axis 1 IS qubit j, and we mix its two slices.
        view = psi.reshape(2 ** j, 2, 2 ** (N - j - 1))
        a0 = view[:, 0, :].copy()
        a1 = view[:, 1, :].copy()
        view[:, 0, :] = c * a0 + s * a1
        view[:, 1, :] = c * a1 + s * a0
        psi = view.reshape(-1)
    return psi


def qaoa_state(params):
    """Build |gamma, beta> for p layers. params = [g1..gp, b1..bp]."""
    p = len(params) // 2
    gammas, betas = params[:p], params[p:]
    psi = PLUS_STATE.copy()
    for layer in range(p):
        psi = apply_cost_layer(psi, gammas[layer])
        psi = apply_mixer_layer(psi, betas[layer])
    return psi


def expected_cost(params):
    """<psi| C |psi> in rupees. This is what the classical optimiser minimises."""
    probs = np.abs(qaoa_state(params)) ** 2
    return float(probs @ C_rupees)


# ======================================================================
# 3. DECODING -- turn a measured bitstring back into a business decision
#    The auxiliary qubit w is scratch space; it is ignored when reading off
#    the answer. Only y and x carry meaning.
# ======================================================================
N_Y = len(STORE_IDS)


def decode(bits):
    """Return (open_stores, assignment, feasible)."""
    y = {s: int(bits[i]) for i, s in enumerate(STORE_IDS)}
    x = {p: int(bits[N_Y + i]) for i, p in enumerate(PAIR_LIST)}

    open_stores = [s for s in STORE_IDS if y[s]]
    assignment = {}
    feasible = True

    for a in AREA_IDS:
        chosen = [s for (s, aa) in PAIR_LIST if aa == a and x[(s, a)]]
        if len(chosen) > 1:
            feasible = False                       # C1: double booked
        assignment[a] = chosen[0] if chosen else None

    load = {s: 0.0 for s in STORE_IDS}
    for (s, a) in PAIR_LIST:
        if x[(s, a)]:
            if not y[s]:
                feasible = False                   # C2: closed store shipping
            load[s] += vol[a]
    for s in STORE_IDS:
        if load[s] > capacity[s]:
            feasible = False                       # C3: over capacity

    return open_stores, assignment, feasible


FEASIBLE_MASK = np.array([decode(row)[2] for row in X])
OPT_COST = C_MIN


# ======================================================================
# 4. p = 1 LANDSCAPE SCAN
#    Before trusting any optimiser, look at the surface it is climbing.
#    With one layer there are only two angles, so the whole landscape fits
#    in a grid we can compute exhaustively.
# ======================================================================
rule("STEP 4 -- THE p=1 ANGLE LANDSCAPE (scanned exhaustively)")
g_grid = np.linspace(-np.pi, np.pi, 61)
b_grid = np.linspace(0.0, np.pi, 31)
surface = np.empty((len(g_grid), len(b_grid)))
for i, g in enumerate(g_grid):
    for j, b in enumerate(b_grid):
        surface[i, j] = expected_cost([g, b])

gi, bj = np.unravel_index(surface.argmin(), surface.shape)
print(f"grid points evaluated  : {surface.size:,}")
print(f"best grid point        : gamma = {g_grid[gi]:+.4f}, beta = {b_grid[bj]:.4f}")
print(f"expected cost there    : Rs {surface.min():,.2f}")
print(f"blind guessing         : Rs {C_MEAN:,.2f}")
print(f"worst grid point       : Rs {surface.max():,.2f}")
print(f"=> one layer already beats guessing by Rs "
      f"{C_MEAN - surface.min():,.2f}")

pd.DataFrame(surface, index=np.round(g_grid, 4),
             columns=np.round(b_grid, 4)).to_csv("data/stage4_landscape_p1.csv")


# ======================================================================
# 5. OPTIMISE THE ANGLES FOR p = 1 .. P_MAX
#
#    WHY RANDOM NUMBERS APPEAR HERE (the first time in this project):
#    the angle landscape above is not convex -- it has many local minima. A
#    local optimiser started from one point finds whichever valley it happens
#    to be standing in. The standard remedy is several random restarts and
#    keeping the best. The generator is SEEDED, so the run is reproducible.
# ======================================================================
rng = np.random.default_rng(7)
P_MAX = 6
RESTARTS = 8
MAXITER = 500      # COBYLA converges well before this for 2p <= 12 parameters

results = []
best_params_by_p = {}

for p in range(1, P_MAX + 1):
    best = None
    for r in range(RESTARTS):
        if p == 1 and r == 0:
            start = np.array([g_grid[gi], b_grid[bj]])      # seed from the scan
        elif p > 1 and r == 0:
            # Warm start: reuse the previous depth's angles and add a small
            # layer. Interpolation like this is standard practice and usually
            # beats starting from scratch.
            prev = best_params_by_p[p - 1]
            q = p - 1
            start = np.concatenate([prev[:q], [0.01], prev[q:], [0.01]])
        else:
            start = np.concatenate([rng.uniform(-np.pi, np.pi, p),
                                    rng.uniform(0.0, np.pi, p)])

        res = minimize(expected_cost, start, method="COBYLA",
                       options={"maxiter": MAXITER, "rhobeg": 0.3})
        if best is None or res.fun < best.fun:
            best = res

    best_params_by_p[p] = best.x
    probs = np.abs(qaoa_state(best.x)) ** 2

    p_opt = float(probs[OPT_INDEX])
    p_feas = float(probs[FEASIBLE_MASK].sum())
    # Approximation ratio measured against blind guessing, which is the honest
    # baseline for a minimisation problem with a large positive offset.
    approx = (C_MEAN - best.fun) / (C_MEAN - C_MIN)

    results.append({
        "p": p,
        "expected_cost": best.fun,
        "approx_ratio": approx,
        "P(optimum)": p_opt,
        "P(feasible)": p_feas,
        "vs_random": p_opt * DIM,
    })
    print(f"  p={p}  <C> = Rs {best.fun:>12,.2f}   ratio {approx:.4f}   "
          f"P(opt) {p_opt:.5f}   P(feas) {p_feas:.4f}   "
          f"{p_opt * DIM:>7,.1f}x random")

table = pd.DataFrame(results)

rule("STEP 5 -- RESULTS BY CIRCUIT DEPTH")
print(table.to_string(index=False))
table.to_csv("data/stage4_results.csv", index=False)


# ======================================================================
# 6. HOW YOU WOULD ACTUALLY USE IT
#    Nobody reads out a full probability distribution from real hardware. You
#    take a few hundred shots, decode each one, throw away the infeasible ones
#    and keep the cheapest survivor. Compare that against spending the same
#    number of shots on uniform random guessing.
# ======================================================================
SHOTS = 500
rule(f"STEP 6 -- SAMPLING {SHOTS} SHOTS (the realistic workflow)")

best_p = int(table.loc[table["expected_cost"].idxmin(), "p"])
probs = np.abs(qaoa_state(best_params_by_p[best_p])) ** 2
probs = probs / probs.sum()

sample_rng = np.random.default_rng(20260909)
qaoa_shots = sample_rng.choice(DIM, size=SHOTS, p=probs)
rand_shots = sample_rng.integers(0, DIM, size=SHOTS)


def best_feasible(indices):
    ok = [i for i in indices if FEASIBLE_MASK[i]]
    if not ok:
        return None, 0
    costs = C_rupees[ok]
    return ok[int(costs.argmin())], len(ok)


q_best, q_ok = best_feasible(qaoa_shots)
r_best, r_ok = best_feasible(rand_shots)

print(f"using the p={best_p} circuit\n")
print(f"{'':22} {'QAOA':>16} {'random guessing':>18}")
print(f"{'feasible shots':22} {q_ok:>16,} {r_ok:>18,}")
print(f"{'best cost found':22} "
      f"{('Rs %s' % f'{C_rupees[q_best]:,.2f}') if q_best is not None else 'none':>16} "
      f"{('Rs %s' % f'{C_rupees[r_best]:,.2f}') if r_best is not None else 'none':>18}")
print(f"{'true optimum':22} {'Rs %s' % f'{OPT_COST:,.2f}':>16}")
print(f"{'optimum found?':22} "
      f"{str(q_best == OPT_INDEX):>16} {str(r_best == OPT_INDEX):>18}")

rule("STEP 7 -- THE DECISION QAOA RETURNS")
open_stores, assignment, feasible = decode(X[q_best])
print(f"bitstring : {''.join(map(str, X[q_best]))}")
print(f"feasible  : {feasible}")
print(f"cost      : Rs {C_rupees[q_best]:,.2f}"
      f"   (optimum Rs {OPT_COST:,.2f})")
print(f"\nopen these dark stores : {open_stores}")
print("serve areas as follows :")
for a in AREA_IDS:
    print(f"  {a} -> {assignment[a] if assignment[a] else 'UNSERVED'}")

print("\ninventory to allocate (units/day):")
alloc = []
for a, s in assignment.items():
    if s is None:
        continue
    for _, d in demand[demand["area_id"] == a].iterrows():
        alloc.append({"store_id": s, "product_id": d["product_id"],
                      "units": d["demand_units"]})
alloc_df = (pd.DataFrame(alloc).groupby(["store_id", "product_id"])["units"]
            .sum().reset_index())
print(alloc_df.pivot(index="store_id", columns="product_id", values="units"))
alloc_df.to_csv("data/stage4_solution.csv", index=False)

rule("SAVED")
for f in ["data/stage4_landscape_p1.csv", "data/stage4_results.csv",
          "data/stage4_solution.csv"]:
    print(f"  {f}")
