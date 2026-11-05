"""Feasibility probe: Citi Bike station imbalance (net flow) for one month.

Downloads one monthly NYC trip file and prints the figures quoted in catalog
entry `citibike-station-imbalance`. Also prints the header of an older file to
show the 2019 -> 2021 schema change.

Usage: python probes/citibike_station_imbalance.py [--month 202604] [--data-dir DIR]
Needs: pip install duckdb. Network: s3.amazonaws.com. Downloads ~165 MB.
"""

import argparse
import io
import re
import urllib.request
import zipfile
from pathlib import Path

import duckdb

BUCKET = "https://s3.amazonaws.com/tripdata"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--month", default="202604")
    parser.add_argument("--data-dir", type=Path, default=Path.home() / ".cache/portfolio-atlas/citibike")
    args = parser.parse_args()
    folder = args.data_dir / args.month
    if not folder.exists():
        folder.mkdir(parents=True)
        archive = folder / "trips.zip"
        urllib.request.urlretrieve(f"{BUCKET}/{args.month}-citibike-tripdata.zip", archive)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(folder)
        archive.unlink()

    with urllib.request.urlopen(f"{BUCKET}?list-type=2") as resp:  # bucket listing (fits in one page)
        listing = resp.read().decode()
    files = re.findall(r"<Key>(\d{6}-citibike-tripdata[^<]*)</Key><LastModified>([^<]{10})[^<]*</LastModified>.*?<Size>(\d+)</Size>", listing)
    for key, uploaded, size in files[-8:]:
        print(f"bucket: {key} uploaded {uploaded} {int(size) / 1e6:.1f} MB")

    for legacy in ("JC-201909-citibike-tripdata.csv.zip", "JC-202102-citibike-tripdata.csv.zip"):
        with urllib.request.urlopen(f"{BUCKET}/{legacy}") as resp, zipfile.ZipFile(io.BytesIO(resp.read())) as zf:
            name = next(n for n in zf.namelist() if n.endswith(".csv") and "MACOSX" not in n)
            print(f"{legacy} header: {zf.open(name).readline().decode().strip()}")

    con = duckdb.connect()
    csvs = str(folder / "**" / "*.csv")
    con.sql(f"create table t as select * from read_csv('{csvs}', types={{'start_station_id': 'VARCHAR', 'end_station_id': 'VARCHAR'}})")
    print(con.sql("select count(*) trips, count(distinct ride_id) unique_ids, min(started_at), max(started_at), "
                  "count(distinct started_at::date) days_present, count(distinct start_station_id) start_station_ids from t"))
    print(con.sql("select count(*) filter (where end_station_id is null) no_end_station, "
                  "count(*) filter (where start_station_id is null) no_start_station, "
                  "count(*) filter (where ended_at - started_at > interval 1 day) over_24h, "
                  "round(100.0 * count(*) filter (where rideable_type = 'electric_bike') / count(*), 1) pct_ebike from t"))
    print(con.sql("select start_station_name, list(distinct start_station_id) ids from t "
                  "group by 1 having count(distinct start_station_id) > 1"))

    print(con.sql("select count(*) filter (where not regexp_full_match(end_station_id, '[0-9]+\\.[0-9]+')) trips_ending_at_nonstandard_ids "
                  "from t where end_station_id is not null"))
    print(con.sql("select end_station_id, any_value(end_station_name) name, count(*) trips from t "
                  "where not regexp_full_match(end_station_id, '[0-9]+\\.[0-9]+') group by 1 order by trips desc limit 6"))
    print(con.sql("select count(*) names_with_several_end_ids from (select end_station_name from t where end_station_id is not null "
                  "group by 1 having count(distinct end_station_id) > 1)"))
    print(con.sql("select end_station_name, list(distinct end_station_id) ids, count(*) trips from t where end_station_id is not null "
                  "group by 1 having count(distinct end_station_id) > 1 order by trips desc limit 5"))

    # Station events (departure = -1, arrival = +1), limited to the month itself: trips that end
    # after midnight on the last day would otherwise add a stray day from the next month.
    # Key on station *name*: the raw IDs are inconsistent for the same station (e.g. 6098.10 vs 6098.1).
    con.sql("""create table ev as
        with month as (select date_trunc('month', min(started_at)) m0 from t)
        select * from (
            select start_station_name station, start_station_id sid, started_at ts, -1 delta from t where start_station_id is not null
            union all
            select end_station_name, end_station_id, ended_at, 1 from t where end_station_id is not null)
        where ts >= (select m0 from month) and ts < (select m0 from month) + interval 1 month""")
    weekdays = con.sql("select count(distinct ts::date) from ev where dayofweek(ts) between 1 and 5").fetchall()[0][0]
    peak = "dayofweek(ts) between 1 and 5 and hour(ts) between 7 and 9"
    for order, label in (("asc", "drain (net outflow)"), ("desc", "fill (net inflow)")):
        print(f"Weekday 07:00-09:59 stations that {label}, per weekday ({weekdays} weekdays):")
        print(con.sql(f"select station, round(sum(delta) / {weekdays}, 1) net_per_weekday from ev "
                      f"where {peak} group by 1 order by sum(delta) {order} limit 5"))
    for key in ("station", "sid"):
        print(f"Average daily net imbalance, sum(|net|)/2 over stations keyed by {key}:")
        print(con.sql(f"""with daily as (select ts::date d, {key}, sum(delta) net from ev group by 1, 2)
            select round(avg(moves)) avg_bikes_per_day from (select d, sum(abs(net)) / 2 moves from daily group by 1)"""))


if __name__ == "__main__":
    main()
