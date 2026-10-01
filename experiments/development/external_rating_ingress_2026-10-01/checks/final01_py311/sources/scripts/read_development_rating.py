"""Read an externally supplied DEV rating; validate its declared byte bindings.

Inputs remain unchanged. The summary does not authenticate a reviewer, verify
blinding or custody, assign scores, or establish quality or acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import development_rating_ingress as ingress  # noqa: E402
from run_managed_conversation import _private_dir, _private_file  # noqa: E402
from tool_policy import _read_bounded_file, _same_file_state  # noqa: E402

ROOT = SCRIPTS.parent
PUBLIC = ROOT / "experiments/development/coordinated_contract_2026-10-01/public_contract"
SOURCES = ((PUBLIC / "rubric.json", ingress.RUBRIC_SHA256),
           (PUBLIC / "delivery_contract.json", ingress.DELIVERY_CONTRACT_SHA256),
           (ROOT / "docs/protocolo_experimental.md", ingress.PROTOCOL_REFERENCE_SHA256))


class RatingReadError(ValueError):
    """Only fixed codes, never a supplied path or exception message."""


class _Parser(argparse.ArgumentParser):
    def error(self, _message):
        raise RatingReadError("arguments_rejected")


def _require(condition, code):
    if not condition:
        raise RatingReadError(code)


def _private_input(path, filename, maximum):
    path = Path(path)
    _require(path.is_absolute() and ".." not in path.parts and path.name == filename, "private_input_path")
    _private_dir(path.parent)
    _private_file(path)
    before = path.lstat()
    _require(before.st_nlink == 1 and 0 < before.st_size <= maximum, "private_input_shape")
    raw = _read_bounded_file(path, "private rating input", maximum)
    _private_dir(path.parent)
    _private_file(path)
    _require(_same_file_state(before, path.lstat()), "private_input_changed")
    return raw, before


def _public_sources():
    rows = []
    for path, expected in SOURCES:
        raw = _read_bounded_file(path, "fixed public rating reference", ingress.MAX_PUBLIC_CONTRACT_BYTES)
        _require(hashlib.sha256(raw).hexdigest() == expected, "public_source_changed")
        rows.append(raw)
    return rows


def read_rating(rating_path, delivery_path, *, rating_sha256, blinded_delivery_sha256):
    """Read bounded original files and recheck their identity and bytes.

    Hashes and private file controls provide cooperative local consistency.
    No external authority or successful redaction follows from these checks.
    """
    rubric, contract, protocol = _public_sources()
    rating, rating_info = _private_input(rating_path, "rating.json", ingress.MAX_RATING_BYTES)
    delivery, delivery_info = _private_input(delivery_path, "blinded-delivery.bin", ingress.MAX_BLINDED_DELIVERY_BYTES)
    report = ingress.validate_development_rating(
        rating, rating_sha256=rating_sha256, blinded_delivery_raw=delivery,
        blinded_delivery_sha256=blinded_delivery_sha256, rubric_raw=rubric,
        rubric_sha256=ingress.RUBRIC_SHA256, delivery_contract_raw=contract,
        delivery_contract_sha256=ingress.DELIVERY_CONTRACT_SHA256)
    again, info = _private_input(rating_path, "rating.json", ingress.MAX_RATING_BYTES)
    _require(again == rating and _same_file_state(info, rating_info), "rating_snapshot_changed")
    again, info = _private_input(delivery_path, "blinded-delivery.bin", ingress.MAX_BLINDED_DELIVERY_BYTES)
    _require(again == delivery and _same_file_state(info, delivery_info), "delivery_snapshot_changed")
    _require(_public_sources() == [rubric, contract, protocol], "reference_snapshot_changed")
    return {**report, "reader": {"classification": "readonly_local_original_rating_reader",
                                "original_files_rechecked": True, "originals_written": False,
                                "fixed_public_byte_pins_verified": True}}


def main(argv=None):
    parser = _Parser(prog="read_development_rating", description=__doc__)
    parser.add_argument("--rating", type=Path, required=True)
    parser.add_argument("--rating-sha256", required=True)
    parser.add_argument("--blinded-delivery", type=Path, required=True)
    parser.add_argument("--blinded-delivery-sha256", required=True)
    try:
        args = parser.parse_args(argv)
        result = read_rating(args.rating, args.blinded_delivery, rating_sha256=args.rating_sha256,
                             blinded_delivery_sha256=args.blinded_delivery_sha256)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (ValueError, OSError, TypeError, KeyError, RuntimeError):
        print(json.dumps({"error": "rating_arguments_or_originals_rejected", "Q_demonstrated": False,
                          "quality_verified": False, "acceptance_assessed": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
