"""Feasibility probe: CAISO April net-load trough and evening ramp by year.

Downloads two EIA-930 tables from Catalyst Cooperative's PUDL release and
prints the figures quoted in catalog entry `caiso-net-load-ramp`.

Usage: python probes/caiso_net_load_ramp.py [--release stable] [--data-dir DIR]
Needs: pip install duckdb. Network: s3.us-west-2.amazonaws.com. Downloads ~170 MB.
"""

import argparse
import json
import urllib.request
from pathlib import Path

import duckdb

BASE = "https://s3.us-west-2.amazonaws.com/pudl.catalyst.coop"
TABLES = ("core_eia930__hourly_operations", "core_eia930__hourly_net_generation_by_energy_source")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", default="stable")
    parser.add_argument("--data-dir", type=Path, default=Path.home() / ".cache/portfolio-atlas/pudl")
    args = parser.parse_args()
    args.data_dir.mkdir(parents=True, exist_ok=True)
    for name in (*TABLES, "pudl_parquet_datapackage"):
        ext = "json" if name.endswith("datapackage") else "parquet"
        target = args.data_dir / f"{name}.{ext}"
        if not target.exists():
            urllib.request.urlretrieve(f"{BASE}/{args.release}/{name}.{ext}", target)
    package = json.loads((args.data_dir / "pudl_parquet_datapackage.json").read_text())
    print(f"PUDL version {package['version']} created {package['created']}; licenses: {[x['name'] for x in package['licenses']]}")

    ops, gen = (str(args.data_dir / f"{t}.parquet") for t in TABLES)
    for t in TABLES:
        print(f"{t}.parquet: {(args.data_dir / f'{t}.parquet').stat().st_size / 1e6:.1f} MB")
    con = duckdb.connect()
    print(con.sql(f"select count(*) rows_, min(datetime_utc), max(datetime_utc), count(distinct balancing_authority_code_eia) bas from '{ops}'"))
    print(con.sql(f"select count(*) rows_, count(net_generation_reported_mwh) reported, count(net_generation_adjusted_mwh) adjusted, "
                  f"count(net_generation_imputed_eia_mwh) imputed from '{gen}'"))
    print("CAISO wind, solar and storage categories (non-null adjusted values):")
    print(con.sql(f"""select generation_energy_source,
        min(datetime_utc) filter (where net_generation_adjusted_mwh is not null)::date first_hour,
        max(datetime_utc) filter (where net_generation_adjusted_mwh is not null)::date last_hour,
        count(net_generation_adjusted_mwh) adjusted, count(net_generation_imputed_eia_mwh) imputed
        from '{gen}' where balancing_authority_code_eia = 'CISO' and regexp_matches(generation_energy_source, '^(solar|wind)|storage')
        group by 1 order by 1"""))
    print(con.sql(f"""select count(*) hours_with_old_and_new_categories from (
        select datetime_utc from '{gen}' where balancing_authority_code_eia = 'CISO' and net_generation_adjusted_mwh is not null
        group by 1 having count(*) filter (where generation_energy_source in ('solar', 'wind')) > 0
                       and count(*) filter (where generation_energy_source like '%integrated_battery_storage') > 0)"""))

    # Old ('solar', 'wind') and new ('*_w_/wo_integrated_battery_storage') categories never overlap
    # in time for CAISO (see output above), so summing all of them per hour does not double count.
    con.sql(f"""create table vre as select datetime_utc, sum(net_generation_adjusted_mwh) mwh from '{gen}'
        where balancing_authority_code_eia = 'CISO' and regexp_matches(generation_energy_source, '^(solar|wind)') group by 1""")
    con.sql(f"""create table h as
        select timezone('America/Los_Angeles', timezone('UTC', o.datetime_utc)) local_time, o.demand_adjusted_mwh - vre.mwh net_load
        from '{ops}' o join vre using (datetime_utc)
        where o.balancing_authority_code_eia = 'CISO' and o.demand_adjusted_mwh is not null and vre.mwh is not null""")
    print("CAISO, April, adjusted values, local time. Trough = min net load 09-16h; ramp = max 17-22h minus trough:")
    print(con.sql("""with daily as (
            select year(local_time) yr, local_time::date d,
                   min(net_load) filter (where hour(local_time) between 9 and 16) trough,
                   max(net_load) filter (where hour(local_time) between 17 and 22) evening_peak
            from h where month(local_time) = 4 group by 1, 2 having count(*) >= 23)
        select yr, count(*) complete_days, round(avg(trough)) avg_trough_mw, round(avg(evening_peak)) avg_evening_peak_mw,
               round(avg(evening_peak - trough)) avg_ramp_mw
        from daily group by yr order by yr"""))


if __name__ == "__main__":
    main()
