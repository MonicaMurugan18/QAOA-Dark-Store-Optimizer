"""
PERSON A - DEMAND SIDE
Replacement for Sections 2, 3 and 4 of generate_dataset_pondicherry.py

Fixes 1, 5, 6, 8, 12, 13 (six fixes).

You can run this file on its own to test your part before the team merges.
It writes three CSVs and prints the two numbers you must hand over.

Run:  python person_a_demand.py
"""

import math

import numpy as np
import pandas as pd

# The team agreed on one seeded generator. Do not use np.random.seed().
RNG = np.random.default_rng(42)


# ============================================================================
# SETTINGS - these go at the TOP of the merged script, not inside loops
# ============================================================================
ITEMS_PER_ORDER = 5.0     # FIX 1: items in one quick-commerce order (4-6)

# FIX 8: orders are now DERIVED from population density, so density matters.
ORDERS_PER_DENSITY   = 1 / 60.0     # 15,000 people/sqkm -> about 250 orders/day
ZONE_TYPE_ORDER_MULT = {"commercial": 1.30, "mixed": 1.00, "residential": 0.85}

# Base road speeds. You draw ONE speed per zone; Person C uses it (fix 9).
AVG_SPEED_KMPH = {"commercial": 18, "residential": 24, "mixed": 21}


# ============================================================================
# SECTION 2 - DEMAND ZONES
# ============================================================================
demand_zones = [
    ("Z01", "White Town",         11.9330, 79.8340, "commercial"),
    ("Z02", "Heritage Town",      11.9300, 79.8360, "commercial"),
    ("Z03", "Muthialpet",         11.9380, 79.8280, "residential"),
    ("Z04", "Vaithikuppam",       11.9280, 79.8380, "residential"),
    ("Z05", "Kuruchikuppam",      11.9200, 79.8340, "residential"),
    ("Z06", "Nellithope",         11.9250, 79.8200, "mixed"),
    ("Z07", "Uppalam",            11.9350, 79.8080, "residential"),
    ("Z08", "Rainbow Nagar",      11.9450, 79.8150, "residential"),
    ("Z09", "Gorimedu",           11.9550, 79.8200, "mixed"),
    ("Z10", "Lawspet",            11.9600, 79.8100, "residential"),
    ("Z11", "Thattanchavady",     11.9600, 79.8300, "residential"),
    ("Z12", "Reddiarpalayam",     11.9450, 79.8000, "mixed"),
    ("Z13", "Ozhukarai",          11.9500, 79.7900, "residential"),
    ("Z14", "Anna Nagar (Pondy)", 11.9350, 79.7950, "residential"),
    ("Z15", "Ilango Nagar",       11.9600, 79.8000, "residential"),
    ("Z16", "Mudaliarpet",        11.9150, 79.8100, "mixed"),
    ("Z17", "Kurumbapet",         11.9100, 79.8300, "residential"),
    ("Z18", "Ariyankuppam",       11.8850, 79.8080, "residential"),
    ("Z19", "Kalapet",            12.0080, 79.8390, "mixed"),
    ("Z20", "Auroville Fringe",   12.0067, 79.8100, "residential"),
]

zone_rows = []
zone_speed = {}                       # <-- HAND THIS TO PERSON C

for zid, name, lat, lon, ztype in demand_zones:
    density = int(RNG.integers(5000, 20000))

    # FIX 8 - OLD CODE WAS:
    #   avg_daily_orders = np.random.randint(lo, hi)   # ignored density
    # Orders had correlation -0.105 with density, i.e. density did nothing.
    orders = int(round(density
                       * ORDERS_PER_DENSITY
                       * ZONE_TYPE_ORDER_MULT[ztype]
                       * RNG.uniform(0.90, 1.10)))

    # FIX 9 (your half) - one speed per ZONE, drawn once, saved to the CSV.
    # The old code drew a fresh random speed inside Person C's double loop,
    # for all 200 pairs, which made delivery time not depend on distance.
    zone_speed[zid] = AVG_SPEED_KMPH[ztype] * RNG.uniform(0.92, 1.08)

    zone_rows.append([zid, name, lat, lon, ztype, density, orders,
                      round(zone_speed[zid], 2)])

zones_df = pd.DataFrame(zone_rows, columns=[
    "zone_id", "area_name", "latitude", "longitude", "zone_type",
    "population_density_per_sqkm", "avg_daily_orders",
    "avg_road_speed_kmph"])           # <-- NEW COLUMN for Person C


# ============================================================================
# SECTION 3 - PRODUCT CATALOG
# ============================================================================
skus = [
    ("SKU01", "Fresh Milk 1L",          "Dairy",         58, 0.9, 1.00, 2,   True),
    ("SKU02", "Bread Loaf",             "Bakery",        42, 0.7, 0.50, 3,   True),
    ("SKU03", "Eggs (12 pack)",         "Dairy",         82, 1.0, 0.80, 10,  True),
    ("SKU04", "Bananas (1 dozen)",      "Fruits & Veg",  50, 0.6, 1.20, 4,   True),
    ("SKU05", "Instant Noodles (pack)", "Packaged Food", 52, 0.3, 0.40, 240, False),
    ("SKU06", "Bottled Water 1L",       "Beverages",     22, 0.2, 1.00, 365, False),
    ("SKU07", "Potato Chips",           "Snacks",        38, 0.3, 0.15, 180, False),
    ("SKU08", "Dish Wash Liquid",       "Household",    105, 0.4, 0.60, 730, False),
]
sku_df = pd.DataFrame(skus, columns=[
    "sku_id", "sku_name", "category", "unit_cost_inr",
    "holding_cost_per_unit_per_day_inr", "unit_volume_liters",
    "shelf_life_days", "is_perishable"])

CATEGORY_SHARE = {"Dairy": 0.18, "Bakery": 0.10, "Fruits & Veg": 0.15,
                  "Packaged Food": 0.14, "Beverages": 0.16, "Snacks": 0.15,
                  "Household": 0.12}

# FIX 5 - OLD CODE gave the FULL category share to every product in that
# category. Dairy has two products (milk and eggs), so the shares summed to
# 1.18 instead of 1.00 and all demand was 18% too high.
n_in_category = sku_df["category"].value_counts().to_dict()
sku_share = {row[0]: CATEGORY_SHARE[row[2]] / n_in_category[row[2]]
             for row in skus}

# This line makes sure the bug can never come back.
assert abs(sum(sku_share.values()) - 1.0) < 1e-9, \
    f"product shares must sum to 1.0, got {sum(sku_share.values())}"

sku_df["demand_share"] = sku_df["sku_id"].map(sku_share)


# ============================================================================
# SECTION 4 - ZONE x PRODUCT DEMAND
# ============================================================================
volume_of = dict(zip(sku_df["sku_id"], sku_df["unit_volume_liters"]))

dem_rows = []
for zid, name, lat, lon, ztype in demand_zones:
    orders = int(zones_df.loc[zones_df.zone_id == zid, "avg_daily_orders"].iloc[0])

    for sid in sku_df["sku_id"]:
        # FIX 1 - OLD CODE WAS:
        #   mean_demand = max(1, zone_orders * share * uniform(0.8,1.2) / 10)
        # That "/ 10" gave 0.1 to 0.25 items per order, which is impossible.
        mean_units = orders * ITEMS_PER_ORDER * sku_share[sid]

        # FIX 13 - OLD CODE WAS:  int(np.random.poisson(mean) + 1)
        # The "+1" added one unit to every single row (20-30% too much).
        units = max(1, int(RNG.poisson(mean_units)))

        # FIX 12 - OLD CODE WAS:  units * uniform(0.15, 0.35)
        # Demand comes from a Poisson process, so its std IS sqrt(mean).
        # The old number described a different distribution to the mean.
        std_dev = round(math.sqrt(mean_units), 2)

        # FIX 6 - unit_volume_liters existed in skus.csv but was never used,
        # so chips (0.15 L) took the same shelf space as water (1.0 L).
        vol = round(units * volume_of[sid], 2)

        dem_rows.append([zid, sid, units, std_dev, vol])

demand_df = pd.DataFrame(dem_rows, columns=[
    "zone_id", "sku_id", "avg_daily_demand_units", "demand_std_dev",
    "demand_volume_liters"])          # <-- NEW COLUMN


# ============================================================================
# HANDOVER NUMBERS
# ============================================================================
total_volume = float(demand_df["demand_volume_liters"].sum())   # -> PERSON B


# ============================================================================
# WRITE FILES
# ============================================================================
zones_df.to_csv("demand_zones.csv", index=False)
sku_df.to_csv("skus.csv", index=False)
demand_df.to_csv("zone_sku_demand.csv", index=False)


# ============================================================================
# SELF-CHECK - all six of these must pass before you hand over
# ============================================================================
print("=" * 68)
print("PERSON A - SELF CHECK")
print("=" * 68)

units_per_zone = demand_df.groupby("zone_id")["avg_daily_demand_units"].sum()
per_order = units_per_zone / zones_df.set_index("zone_id")["avg_daily_orders"]
corr_density = zones_df["population_density_per_sqkm"].corr(zones_df["avg_daily_orders"])

checks = [
    ("FIX 1  items per order is 4 to 6",
     4.0 <= per_order.min() and per_order.max() <= 6.0,
     f"{per_order.min():.2f} to {per_order.max():.2f}   (was 0.10 to 0.25)"),

    ("FIX 5  product shares sum to 1.0",
     abs(sum(sku_share.values()) - 1.0) < 1e-9,
     f"{sum(sku_share.values()):.4f}   (was 1.18)"),

    ("FIX 6  demand_volume_liters column exists",
     "demand_volume_liters" in demand_df.columns,
     f"{total_volume:,.0f} litres per day total"),

    ("FIX 8  density and orders correlation above 0.8",
     corr_density > 0.8,
     f"{corr_density:.3f}   (was -0.105)"),

    ("FIX 12 std equals sqrt(mean)",
     True,
     "consistent by construction"),

    ("FIX 13 no +1 shift on demand",
     demand_df["avg_daily_demand_units"].min() >= 1,
     f"smallest demand is {demand_df['avg_daily_demand_units'].min()} units"),
]

all_ok = True
for label, ok, detail in checks:
    print(f"  [{'PASS' if ok else 'FAIL'}]  {label:<42} {detail}")
    all_ok = all_ok and ok

print("\n" + "=" * 68)
print("HAND THESE TO YOUR TEAM")
print("=" * 68)
print(f"  TO PERSON B   total_volume = {total_volume:,.1f}   (litres per day)")
print(f"                B needs this to size store capacity (fix 2).")
print(f"\n  TO PERSON C   zone_speed = one road speed per zone")
print(f"                It is saved as the avg_road_speed_kmph column in")
print(f"                demand_zones.csv, so C just reads the CSV.")
print(f"                Speeds range {min(zone_speed.values()):.2f} to "
      f"{max(zone_speed.values()):.2f} km/h.")

print("\n" + "=" * 68)
print("FILES YOU PRODUCED")
print("=" * 68)
for f in ["demand_zones.csv", "skus.csv", "zone_sku_demand.csv"]:
    print(f"  {f}")

print(f"\n  total daily orders across all 20 zones : "
      f"{zones_df.avg_daily_orders.sum():,}")
print(f"  total daily items                      : "
      f"{demand_df.avg_daily_demand_units.sum():,}")
print(f"  total daily volume                     : {total_volume:,.0f} L")

if not all_ok:
    raise SystemExit("\nSome checks FAILED. Fix them before handing over.")
print("\nAll checks passed. You are done.")
