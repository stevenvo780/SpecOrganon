"""Strict, read-only inspection of declared common tool policies."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPTS / "tool_policy.py"
sys.path.insert(0, str(SCRIPTS))
import tool_policy as inspector  # noqa: E402


def _policy() -> dict[str, Any]:
    return {
        "schema": 1,
        "classification": "common_tool_policy_development_unenforced",
        "runtime_image_sha256": "a" * 64,
        "network": "disabled",
        "read_roots": ["/case"],
        "write_roots": ["/work"],
        "generic_tools": [
            {"id": "read_file", "version": "1.2.0", "executable_sha256": "b" * 64},
            {"id": "list-files", "version": "2026.09", "executable_sha256": "c" * 64},
        ],
        "limits": {
            "measured_tokens": 80_000,
            "active_seconds": 5_400,
            "tool_calls": 120,
        },
    }


def _write_policy(path: Path, policy: dict[str, Any]) -> bytes:
    data = json.dumps(policy, sort_keys=True, separators=(",", ":")).encode("utf-8")
    path.write_bytes(data)
    return data


def _cli(policy: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(policy), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )


def test_valid_policy_matches_expected_limits_and_reports_unenforced(
    tmp_path: Path,
) -> None:
    policy = _policy()
    path = tmp_path / "tool_policy"
    data = _write_policy(path, policy)

    result = inspector.inspect_tool_policy(path, expected_limits=policy["limits"])

    assert result == {
        "schema": 1,
        "classification": "development_tool_policy_inspection_unenforced",
        "notice": inspector.INSPECTION_NOTICE,
        "sha256": hashlib.sha256(data).hexdigest(),
        "limits": policy["limits"],
    }
    assert "does not enforce sandbox" in result["notice"]
    assert path.read_bytes() == data


def test_validated_policy_bytes_expose_tool_declarations_without_execution(
    tmp_path: Path,
) -> None:
    policy = _policy()
    data = _write_policy(tmp_path / "tool_policy", policy)
    parsed = inspector.validate_tool_policy_bytes(
        data, expected_limits=policy["limits"]
    )
    assert parsed == policy
    assert parsed is not policy
    with pytest.raises(inspector.ToolPolicyError, match="limits differ"):
        inspector.validate_tool_policy_bytes(
            data, expected_limits={**policy["limits"], "tool_calls": 1}
        )


def test_pinned_policy_bytes_share_path_validation_and_bounds(tmp_path: Path) -> None:
    policy = _policy()
    path = tmp_path / "tool_policy"
    data = _write_policy(path, policy)
    assert inspector.inspect_tool_policy_bytes(
        data, expected_limits=policy["limits"]
    ) == inspector.inspect_tool_policy(path, expected_limits=policy["limits"])

    path.write_bytes(b"replacement")
    assert (
        inspector.inspect_tool_policy_bytes(data, expected_limits=policy["limits"])[
            "sha256"
        ]
        == hashlib.sha256(data).hexdigest()
    )
    with pytest.raises(inspector.ToolPolicyError, match="limits differ"):
        inspector.inspect_tool_policy_bytes(
            data, expected_limits={**policy["limits"], "tool_calls": 121}
        )
    with pytest.raises(inspector.ToolPolicyError, match="duplicate JSON object key"):
        inspector.inspect_tool_policy_bytes(
            data.replace(b'"schema":1', b'"schema":1,"schema":1'),
            expected_limits=policy["limits"],
        )
    with pytest.raises(inspector.ToolPolicyError, match="bounded bytes"):
        inspector.inspect_tool_policy_bytes(
            b" " * (inspector.MAX_POLICY_BYTES + 1),
            expected_limits=policy["limits"],
        )


def test_cli_accepts_release_manifest_and_expected_limits(tmp_path: Path) -> None:
    policy = _policy()
    path = tmp_path / "tool_policy"
    _write_policy(path, policy)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"limits": policy["limits"]}), encoding="utf-8")

    with_manifest = _cli(path, "--release-manifest", str(manifest))
    with_limits = _cli(path, "--expected-limits", json.dumps(policy["limits"]))

    assert with_manifest.returncode == with_limits.returncode == 0
    assert json.loads(with_manifest.stdout) == json.loads(with_limits.stdout)
    assert with_manifest.stderr == with_limits.stderr == ""


def test_forged_policy_limits_do_not_match_release_or_expected_caps(
    tmp_path: Path,
) -> None:
    original = _policy()
    forged = copy.deepcopy(original)
    forged["limits"]["tool_calls"] += 1
    path = tmp_path / "tool_policy"
    _write_policy(path, forged)
    manifest = {"limits": original["limits"]}

    with pytest.raises(inspector.ToolPolicyError, match="limits differ"):
        inspector.inspect_tool_policy(path, release_manifest=manifest)
    with pytest.raises(inspector.ToolPolicyError, match="limits differ"):
        inspector.inspect_tool_policy(path, expected_limits=original["limits"])


@pytest.mark.parametrize("source", ["missing", "both", "bad_expected", "bad_release"])
def test_independent_cap_source_is_required_and_validated(
    tmp_path: Path, source: str
) -> None:
    policy = _policy()
    path = tmp_path / "tool_policy"
    _write_policy(path, policy)
    if source == "missing":
        kwargs: dict[str, Any] = {}
    elif source == "both":
        kwargs = {
            "release_manifest": {"limits": policy["limits"]},
            "expected_limits": policy["limits"],
        }
    elif source == "bad_expected":
        kwargs = {"expected_limits": {**policy["limits"], "tool_calls": True}}
    else:
        kwargs = {
            "release_manifest": {"limits": {**policy["limits"], "tool_calls": True}}
        }

    with pytest.raises(inspector.ToolPolicyError):
        inspector.inspect_tool_policy(path, **kwargs)


@pytest.mark.parametrize(
    "change,pattern",
    [
        ("schema_bool", "schema"),
        ("schema_number", "schema"),
        ("classification", "classification"),
        ("runtime_uppercase", "runtime_image_sha256"),
        ("runtime_short", "runtime_image_sha256"),
        ("network", "network"),
        ("read_roots", "read_roots"),
        ("write_roots", "write_roots"),
        ("top_extra", "exactly"),
        ("tool_extra", "exactly"),
        ("tool_id_path", "simple lowercase ID"),
        ("tool_id_upper", "simple lowercase ID"),
        ("tool_id_duplicate", "duplicate generic tool id"),
        ("tool_version_empty", "version"),
        ("tool_hash_upper", "executable_sha256"),
        ("limit_bool", "positive integer"),
        ("limit_zero", "positive integer"),
        ("limit_extra", "exactly"),
    ],
)
def test_malformed_or_factual_policy_content_rejected(
    tmp_path: Path, change: str, pattern: str
) -> None:
    valid = _policy()
    policy = copy.deepcopy(valid)
    if change == "schema_bool":
        policy["schema"] = True
    elif change == "schema_number":
        policy["schema"] = 2
    elif change == "classification":
        policy["classification"] = "enforced"
    elif change == "runtime_uppercase":
        policy["runtime_image_sha256"] = "A" * 64
    elif change == "runtime_short":
        policy["runtime_image_sha256"] = "a" * 63
    elif change == "network":
        policy["network"] = "enabled"
    elif change == "read_roots":
        policy["read_roots"].append("/secret")
    elif change == "write_roots":
        policy["write_roots"] = ["/tmp"]
    elif change == "top_extra":
        policy["observed_result"] = "success"
    elif change == "tool_extra":
        policy["generic_tools"][0]["purpose"] = "proved intervention"
    elif change == "tool_id_path":
        policy["generic_tools"][0]["id"] = "../shell"
    elif change == "tool_id_upper":
        policy["generic_tools"][0]["id"] = "Shell"
    elif change == "tool_id_duplicate":
        policy["generic_tools"][1]["id"] = "read_file"
    elif change == "tool_version_empty":
        policy["generic_tools"][0]["version"] = "  "
    elif change == "tool_hash_upper":
        policy["generic_tools"][0]["executable_sha256"] = "B" * 64
    elif change == "limit_bool":
        policy["limits"]["measured_tokens"] = True
    elif change == "limit_zero":
        policy["limits"]["active_seconds"] = 0
    else:
        policy["limits"]["outcome"] = 1
    path = tmp_path / "tool_policy"
    _write_policy(path, policy)

    with pytest.raises(inspector.ToolPolicyError, match=pattern):
        inspector.inspect_tool_policy(path, expected_limits=valid["limits"])


@pytest.mark.parametrize(
    "data",
    [
        b'{"schema":1,"schema":1}',
        b'{"limits":{"tool_calls":1,"tool_calls":2}}',
        b'{"limits":NaN}',
        b'{"limits":Infinity}',
        b'{"limits":1e1000}',
        b"\xff",
    ],
)
def test_non_strict_json_rejected(tmp_path: Path, data: bytes) -> None:
    path = tmp_path / "tool_policy"
    path.write_bytes(data)

    with pytest.raises(inspector.ToolPolicyError):
        inspector.inspect_tool_policy(path, expected_limits=_policy()["limits"])


def test_symlink_fifo_and_oversize_policy_rejected(tmp_path: Path) -> None:
    valid = _policy()
    target = tmp_path / "real-policy"
    _write_policy(target, valid)
    symlink = tmp_path / "symlink-policy"
    symlink.symlink_to(target)
    fifo = tmp_path / "fifo-policy"
    os.mkfifo(fifo)
    oversized = tmp_path / "oversized-policy"
    oversized.write_bytes(b" " * (inspector.MAX_POLICY_BYTES + 1))

    for path in (symlink, fifo, oversized):
        process = _cli(path, "--expected-limits", json.dumps(valid["limits"]))
        assert process.returncode == 2
        assert process.stdout == ""


def test_symlinked_parent_directory_rejected_for_policy_and_manifest(
    tmp_path: Path,
) -> None:
    policy = _policy()
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    real_policy = real_parent / "tool_policy"
    _write_policy(real_policy, policy)
    (real_parent / "manifest.json").write_text(
        json.dumps({"limits": policy["limits"]}), encoding="utf-8"
    )
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(inspector.ToolPolicyError, match="cannot be read securely"):
        inspector.inspect_tool_policy(
            linked_parent / "tool_policy", expected_limits=policy["limits"]
        )
    with pytest.raises(inspector.ToolPolicyError, match="cannot be read securely"):
        inspector.inspect_tool_policy(
            real_policy, release_manifest=linked_parent / "manifest.json"
        )


def test_trailing_slash_rejected_for_policy_and_manifest(tmp_path: Path) -> None:
    policy = _policy()
    policy_path = tmp_path / "tool_policy"
    _write_policy(policy_path, policy)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"limits": policy["limits"]}), encoding="utf-8")

    with pytest.raises(inspector.ToolPolicyError, match="trailing slash"):
        inspector.inspect_tool_policy(
            f"{policy_path}/", expected_limits=policy["limits"]
        )
    with pytest.raises(inspector.ToolPolicyError, match="trailing slash"):
        inspector.inspect_tool_policy(policy_path, release_manifest=f"{manifest_path}/")


def test_file_name_substitution_during_read_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    valid = _policy()
    path = tmp_path / "tool_policy"
    data = _write_policy(path, valid)
    replacement = tmp_path / "replacement"
    replacement.write_bytes(data)
    real_read = inspector.os.read
    replaced = False

    def read_then_replace(fd: int, amount: int) -> bytes:
        nonlocal replaced
        chunk = real_read(fd, amount)
        if chunk and not replaced:
            os.replace(replacement, path)
            replaced = True
        return chunk

    monkeypatch.setattr(inspector.os, "read", read_then_replace)
    with pytest.raises(inspector.ToolPolicyError, match="changed while being read"):
        inspector.inspect_tool_policy(path, expected_limits=valid["limits"])


def test_parent_directory_substitution_during_read_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = _policy()
    parent = tmp_path / "policy-parent"
    parent.mkdir()
    path = parent / "tool_policy"
    data = _write_policy(path, policy)
    replacement = tmp_path / "replacement-parent"
    replacement.mkdir()
    (replacement / "tool_policy").write_bytes(data)
    moved = tmp_path / "moved-parent"
    real_read = inspector.os.read
    replaced = False

    def read_then_replace(fd: int, amount: int) -> bytes:
        nonlocal replaced
        chunk = real_read(fd, amount)
        if chunk and not replaced:
            os.replace(parent, moved)
            os.replace(replacement, parent)
            replaced = True
        return chunk

    monkeypatch.setattr(inspector.os, "read", read_then_replace)
    with pytest.raises(inspector.ToolPolicyError, match="parent directory changed"):
        inspector.inspect_tool_policy(path, expected_limits=policy["limits"])


def test_manifest_file_uses_strict_json_and_no_follow(tmp_path: Path) -> None:
    policy = _policy()
    path = tmp_path / "tool_policy"
    _write_policy(path, policy)
    manifest = tmp_path / "manifest.json"
    manifest.write_bytes(b'{"limits":{},"limits":{}}')
    with pytest.raises(inspector.ToolPolicyError, match="duplicate JSON object key"):
        inspector.inspect_tool_policy(path, release_manifest=manifest)

    real_manifest = tmp_path / "real-manifest.json"
    real_manifest.write_text(json.dumps({"limits": policy["limits"]}), encoding="utf-8")
    manifest.unlink()
    manifest.symlink_to(real_manifest)
    with pytest.raises(inspector.ToolPolicyError, match="cannot be read securely"):
        inspector.inspect_tool_policy(path, release_manifest=manifest)
