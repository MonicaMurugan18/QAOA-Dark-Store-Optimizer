"""Database connection and schema."""

from sqlalchemy import inspect

from app.database import check_connection, engine


def test_connection_ok():
    ok, message = check_connection()
    assert ok, f"database unreachable: {message}"


def test_all_five_tables_exist():
    tables = set(inspect(engine).get_table_names())
    expected = {
        "stores",
        "products",
        "demand",
        "optimization_runs",
        "optimization_results",
    }
    assert expected <= tables, f"missing tables: {expected - tables}"


def test_seed_loaded(db):
    from app.models import Demand, Product, Store

    assert db.query(Store).count() == 6, "expected the 6 mapped Puducherry stores"
    assert db.query(Product).count() >= 3
    assert db.query(Demand).count() >= 9


def test_seed_rows_declare_provenance(db):
    """No invented number may be presented as real operator data."""
    from app.models import Store

    for store in db.query(Store).all():
        assert store.data_source, f"store {store.id} has no data_source"
        assert "DEMO" in store.data_source or "APPROX" in store.data_source
