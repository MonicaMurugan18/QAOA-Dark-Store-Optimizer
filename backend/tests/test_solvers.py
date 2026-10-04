"""QUBO generation, the classical solver, QAOA execution and validation."""

import pytest

from app.services.classical_service import solve_classical
from app.services.qaoa_service import brute_force_qubo, solve_qaoa
from app.services.qubo_service import build_qubo, decode_bits
from app.services.validation_service import evaluate_solution
from tests.conftest import KNOWN_OPTIMUM

TOL = 0.5  # rupees


# ======================================================== QUBO generation
def test_qubo_compact_is_small(instance):
    model = build_qubo(instance, encoding="compact")
    assert model.n_qubits == 11, "the dev instance should encode in 11 qubits"
    assert len(model.decision_names) == 10
    assert model.n_auxiliary == 1


def test_qubo_slack_encoding_is_larger(instance):
    """The textbook slack encoding is correct but far more expensive."""
    compact = build_qubo(instance, encoding="compact")
    slack = build_qubo(instance, encoding="slack")
    assert slack.n_qubits > compact.n_qubits
    assert slack.n_auxiliary > compact.n_auxiliary


def test_qubo_has_all_constraints(instance):
    model = build_qubo(instance, encoding="compact")
    names = [c.name for c in model.program.linear_constraints]
    assert any(n.startswith("c1_single_source") for n in names)
    assert any(n.startswith("c2_coupling") for n in names)
    assert any(n.startswith("c3_capacity") for n in names)
    assert "c4_budget" in names


def test_qubo_penalty_exceeds_best_objective_gain(instance):
    """If a penalty were too small, violating a constraint would be profitable."""
    model = build_qubo(instance, encoding="compact")
    max_revenue = max(a.revenue for a in instance.areas)
    assert model.penalty > max_revenue


def test_brute_force_matches_known_optimum(instance):
    model = build_qubo(instance, encoding="compact")
    bf = brute_force_qubo(model)
    assert bf is not None
    assert bf["states_enumerated"] == 2 ** model.n_qubits
    assert abs(bf["objective_value_maximisation"] - KNOWN_OPTIMUM) < TOL


# ======================================================= classical solver
def test_classical_finds_proven_optimum(instance):
    metrics, details = solve_classical(instance, time_limit_sec=30)
    assert details["pulp_status"] == "Optimal"
    assert details["proven_optimal"] is True
    assert metrics.feasible, metrics.violations
    assert abs(metrics.objective_value - KNOWN_OPTIMUM) < TOL


def test_classical_respects_budget(instance):
    metrics, _ = solve_classical(instance, time_limit_sec=30)
    assert metrics.budget_used <= instance.budget + 1e-6


def test_classical_respects_capacity(instance):
    metrics, _ = solve_classical(instance, time_limit_sec=30)
    check = next(c for c in metrics.checks if c["name"] == "C3_storage_capacity")
    assert check["satisfied"]


def test_tight_budget_changes_the_plan(db, dev_ids):
    """A budget that only affords one store must produce a smaller plan."""
    from app.services.data_service import build_instance

    tight = build_instance(db, budget=9500, **dev_ids)
    metrics, details = solve_classical(tight, time_limit_sec=30)
    assert details["pulp_status"] == "Optimal"
    assert metrics.budget_used <= 9500 + 1e-6
    assert len(metrics.selected_stores) <= 1


# ================================================================== QAOA
def test_qaoa_runs_and_is_feasible(instance):
    metrics, details = solve_qaoa(
        instance, reps=3, maxiter=150, shots=2048, seed=42
    )
    assert details["n_qubits"] == 11
    assert details["runtime"] < 60, "QAOA should finish in seconds at this size"
    assert metrics.feasible, metrics.violations


def test_qaoa_reaches_known_optimum_at_p3(instance):
    metrics, _ = solve_qaoa(instance, reps=3, maxiter=150, shots=2048, seed=42)
    assert abs(metrics.objective_value - KNOWN_OPTIMUM) < TOL


def test_qaoa_low_depth_is_feasible_but_may_be_suboptimal(instance):
    """p=1 is expected to return a valid but worse plan. Documented, not hidden."""
    metrics, details = solve_qaoa(instance, reps=1, maxiter=5, shots=256, seed=42)
    assert metrics.feasible, metrics.violations
    assert metrics.objective_value <= KNOWN_OPTIMUM + TOL
    assert details["returned_feasible_sample"] is True


def test_qaoa_reports_no_optimality_guarantee(instance):
    _, details = solve_qaoa(instance, reps=1, maxiter=5, shots=256, seed=42)
    joined = " ".join(details["notes"]).lower()
    assert "no optimality guarantee" in joined
    assert "does not" in joined and "enumerate" in joined


def test_qaoa_hamiltonian_rescaling_recorded(instance):
    _, details = solve_qaoa(instance, reps=1, maxiter=5, shots=256, seed=42)
    assert details["hamiltonian_scale_divisor"] > 1


def test_qaoa_rejects_oversized_instance(instance):
    from app.services.qaoa_service import QaoaTooLargeError

    with pytest.raises(QaoaTooLargeError) as exc:
        solve_qaoa(instance, reps=1, maxiter=5, shots=128, max_qubits=4)
    assert "qubit" in str(exc.value).lower()


def test_qaoa_and_classical_agree_at_sufficient_depth(instance):
    q, _ = solve_qaoa(instance, reps=3, maxiter=150, shots=2048, seed=42)
    c, _ = solve_classical(instance, time_limit_sec=30)
    assert abs(q.objective_value - c.objective_value) < TOL


# ============================================= independent validation
def test_validator_catches_inventory_in_unopened_store(instance):
    """C2: assigning an area to a store that was not opened must be reported."""
    area = instance.areas[0].name
    server = instance.servers_of(area)[0]
    metrics = evaluate_solution(instance, selected_stores=[], assignment={area: server})
    assert not metrics.feasible
    assert any(v.startswith("C2") for v in metrics.violations)


def test_validator_catches_capacity_overflow(instance):
    """Force every area onto one store and expect a capacity violation."""
    target = None
    for store in instance.stores:
        served = instance.served_by(store.id)
        if len(served) == len(instance.areas):
            target = store
            break
    if target is None:
        pytest.skip("no single store can reach every area in this instance")

    assignment = {a.name: target.id for a in instance.areas}
    metrics = evaluate_solution(instance, [target.id], assignment)
    total = sum(a.volume for a in instance.areas)
    if total > target.storage_capacity:
        assert not metrics.feasible
        assert any(v.startswith("C3") for v in metrics.violations)


def test_validator_catches_budget_violation(instance):
    """Opening every store must exceed the budget on the dev instance."""
    all_ids = instance.store_ids
    assignment = {a.name: None for a in instance.areas}
    metrics = evaluate_solution(instance, all_ids, assignment)
    total_cost = sum(s.opening_cost for s in instance.stores)
    if total_cost > instance.budget:
        assert not metrics.feasible
        assert any(v.startswith("C4") for v in metrics.violations)


def test_validator_catches_double_assignment(instance):
    """C1: two stores serving one area must be reported, not silently repaired."""
    area = next(
        (a.name for a in instance.areas if len(instance.servers_of(a.name)) >= 2),
        None,
    )
    if area is None:
        pytest.skip("no area has two candidate servers")
    s1, s2 = instance.servers_of(area)[:2]
    flags = {(s1, area): 1, (s2, area): 1}
    metrics = evaluate_solution(instance, [s1, s2], {area: s1}, flags)
    assert any(v.startswith("C1") for v in metrics.violations)


def test_validator_catches_unknown_store_id(instance):
    metrics = evaluate_solution(instance, [987654], {a.name: None for a in instance.areas})
    assert not metrics.feasible
    assert any("not in the instance" in v for v in metrics.violations)


def test_empty_plan_is_feasible_but_serves_nothing(instance):
    """Serving nobody breaks no constraint; it just earns nothing."""
    metrics = evaluate_solution(instance, [], {a.name: None for a in instance.areas})
    assert metrics.feasible
    assert metrics.demand_units_served == 0
    assert metrics.objective_value == 0


def test_decode_ignores_auxiliary_bits(instance):
    import numpy as np

    model = build_qubo(instance, encoding="compact")
    bits = np.zeros(model.n_qubits)
    selected, assignment = decode_bits(model, bits)
    assert selected == []
    assert all(v is None for v in assignment.values())
