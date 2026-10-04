"""QAOA solver, built directly on Qiskit primitives.

Flow:  instance -> QUBO -> Ising -> QAOAAnsatz -> StatevectorSampler
       -> classical angle optimisation -> measure -> decode -> validate

WHAT QAOA ACTUALLY DOES
=======================
QAOA prepares a state whose measurement distribution is BIASED towards low-cost
bitstrings, then samples it:

    |psi(gamma, beta)> = U_B(beta_p) U_C(gamma_p) ... U_B(beta_1) U_C(gamma_1) |+>^n

    U_C(gamma) = exp(-i gamma H_C)    phase separator, built from the QUBO
    U_B(beta)  = exp(-i beta sum X)   mixer

A classical optimiser tunes the 2p angles to lower the expected cost, then the
final state is measured.

IT DOES NOT ENUMERATE ANYTHING. QAOA never checks every possible solution and
carries no optimality guarantee. It returns samples from a biased distribution:
often good, sometimes not, and possibly INFEASIBLE, because a QUBO can only
penalise a constraint violation, never forbid it. Every candidate is therefore
passed through the independent validator, and the API always reports whether the
returned plan was feasible.

WHY THIS DOES NOT USE qiskit_algorithms.QAOA
============================================
It was measured first. With qiskit-algorithms 0.4.0 on Qiskit 2.5,
QAOA.compute_minimum_eigenvalue scales pathologically in the qubit count:

    n= 3  0.18s      n= 9  12.26s
    n= 5  0.20s      n=11  did not finish in 200s
    n= 7  0.55s

roughly 20x per two qubits, where statevector growth predicts 4x. Qiskit's own
components are not the problem -- QAOAAnsatz builds in 0.000s and a single
StatevectorSampler call takes 0.064s at 11 qubits. So the high-level wrapper is
replaced by an explicit loop over those same Qiskit primitives. Same algorithm,
same library, ~50 lines we can log and time.

HAMILTONIAN NORMALISATION
=========================
U_C = exp(-i gamma H_C). Our raw coefficients reach |c| ~ 91,500, so a gamma of
even 1e-3 spins phases through ~90 radians -- about 14 full turns. Neighbouring
costs wrap different numbers of times, the angle landscape becomes noise at any
step size the optimiser can take, and nothing can be tuned.

We therefore divide the cost operator by its largest coefficient:

    H_scaled = H_C / max|c|

This is SAFE and ORDER-PRESERVING. Dividing by a positive constant is a
monotone transformation, so the ranking of every solution is unchanged and the
argmin is identical; it is exactly equivalent to reparametrising gamma. The
identity term is dropped as well, since it only contributes a global phase,
which is unobservable.

All reported costs and objective values are computed from the ORIGINAL,
unscaled QUBO, so the rupee figures in the API are real.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
from qiskit.circuit.library import QAOAAnsatz
from qiskit.primitives import StatevectorSampler
from qiskit.quantum_info import SparsePauliOp
from qiskit_optimization.translators import to_ising
from scipy.optimize import minimize

from app.config import settings
from app.services.data_service import OptimizationInstance
from app.services.qubo_service import (
    QuboModel,
    build_qubo,
    decode_bits,
    qubo_cost,
    raw_link_flags,
)
from app.services.validation_service import SolutionMetrics, evaluate_solution

SOLVER_NAME = "qaoa_qiskit_simulator"


class QaoaTooLargeError(ValueError):
    """Raised when the QUBO needs more qubits than the simulator budget allows."""


@dataclass
class _Trace:
    """Per-iteration record, so a slow or stuck run is visible, not mysterious."""

    iterations: int = 0
    circuit_calls: int = 0
    best_expectation: float = float("inf")
    history: list[dict] = field(default_factory=list)
    started: float = field(default_factory=time.perf_counter)


def _normalised_cost_operator(op: SparsePauliOp) -> tuple[SparsePauliOp, float]:
    """Drop the identity term and divide by the largest coefficient.

    Returns (scaled_operator, scale). Order-preserving: see module docstring.
    """
    labels = [str(p) for p in op.paulis]
    coeffs = np.real(op.coeffs)

    keep = [(lbl, c) for lbl, c in zip(labels, coeffs) if set(lbl) != {"I"}]
    if not keep:
        raise ValueError("cost operator has no non-identity terms")

    scale = max(abs(c) for _, c in keep)
    if scale == 0:
        raise ValueError("cost operator coefficients are all zero")

    scaled = SparsePauliOp.from_list([(lbl, float(c) / scale) for lbl, c in keep])
    return scaled, float(scale)


def _bits_from_qiskit_string(bitstring: str, n_qubits: int) -> np.ndarray:
    """Convert a Qiskit measurement string to variable-indexed bits.

    Qiskit prints bitstrings little-endian: the RIGHTMOST character is qubit 0.
    QAOAAnsatz qubit i corresponds to QUBO variable i, so variable i is read
    from position (n - 1 - i). Getting this backwards silently decodes a
    different solution, so it is done in exactly one place.
    """
    s = bitstring.replace(" ", "").zfill(n_qubits)
    return np.array([int(s[n_qubits - 1 - i]) for i in range(n_qubits)], dtype=float)


def solve_qaoa(
    instance: OptimizationInstance,
    reps: int | None = None,
    maxiter: int | None = None,
    shots: int | None = None,
    seed: int = 42,
    encoding: str = "compact",
    max_qubits: int | None = None,
    final_shots_multiplier: int = 4,
    verbose: bool = False,
) -> tuple[SolutionMetrics, dict]:
    """Run QAOA on a simulator. Returns (metrics, solver_details).

    The reported solution is the best FEASIBLE bitstring observed in the final
    measurement, which is how QAOA is used in practice: take shots, decode them,
    discard the invalid ones, keep the best survivor. If nothing feasible was
    sampled, the lowest-cost sample is reported and the validation block says
    why it cannot be used.
    """
    reps = reps if reps is not None else settings.qaoa_default_reps
    maxiter = maxiter if maxiter is not None else settings.qaoa_default_maxiter
    shots = shots if shots is not None else settings.qaoa_default_shots
    limit = max_qubits if max_qubits is not None else settings.qaoa_max_qubits

    stage_times: dict[str, float] = {}
    t_start = time.perf_counter()

    # ------------------------------------------------------- 1. QUBO
    t = time.perf_counter()
    model: QuboModel = build_qubo(instance, encoding=encoding)
    stage_times["build_qubo"] = time.perf_counter() - t

    if model.n_qubits > limit:
        raise QaoaTooLargeError(
            f"this instance needs {model.n_qubits} qubits with the {encoding!r} "
            f"encoding, above the simulator limit of {limit}. Reduce the instance "
            f"(fewer stores/areas/products), or raise QAOA_MAX_QUBITS if you have "
            f"memory for 2**n amplitudes."
        )

    n = model.n_qubits

    # ------------------------------------------------ 2. Ising + scaling
    t = time.perf_counter()
    op, ising_offset = to_ising(model.qubo)
    scaled_op, scale = _normalised_cost_operator(op)
    stage_times["to_ising_and_normalise"] = time.perf_counter() - t

    # --------------------------------------------------- 3. the circuit
    t = time.perf_counter()
    ansatz = QAOAAnsatz(cost_operator=scaled_op, reps=reps)
    circuit = ansatz.decompose(reps=3)
    circuit.measure_all()
    stage_times["build_circuit"] = time.perf_counter() - t

    sampler = StatevectorSampler(seed=seed, default_shots=shots)
    trace = _Trace()

    # Cost of every bitstring is evaluated against the ORIGINAL QUBO, so the
    # numbers the optimiser minimises are real rupees, not scaled units.
    cost_cache: dict[str, float] = {}

    def true_cost(bitstring: str) -> float:
        cached = cost_cache.get(bitstring)
        if cached is None:
            cached = qubo_cost(model, _bits_from_qiskit_string(bitstring, n))
            cost_cache[bitstring] = cached
        return cached

    def expectation(params: np.ndarray) -> float:
        """Mean QUBO cost of the sampled distribution at these angles."""
        trace.circuit_calls += 1
        result = sampler.run([(circuit, np.asarray(params, dtype=float))]).result()
        counts = result[0].data.meas.get_counts()
        total = sum(counts.values())
        mean = sum(c * true_cost(b) for b, c in counts.items()) / total

        trace.iterations += 1
        if mean < trace.best_expectation:
            trace.best_expectation = mean
        if verbose or trace.iterations <= 3 or trace.iterations % 25 == 0:
            trace.history.append(
                {
                    "iteration": trace.iterations,
                    "expectation": round(mean, 4),
                    "elapsed_sec": round(time.perf_counter() - trace.started, 3),
                }
            )
        return mean

    # ------------------------------------- 4. classical angle optimisation
    rng = np.random.default_rng(seed)
    x0 = np.concatenate(
        [rng.uniform(0, np.pi, reps), rng.uniform(0, np.pi, reps)]
    )[: ansatz.num_parameters]

    t = time.perf_counter()
    opt = minimize(
        expectation,
        x0,
        method="COBYLA",
        options={"maxiter": max(maxiter, ansatz.num_parameters + 2), "rhobeg": 0.5},
    )
    stage_times["angle_optimisation"] = time.perf_counter() - t

    # ------------------------------------------- 5. final measurement
    t = time.perf_counter()
    final_sampler = StatevectorSampler(
        seed=seed + 1, default_shots=shots * final_shots_multiplier
    )
    final = final_sampler.run([(circuit, np.asarray(opt.x, dtype=float))]).result()
    final_counts = final[0].data.meas.get_counts()
    total_shots = sum(final_counts.values())
    stage_times["final_measurement"] = time.perf_counter() - t

    # ------------------------------------------- 6. decode and validate
    t = time.perf_counter()
    best_feasible: tuple[float, SolutionMetrics, str] | None = None
    best_any: tuple[float, SolutionMetrics, str] | None = None
    feasible_shots = 0

    for bitstring, count in final_counts.items():
        bits = _bits_from_qiskit_string(bitstring, n)
        selected, assignment = decode_bits(model, bits)
        metrics = evaluate_solution(
            instance, selected, assignment, raw_link_flags(model, bits)
        )
        cost = qubo_cost(model, bits)

        if best_any is None or cost < best_any[0]:
            best_any = (cost, metrics, bitstring)

        if metrics.feasible:
            feasible_shots += count
            # Rank feasible candidates by the real objective, which is what we
            # report, rather than by the penalised QUBO value.
            if (
                best_feasible is None
                or metrics.objective_value > best_feasible[1].objective_value
            ):
                best_feasible = (cost, metrics, bitstring)

    chosen_cost, chosen_metrics, chosen_bits = best_feasible or best_any
    stage_times["decode_and_validate"] = time.perf_counter() - t

    probability_feasible = feasible_shots / total_shots if total_shots else 0.0
    probability_of_returned = final_counts.get(chosen_bits, 0) / total_shots

    details = {
        "solver": "QAOA (Qiskit QAOAAnsatz + StatevectorSampler, local simulator)",
        "implementation": "explicit loop over Qiskit primitives",
        "encoding": model.encoding,
        "n_qubits": n,
        "n_decision_variables": len(model.decision_names),
        "n_auxiliary_variables": model.n_auxiliary,
        "reps_p": reps,
        "maxiter": maxiter,
        "shots_per_iteration": shots,
        "final_shots": total_shots,
        "seed": seed,
        "penalty_weight": round(model.penalty, 4),
        "hamiltonian_scale_divisor": round(scale, 4),
        "ising_offset": round(float(ising_offset), 4),
        "circuit_depth": circuit.depth(),
        "circuit_operations": len(circuit.data),
        "optimizer": "scipy COBYLA",
        "optimizer_success": bool(opt.success),
        "optimizer_message": str(opt.message),
        "circuit_evaluations": trace.circuit_calls,
        "best_expectation_rupees_minimisation": round(trace.best_expectation, 4),
        "final_angles": [round(float(v), 6) for v in opt.x],
        "distinct_bitstrings_sampled": len(final_counts),
        "feasible_shot_fraction": round(probability_feasible, 6),
        "probability_of_returned_solution": round(probability_of_returned, 6),
        "returned_feasible_sample": best_feasible is not None,
        "qubo_value_of_returned_solution": round(chosen_cost, 6),
        "returned_bitstring": chosen_bits,
        "stage_times_sec": {k: round(v, 4) for k, v in stage_times.items()},
        "iteration_history": trace.history,
        "runtime": time.perf_counter() - t_start,
        "qubo_summary": model.summary(),
        "notes": [
            "QAOA samples a biased probability distribution. It does not "
            "enumerate the search space and gives no optimality guarantee.",
            "The cost operator was divided by its largest coefficient before "
            "building the circuit. That is a monotone rescaling, so it leaves "
            "the ordering of all solutions and the location of the optimum "
            "unchanged; all reported values use the original unscaled QUBO.",
            "Constraints are penalties inside the QUBO, so an infeasible sample "
            "is an expected outcome rather than a bug.",
            "qiskit_algorithms.QAOA is deliberately not used: it was measured "
            "to scale pathologically on this version combination (>200s at 11 "
            "qubits versus 0.064s per sampler call).",
        ],
    }
    if best_feasible is None:
        details["notes"].append(
            "NO feasible bitstring was sampled. Increase reps (p), maxiter, or "
            "shots. The reported plan is the lowest-cost sample and its "
            "validation block lists the violations."
        )

    return chosen_metrics, details


def qubo_only(instance: OptimizationInstance, encoding: str = "compact") -> dict:
    """Build the QUBO and report its structure without running a circuit."""
    model = build_qubo(instance, encoding=encoding)
    return {
        **model.summary(),
        "decision_variables": model.decision_names,
        "all_variables": model.variable_names,
        "within_simulator_limit": model.n_qubits <= settings.qaoa_max_qubits,
        "simulator_limit": settings.qaoa_max_qubits,
    }


def brute_force_qubo(model: QuboModel, max_qubits: int = 22) -> dict | None:
    """Exhaustively minimise the QUBO.

    An internal cross-check for small instances only. Never presented as a QAOA
    result, and never used as an optimality reference unless explicitly labelled.
    """
    if model.n_qubits > max_qubits:
        return None
    import itertools

    X = np.array(list(itertools.product([0, 1], repeat=model.n_qubits)), dtype=float)
    costs = np.einsum("ij,ij->i", X @ model.Q, X) + model.offset
    best = int(costs.argmin())
    return {
        "qubo_minimum": float(costs[best]),
        "objective_value_maximisation": float(-costs[best]),
        "bitstring_variable_order": "".join(str(int(b)) for b in X[best]),
        "states_enumerated": int(len(X)),
    }
