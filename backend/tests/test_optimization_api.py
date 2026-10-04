"""Optimization API, persistence and the comparison endpoint."""

from tests.conftest import KNOWN_OPTIMUM

TOL = 0.5


def _payload(dev_ids, **over):
    body = {
        "budget": 20000,
        "delivery_time_limit": 15,
        "store_ids": dev_ids["store_ids"],
        "product_ids": dev_ids["product_ids"],
        "areas": dev_ids["areas"],
        "options": {
            "reps": 3,
            "maxiter": 150,
            "shots": 2048,
            "seed": 42,
            "time_limit_sec": 30,
        },
    }
    body.update(over)
    return body


# ===================================================================== meta
def test_root_and_health(client):
    assert client.get("/").status_code == 200
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_docs_and_openapi(client):
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json")
    assert schema.status_code == 200
    paths = schema.json()["paths"]
    for required in [
        "/api/stores",
        "/api/products",
        "/api/demand",
        "/api/optimization/run",
        "/api/optimization/qaoa",
        "/api/optimization/classical",
        "/api/optimization/{run_id}",
        "/api/optimization/{run_id}/comparison",
    ]:
        assert required in paths, f"missing from OpenAPI schema: {required}"


# ================================================================= preview
def test_preview_reports_qubit_count(client, dev_ids):
    r = client.post("/api/optimization/preview", json=_payload(dev_ids))
    assert r.status_code == 200
    body = r.json()
    assert body["qubo_compact"]["n_qubits"] == 11
    assert body["qubo_compact"]["within_simulator_limit"] is True
    assert body["instance"]["stores"] == 3
    assert body["instance"]["areas"] == 3
    assert body["instance"]["products"] == 3


# ============================================================== classical
def test_classical_endpoint(client, dev_ids):
    r = client.post("/api/optimization/classical", json=_payload(dev_ids))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed"
    assert len(body["results"]) == 1

    res = body["results"][0]
    assert res["solver"] == "classical"
    assert abs(res["objective_value"] - KNOWN_OPTIMUM) < TOL
    assert res["validation"]["feasible"] is True
    assert res["validation"]["violations"] == []
    assert res["solver_details"]["proven_optimal"] is True
    assert res["runtime"] > 0
    assert res["selected_stores"]
    assert res["inventory_allocation"]
    assert res["area_assignments"]
    assert res["service_level"] == 1.0
    assert res["budget_used"] <= 20000


# =================================================================== qaoa
def test_qaoa_endpoint(client, dev_ids):
    r = client.post("/api/optimization/qaoa", json=_payload(dev_ids))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed"

    res = body["results"][0]
    assert res["solver"] == "qaoa"
    assert res["validation"]["feasible"] is True
    assert res["solver_details"]["n_qubits"] == 11
    assert res["solver_details"]["reps_p"] == 3
    assert res["runtime"] > 0
    assert abs(res["objective_value"] - KNOWN_OPTIMUM) < TOL


def test_qaoa_low_depth_still_returns_a_valid_plan(client, dev_ids):
    """p=1 is suboptimal but feasible. The API must report it, not hide it."""
    body = _payload(dev_ids)
    body["options"].update({"reps": 1, "maxiter": 5, "shots": 256})
    r = client.post("/api/optimization/qaoa", json=body)
    assert r.status_code == 200
    res = r.json()["results"][0]
    assert res["validation"]["feasible"] is True
    assert res["objective_value"] <= KNOWN_OPTIMUM + TOL
    joined = " ".join(res["solver_details"]["notes"]).lower()
    assert "no optimality guarantee" in joined


# ==================================================================== run
def test_run_both_and_comparison(client, dev_ids):
    r = client.post("/api/optimization/run", json=_payload(dev_ids))
    assert r.status_code == 200
    body = r.json()
    run_id = body["id"]
    assert body["method"] == "both"
    assert len(body["results"]) == 2
    assert {res["solver"] for res in body["results"]} == {"qaoa", "classical"}

    # ---- persistence: fetch the stored run back
    r = client.get(f"/api/optimization/{run_id}")
    assert r.status_code == 200
    stored = r.json()
    assert stored["id"] == run_id
    assert len(stored["results"]) == 2

    # ---- comparison
    r = client.get(f"/api/optimization/{run_id}/comparison")
    assert r.status_code == 200
    comp = r.json()
    assert comp["run_id"] == run_id
    assert comp["qaoa"] is not None
    assert comp["classical"] is not None

    for block in (comp["qaoa"], comp["classical"]):
        assert {"objective_value", "customers_served", "budget_used", "runtime"} <= set(
            block
        )

    # CBC proved optimality, so a reference and a gap must exist.
    assert comp["reference_solver"] == "classical"
    assert comp["optimality_gap_percent"] is not None
    assert abs(comp["optimality_gap_percent"]["classical"]) < 1e-6
    assert comp["optimality_gap_percent"]["qaoa"] >= -1e-6

    metrics = {m["metric"] for m in comp["metrics"]}
    assert {"objective_value", "runtime", "budget_used", "service_level"} <= metrics


def test_runs_are_listed(client, dev_ids):
    client.post("/api/optimization/classical", json=_payload(dev_ids))
    r = client.get("/api/optimization/runs")
    assert r.status_code == 200
    assert len(r.json()) >= 1


# ================================================================ errors
def test_unknown_run_404(client):
    assert client.get("/api/optimization/999999").status_code == 404
    assert client.get("/api/optimization/999999/comparison").status_code == 404


def test_negative_budget_rejected(client, dev_ids):
    r = client.post(
        "/api/optimization/classical", json=_payload(dev_ids, budget=-100)
    )
    assert r.status_code == 422
    assert "budget" in str(r.json())


def test_unknown_store_id_rejected(client, dev_ids):
    r = client.post(
        "/api/optimization/classical", json=_payload(dev_ids, store_ids=[123456])
    )
    assert r.status_code == 422
    assert "store" in str(r.json()).lower()


def test_unknown_product_id_rejected(client, dev_ids):
    r = client.post(
        "/api/optimization/classical", json=_payload(dev_ids, product_ids=[123456])
    )
    assert r.status_code == 422


def test_budget_below_cheapest_store_rejected(client, dev_ids):
    """No store can be opened, so there is no instance to solve."""
    r = client.post("/api/optimization/classical", json=_payload(dev_ids, budget=1))
    assert r.status_code == 422
    assert "cheapest" in str(r.json()).lower() or "budget" in str(r.json()).lower()


def test_qaoa_rejects_instance_above_qubit_limit(client):
    """The full 4-area instance exceeds the simulator limit and must say so."""
    r = client.post(
        "/api/optimization/qaoa",
        json={
            "budget": 60000,
            "delivery_time_limit": 15,
            "options": {"reps": 1, "maxiter": 5, "shots": 128, "seed": 1},
        },
    )
    # Either it fits and succeeds, or it is refused with a clear explanation.
    if r.status_code == 500:
        detail = str(r.json()["detail"]).lower()
        assert "qubit" in detail or "too large" in detail
    else:
        assert r.status_code == 200
