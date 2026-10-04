"""
Stage 1 -- Build and inspect the sample dataset.

Project: QAOA for Joint Dark Store Location Selection and Inventory Allocation
         in Hyperlocal Quick Commerce.

This file ONLY builds data. No optimisation, no QAOA, no quantum library.
Every number below is hand-chosen (not random) so that the instance is
reproducible and so that you can reason about the right answer by hand later.

Run:  python stage1_dataset.py
"""

import numpy as np
import pandas as pd

# Show all columns and avoid scientific notation when printing.
pd.set_option("display.width", 120)
pd.set_option("display.max_columns", 50)
pd.set_option("display.float_format", lambda v: f"{v:,.2f}")


# ----------------------------------------------------------------------
# 1. CANDIDATE DARK STORES
#    A "dark store" is a small warehouse with no walk-in customers.
#    x_km / y_km are positions on a flat 1 km grid over the city zone.
# ----------------------------------------------------------------------
stores = pd.DataFrame(
    {
        "store_id":       ["S1", "S2", "S3", "S4"],
        "store_name":     ["Anna Nagar Hub", "T Nagar Hub", "Velachery Hub", "Adyar Hub"],
        "x_km":           [2.0, 5.0, 7.5, 5.5],
        "y_km":           [6.0, 4.3, 1.5, 1.0],
        "opening_cost":   [9000, 12000, 7000, 8500],   # rupees per day, amortised
        "capacity_units": [1000, 1200,  600,  750],    # volume units per day
    }
)


# ----------------------------------------------------------------------
# 2. CUSTOMER AREAS (demand clusters / delivery pincodes)
# ----------------------------------------------------------------------
areas = pd.DataFrame(
    {
        "area_id":    ["A1", "A2", "A3", "A4"],
        "area_name":  ["Kilpauk", "Nungambakkam", "Guindy", "Besant Nagar"],
        "x_km":       [1.5, 4.0, 6.5, 4.5],
        "y_km":       [7.5, 5.5, 2.5, 0.5],
        "households": [4200, 6100, 3800, 3300],
    }
)


# ----------------------------------------------------------------------
# 3. PRODUCTS
#    volume_per_unit converts "one item" into the shared capacity currency,
#    so that one number (capacity_units) can bound a mixed basket.
# ----------------------------------------------------------------------
products = pd.DataFrame(
    {
        "product_id":       ["P1", "P2", "P3"],
        "product_name":     ["Milk & Bread", "Snacks", "Household Care"],
        "volume_per_unit":  [1.0, 1.5, 2.5],   # shelf/bin space of one item
        "profit_per_unit":  [12, 20, 35],      # rupees earned per item sold
        "penalty_per_unit": [25, 15, 10],      # rupees lost per item NOT served
    }
)


# ----------------------------------------------------------------------
# 4. DEMAND  (one row per area-product pair -> "long" / tidy format)
#    Values are a typical weekday's orders. Chosen so that no single store
#    can serve the whole zone -- that is what makes the problem interesting.
# ----------------------------------------------------------------------
demand = pd.DataFrame(
    {
        "area_id":      ["A1", "A1", "A1", "A2", "A2", "A2",
                         "A3", "A3", "A3", "A4", "A4", "A4"],
        "product_id":   ["P1", "P2", "P3", "P1", "P2", "P3",
                         "P1", "P2", "P3", "P1", "P2", "P3"],
        "demand_units": [180,   90,   40,  220,  130,   60,
                         150,   80,   35,  130,   70,   30],
    }
)

# Attach volume_per_unit to each demand row, then convert items -> volume.
demand = demand.merge(
    products[["product_id", "volume_per_unit"]], on="product_id", how="left"
)
demand["demand_volume"] = demand["demand_units"] * demand["volume_per_unit"]


# ----------------------------------------------------------------------
# 5. DISTANCE AND DELIVERY TIME  (store x area)
#    Computed with NumPy broadcasting instead of typed by hand, so the
#    numbers always stay consistent with the coordinates above.
# ----------------------------------------------------------------------
AVG_SPEED_KMPH = 20.0    # realistic scooter speed in dense city traffic
HANDLING_MIN   = 3.0     # picking + packing before the rider leaves
SLA_MINUTES    = 15.0    # the quick-commerce delivery promise

store_xy = stores[["x_km", "y_km"]].to_numpy()     # shape (4, 2)
area_xy  = areas[["x_km", "y_km"]].to_numpy()      # shape (4, 2)

diff = store_xy[:, np.newaxis, :] - area_xy[np.newaxis, :, :]   # (4, 4, 2)
distance_matrix = np.sqrt((diff ** 2).sum(axis=2))              # (4, 4) km
time_matrix = HANDLING_MIN + (distance_matrix / AVG_SPEED_KMPH) * 60.0

# Turn the two matrices into one tidy table of 4 x 4 = 16 store-area links.
links = pd.DataFrame(
    {
        "store_id":     np.repeat(stores["store_id"].to_numpy(), len(areas)),
        "area_id":      np.tile(areas["area_id"].to_numpy(), len(stores)),
        "distance_km":  distance_matrix.ravel(),
        "delivery_min": time_matrix.ravel(),
    }
)
links["within_sla"] = links["delivery_min"] <= SLA_MINUTES


# ----------------------------------------------------------------------
# 6. SAVE
# ----------------------------------------------------------------------
stores.to_csv("data/stores.csv", index=False)
areas.to_csv("data/areas.csv", index=False)
products.to_csv("data/products.csv", index=False)
demand.to_csv("data/demand.csv", index=False)
links.to_csv("data/store_area_links.csv", index=False)


# ----------------------------------------------------------------------
# 7. INSPECT  (this is the part you actually read)
# ----------------------------------------------------------------------
def rule(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


rule("STORES")
print(stores)
print(stores.dtypes)

rule("CUSTOMER AREAS")
print(areas)

rule("PRODUCTS")
print(products)

rule("DEMAND (long format)")
print(demand)

rule("DEMAND (pivot: area x product, in items)")
print(demand.pivot(index="area_id", columns="product_id", values="demand_units"))

rule("DELIVERY TIME MATRIX (minutes, store x area)")
print(links.pivot(index="store_id", columns="area_id", values="delivery_min"))

rule("SERVICEABLE PAIRS (delivery_min <= 15)")
print(links.pivot(index="store_id", columns="area_id", values="within_sla"))

rule("SANITY CHECKS")
missing = (
    stores.isna().sum().sum() + areas.isna().sum().sum()
    + products.isna().sum().sum() + demand.isna().sum().sum()
)
print(f"missing values anywhere      : {missing}")

total_demand_vol = demand["demand_volume"].sum()
total_capacity   = stores["capacity_units"].sum()
print(f"total demand volume/day      : {total_demand_vol:,.1f}")
print(f"total capacity if ALL open   : {total_capacity:,.1f}")
print(f"largest single store capacity: {stores['capacity_units'].max():,.1f}")
print(f"=> at least 2 stores must open: "
      f"{stores['capacity_units'].max() < total_demand_vol}")

per_area = demand.groupby("area_id")["demand_volume"].sum()
print("\ndemand volume per area:")
print(per_area)

print("\ncoverage: how many stores can reach each area inside the SLA")
cover = links[links["within_sla"]].groupby("area_id")["store_id"].agg(["count", list])
print(cover)
print(f"\nevery area reachable by >=1 store: {len(cover) == len(areas)}")

rule("PROBLEM SIZE (for Stage 2 planning)")
n_open_vars = len(stores)
n_assign_vars = int(links["within_sla"].sum())
print(f"binary open variables  y[s]      : {n_open_vars}")
print(f"serviceable store-area pairs     : {n_assign_vars}")
print(f"if assignment is also binary x[s,a]: {n_open_vars + n_assign_vars} qubits total")
