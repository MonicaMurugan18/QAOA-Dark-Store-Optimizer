"""Ingestion CLI.

Usage:
    python ingest.py                     # every step, using cached raw files
    python ingest.py --steps stores,zones
    python ingest.py --fresh             # bypass the raw cache, re-download
    python ingest.py --no-router         # skip OSRM, use labelled estimates
    python ingest.py --zone-limit 12 --product-limit 6
    python ingest.py --status            # print provenance summary only

Downloads are NOT performed on server startup. Refreshing is always an explicit
manual operation, because the public endpoints used here are free community
resources.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

logging.basicConfig(
    level=logging.INFO, format="%(levelname)-7s %(name)s | %(message)s"
)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.database import SessionLocal, init_db  # noqa: E402
from app.services.ingestion.ingestion_manager import (  # noqa: E402
    STEPS,
    data_status,
    run_ingestion,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Real-data ingestion pipeline")
    ap.add_argument("--steps", default=",".join(STEPS),
                    help=f"comma-separated subset of {STEPS}")
    ap.add_argument("--fresh", action="store_true",
                    help="re-download instead of using data/raw cache")
    ap.add_argument("--no-router", action="store_true",
                    help="skip OSRM; write labelled haversine estimates")
    ap.add_argument("--zone-limit", type=int, default=None)
    ap.add_argument("--product-limit", type=int, default=None)
    ap.add_argument("--status", action="store_true",
                    help="print the provenance summary and exit")
    args = ap.parse_args()

    init_db()
    db = SessionLocal()
    try:
        if args.status:
            print(json.dumps(data_status(db), indent=2, default=str))
            return 0

        run = run_ingestion(
            db,
            steps=[s.strip() for s in args.steps.split(",") if s.strip()],
            use_cache=not args.fresh,
            use_router=not args.no_router,
            zone_limit=args.zone_limit,
            product_limit=args.product_limit,
        )

        print("\n" + "=" * 70)
        print(f"INGESTION RUN #{run.id}  status={run.status}")
        print("=" * 70)
        for step, rep in (run.report or {}).items():
            print(f"\n--- {step} ---")
            print(
                f"  fetched {rep['fetched']}   inserted {rep['inserted']}   "
                f"updated {rep['updated']}   rejected {rep['rejected']}"
            )
            if rep.get("skipped_reason"):
                print(f"  SKIPPED: {rep['skipped_reason']}")
            for w in rep.get("warnings", []):
                print(f"  note: {w}")
            for r in rep.get("rejection_sample", [])[:5]:
                print(f"  rejected: {r['reason']}")
            if rep["rejected"] > len(rep.get("rejection_sample", [])):
                print(
                    f"  ... {rep['rejected']} rejected in total "
                    f"(all logged, see data_ingestion_runs.report)"
                )
        if run.error_message:
            print(f"\nERRORS: {run.error_message}")

        print("\n" + "=" * 70)
        print("PROVENANCE SUMMARY")
        print("=" * 70)
        print(json.dumps(data_status(db), indent=2, default=str))
        return 0 if run.status == "completed" else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
