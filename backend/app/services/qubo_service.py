"""QUBO formulation of the joint location + inventory problem.

WHAT A QUBO IS AND WHY WE NEED ONE
==================================
A QAOA circuit can only minimise an expression of the form

    cost(z) = z^T Q z + offset,        z_k in {0, 1}

a quadratic polynomial in binary variables with no hard constraints. Our model
(see data_service for the full statement) has inequality constraints, so they
have to be folded into the objective as penalties.

BINARY DECISION VARIABLES
-------------------------
    x_i       one per candidate store        -> "open store i"
    s_{i,a}   one per service-feasible link  -> "store i serves area a"

    Links that break the delivery promise are never created, so constraint C5
    (delivery / service radius) costs ZERO variables. That is the single largest
    qubit saving in the formulation.

    Inventory is NOT a variable. inv_{i,j} = sum_a s_{i,a} * d_{a,j} follows
    exactly from the assignment. Free integer inventory variables would need a
    binary expansion per store-product pair.

OBJECTIVE TERMS (maximised; the QUBO minimises the negation)
------------------------------------------------------------
    + rev_a   * s_{i,a}     margin earned by serving area a from store i
    - f_i     * x_i         cost of opening store i
    - deliv_{i,a} * s_{i,a} rider cost of that link

CONSTRAINT PENALTY TERMS
------------------------
    C1  single sourcing            sum_i s_{i,a} <= 1
        Penalty: lambda * s_{i,a} * s_{i',a} for every pair of servers of a.
        Serving an area twice would double-count its margin.

    C2  store-inventory coupling   s_{i,a} <= x_i
        Penalty: lambda * s_{i,a} * (1 - x_i)
        This is the term that JOINS the two halves of the problem. Without it
        the model would cheerfully allocate stock to a store it never opened.

    C3  storage capacity           sum_a vol_a * s_{i,a} <= cap_i
        C4  budget                 sum_i f_i * x_i <= B
        See "TWO ENCODINGS" below -- these are the two inequalities, and how
        they are handled decides the qubit count.

    C5  delivery / service radius  structural, via the variable set.

TWO ENCODINGS
=============
"slack"  -- textbook. qiskit-optimization adds an integer slack variable per
            inequality and squares the resulting equality. Correct and fully
            general, but a slack bounded by V needs ceil(log2(V)) qubits: on the
            3x3x3 demo instance that is 48 extra qubits for a 10-variable
            problem, i.e. 58 qubits total. Unusable on a simulator.

"compact" -- default. An inequality over binary variables is violated only by
            certain SUBSETS of those variables. We enumerate the MINIMAL
            violating subsets (minimal: no proper subset already violates) and
            penalise each one directly. A subset of size 2 is already quadratic
            and costs nothing extra; size k >= 3 is reduced to degree 2 with
            k-2 auxiliary qubits via Rosenberg AND gadgets. A constraint that no
            reachable solution can violate produces no terms at all.

            On the demo instance this gives ~11 qubits instead of 58.

            The two encodings describe the SAME feasible set. They differ only
            in how infeasible points are priced, which is a modelling choice,
            not a change of problem.

PENALTY WEIGHT
--------------
A penalty must exceed the largest objective gain obtainable by breaking that
constraint, or cheating becomes profitable and the QUBO's minimum is not a valid
plan. The weight is derived from the instance, not hard-coded. Bigger is not
better: an oversized penalty squeezes the real cost differences into a tiny
fraction of the coefficient range and flattens QAOA's angle landscape.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np
from qiskit_optimization import QuadraticProgram
from qiskit_optimization.converters import QuadraticProgramToQubo

from app.services.data_service import OptimizationInstance

ENCODINGS = ("compact", "slack")


def store_var(store_id: int) -> str:
    return f"x_{store_id}"


def link_var(store_id: int, area: str) -> str:
    # Area names contain spaces; variable names must not.
    return f"s_{store_id}__{area.replace(' ', '_')}"


class QuboBuildError(ValueError):
    """Raised when the instance cannot be encoded as a QUBO."""


@dataclass
class QuboModel:
    """A QUBO plus the bookkeeping needed to decode and audit it."""

    encoding: str
    program: QuadraticProgram      # constrained model (the shared reference)
    qubo: QuadraticProgram         # unconstrained QUBO (what QAOA solves)
    Q: np.ndarray                  # upper-triangular QUBO matrix
    offset: float
    variable_names: list[str]      # QUBO variable order, includes aux/slack
    decision_names: list[str]      # x_i and s_{i,a} only
    store_var_index: dict[int, int]
    link_var_index: dict[tuple[int, str], int]
    penalty: float
    n_qubits: int
    n_auxiliary: int
    violating_subsets: dict[str, list[list[str]]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "encoding": self.encoding,
            "n_qubits": self.n_qubits,
            "n_decision_variables": len(self.decision_names),
            "n_auxiliary_variables": self.n_auxiliary,
            "search_space_size": f"2^{self.n_qubits}",
            "penalty_weight": round(self.penalty, 4),
            "qubo_offset": round(self.offset, 6),
            "constraints_in_reference_model": len(self.program.linear_constraints),
            "violating_subsets": self.violating_subsets,
            "notes": self.notes,
        }


# ===========================================================================
# Penalty weight
# ===========================================================================
def _penalty_weight(instance: OptimizationInstance) -> float:
    """Strictly larger than any gain available from violating a constraint."""
    max_revenue = max((a.revenue for a in instance.areas), default=0.0)
    max_open = max((s.opening_cost for s in instance.stores), default=0.0)
    max_deliv = max(instance.delivery_cost.values(), default=0.0)
    return 2.0 * (max_revenue + max_open + max_deliv) + 1.0


# ===========================================================================
# The constrained reference model
# ===========================================================================
def build_quadratic_program(instance: OptimizationInstance) -> QuadraticProgram:
    """The model with C1-C4 as explicit constraints.

    This is the shared reference: the PuLP baseline builds the identical
    mathematics independently, and the "slack" encoding converts this directly.
    """
    qp = QuadraticProgram("joint_darkstore_location_inventory")

    for s in instance.stores:
        qp.binary_var(store_var(s.id))
    for store_id, area in sorted(instance.links):
        qp.binary_var(link_var(store_id, area))

    linear: dict[str, float] = {store_var(s.id): -s.opening_cost for s in instance.stores}
    for (store_id, area_name), cost in instance.delivery_cost.items():
        linear[link_var(store_id, area_name)] = instance.area(area_name).revenue - cost
    qp.maximize(linear=linear)

    # C1 single sourcing
    for area in instance.areas:
        servers = instance.servers_of(area.name)
        if servers:
            qp.linear_constraint(
                linear={link_var(i, area.name): 1 for i in servers},
                sense="<=",
                rhs=1,
                name=f"c1_single_source__{area.name.replace(' ', '_')}",
            )

    # C2 coupling
    for store_id, area_name in sorted(instance.links):
        qp.linear_constraint(
            linear={link_var(store_id, area_name): 1, store_var(store_id): -1},
            sense="<=",
            rhs=0,
            name=f"c2_coupling__{store_id}__{area_name.replace(' ', '_')}",
        )

    # C3 capacity (integerised coefficients -- see OptimizationInstance)
    vol_int, cap_int = instance.area_volume_int, instance.store_capacity_int
    for s in instance.stores:
        served = instance.served_by(s.id)
        if served:
            lin = {link_var(s.id, a): vol_int[a] for a in served}
            lin[store_var(s.id)] = -cap_int[s.id]
            qp.linear_constraint(linear=lin, sense="<=", rhs=0,
                                 name=f"c3_capacity__{s.id}")

    # C4 budget
    cost_int = instance.store_cost_int
    qp.linear_constraint(
        linear={store_var(s.id): cost_int[s.id] for s in instance.stores},
        sense="<=",
        rhs=instance.budget_int,
        name="c4_budget",
    )
    return qp


# ===========================================================================
# Minimal violating subsets
# ===========================================================================
def _minimal_violating_subsets(
    items: list, weight: dict, limit: float, max_size: int = 6
) -> list[tuple]:
    """Smallest subsets of `items` whose total weight exceeds `limit`.

    "Minimal" means no proper subset already exceeds the limit, so no redundant
    penalty is ever written. If no subset violates, the constraint can never be
    broken and the result is empty -- the constraint costs nothing.
    """
    minimal: list[tuple] = []
    for size in range(1, min(len(items), max_size) + 1):
        for combo in itertools.combinations(items, size):
            if sum(weight[c] for c in combo) <= limit:
                continue
            if any(set(m) <= set(combo) for m in minimal):
                continue
            minimal.append(tuple(combo))
    return minimal


# ===========================================================================
# Compact encoding
# ===========================================================================
class _QuboBuilder:
    """Accumulates QUBO terms over a growing variable list."""

    def __init__(self, names: list[str], penalty: float):
        self.names = list(names)
        self.index = {n: i for i, n in enumerate(self.names)}
        self.terms: dict[tuple[int, int], float] = {}
        self.offset = 0.0
        self.penalty = penalty
        self.and_cache: dict[frozenset, str] = {}
        self.n_aux = 0

    def new_var(self, name: str) -> str:
        self.index[name] = len(self.names)
        self.names.append(name)
        self.n_aux += 1
        return name

    def lin(self, name: str, coeff: float) -> None:
        i = self.index[name]
        self.terms[(i, i)] = self.terms.get((i, i), 0.0) + coeff

    def quad(self, a: str, b: str, coeff: float) -> None:
        i, j = sorted((self.index[a], self.index[b]))
        if i == j:  # x^2 == x for a binary variable
            self.terms[(i, i)] = self.terms.get((i, i), 0.0) + coeff
        else:
            self.terms[(i, j)] = self.terms.get((i, j), 0.0) + coeff

    def make_and(self, a: str, b: str) -> str:
        """Add an auxiliary w forced to equal a AND b (Rosenberg reduction).

        The penalty  lambda * (3w + ab - 2wa - 2wb)  is zero exactly when
        w == a AND b and strictly positive otherwise, so a minimiser sets w
        correctly on its own without a separate constraint.
        """
        key = frozenset((a, b))
        if key in self.and_cache:
            return self.and_cache[key]
        w = self.new_var(f"w__{a}__AND__{b}")
        lam = self.penalty
        self.lin(w, 3.0 * lam)
        self.quad(a, b, lam)
        self.quad(w, a, -2.0 * lam)
        self.quad(w, b, -2.0 * lam)
        self.and_cache[key] = w
        return w

    def penalise_product(self, variables: list[str], weight: float) -> None:
        """Penalise the conjunction of `variables` by `weight`.

        Degree 1 and 2 are written directly. Degree k >= 3 is chained down with
        k-2 AND gadgets.
        """
        if not variables:
            return
        if len(variables) == 1:
            self.lin(variables[0], weight)
            return
        if len(variables) == 2:
            self.quad(variables[0], variables[1], weight)
            return
        acc = variables[0]
        for v in variables[1:-1]:
            acc = self.make_and(acc, v)
        self.quad(acc, variables[-1], weight)

    def matrix(self) -> np.ndarray:
        n = len(self.names)
        Q = np.zeros((n, n))
        for (i, j), c in self.terms.items():
            Q[i, j] += c
        return Q


def _build_compact(instance: OptimizationInstance, penalty: float) -> tuple:
    """Build the slack-free QUBO. Returns (builder, violating_subsets)."""
    names = [store_var(s.id) for s in instance.stores] + [
        link_var(i, a) for (i, a) in sorted(instance.links)
    ]
    b = _QuboBuilder(names, penalty)

    # ---- objective, negated because a QUBO minimises -------------------
    for s in instance.stores:
        b.lin(store_var(s.id), s.opening_cost)
    for (store_id, area_name), cost in instance.delivery_cost.items():
        rev = instance.area(area_name).revenue
        b.lin(link_var(store_id, area_name), -(rev - cost))

    violating: dict[str, list[list[str]]] = {}

    # ---- C1 single sourcing -------------------------------------------
    for area in instance.areas:
        servers = instance.servers_of(area.name)
        for i1, i2 in itertools.combinations(sorted(servers), 2):
            b.quad(link_var(i1, area.name), link_var(i2, area.name), penalty)

    # ---- C2 coupling: penalty * s * (1 - x) ---------------------------
    for store_id, area_name in sorted(instance.links):
        sv, xv = link_var(store_id, area_name), store_var(store_id)
        b.lin(sv, penalty)
        b.quad(sv, xv, -penalty)

    # ---- C3 capacity via minimal violating subsets --------------------
    vol_int, cap_int = instance.area_volume_int, instance.store_capacity_int
    for s in instance.stores:
        served = instance.served_by(s.id)
        if not served:
            continue
        subsets = _minimal_violating_subsets(
            sorted(served), vol_int, cap_int[s.id]
        )
        if subsets:
            violating[f"c3_capacity__{s.id}"] = [list(t) for t in subsets]
        for sub in subsets:
            # A flat weight is enough: `penalty` already exceeds the largest
            # objective gain any solution could obtain by overfilling a store.
            # Scaling it by the overflow volume would only widen the coefficient
            # range and flatten QAOA's angle landscape for no benefit.
            b.penalise_product([link_var(s.id, a) for a in sub], penalty)

    # ---- C4 budget via minimal violating subsets ----------------------
    cost_int = instance.store_cost_int
    budget_subsets = _minimal_violating_subsets(
        instance.store_ids, cost_int, instance.budget_int, max_size=len(instance.stores)
    )
    if budget_subsets:
        violating["c4_budget"] = [
            [instance.store(i).name for i in t] for t in budget_subsets
        ]
    for sub in budget_subsets:
        b.penalise_product([store_var(i) for i in sub], penalty)

    return b, violating


def _compact_to_program(b: _QuboBuilder, Q: np.ndarray) -> QuadraticProgram:
    """Wrap a bare QUBO matrix as an unconstrained QuadraticProgram for Qiskit."""
    qp = QuadraticProgram("joint_darkstore_qubo_compact")
    for n in b.names:
        qp.binary_var(n)
    linear = {b.names[i]: Q[i, i] for i in range(len(b.names)) if Q[i, i] != 0}
    quadratic = {
        (b.names[i], b.names[j]): Q[i, j]
        for i in range(len(b.names))
        for j in range(i + 1, len(b.names))
        if Q[i, j] != 0
    }
    qp.minimize(constant=b.offset, linear=linear, quadratic=quadratic)
    return qp


# ===========================================================================
# Public entry point
# ===========================================================================
def build_qubo(
    instance: OptimizationInstance, encoding: str = "compact"
) -> QuboModel:
    if encoding not in ENCODINGS:
        raise QuboBuildError(f"encoding must be one of {ENCODINGS}, got {encoding!r}")

    reference = build_quadratic_program(instance)
    penalty = _penalty_weight(instance)
    decision = [v.name for v in reference.variables]

    if encoding == "slack":
        qubo = QuadraticProgramToQubo(penalty=penalty).convert(reference)
        names = [v.name for v in qubo.variables]
        n = len(names)
        Q = np.zeros((n, n))
        obj = qubo.objective
        for k, c in obj.linear.to_dict().items():
            Q[k, k] += c
        for (k, m), c in obj.quadratic.to_dict().items():
            i, j = (k, m) if k <= m else (m, k)
            Q[i, j] += c
        offset = float(obj.constant)
        n_aux = n - len(decision)
        violating: dict[str, list[list[str]]] = {}
        notes = [
            f"{n_aux} integer slack qubits were added to convert inequality "
            f"constraints into equalities. Slack cost dominates the register.",
            "Slack variables carry no business meaning and are ignored when "
            "decoding a solution.",
        ]
    else:
        b, violating = _build_compact(instance, penalty)
        Q = b.matrix()
        names = b.names
        offset = b.offset
        n_aux = b.n_aux
        qubo = _compact_to_program(b, Q)
        notes = [
            "Inequalities are encoded as penalties on their minimal violating "
            "subsets, so no slack variables are needed.",
            f"{n_aux} auxiliary qubits were added by AND gadgets to reduce "
            f"degree-3-or-higher penalty terms to degree 2.",
            "A constraint that no reachable solution can violate contributes "
            "no terms at all.",
        ]

    notes.append(
        "The delivery/service constraint is enforced structurally by omitting "
        "infeasible store-area links, so it consumes no qubits."
    )
    notes.append(
        "objective_value is reported in the original MAXIMISATION sense; the "
        "QUBO itself minimises the negation."
    )

    index = {n: i for i, n in enumerate(names)}
    return QuboModel(
        encoding=encoding,
        program=reference,
        qubo=qubo,
        Q=Q,
        offset=offset,
        variable_names=names,
        decision_names=decision,
        store_var_index={s.id: index[store_var(s.id)] for s in instance.stores},
        link_var_index={(i, a): index[link_var(i, a)] for (i, a) in instance.links},
        penalty=penalty,
        n_qubits=len(names),
        n_auxiliary=n_aux,
        violating_subsets=violating,
        notes=notes,
    )


# ===========================================================================
# Evaluation and decoding
# ===========================================================================
def qubo_cost(model: QuboModel, bits: np.ndarray) -> float:
    """z^T Q z + offset, in minimisation sense."""
    z = np.asarray(bits, dtype=float)
    return float(z @ model.Q @ z) + model.offset


def decode_bits(
    model: QuboModel, bits: np.ndarray
) -> tuple[list[int], dict[str, int | None]]:
    """(selected store ids, area -> serving store id or None).

    Auxiliary and slack bits are discarded. If a bitstring assigns an area to
    more than one store, the extra assignments are dropped HERE but reported by
    the validator -- the violation is never silently repaired.
    """
    selected = sorted(
        sid for sid, idx in model.store_var_index.items() if round(bits[idx]) == 1
    )
    assignment: dict[str, int | None] = {}
    for (store_id, area), idx in sorted(model.link_var_index.items()):
        if round(bits[idx]) == 1:
            assignment.setdefault(area, store_id)
    for (_, area) in model.link_var_index:
        assignment.setdefault(area, None)
    return selected, assignment


def raw_link_flags(model: QuboModel, bits: np.ndarray) -> dict[tuple[int, str], int]:
    """Every link bit exactly as measured, with no repair applied."""
    return {key: int(round(bits[idx])) for key, idx in model.link_var_index.items()}
