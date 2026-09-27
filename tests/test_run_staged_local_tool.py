"""Integrated checks for one local, digest-pinned tool on real N/S/T stages."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import local_replay_sandbox as sandbox  # noqa: E402
import local_run_admission as admission  # noqa: E402
import plan_confirmatory  # noqa: E402
import preflight_assets  # noqa: E402
import run_staged_local_tool as runner  # noqa: E402
import stage_released_run  # noqa: E402
import test_inspect_released_payload as fixture  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_admission_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(admission.ROOT_ENV, str(tmp_path / "admissions"))


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _tool(path: Path, body: str) -> None:
    path.write_text(f"#!{sys.executable}\n" + body, encoding="utf-8")
    path.chmod(0o700)


def _stage(tmp_path: Path, arm: str, body: str) -> tuple[dict, Path, str, Path, Path, tuple[bytes, ...]]:
    tool = tmp_path / "generic_tool"
    _tool(tool, body)
    schedule, assets, schedule_path, hidden = fixture._fixture(tmp_path)
    policy_path = Path(assets["inputs"]["tool_policy"])
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["generic_tools"] = [
        {"id": "local_analyzer", "version": "1", "executable_sha256": _sha(tool.read_bytes())}
    ]
    policy_bytes = json.dumps(policy, sort_keys=True).encode("utf-8")
    policy_path.write_bytes(policy_bytes)
    manifest = dict(schedule["inputs"])
    manifest["tool_policy"] = {**manifest["tool_policy"], "sha256": _sha(policy_bytes)}
    raw = {
        "schema": 1,
        "seed": schedule["seed"],
        "protocol_sha256": schedule["protocol_sha256"],
        "tool_call_cap": schedule["per_run_limits"]["tool_calls"],
        "models": schedule["models"],
        "cases": schedule["cases"],
        "inputs": manifest,
    }
    schedule = plan_confirmatory.compile_schedule(raw)
    schedule_path.write_text(json.dumps(schedule), encoding="utf-8")
    assets["schedule_sha256"] = schedule["schedule_sha256"]
    assets["input_sha256"] = schedule["input_sha256"]
    run = next(item for item in schedule["runs"] if item["arm"] == arm and item["case_id"] == "R-F")
    release = tmp_path / "release"
    preflight_assets.preflight(schedule, assets, run_id=run["run_id"], output_dir=release)
    stage = tmp_path / "stage"
    stage_released_run.stage_released_run(schedule, release, stage)
    return schedule, schedule_path, run["run_id"], stage, tool, hidden


@pytest.fixture
def available_sandbox() -> None:
    capability = sandbox.probe_sandbox()
    if not capability.available:
        pytest.skip(capability.reason or "sandbox unavailable")


GOOD_BODY = """
import sys
from pathlib import Path
case, inputs, work = map(Path, sys.argv[1:])
assert (case / 'task.md').read_text() == 'Visible task for R-F.\\n'
assert (inputs / 'tool_policy').is_file()
(work / 'report.md').write_text('local result\\n')
print('local stdout')
print('local stderr', file=sys.stderr)
"""


@pytest.mark.parametrize("arm", ["N", "S", "T"])
def test_real_stage_run_and_separate_receipt(
    tmp_path: Path, available_sandbox: None, arm: str,
) -> None:
    schedule, schedule_path, run_id, stage, tool, hidden = _stage(tmp_path, arm, GOOD_BODY)
    receipt = tmp_path / "receipt"
    process = subprocess.run(
        [sys.executable, "-B", str(SCRIPTS / "run_staged_local_tool.py"),
         str(schedule_path), run_id, str(stage), "local_analyzer", str(tool), str(receipt)],
        capture_output=True, text=True, check=False, timeout=20,
    )
    assert process.returncode == 0, process.stderr
    report = json.loads(process.stdout)
    assert report == json.loads((receipt / "receipt.json").read_text())
    assert report["status"] == "success"
    assert report["run_id"] == run_id
    assert report["schedule_sha256"] == schedule["schedule_sha256"]
    assert report["stage_unchanged_after_run"] is True
    assert report["runtime_image_verified"] is False
    assert report["output_inventory_complete"] is True
    assert report["deliverables_present"] is True
    assert report["outputs"] == [
        {"path": "report.md", "bytes": len(b"local result\n"), "sha256": _sha(b"local result\n")}
    ]
    assert report["provider_calls"] == 0
    assert report["measured_tokens"] is None
    assert report["criterion_4"] == "not_assessed"
    assert report["provider_receipt"] is False
    assert report["execution_bytes_sealed"] is True
    assert report["sealed_executable_sha256"] == _sha(tool.read_bytes())
    assert (receipt / "stdout").read_text() == "local stdout\n"
    assert (receipt / "stderr").read_text() == "local stderr\n"
    assert (receipt.stat().st_mode & 0o777) == 0o700
    assert {path.name for path in receipt.iterdir()} == {
        "stdout", "stderr", "reservation.json", "receipt.json"
    }
    assert all((path.stat().st_mode & 0o777) == 0o600 for path in receipt.iterdir())
    assert set(path.name for path in stage.iterdir()) == {"case", "inputs", "work", "stage.json"}
    for secret in hidden:
        assert secret not in (receipt / "receipt.json").read_bytes()


def test_rejects_mismatched_executable_before_receipt(tmp_path: Path) -> None:
    schedule, _, run_id, stage, tool, _ = _stage(tmp_path, "N", GOOD_BODY)
    tool.write_bytes(tool.read_bytes() + b"#changed\n")
    receipt = tmp_path / "receipt"
    with pytest.raises(runner.LocalToolError, match="SHA-256"):
        runner.run_staged_local_tool(schedule, run_id, stage, "local_analyzer", tool, receipt)
    assert not receipt.exists()
    assert list((stage / "work").iterdir()) == []


def test_tool_cannot_read_hidden_or_write_outside_or_use_network(
    tmp_path: Path, available_sandbox: None,
) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("untouched", encoding="utf-8")
    hidden_path = tmp_path / "source" / "R-F.reference"
    body = f"""
import socket
import sys
from pathlib import Path
case, inputs, work = map(Path, sys.argv[1:])
for operation in (
    lambda: Path({str(hidden_path)!r}).read_bytes(),
    lambda: Path({str(outside)!r}).write_text('changed'),
    lambda: (inputs / 'tool_policy').write_text('changed'),
    lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM),
):
    try:
        operation()
    except OSError:
        pass
    else:
        raise AssertionError('forbidden operation succeeded')
(work / 'report.md').write_text('boundary held')
"""
    schedule, _, run_id, stage, tool, hidden = _stage(tmp_path, "N", body)
    report = runner.run_staged_local_tool(schedule, run_id, stage, "local_analyzer", tool, tmp_path / "receipt")
    assert report["status"] == "success", (tmp_path / "receipt" / "stderr").read_text()
    assert outside.read_text() == "untouched"
    assert hidden[0] == hidden_path.read_bytes()
    assert (stage / "work" / "report.md").read_text() == "boundary held"


@pytest.mark.parametrize("body,status", [
    ("import time\ntime.sleep(3)\n", "timeout"),
    ("raise SystemExit(7)\n", "tool_failure"),
    ("print('no deliverable')\n", "deliverables_missing"),
])
def test_distinguishes_timeout_failure_and_missing_deliverable(
    tmp_path: Path, available_sandbox: None, body: str, status: str,
) -> None:
    schedule, _, run_id, stage, tool, _ = _stage(tmp_path, "N", body)
    report = runner.run_staged_local_tool(
        schedule, run_id, stage, "local_analyzer", tool, tmp_path / "receipt",
        wall_seconds=0.3 if status == "timeout" else 5,
    )
    assert report["status"] == status
    assert report["timed_out"] is (status == "timeout")
    assert report["exit_code"] == (7 if status == "tool_failure" else None if status == "timeout" else 0)
    assert report["provider_calls"] == 0


def test_output_inventory_limit_is_explicit(tmp_path: Path, available_sandbox: None) -> None:
    body = """
import sys
from pathlib import Path
work = Path(sys.argv[3])
for index in range(260):
    (work / f'f-{index:03d}').write_text('x')
(work / 'report.md').write_text('done')
"""
    schedule, _, run_id, stage, tool, _ = _stage(tmp_path, "N", body)
    report = runner.run_staged_local_tool(schedule, run_id, stage, "local_analyzer", tool, tmp_path / "receipt")
    assert report["status"] == "output_inventory_incomplete"
    assert report["output_inventory_complete"] is False
    assert report["deliverables_present"] is None
    assert len(report["outputs"]) <= runner.MAX_WORK_FILES


def test_missing_sandbox_is_a_launch_failure_with_local_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule, _, run_id, stage, tool, _ = _stage(tmp_path, "N", GOOD_BODY)
    monkeypatch.setattr(
        sandbox, "probe_sandbox",
        lambda: sandbox.SandboxCapability(False, None, "Landlock unavailable"),
    )
    receipt = tmp_path / "receipt"
    report = runner.run_staged_local_tool(schedule, run_id, stage, "local_analyzer", tool, receipt)
    assert report["status"] == "launch_failure"
    assert report["launch_error"] == "SandboxUnavailable: Landlock unavailable"
    assert report["local_tool_calls"] == 0
    assert report["execution_bytes_sealed"] is False
    assert report["stdout"] is None and report["stderr"] is None
    assert json.loads((receipt / "receipt.json").read_text()) == report
    assert list((stage / "work").iterdir()) == []


def test_post_run_stage_mutation_is_flagged(
    tmp_path: Path, available_sandbox: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule, _, run_id, stage, tool, _ = _stage(tmp_path, "N", GOOD_BODY)
    actual = runner.run_sandboxed

    def alter_after_child(**kwargs: object) -> sandbox.SandboxResult:
        result = actual(**kwargs)
        (stage / "inputs" / "arm_prompt").write_text("changed", encoding="utf-8")
        return result

    monkeypatch.setattr(runner, "run_sandboxed", alter_after_child)
    report = runner.run_staged_local_tool(schedule, run_id, stage, "local_analyzer", tool, tmp_path / "receipt")
    assert report["status"] == "stage_or_executable_mutated"
    assert report["stage_unchanged_after_run"] is False
    assert (tmp_path / "receipt" / "receipt.json").exists()


def test_source_swap_at_launch_cannot_change_executed_bytes(
    tmp_path: Path, available_sandbox: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule, _, run_id, stage, tool, _ = _stage(tmp_path, "N", GOOD_BODY)
    original = tool.read_bytes()
    actual = runner.run_sandboxed

    def swap_original_path(**kwargs: object) -> sandbox.SandboxResult:
        _tool(tool, "import sys\nfrom pathlib import Path\nPath(sys.argv[3], 'report.md').write_text('wrong bytes')\n")
        try:
            return actual(**kwargs)
        finally:
            tool.write_bytes(original)

    monkeypatch.setattr(runner, "run_sandboxed", swap_original_path)
    report = runner.run_staged_local_tool(schedule, run_id, stage, "local_analyzer", tool, tmp_path / "receipt")
    assert report["status"] == "success"
    assert report["sealed_executable_sha256"] == _sha(original)
    assert report["execution_bytes_sealed"] is True
    assert (stage / "work" / "report.md").read_text() == "local result\n"


def test_receipt_executable_path_swap_cannot_change_sealed_launch(
    tmp_path: Path, available_sandbox: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule, _, run_id, stage, tool, _ = _stage(tmp_path, "N", GOOD_BODY)
    receipt = tmp_path / "receipt"
    actual = runner.run_sandboxed

    def swap_old_launch_path(**kwargs: object) -> sandbox.SandboxResult:
        replacement = receipt / "executable"
        _tool(replacement, "import sys\nfrom pathlib import Path\nPath(sys.argv[3], 'report.md').write_text('wrong bytes')\n")
        try:
            return actual(**kwargs)
        finally:
            replacement.unlink()

    monkeypatch.setattr(runner, "run_sandboxed", swap_old_launch_path)
    report = runner.run_staged_local_tool(schedule, run_id, stage, "local_analyzer", tool, receipt)
    assert report["status"] == "success"
    assert report["execution_bytes_sealed"] is True
    assert (stage / "work" / "report.md").read_text() == "local result\n"


@pytest.mark.parametrize("mutation", ["policy", "arm_prompt"])
def test_mutation_immediately_after_stage_verifier_is_rejected_before_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str,
) -> None:
    schedule, _, run_id, stage, tool, _ = _stage(tmp_path, "N", GOOD_BODY)
    selected_tool = tool
    if mutation == "policy":
        selected_tool = tmp_path / "alternate_tool"
        _tool(selected_tool, "import sys\nfrom pathlib import Path\nPath(sys.argv[3], 'report.md').write_text('alternate')\n")
    actual_verify = runner.verify_stage

    def mutate_after_verify(*args: object) -> dict:
        result = actual_verify(*args)
        if mutation == "policy":
            policy_path = stage / "inputs" / "tool_policy"
            policy = json.loads(policy_path.read_text())
            policy["generic_tools"][0]["executable_sha256"] = _sha(selected_tool.read_bytes())
            policy_path.write_text(json.dumps(policy), encoding="utf-8")
        else:
            (stage / "inputs" / "arm_prompt").write_text("changed after verify", encoding="utf-8")
        return result

    monkeypatch.setattr(runner, "verify_stage", mutate_after_verify)
    with pytest.raises(runner.LocalToolError, match="changed across verification"):
        runner.run_staged_local_tool(
            schedule, run_id, stage, "local_analyzer", selected_tool, tmp_path / "receipt"
        )
    assert not (tmp_path / "receipt").exists()
    assert list((stage / "work").iterdir()) == []


def test_tool_may_create_work_subdirectory_without_stage_mutation(
    tmp_path: Path, available_sandbox: None,
) -> None:
    body = """
import sys
from pathlib import Path
work = Path(sys.argv[3])
(work / 'detail').mkdir()
(work / 'detail' / 'note.txt').write_text('detail')
(work / 'report.md').write_text('done')
"""
    schedule, _, run_id, stage, tool, _ = _stage(tmp_path, "N", body)
    report = runner.run_staged_local_tool(schedule, run_id, stage, "local_analyzer", tool, tmp_path / "receipt")
    assert report["status"] == "success"
    assert report["stage_unchanged_after_run"] is True
    assert {item["path"] for item in report["outputs"]} == {"detail/note.txt", "report.md"}


def test_policy_limit_and_work_preflight_rejections(tmp_path: Path) -> None:
    schedule, _, run_id, stage, tool, _ = _stage(tmp_path, "N", GOOD_BODY)
    with pytest.raises(runner.LocalToolError, match="invalid local wall"):
        runner.run_staged_local_tool(
            schedule, run_id, stage, "local_analyzer", tool,
            tmp_path / "receipt-limits", wall_seconds=600,
        )
    (stage / "work" / "old").write_text("existing", encoding="utf-8")
    with pytest.raises(runner.StageVerificationError, match="work directory is not empty"):
        runner.run_staged_local_tool(
            schedule, run_id, stage, "local_analyzer", tool, tmp_path / "receipt-work"
        )
    assert not (tmp_path / "receipt-limits").exists()
    assert not (tmp_path / "receipt-work").exists()


def test_policy_limit_mutation_rejected_before_receipt(tmp_path: Path) -> None:
    schedule, _, run_id, stage, tool, _ = _stage(tmp_path, "N", GOOD_BODY)
    policy_path = stage / "inputs" / "tool_policy"
    policy = json.loads(policy_path.read_text())
    policy["limits"]["tool_calls"] += 1
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(runner.StageVerificationError):
        runner.run_staged_local_tool(
            schedule, run_id, stage, "local_analyzer", tool, tmp_path / "receipt"
        )
    assert not (tmp_path / "receipt").exists()


def test_symlinked_executable_rejected(tmp_path: Path) -> None:
    schedule, _, run_id, stage, tool, _ = _stage(tmp_path, "N", GOOD_BODY)
    link = tmp_path / "tool-link"
    link.symlink_to(tool)
    with pytest.raises(runner.ToolPolicyError, match="cannot be read securely"):
        runner.run_staged_local_tool(schedule, run_id, stage, "local_analyzer", link, tmp_path / "receipt")
    assert not (tmp_path / "receipt").exists()
