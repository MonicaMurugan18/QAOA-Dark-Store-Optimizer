"""
Corrected Puducherry dataset generator (v2).

Rewrite of `generate_dataset_pondicherry.py` fixing the twelve problems found in
the audit. Every change is marked with  # FIX n  and explained.

Output: data_pondicherry/  (full 10x20 instance, for classical baselines)
        data_pondicherry/sub/  (4x5 sub-instance, small enough for QAOA)

Run:  python generate_pondicherry_v2.py
"""

import itertools
import math
import os

import numpy as np
import pandas as pd

OUT = "data_pondicherry"
SUB = os.path.join(OUT, "sub")
os.makedirs(SUB, exist_ok=True)

# One modern, explicitly-seeded generator. The original used the legacy global
# np.random.seed(42); default_rng is the current API and keeps state local.
RNG = np.random.default_rng(42)


# ---------------------------------------------------------------------------
# GLOBAL PARAMETERS -- every magic number now has a name and a justification
# ---------------------------------------------------------------------------
ITEMS_PER_ORDER      = 5.0    # FIX 1: a quick-commerce basket, 4-6 items
HANDLING_MIN         = 3.0    # FIX 3: picking + packing before the rider leaves
SERVICE_PROMISE_MIN  = 15.0   # FIX 9: the SLA the whole problem hinges on

# FIX 15: how big one store is, relative to the whole city's demand.
#
# The first version of this fix set TOTAL capacity across all candidates to
# 2.2x total demand. That was the wrong knob. Spread over 11 candidates it made
# each store hold only 0.14-0.28x of demand, so capacity FORCED nine or ten
# stores open and there was no siting decision left to make.
#
# What matters is the size of one store against the demand a minimal set of
# stores has to carry. We compute the smallest number of stores that can cover
# every zone inside the SLA (K), then size a store at demand/K plus headroom.
# Coverage and capacity then bind at the same point, which is the regime where
# the choice of WHICH stores is actually hard.
CAPACITY_HEADROOM    = 1.25   # a minimal cover runs at about 80% full
CIRCUITY_FACTOR      = 1.30   # straight-line -> road distance
RENT_PER_SQFT_BASE   = 35.0   # FIX 6: INR / sqft / month, Puducherry
SETUP_PER_SQFT       = (280.0, 360.0)   # FIX 6: INR / sqft one-time fit-out
AMORTISE_MONTHS      = 36     # FIX 10: 3-year horizon for the setup cost
DAYS_PER_MONTH       = 30.4

# FIX 16: running a dark store is mostly PEOPLE, not rent.
#
# The first version costed a store at rent + amortised fit-out only, giving
# Rs 1,560-3,633 per day. Delivering to one zone costs Rs 1,624-9,348 per day.
# So opening another store was cheaper than driving further, and the optimiser
# correctly opened all eleven -- there was no trade-off to solve.
#
# A real dark store runs 6-12 pickers, packers and a supervisor, plus power and
# cold chain for the perishables. Those dominate rent by 3-4x. Adding them puts
# a store at Rs 5,300-10,700 per day, which is the same scale as the hand-built
# Chennai instance (Rs 7,000-12,000) and restores the trade-off.
STAFF_PER_1000_SQFT      = 6.0      # pickers + packers + supervisor
MONTHLY_WAGE_INR         = 16000.0  # Puducherry warehouse wage
UTILITIES_PER_SQFT_MONTH = 22.0     # power, refrigeration, packaging
AVG_SPEED_KMPH       = {"commercial": 18, "residential": 24, "mixed": 21}

TOWN_CENTRE = (11.9330, 79.8340)     # White Town, for the rent gradient


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# 1. DEMAND ZONES  (built first now -- capacity has to be sized against demand)
# ---------------------------------------------------------------------------
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
    # FIX 14: DS10 Villianur could not reach a single zone inside the SLA, so
    # it was a candidate nobody could ever use -- a variable that costs a qubit
    # and can only ever be zero. Villianur is a real populated commune, so the
    # honest fix is to admit it has customers, not to delete the site.
    ("Z21", "Villianur",          11.9500, 79.7500, "residential"),
]

# FIX 7: density is no longer decorative. Orders are DERIVED from it, so the
# column earns its place and the correlation is real by construction.
ZONE_TYPE_ORDER_MULT = {"commercial": 1.30, "mixed": 1.00, "residential": 0.85}
ORDERS_PER_DENSITY   = 1 / 60.0          # 15,000 people/sqkm -> ~250 orders/day

zone_rows = []
zone_speed = {}
for zid, name, lat, lon, ztype in demand_zones:
    density = int(RNG.integers(5000, 20000))
    orders = int(round(density * ORDERS_PER_DENSITY
                       * ZONE_TYPE_ORDER_MULT[ztype]
                       * RNG.uniform(0.90, 1.10)))
    # FIX 8: one speed per ZONE, drawn once. The original drew a fresh speed for
    # every (site, zone) pair, which made travel time not a function of distance
    # and broke the triangle inequality.
    zone_speed[zid] = AVG_SPEED_KMPH[ztype] * RNG.uniform(0.92, 1.08)
    zone_rows.append([zid, name, lat, lon, ztype, density, orders,
                      round(zone_speed[zid], 2)])

zones_df = pd.DataFrame(zone_rows, columns=[
    "zone_id", "area_name", "latitude", "longitude", "zone_type",
    "population_density_per_sqkm", "avg_daily_orders", "avg_road_speed_kmph"])


# ---------------------------------------------------------------------------
# 2. SKU CATALOG
# ---------------------------------------------------------------------------
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

# FIX 4: the original applied the whole category share to EVERY SKU in that
# category. Dairy has two SKUs, so the shares summed to 1.18 instead of 1.00.
# Split each category's share evenly across its members.
n_in_category = sku_df["category"].value_counts().to_dict()
sku_share = {s[0]: CATEGORY_SHARE[s[2]] / n_in_category[s[2]] for s in skus}
assert abs(sum(sku_share.values()) - 1.0) < 1e-9, "SKU shares must sum to 1"
sku_df["demand_share"] = sku_df["sku_id"].map(sku_share)


# ---------------------------------------------------------------------------
# 3. ZONE x SKU DEMAND
# ---------------------------------------------------------------------------
vol_of = dict(zip(sku_df["sku_id"], sku_df["unit_volume_liters"]))

dem_rows = []
for zid, name, lat, lon, ztype in demand_zones:
    orders = int(zones_df.loc[zones_df.zone_id == zid, "avg_daily_orders"].iloc[0])
    for sid in sku_df["sku_id"]:
        # FIX 1: units = orders x basket size x SKU share. The original divided
        # by an unexplained 10, which produced 0.1-0.25 items per order.
        mean_units = orders * ITEMS_PER_ORDER * sku_share[sid]
        # FIX 12: no "+1" shift. That inflated every mean by one unit.
        units = max(1, int(RNG.poisson(mean_units)))
        # FIX 11: std is now the Poisson std of the process that generated it,
        # not an unrelated 15-35% of the realised value.
        dem_rows.append([zid, sid, units, round(math.sqrt(mean_units), 2),
                         round(units * vol_of[sid], 2)])

demand_df = pd.DataFrame(dem_rows, columns=[
    "zone_id", "sku_id", "avg_daily_demand_units", "demand_std_dev",
    "demand_volume_liters"])                       # FIX 5: volume now carried

zone_volume = demand_df.groupby("zone_id")["demand_volume_liters"].sum()
TOTAL_VOLUME = float(zone_volume.sum())


# ---------------------------------------------------------------------------
# 4. CANDIDATE DARK STORES
# ---------------------------------------------------------------------------
# FIX 3: sites are candidate PLOTS near a neighbourhood, not the neighbourhood
# centroid itself. A fixed small offset stops nine of ten sites landing exactly
# on a demand zone and producing 0.00-minute deliveries.
SITE_OFFSET_DEG = 0.0035          # about 390 m

candidate_sites = [
    ("DS01", "White Town",     11.9330, 79.8340), ("DS02", "Muthialpet",     11.9380, 79.8280),
    ("DS03", "Lawspet",        11.9600, 79.8100), ("DS04", "Kalapet",        12.0080, 79.8390),
    ("DS05", "Ariyankuppam",   11.8850, 79.8080), ("DS06", "Ozhukarai",      11.9500, 79.7900),
    ("DS07", "Reddiarpalayam", 11.9450, 79.8000), ("DS08", "Mudaliarpet",    11.9150, 79.8100),
    ("DS09", "Thattanchavady", 11.9600, 79.8300), ("DS10", "Villianur",      11.9500, 79.7500),
    # FIX 13: the original ten sites left Z20 (Auroville Fringe) with no server
    # inside the 15-minute promise -- its nearest plot was 15.13 min, eight
    # seconds over. An unreachable zone makes the instance ill posed, so add a
    # real candidate at Kuilapalayam, the village on Auroville's edge.
    ("DS11", "Kuilapalayam",   11.9958, 79.8175),
]

sqft_choices = [1000, 1200, 1500, 1800, 2000]
site_raw = []
for i, (sid, name, lat, lon) in enumerate(candidate_sites):
    angle = 2 * math.pi * i / len(candidate_sites)
    slat = lat + SITE_OFFSET_DEG * math.cos(angle)
    slon = lon + SITE_OFFSET_DEG * math.sin(angle)
    sqft = int(RNG.choice(sqft_choices))
    site_raw.append([sid, name + " (plot)", round(slat, 5), round(slon, 5), sqft])

total_sqft = sum(r[4] for r in site_raw)

site_rows = []
for sid, name, slat, slon, sqft in site_raw:
    # FIX 6: rent is a price per sqft times a distance-to-centre premium, not an
    # independent random draw. The original had corr(rent, sqft) = 0.26 and made
    # a 1,200 sqft plot cost more than a 2,000 sqft one.
    d_centre = haversine_km(slat, slon, *TOWN_CENTRE)
    premium = float(np.clip(1.35 - 0.05 * d_centre, 0.80, 1.35))
    rent = int(round(sqft * RENT_PER_SQFT_BASE * premium * RNG.uniform(0.95, 1.05) / 100) * 100)
    setup = int(round(sqft * RNG.uniform(*SETUP_PER_SQFT) / 1000) * 1000)

    # FIX 16: the running cost of a store is staff + utilities + rent, not rent
    # alone. Staff scales with floor area because a bigger store picks more
    # orders in parallel.
    staff = int(round(sqft / 1000.0 * STAFF_PER_1000_SQFT))
    staff_cost = staff * MONTHLY_WAGE_INR
    utilities = sqft * UTILITIES_PER_SQFT_MONTH

    # FIX 10: one comparable number. Monthly costs and a one-time fit-out cannot
    # be added together without an amortisation horizon; state it explicitly.
    daily_open = round((rent + staff_cost + utilities) / DAYS_PER_MONTH
                       + setup / (AMORTISE_MONTHS * DAYS_PER_MONTH), 2)

    site_rows.append([sid, name, slat, slon, sqft, round(d_centre, 2),
                      round(premium, 3), rent, staff, int(staff_cost),
                      int(utilities), setup, daily_open])

sites_df = pd.DataFrame(site_rows, columns=[
    "site_id", "area_name", "latitude", "longitude", "capacity_sqft",
    "km_to_town_centre", "location_premium", "monthly_rent_inr",
    "staff_count", "monthly_staff_inr", "monthly_utilities_inr",
    "setup_cost_inr", "daily_opening_cost_inr"])
# Capacity is deliberately NOT set here. It depends on the SLA coverage
# structure, which does not exist until the travel matrix is built. See
# section 5b.


# ---------------------------------------------------------------------------
# 5. TRAVEL TIME MATRIX
# ---------------------------------------------------------------------------
tt_rows = []
for _, s in sites_df.iterrows():
    for zid, zname, zlat, zlon, ztype in demand_zones:
        road_km = haversine_km(s.latitude, s.longitude, zlat, zlon) * CIRCUITY_FACTOR
        # FIX 3: every delivery costs picking time, so no pair can be 0 minutes.
        # FIX 8: speed comes from the zone, so time is a function of distance.
        minutes = HANDLING_MIN + (road_km / zone_speed[zid]) * 60.0
        tt_rows.append([s.site_id, zid, round(road_km, 3), round(minutes, 2),
                        bool(minutes <= SERVICE_PROMISE_MIN)])

travel_df = pd.DataFrame(tt_rows, columns=[
    "site_id", "zone_id", "road_distance_km", "delivery_time_min",
    "within_sla"])                                  # FIX 9: the SLA is in the data

site_dist = [[a.site_id, b.site_id,
              round(haversine_km(a.latitude, a.longitude,
                                 b.latitude, b.longitude) * CIRCUITY_FACTOR, 3)]
             for i, a in sites_df.iterrows()
             for j, b in sites_df.iterrows() if i < j]
site_dist_df = pd.DataFrame(site_dist,
                            columns=["site_id_a", "site_id_b", "road_distance_km"])


# ---------------------------------------------------------------------------
# 5b. STORE CAPACITY  (FIX 15 -- must come after the SLA matrix exists)
#
# Find K, the smallest number of stores whose SLA reach covers every zone. Then
# size one store at demand/K plus headroom, so that a minimal cover can just
# carry the city. Below that, capacity forces extra stores open and the siting
# decision disappears; far above it, capacity stops binding at all.
# ---------------------------------------------------------------------------
reach = {s: set(travel_df.loc[(travel_df.site_id == s) & travel_df.within_sla,
                              "zone_id"])
         for s in sites_df.site_id}
all_zones = set(zones_df.zone_id)

# FIX 14: a candidate that can reach nothing is a variable that can only ever
# be zero. It costs a qubit and buys nothing, so refuse to ship one.
dead = [s for s, r in reach.items() if not r]
assert not dead, f"candidate sites that reach no zone inside the SLA: {dead}"

K = None
for k in range(1, len(sites_df) + 1):
    if any(set().union(*[reach[s] for s in combo]) == all_zones
           for combo in itertools.combinations(sites_df.site_id, k)):
        K = k
        break
assert K is not None, "no set of sites covers every zone -- instance is broken"

mean_cap = TOTAL_VOLUME / K * CAPACITY_HEADROOM
sites_df["daily_capacity_liters"] = (
    (mean_cap * len(sites_df) * sites_df.capacity_sqft / total_sqft / 25)
    .round() * 25)


# ---------------------------------------------------------------------------
# 6. WRITE, THEN CHECK
# ---------------------------------------------------------------------------
def write(df, name, folder=OUT):
    df.to_csv(os.path.join(folder, name), index=False)


write(sites_df, "candidate_dark_stores.csv")
write(zones_df, "demand_zones.csv")
write(sku_df, "skus.csv")
write(demand_df, "zone_sku_demand.csv")
write(travel_df, "travel_time_matrix.csv")
write(site_dist_df, "site_to_site_distance.csv")


def rule(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


rule("WHAT CHANGED -- VERIFICATION OF EACH FIX")

units = demand_df.groupby("zone_id")["avg_daily_demand_units"].sum()
per_order = (units / zones_df.set_index("zone_id")["avg_daily_orders"])
print(f"FIX 1  items per order         : {per_order.min():.2f} - {per_order.max():.2f}"
      f"   (was 0.10 - 0.25)")
print(f"FIX 2  capacity / demand       : "
      f"{sites_df.daily_capacity_liters.sum() / TOTAL_VOLUME:.2f}x"
      f"   (was 283.9x)")
print(f"       largest single store    : "
      f"{sites_df.daily_capacity_liters.max() / TOTAL_VOLUME:.2f}x of total demand"
      f"  -> at least "
      f"{int(np.ceil(TOTAL_VOLUME / sites_df.daily_capacity_liters.max()))} stores must open")
print(f"FIX 3  zero-time deliveries    : {int((travel_df.delivery_time_min == 0).sum())}"
      f"   (was 9)")
print(f"       fastest delivery        : {travel_df.delivery_time_min.min():.2f} min")
print(f"FIX 4  SKU shares sum          : {sku_df.demand_share.sum():.4f}   (was 1.18)")
print(f"FIX 5  demand volume carried   : yes, {TOTAL_VOLUME:,.0f} L/day total")
print(f"FIX 6  corr(rent, sqft)        : "
      f"{sites_df.monthly_rent_inr.corr(sites_df.capacity_sqft):.3f}   (was 0.262)")
print(f"       rent per sqft spread    : "
      f"{(sites_df.monthly_rent_inr / sites_df.capacity_sqft).min():.1f} - "
      f"{(sites_df.monthly_rent_inr / sites_df.capacity_sqft).max():.1f} INR"
      f"   (was 25.5 - 63.7)")
print(f"FIX 7  corr(density, orders)   : "
      f"{zones_df.population_density_per_sqkm.corr(zones_df.avg_daily_orders):.3f}"
      f"   (was -0.105)")
sp = travel_df.merge(zones_df[["zone_id", "zone_type"]], on="zone_id")
sp = sp[sp.delivery_time_min > HANDLING_MIN]
sp["kmph"] = sp.road_distance_km / ((sp.delivery_time_min - HANDLING_MIN) / 60)
print(f"FIX 8  implied speed spread    : within each zone, "
      f"{sp.groupby('zone_id')['kmph'].std().max():.4f} km/h"
      f"   (was up to 3.2 km/h)")
print(f"FIX 9  SLA column present      : yes, promise = {SERVICE_PROMISE_MIN:.0f} min")
print(f"FIX 10 daily opening cost      : Rs "
      f"{sites_df.daily_opening_cost_inr.min():,.0f} - "
      f"{sites_df.daily_opening_cost_inr.max():,.0f} per day")
# Rider economics, only used here to check the open-vs-deliver balance. The
# pipeline recomputes these itself from the CSVs.
RIDER_COST_PER_MIN = 3.0
zone_orders_map = np.ceil(
    demand_df.groupby("zone_id")["avg_daily_demand_units"].sum()
    / ITEMS_PER_ORDER).to_dict()

_deliv = travel_df[travel_df.within_sla].copy()
_deliv["cost"] = (RIDER_COST_PER_MIN * _deliv.delivery_time_min
                  * _deliv.zone_id.map(zone_orders_map))
_cheapest = _deliv.groupby("zone_id")["cost"].min()
print(f"FIX 16 open vs deliver balance : open Rs "
      f"{sites_df.daily_opening_cost_inr.mean():,.0f}/day  vs  deliver Rs "
      f"{_cheapest.mean():,.0f}/day per zone")
print(f"       ratio                   : "
      f"{sites_df.daily_opening_cost_inr.mean() / _cheapest.mean():.2f}x"
      f"   (was 0.57x -- opening was CHEAPER than delivering)")
print(f"       staff per store         : {sites_df.staff_count.min()}-"
      f"{sites_df.staff_count.max()} people, "
      f"{100 * sites_df.monthly_staff_inr.sum() / (sites_df.monthly_staff_inr + sites_df.monthly_rent_inr + sites_df.monthly_utilities_inr).sum():.0f}% "
      f"of monthly running cost")
print(f"FIX 11 std vs Poisson          : std = sqrt(mean), consistent by construction")
print(f"FIX 12 Poisson +1 shift        : removed")

rule("IS THE INSTANCE WELL POSED?")
n_pairs = int(travel_df.within_sla.sum())
cov = travel_df[travel_df.within_sla].groupby("zone_id")["site_id"].nunique()
print(f"SLA-feasible site-zone pairs : {n_pairs} of {len(travel_df)}")
print(f"zones with >= 1 server       : {len(cov)} of {len(demand_zones)}")
if len(cov) < len(demand_zones):
    missing = set(zones_df.zone_id) - set(cov.index)
    print(f"  UNREACHABLE ZONES          : {sorted(missing)}  <-- must be fixed")
print(f"servers per zone             : min {cov.min()}, median {cov.median():.0f}, "
      f"max {cov.max()}")
print(f"qubits for the full instance : {len(sites_df)} + {n_pairs} = "
      f"{len(sites_df) + n_pairs} decision bits, before auxiliaries")

print(f"\nFIX 14 dead candidate sites  : {len(dead)}   (was 1: DS10 Villianur)")
print(f"FIX 15 smallest SLA cover    : {K} stores")
covers = [c for c in itertools.combinations(sites_df.site_id, K)
          if set().union(*[reach[s] for s in c]) == all_zones]
cap_of = dict(zip(sites_df.site_id, sites_df.daily_capacity_liters))
fits = [c for c in covers if sum(cap_of[s] for s in c) >= TOTAL_VOLUME]
print(f"       {K}-store sets that cover    : {len(covers)}")
print(f"       ...and can also HOLD demand : {len(fits)}   "
      f"(was 0 -- capacity forced ~10 stores open)")
if fits:
    c = fits[0]
    print(f"       e.g. {'+'.join(c)}: "
          f"{TOTAL_VOLUME:,.0f} L into {sum(cap_of[s] for s in c):,.0f} L "
          f"({100 * TOTAL_VOLUME / sum(cap_of[s] for s in c):.0f}% full)")
print(f"       -> the real question is now WHICH {K}, not whether to open them all")


# ---------------------------------------------------------------------------
# 7. QAOA-SIZED SUB-INSTANCE
#    The full 10x20 needs ~70-110 qubits. Carve out a contiguous southern/central
#    block small enough to simulate, keeping the same schema.
# ---------------------------------------------------------------------------
SUB_SITES = ["DS01", "DS02", "DS07", "DS08"]
SUB_ZONES = ["Z01", "Z03", "Z05", "Z07", "Z16"]

sub_sites = sites_df[sites_df.site_id.isin(SUB_SITES)].copy()
sub_zones = zones_df[zones_df.zone_id.isin(SUB_ZONES)].copy()
sub_dem = demand_df[demand_df.zone_id.isin(SUB_ZONES)].copy()
sub_tt = travel_df[travel_df.site_id.isin(SUB_SITES)
                   & travel_df.zone_id.isin(SUB_ZONES)].copy()

# Re-size the sub-instance capacities against ITS OWN demand and ITS OWN
# coverage structure. Copying the parent's numbers would make the constraint
# stop binding on the smaller problem, which is bug 2 all over again.
sub_volume = sub_dem["demand_volume_liters"].sum()
sub_reach = {s: set(sub_tt.loc[(sub_tt.site_id == s) & sub_tt.within_sla,
                               "zone_id"])
             for s in SUB_SITES}
K_sub = next(k for k in range(1, len(SUB_SITES) + 1)
             if any(set().union(*[sub_reach[s] for s in c]) == set(SUB_ZONES)
                    for c in itertools.combinations(SUB_SITES, k)))
sub_mean_cap = sub_volume / K_sub * CAPACITY_HEADROOM
sub_sites["daily_capacity_liters"] = (
    (sub_mean_cap * len(SUB_SITES) * sub_sites.capacity_sqft
     / sub_sites.capacity_sqft.sum() / 25).round() * 25)

write(sub_sites, "candidate_dark_stores.csv", SUB)
write(sub_zones, "demand_zones.csv", SUB)
write(sku_df, "skus.csv", SUB)
write(sub_dem, "zone_sku_demand.csv", SUB)
write(sub_tt, "travel_time_matrix.csv", SUB)

rule("QAOA SUB-INSTANCE (4 sites x 5 zones)")
sub_pairs = int(sub_tt.within_sla.sum())
sub_cov = sub_tt[sub_tt.within_sla].groupby("zone_id")["site_id"].nunique()
print(f"SLA-feasible pairs : {sub_pairs} of {len(sub_tt)}")
print(f"zones covered      : {len(sub_cov)} of {len(SUB_ZONES)}")
print(f"demand volume      : {sub_volume:,.0f} L/day")
print(f"total capacity     : {sub_sites.daily_capacity_liters.sum():,.0f} L/day "
      f"({sub_sites.daily_capacity_liters.sum() / sub_volume:.2f}x)")
print(f"largest store      : {sub_sites.daily_capacity_liters.max():,.0f} L "
      f"-> at least "
      f"{int(np.ceil(sub_volume / sub_sites.daily_capacity_liters.max()))} stores must open")
print(f"qubits             : {len(SUB_SITES)} + {sub_pairs} = "
      f"{len(SUB_SITES) + sub_pairs}   (simulable)")

rule("SAVED")
for f in sorted(os.listdir(OUT)):
    if f.endswith(".csv"):
        print(f"  {OUT}/{f}")
for f in sorted(os.listdir(SUB)):
    print(f"  {SUB}/{f}")
