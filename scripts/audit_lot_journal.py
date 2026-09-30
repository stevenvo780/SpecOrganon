"""Compatibility entry point for the incremental declared lot-journal auditor."""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from specorganon.lot_journal import LotJournalError, audit_lot_journal, main, read_journal
except ModuleNotFoundError as exc:
    if exc.name != "specorganon":
        raise
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from specorganon.lot_journal import LotJournalError, audit_lot_journal, main, read_journal

__all__ = ["LotJournalError", "audit_lot_journal", "main", "read_journal"]


if __name__ == "__main__":
    raise SystemExit(main())
