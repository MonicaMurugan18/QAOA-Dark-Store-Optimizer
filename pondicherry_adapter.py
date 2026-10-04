"""
Adapter: corrected Puducherry dataset  ->  the Stage 1-6 pipeline.

The two sides use different names for the same things:

    Puducherry CSVs           pipeline
    ---------------           --------
    site_id                   store_id
    zone_id                   area_id
    delivery_time_min         delivery_min
    daily_capacity_liters     capacity_units      (litres are the volume unit)
    daily_opening_cost_inr    opening_cost
    demand_volume_liters      demand_volume
    sku_id                    product_id

It also has to INVENT two columns the pipeline needs and the dataset does not
carry: profit per unit and the churn penalty per unit. Both are derived from
unit_cost_inr with a stated rule, not guessed per product -- see below.

Import this, do not run it directly.
"""

import numpy as np
import pandas as pd

import qaoa_pipeline as qp

# ---------------------------------------------------------------------------
# Turning a price list into an objective function
#
# The pipeline minimises: opening cost + delivery cost + cost of NOT serving.
# The dataset gives unit_cost_inr (what we pay a supplier), which is neither.
#
# GROSS_MARGIN   quick commerce runs on a thin gross margin, 15-25%. Taking 18%
#                puts milk at Rs 10 profit, which matches the Rs 12 we used in
#                the hand-built Chennai instance.
# CHURN          failing to deliver costs more than the lost margin: the
#                customer stops using the app. It costs far more for a daily
#                staple than for dish wash liquid, so it is keyed to the
#                perishable flag, which is exactly the staple/non-staple split.
#                0.45 puts milk at Rs 26, against the Rs 25 used for Chennai.
# ---------------------------------------------------------------------------
GROSS_MARGIN         = 0.18
CHURN_PERISHABLE     = 0.45
CHURN_NON_PERISHABLE = 0.18


def load_pondicherry(folder, name=None):
    """Read the corrected Puducherry CSVs and return a pipeline instance."""
    sites = pd.read_csv(f"{folder}/candidate_dark_stores.csv")
    zones = pd.read_csv(f"{folder}/demand_zones.csv")
    skus = pd.read_csv(f"{folder}/skus.csv")
    dem = pd.read_csv(f"{folder}/zone_sku_demand.csv")
    tt = pd.read_csv(f"{folder}/travel_time_matrix.csv")

    # --- products: add the two columns the objective function needs ---------
    products = pd.DataFrame({
        "product_id": skus["sku_id"],
        "product_name": skus["sku_name"],
        "volume_per_unit": skus["unit_volume_liters"],
        "profit_per_unit": (skus["unit_cost_inr"] * GROSS_MARGIN).round(),
        "penalty_per_unit": (
            skus["unit_cost_inr"]
            * np.where(skus["is_perishable"], CHURN_PERISHABLE,
                       CHURN_NON_PERISHABLE)).round(),
    })

    # --- stores -------------------------------------------------------------
    stores = pd.DataFrame({
        "store_id": sites["site_id"],
        "store_name": sites["area_name"],
        "x_km": sites["longitude"],          # kept only for reference
        "y_km": sites["latitude"],
        "opening_cost": sites["daily_opening_cost_inr"],
        "capacity_units": sites["daily_capacity_liters"],
    })

    areas = pd.DataFrame({
        "area_id": zones["zone_id"],
        "area_name": zones["area_name"],
        "x_km": zones["longitude"],
        "y_km": zones["latitude"],
    })

    # --- demand -------------------------------------------------------------
    demand = pd.DataFrame({
        "area_id": dem["zone_id"],
        "product_id": dem["sku_id"],
        "demand_units": dem["avg_daily_demand_units"],
        "demand_volume": dem["demand_volume_liters"],
    }).merge(products[["product_id", "volume_per_unit"]],
             on="product_id", how="left")

    # --- links --------------------------------------------------------------
    links = pd.DataFrame({
        "store_id": tt["site_id"],
        "area_id": tt["zone_id"],
        "distance_km": tt["road_distance_km"],
        "delivery_min": tt["delivery_time_min"],
        "within_sla": tt["within_sla"].astype(bool),
    })

    sla = float(tt.loc[tt["within_sla"], "delivery_time_min"].max())
    inst = qp._finalise(stores, areas, demand, links, sla,
                        name or folder, products=products)
    inst["products_raw"] = skus
    inst["raw"] = {"stores": stores, "areas": areas, "demand": demand,
                   "links": links, "products": products, "sla": sla}
    return inst


def slice_instance(inst, store_ids, area_ids, slack=2.2, name=None):
    """Cut a smaller instance out of a big one.

    Capacity is RE-SIZED against the slice's own demand. Copying the parent's
    capacities would make the constraint stop binding on the smaller problem,
    which is the bug we just spent a day removing from this dataset.
    """
    raw = inst["raw"]
    stores = raw["stores"][raw["stores"].store_id.isin(store_ids)].copy()
    areas = raw["areas"][raw["areas"].area_id.isin(area_ids)].copy()
    demand = raw["demand"][raw["demand"].area_id.isin(area_ids)].copy()
    links = raw["links"][raw["links"].store_id.isin(store_ids)
                         & raw["links"].area_id.isin(area_ids)].copy()

    total_volume = demand["demand_volume"].sum()
    share = stores["capacity_units"] / stores["capacity_units"].sum()
    stores["capacity_units"] = (slack * total_volume * share / 25).round() * 25

    return qp._finalise(stores, areas, demand, links, raw["sla"],
                        name or f"pondy-{len(store_ids)}x{len(area_ids)}",
                        products=raw["products"])
