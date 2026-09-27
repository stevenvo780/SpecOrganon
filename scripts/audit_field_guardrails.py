"""Compatibility entry point for the packaged field-guardrail auditor."""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from specorganon import field_guardrails as _implementation
except ModuleNotFoundError as exc:
    if exc.name != "specorganon":
        raise
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from specorganon import field_guardrails as _implementation


__all__ = [name for name in vars(_implementation) if not name.startswith("_")]
main = _implementation.main


def __getattr__(name: str):
    return getattr(_implementation, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_implementation)))


if __name__ == "__main__":
    raise SystemExit(main())
