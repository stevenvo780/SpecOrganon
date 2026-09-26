"""Rebuild the exposed D-E development packet from a pinned public UCI ZIP.

Usage: python scripts/build_energy_case.py --archive /path/to/uci-374.zip
       --output-dir cases/building_energy
The original archive is not committed; only the deterministic seven-day slice is.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import zipfile
from datetime import datetime, timedelta
from pathlib import Path


SOURCE_URL = "https://archive.ics.uci.edu/static/public/374/appliances+energy+prediction.zip"
SOURCE_DOI = "https://doi.org/10.24432/C5VC8G"
ARCHIVE_SHA256 = "2fccf354445d886e7917620b0195db1f3e3e34d5a067a93b844694a4c561255a"
MEMBER_NAME = "energydata_complete.csv"
MEMBER_SHA256 = "2820bf712ad0275cb18b85a05250926100d8e65ebb9f4d2d016ca91ea152a25d"
EXPECTED_COLUMNS = (
    "date", "Appliances", "lights", "T1", "RH_1", "T2", "RH_2", "T3", "RH_3",
    "T4", "RH_4", "T5", "RH_5", "T6", "RH_6", "T7", "RH_7", "T8", "RH_8",
    "T9", "RH_9", "T_out", "Press_mm_hg", "RH_out", "Windspeed", "Visibility",
    "Tdewpoint", "rv1", "rv2",
)


class CaseBuildError(ValueError):
    """The archive or deterministic sample cannot support this packet."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def first_complete_week(member: bytes, *, expected_columns: tuple[str, ...] = EXPECTED_COLUMNS
                        ) -> tuple[bytes, datetime, datetime, int]:
    """Select seven whole calendar days after the first partial day, preserving CSV bytes."""
    try:
        lines = member.decode("utf-8-sig").splitlines(keepends=True)
    except UnicodeDecodeError as exc:
        raise CaseBuildError("CSV is not UTF-8") from exc
    if len(lines) < 2:
        raise CaseBuildError("CSV has no observations")
    parsed = [list(csv.reader([line])) for line in lines]
    if any(len(item) != 1 for item in parsed):
        raise CaseBuildError("CSV has a multiline or malformed record")
    header = tuple(parsed[0][0])
    if header != expected_columns:
        raise CaseBuildError("CSV columns differ from the pinned source schema")
    timestamps: list[datetime] = []
    for index, item in enumerate(parsed[1:], 1):
        row = item[0]
        if len(row) != len(header):
            raise CaseBuildError(f"CSV row {index} has wrong column count")
        try:
            timestamps.append(datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S"))
        except ValueError as exc:
            raise CaseBuildError(f"CSV row {index} has invalid date") from exc
    if timestamps != sorted(timestamps) or len(timestamps) != len(set(timestamps)):
        raise CaseBuildError("CSV timestamps are not strictly ordered and unique")
    first = timestamps[0]
    start = first.replace(hour=0, minute=0, second=0)
    if first != start:
        start += timedelta(days=1)
    end = start + timedelta(days=7)
    selected = [(timestamp, line) for timestamp, line in zip(timestamps, lines[1:], strict=True)
                if start <= timestamp < end]
    expected_times = [start + timedelta(minutes=10 * index) for index in range(7 * 24 * 6)]
    if [timestamp for timestamp, _ in selected] != expected_times:
        raise CaseBuildError("first seven complete days lack uninterrupted ten-minute observations")
    # The source has no quoted line breaks; retain every selected row's original bytes.
    sample = lines[0].encode("utf-8") + b"".join(line.encode("utf-8") for _, line in selected)
    return sample, start, end, len(selected)


def build(archive: Path, output_dir: Path, *, archive_sha256: str = ARCHIVE_SHA256,
          member_sha256: str = MEMBER_SHA256) -> dict[str, object]:
    raw = archive.read_bytes()
    if sha256(raw) != archive_sha256:
        raise CaseBuildError("source ZIP SHA-256 does not match the pinned archive")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zipped:
            if zipped.namelist() != [MEMBER_NAME]:
                raise CaseBuildError("source ZIP members differ from the pinned archive")
            member = zipped.read(MEMBER_NAME)
    except (zipfile.BadZipFile, RuntimeError) as exc:
        raise CaseBuildError("source ZIP cannot be read") from exc
    if sha256(member) != member_sha256:
        raise CaseBuildError("source CSV SHA-256 does not match the pinned member")
    sample, start, end, count = first_complete_week(member)
    manifest: dict[str, object] = {
        "schema": 1,
        "classification": "development_public_observational_case_not_an_intervention",
        "source": {
            "title": "Appliances Energy Prediction",
            "publisher": "UCI Machine Learning Repository",
            "creator": "Luis Candanedo",
            "doi": SOURCE_DOI,
            "url": SOURCE_URL,
            "license": "CC BY 4.0",
            "archive_sha256": archive_sha256,
            "member": MEMBER_NAME,
            "member_sha256": member_sha256,
        },
        "selection": {
            "rule": "first seven whole calendar days after the source's partial opening day",
            "start_inclusive": start.isoformat(sep=" "),
            "end_exclusive": end.isoformat(sep=" "),
            "timestamp_timezone": "not specified by source CSV",
            "interval_minutes": 10,
            "rows": count,
            "columns": list(EXPECTED_COLUMNS),
            "sample_sha256": sha256(sample),
        },
        "limits": [
            "One observed low-energy house, not a sample of buildings or a causal trial.",
            "The excerpt is seven days; no intervention, control assignment, occupancy, costs or harms are observed.",
            "Weather data include interpolated hourly airport observations according to the UCI record.",
            "The two rv columns are random variables for model diagnostics, not intervention variables.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    targets = {
        output_dir / "sample_first_complete_week.csv": sample,
        output_dir / "source_manifest.json": (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
    }
    for path, data in targets.items():
        if path.exists() and path.read_bytes() != data:
            raise CaseBuildError(f"refusing to overwrite different existing file: {path}")
    for path, data in targets.items():
        if not path.exists():
            path.write_bytes(data)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        manifest = build(args.archive, args.output_dir)
    except (CaseBuildError, OSError) as exc:
        print(f"energy case build failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"rows": manifest["selection"]["rows"],
                      "sample_sha256": manifest["selection"]["sample_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
