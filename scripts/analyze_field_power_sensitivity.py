"""Compatibility entry point for offline field power sensitivity development."""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from specorganon.field_power_sensitivity import main
except ModuleNotFoundError as exc:
    if exc.name != "specorganon":
        raise
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from specorganon.field_power_sensitivity import main


if __name__ == "__main__":
    raise SystemExit(main())
