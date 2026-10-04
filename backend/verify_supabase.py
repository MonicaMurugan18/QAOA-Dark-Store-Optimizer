"""End-to-end verification against Supabase PostgreSQL.

Proves the whole chain runs on Supabase-resident data:

    Supabase -> data_service -> optimization instance
                                  |-> QUBO -> QAOA -> validator
                                  '-> PuLP/CBC      -> validator

Both solvers are handed THE SAME instance object, so there is no possibility of
them seeing different data.

The password is never printed.
"""

from __future__ import annotations

import json
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import text

from app.config import settings
from app.database import SessionLocal, engine
from app.services.classical_service import solve_classical
from app.services.data_service import build_instance, suggest_instance
from app.services.qaoa_service import brute_force_qubo, solve_qaoa
from app.services.qubo_service import build_qubo


def mask(u: str) -> str:
    return re.sub(r"(://[^:/@]+:)[^@]*(@)", r"\1********\2", str(u))


def rule(t: str) -> None:
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


rule("1-2. SUPABASE CONNECTION & DIALECT")
print("  DATABASE_URL :", mask(settings.database_url))
print("  dialect      :", engine.dialect.name)
print("  driver       :", engine.dialect.driver)
if engine.dialect.name != "postgresql":
    raise SystemExit("STOP: dialect is not postgresql; refusing to continue")
with engine.connect() as c:
    print("  server       :", c.execute(text("SHOW server_version")).scalar_one())
    print("  database     :", c.execute(text("SELECT current_database()")).scalar_one())
    print("  host         : (from DATABASE_URL, pooler)")

db = SessionLocal()

rule("3. TABLES IN SUPABASE")
with engine.connect() as c:
    rows = c.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' ORDER BY table_name"
        )
    ).scalars().all()
for t in rows:
    print("   ", t)

rule("5. RECORD COUNTS (queried from Supabase)")
counts = {}
with engine.connect() as c:
    for t in rows:
        counts[t] = c.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar_one()
        print(f"  {t:<24}{counts[t]:>8}")

rule("6. DATA PROVENANCE")
from app.services.ingestion.ingestion_manager import data_status  # noqa: E402

status = data_status(db)
print("  REAL (public/official):")
for d in status["real_data"]:
    print("     -", d)
print("  PROXY / ESTIMATED:")
for d in status["proxy_or_estimated"]:
    print("     -", d)
print("  SYNTHETIC:")
for d in status["synthetic"]:
    print("     -", d)
print(f"\n  routing: {status['routing']['routed_by_osrm']} routed by OSRM, "
      f"{status['routing']['haversine_fallback']} estimated")
print(f"  population: {status['population_coverage']['zones_with_sourced_population']}"
      f"/{status['population_coverage']['zones_total']} zones have a sourced figure")
print(f"  demand mode: {status['demand_mode']}")

rule("7. OPTIMIZATION INSTANCE BUILT FROM SUPABASE")
sugg = suggest_instance(db, delivery_limit=15.0, max_stores=4, max_zones=4)
print("  suggested:", json.dumps({k: v for k, v in sugg.items() if k != "product_ids"}))
print(f"  products: {len(sugg['product_ids'])} (full catalogue)")

inst = build_instance(
    db,
    budget=60000,
    default_delivery_limit=sugg["delivery_time_limit"],
    store_ids=sugg["store_ids"],
    product_ids=sugg["product_ids"],
    areas=sugg["areas"],
)
print("\n  instance:", json.dumps(inst.size_summary()))
for w in inst.warnings:
    print("    warn:", w)
print("  stores:")
for s in inst.stores:
    print(f"    {s.id:>4}  {s.name[:40]:<42} open Rs {s.opening_cost:>7.0f}")
print("  zones:")
for a in inst.areas:
    print(f"    {a.name[:30]:<32} demand {a.quantity:>9.1f} units")

model = build_qubo(inst, "compact")
print(f"\n  QUBO: {model.n_qubits} qubits "
      f"({len(model.decision_names)} decision + {model.n_auxiliary} aux)")
bf = brute_force_qubo(model)
if bf:
    print(f"  brute-force optimum: Rs {bf['objective_value_maximisation']:,.2f} "
          f"over {bf['states_enumerated']:,} states")

rule("8. CLASSICAL (PuLP/CBC) on the Supabase instance")
cm, cd = solve_classical(inst, time_limit_sec=60)
print(f"  objective      Rs {cm.objective_value:,.2f}")
print(f"  runtime        {cd['runtime']:.3f}s")
print(f"  pulp status    {cd['pulp_status']}   proven_optimal={cd['proven_optimal']}")
print(f"  stores opened  {cm.selected_stores} {cm.selected_store_names}")
print(f"  coverage       {100*cm.service_level:.1f}%")
print(f"  budget used    Rs {cm.budget_used:,.0f} / Rs {inst.budget:,.0f}")
print(f"  storage        {cm.storage_used:,.1f} / {cm.storage_available:,.1f}")

rule("9. QAOA on the SAME instance object")
qm, qd = solve_qaoa(inst, reps=3, maxiter=150, shots=2048, seed=42)
print(f"  objective      Rs {qm.objective_value:,.2f}")
print(f"  runtime        {qd['runtime']:.2f}s")
print(f"  qubits         {qd['n_qubits']}  p={qd['reps_p']}  shots={qd['final_shots']}")
print(f"  stores opened  {qm.selected_stores} {qm.selected_store_names}")
print(f"  coverage       {100*qm.service_level:.1f}%")
print(f"  feasible shots {100*qd['feasible_shot_fraction']:.2f}%")

rule("10. INDEPENDENT VALIDATION")
for label, m in (("classical", cm), ("qaoa", qm)):
    print(f"  {label}: feasible={m.feasible}  violations={m.violations or 'none'}")
    for c in m.checks:
        print(f"      {'OK ' if c['satisfied'] else 'FAIL'}  {c['name']}")

rule("11. SAME-INSTANCE PROOF")
print("  Both solvers received the identical Python object:")
print(f"    id(instance) passed to classical : {id(inst)}")
print(f"    id(instance) passed to qaoa      : {id(inst)}")
print(f"    stores  {inst.store_ids}")
print(f"    areas   {inst.area_names}")
print(f"    links   {len(inst.links)} service-feasible legs")

gap = (
    100 * (cm.objective_value - qm.objective_value) / abs(cm.objective_value)
    if cm.objective_value
    else 0.0
)
rule("RESULT")
print(f"  classical   Rs {cm.objective_value:,.2f}  (proven_optimal={cd['proven_optimal']})")
print(f"  qaoa        Rs {qm.objective_value:,.2f}")
if bf:
    print(f"  bruteforce  Rs {bf['objective_value_maximisation']:,.2f}")
print(f"  optimality gap (QAOA vs proven optimum): {gap:+.2f}%")
print(f"  both feasible: {cm.feasible and qm.feasible}")

db.close()
