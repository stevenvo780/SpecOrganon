"""Data-selection controls for the exposed public building-energy case."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
from build_energy_case import CaseBuildError, build, first_complete_week  # noqa: E402


def sample_source() -> bytes:
    first = datetime(2026, 1, 1, 17)
    lines = [b'date,Appliances,lights\r\n']
    for index in range(42 + 7 * 24 * 6 + 1):
        timestamp = first + timedelta(minutes=10 * index)
        lines.append(f'{timestamp:%Y-%m-%d %H:%M:%S},{index},0\r\n'.encode())
    return b"".join(lines)


def test_selection_uses_first_complete_week_and_preserves_source_rows() -> None:
    source = sample_source()
    selected, start, end, count = first_complete_week(
        source, expected_columns=("date", "Appliances", "lights"),
    )
    source_lines = source.splitlines(keepends=True)
    assert selected == source_lines[0] + b"".join(source_lines[43:43 + 1008])
    assert (start, end, count) == (datetime(2026, 1, 2), datetime(2026, 1, 9), 1008)


def test_selection_rejects_a_missing_ten_minute_observation() -> None:
    source = sample_source().splitlines(keepends=True)
    del source[100]
    with pytest.raises(CaseBuildError, match="uninterrupted"):
        first_complete_week(b"".join(source), expected_columns=("date", "Appliances", "lights"))


def test_build_rejects_unpinned_archive_without_writing(tmp_path: Path) -> None:
    archive = tmp_path / "changed.zip"
    archive.write_bytes(b"not the pinned source")
    target = tmp_path / "case"
    with pytest.raises(CaseBuildError, match="SHA-256"):
        build(archive, target)
    assert not target.exists()
