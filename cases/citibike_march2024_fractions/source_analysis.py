"""Describe the NYC Comptroller's archived Citi Bike station-status sample.

The input is a local Parquet file. This script never fetches or republishes the
operator's feed. Its unit is a station-snapshot row, not a station-minute or a
ride attempt. Run with Python 3.11, pyarrow 21.0.0 and tzdata 2026.4.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import timezone
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


REQUIRED = {
    "capacity": pa.int64(),
    "is_renting": pa.int64(),
    "is_returning": pa.int64(),
    "num_bikes_available": pa.int64(),
    "num_docks_available": pa.int64(),
    "station_id": pa.string(),
    "last_updated": pa.timestamp("us", tz="US/Eastern"),
}
SOURCE_COMMIT = "4c36513cf3842efe9a2940a78974bf45cb13fc0b"
SOURCE_BLOB_SHA1 = "6efe8e7cbf30591af1b9f4614be60a35650facdf"
SAMPLE_SHA256 = "661221e1f6fc01ba6475cee61597e432fc0858689195b6c12255a6c005b52fc4"


def _count(mask: Any) -> int:
    return int(pc.sum(pc.cast(mask, pa.int64())).as_py())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def analyze(path: Path) -> dict[str, Any]:
    actual_sha256 = _sha256(path)
    if actual_sha256 != SAMPLE_SHA256:
        raise ValueError("input SHA-256 differs from the pinned sample")
    table = pq.read_table(path)
    if table.num_rows == 0:
        raise ValueError("sample is empty")
    for name, expected_type in REQUIRED.items():
        if name not in table.column_names or table.schema.field(name).type != expected_type:
            raise ValueError(f"sample column {name} is absent or has the wrong type")
        if table[name].null_count:
            raise ValueError(f"sample column {name} contains nulls")
    if _count(pc.equal(table["station_id"], "")):
        raise ValueError("sample contains an empty station ID")
    pairs = table.group_by(["last_updated", "station_id"]).aggregate([("capacity", "count")])
    if pairs.num_rows != table.num_rows:
        raise ValueError("sample repeats a station and snapshot timestamp")

    renting = table["is_renting"]
    returning = table["is_returning"]
    capacity = table["capacity"]
    bikes = table["num_bikes_available"]
    docks = table["num_docks_available"]
    binary_flags = pc.and_(
        pc.is_in(renting, value_set=pa.array([0, 1], type=pa.int64())),
        pc.is_in(returning, value_set=pa.array([0, 1], type=pa.int64())),
    )
    if _count(pc.invert(binary_flags)):
        raise ValueError("sample has nonbinary rental or return flags")
    positive_capacity = pc.greater(capacity, 0)
    nonnegative_counts = pc.and_(pc.greater_equal(bikes, 0), pc.greater_equal(docks, 0))
    individual_fit = pc.and_(pc.less_equal(bikes, capacity), pc.less_equal(docks, capacity))
    combined_fit = pc.less_equal(pc.add_checked(bikes, docks), capacity)
    conservative_dock_rows = pc.and_(
        positive_capacity, pc.and_(nonnegative_counts, pc.and_(individual_fit, combined_fit))
    )
    denominator = _count(conservative_dock_rows)
    if denominator == 0:
        raise ValueError("no station-snapshot rows pass the declared quality rule")
    rental_rows = _count(pc.and_(conservative_dock_rows,
                                 pc.and_(pc.equal(renting, 1), pc.greater(bikes, 0))))
    return_rows = _count(pc.and_(conservative_dock_rows,
                                 pc.and_(pc.equal(returning, 1), pc.greater(docks, 0))))

    by_snapshot = table.group_by("last_updated").aggregate([("station_id", "count")])
    timestamps = sorted(by_snapshot["last_updated"].to_pylist())
    gaps = [(later - earlier).total_seconds()
            for earlier, later in zip(timestamps, timestamps[1:])]
    station_counts = by_snapshot["station_id_count"].to_pylist()

    def utc(value: Any) -> str:
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    return {
        "classification": "published_historical_station_snapshot_analysis_development",
        "source": f"https://github.com/NYCComptroller/citi-bike-gbfs/blob/{SOURCE_COMMIT}/dataset.parquet",
        "source_git_blob_sha1": SOURCE_BLOB_SHA1,
        "input_sha256": actual_sha256,
        "input_bytes": path.stat().st_size,
        "rows": table.num_rows,
        "snapshot_count": len(timestamps),
        "station_id_count": int(pc.count_distinct(table["station_id"]).as_py()),
        "first_snapshot_utc": utc(timestamps[0]),
        "last_snapshot_utc": utc(timestamps[-1]),
        "rows_per_snapshot_min": min(station_counts),
        "rows_per_snapshot_max": max(station_counts),
        "gaps_over_30_minutes": sum(gap > 1800 for gap in gaps),
        "largest_gap_seconds": int(max(gaps, default=0)),
        "quality": {
            "nonpositive_capacity_rows": _count(pc.invert(positive_capacity)),
            "negative_available_count_rows": _count(pc.invert(nonnegative_counts)),
            "bike_count_above_capacity_rows": _count(pc.greater(bikes, capacity)),
            "dock_count_above_capacity_rows": _count(pc.greater(docks, capacity)),
            "bike_plus_dock_above_capacity_rows": _count(pc.invert(combined_fit)),
            "conservative_dock_rows": denominator,
            "excluded_rows": table.num_rows - denominator,
        },
        "snapshot_row_service": {
            "denominator": denominator,
            "rental_enabled_with_bike": rental_rows,
            "return_enabled_with_dock": return_rows,
        },
        "scope_limits": [
            "Historical sample spans March 2024, not the June 2026 documentary case.",
            "Irregular snapshots are not weighted as station-minutes.",
            "The sample has no station-level last_reported or attempted rides.",
            "Integer 0/1 flags are accepted only for this archived Parquet schema; this does not validate a live GBFS feed.",
            "Feed availability is neither realized user access nor an intervention effect.",
        ],
        "criterion_5": "not_assessed",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sample", type=Path)
    args = parser.parse_args(argv)
    try:
        report = analyze(args.sample)
    except (OSError, ValueError, pa.ArrowException) as exc:
        print(f"Citi Bike sample analysis failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
