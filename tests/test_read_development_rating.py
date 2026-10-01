"""Synthetic original files only; no reviewer or real rating is supplied."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import read_development_rating as reader  # noqa: E402


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def originals(tmp_path):
    tmp_path.chmod(0o700)
    rating, delivery = tmp_path / "rating.json", tmp_path / "blinded-delivery.bin"
    delivery.write_bytes(b"SYNTHETIC PRIVATE DELIVERY, NOT A REAL CASE")
    delivery.chmod(0o600)
    value = {"schema": 1, "classification": reader.ingress.CLASSIFICATION,
             "blinded_delivery_sha256": sha(delivery.read_bytes()),
             "rubric_sha256": reader.ingress.RUBRIC_SHA256,
             "delivery_contract_sha256": reader.ingress.DELIVERY_CONTRACT_SHA256,
             "reviewer_reference_sha256": None, "scores": dict.fromkeys(reader.ingress.DIMENSIONS, 20),
             "declarations": dict.fromkeys(reader.ingress.DECLARATION_FIELDS, True),
             "critical_incidents": [{"incident_id": "PRIVATE-SENTINEL", "type": "false_test_result",
                                     "evidence_sha256": sha(b"SYNTHETIC EVIDENCE"),
                                     "description": "PRIVATE-SENTINEL"}]}
    rating.write_bytes(json.dumps(value, indent=2).encode() + b"\n")
    rating.chmod(0o600)
    return rating, delivery, value


def read(originals):
    rating, delivery, _value = originals
    return reader.read_rating(rating, delivery, rating_sha256=sha(rating.read_bytes()),
                              blinded_delivery_sha256=sha(delivery.read_bytes()))


def test_valid_private_files_unchanged_and_high_total_not_quality(originals):
    rating, delivery, _value = originals
    before = [(p.read_bytes(), p.stat()) for p in (rating, delivery)]
    report = read(originals)
    assert report["declared_component_total"] == 100 and report["has_declared_critical_incidents"]
    assert not report["quality_verified"] and not report["reviewer_identity_verified"] and not report["Q_demonstrated"]
    assert report["reader"]["original_files_rechecked"] and not report["reader"]["originals_written"]
    assert "PRIVATE-SENTINEL" not in json.dumps(report)
    for path, (raw, info) in zip((rating, delivery), before):
        assert path.read_bytes() == raw and reader._same_file_state(path.stat(), info)


@pytest.mark.parametrize("which", [0, 1])
def test_public_mode_rejected(originals, which):
    originals[which].chmod(0o644)
    with pytest.raises(ValueError):
        read(originals)


def test_private_directory_required(originals):
    originals[0].parent.chmod(0o755)
    with pytest.raises(ValueError):
        read(originals)


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo"])
def test_nonregular_or_multiple_link_input_rejected(originals, kind):
    rating = originals[0]
    old = rating.with_name("saved.json")
    rating.rename(old)
    if kind == "symlink":
        rating.symlink_to(old)
    elif kind == "hardlink":
        os.link(old, rating)
    else:
        os.mkfifo(rating, mode=0o600)
    with pytest.raises(ValueError), patch.object(reader, "_read_bounded_file", wraps=reader._read_bounded_file):
        reader._private_input(rating, "rating.json", 256 * 1024)


def test_symlink_parent_rejected(originals, tmp_path):
    alias = tmp_path / "alias"
    alias.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        reader._private_input(alias / "rating.json", "rating.json", 256 * 1024)


def test_symlink_ancestor_rejected_even_with_real_private_immediate_parent(originals, tmp_path):
    inner = tmp_path / "inner"
    inner.mkdir(mode=0o700)
    nested = inner / "rating.json"
    nested.write_bytes(originals[0].read_bytes())
    nested.chmod(0o600)
    alias = tmp_path / "alias"
    alias.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        reader._private_input(alias / "inner/rating.json", "rating.json", 256 * 1024)


def test_hardlink_added_during_read_rejected(originals):
    rating = originals[0]
    original = reader._read_bounded_file
    def changing(path, label, maximum):
        raw = original(path, label, maximum)
        os.link(rating, rating.with_name("new-link.json"))
        return raw
    with patch.object(reader, "_read_bounded_file", changing), pytest.raises(ValueError):
        reader._private_input(rating, "rating.json", 256 * 1024)


def test_identical_byte_replacement_between_captures_rejected(originals):
    native = reader.ingress.validate_development_rating
    def changing(*args, **kwargs):
        report = native(*args, **kwargs)
        rating = originals[0]
        replacement = rating.with_name("replacement.json")
        replacement.write_bytes(rating.read_bytes())
        replacement.chmod(0o600)
        replacement.replace(rating)
        return report
    with patch.object(reader.ingress, "validate_development_rating", changing), pytest.raises(ValueError):
        read(originals)


def test_changed_public_protocol_rejected(originals):
    sources = copy.copy(reader.SOURCES)
    sources = (*sources[:-1], (sources[-1][0], "0" * 64))
    with patch.object(reader, "SOURCES", sources), pytest.raises(ValueError):
        read(originals)


def test_content_tampered_since_given_hash_rejected(originals):
    rating, delivery, _value = originals
    digest = sha(rating.read_bytes())
    rating.write_bytes(rating.read_bytes() + b" ")
    with pytest.raises(ValueError):
        reader.read_rating(rating, delivery, rating_sha256=digest, blinded_delivery_sha256=sha(delivery.read_bytes()))


@pytest.mark.parametrize("kind", ["missing", "unknown", "bad_basename", "bad_content"])
def test_main_rejections_do_not_print_supplied_private_data(originals, capsys, kind):
    rating, delivery, _value = originals
    argv = ["--rating", str(rating), "--rating-sha256", sha(rating.read_bytes()),
            "--blinded-delivery", str(delivery), "--blinded-delivery-sha256", sha(delivery.read_bytes())]
    if kind == "missing":
        argv = ["--rating", "/PRIVATE-SENTINEL/rating.json"]
    elif kind == "unknown":
        argv += ["--PRIVATE-SENTINEL", "PRIVATE-SENTINEL"]
    elif kind == "bad_basename":
        argv[1] = str(rating.with_name("PRIVATE-SENTINEL.json"))
    else:
        rating.write_bytes(b'{"PRIVATE-SENTINEL":"bad"}')
        argv[3] = sha(rating.read_bytes())
    assert reader.main(argv) == 2
    captured = capsys.readouterr()
    assert "PRIVATE-SENTINEL" not in captured.out + captured.err
    assert captured.err == "" and not json.loads(captured.out)["Q_demonstrated"]


def test_relative_and_oversized_input_rejected(originals):
    with pytest.raises(ValueError):
        reader._private_input(Path("rating.json"), "rating.json", 256 * 1024)
    with pytest.raises(ValueError):
        reader._private_input(originals[0], "rating.json", 1)
