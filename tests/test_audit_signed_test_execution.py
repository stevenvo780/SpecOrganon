"""A signed declaration is not a local observation until its bytes match."""

from __future__ import annotations

import base64
import hashlib
import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from specorganon import approval, engine
from specorganon.ledger import read_project

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import audit_signed_test_execution as audit  # noqa: E402
import local_replay_sandbox as sandbox  # noqa: E402


EXECUTABLE = next(
    (path for path in (Path(sys.executable).resolve(strict=True),
                      Path("/usr/bin/python3").resolve(strict=True))
     if path.is_file() and path.stat().st_size <= audit.MAX_EXECUTABLE_BYTES),
    None,
)
if EXECUTABLE is None:
    pytest.skip("no sealable local Python executable", allow_module_level=True)
EXECUTABLE_SHA256 = hashlib.sha256(EXECUTABLE.read_bytes()).hexdigest()
ACTOR = "executor:local-audit-test"
AUTHOR = "agent:writer"
GOOD = b"local observation\n"


@pytest.fixture
def available_sandbox() -> None:
    capability = sandbox.probe_sandbox()
    if not capability.available:
        pytest.skip(capability.reason or "sandbox unavailable")


def _signed_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                 argv: list[str], report: dict) -> Path:
    case = tmp_path / "case"
    registry = tmp_path / "registry.json"
    monkeypatch.setenv("ORGANON_APPROVERS_FILE", str(registry))
    engine.create_case(case, "Local signed audit", "synthetic", AUTHOR)
    project = read_project(case)["project"]
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    registry.write_text(json.dumps({"schema": 2, "cases": {project["case_id"]: {
        "path": str(case.resolve(strict=True)),
        "project_sha256": approval.project_fingerprint(project),
        "approvers": {}, "phase_reviewers": {},
        "test_executors": {ACTOR: base64.b64encode(public).decode("ascii")},
    }}}), encoding="utf-8")
    engine.put_item(case, "t1", "test", "Local synthetic command", [], {
        "passed": True, "argv": argv, "command": shlex.join(argv),
    }, AUTHOR)
    challenge = engine.test_execution_challenge(case, "t1", report, ACTOR)
    signature = base64.b64encode(key.sign(base64.b64decode(challenge["message_base64"]))).decode("ascii")
    engine.record_test_execution(case, "t1", report, ACTOR, signature)
    return case


def _run_dir(tmp_path: Path) -> Path:
    run = tmp_path / "run"
    run.mkdir(mode=0o700)
    (run / "input").mkdir(mode=0o700)
    (run / "input" / "payload.txt").write_bytes(GOOD)
    return run


def _command(*, artifact: bytes | None = GOOD, exit_code: int = 0,
             sleep: float = 0) -> list[str]:
    script = (
        "from pathlib import Path; import os,sys,time; "
        f"time.sleep({sleep!r}); "
        "data=Path('payload.txt').read_bytes(); "
        "out=Path(os.environ['HOME'])/'results'; out.mkdir(); "
        + (f"(out/'output.txt').write_bytes({artifact!r}); " if artifact is not None else "")
        + "sys.stdout.buffer.write(data); sys.stderr.buffer.write(b'warning\\n'); "
        + f"sys.exit({exit_code})"
    )
    return [str(EXECUTABLE), "-I", "-c", script]


def _report(argv: list[str], *, artifact_digest: str | None = None,
            stdout_digest: str | None = None, exit_code: int = 0,
            timed_out: bool = False) -> dict:
    return {
        "schema": 1, "argv": argv, "exit_code": exit_code,
        "timed_out": timed_out,
        "stdout_sha256": stdout_digest or hashlib.sha256(GOOD).hexdigest(),
        "stderr_sha256": hashlib.sha256(b"warning\n").hexdigest(),
        "artifacts": [{"path": "results/output.txt",
                       "sha256": artifact_digest or hashlib.sha256(GOOD).hexdigest()}],
    }


def _cli(case: Path, run: Path, capsys: pytest.CaptureFixture[str],
         *, pin: str = EXECUTABLE_SHA256, timeout: float = 10) -> tuple[int, dict]:
    status = audit.main([
        str(case), "t1", str(run), "--executable-sha256", pin,
        "--timeout-seconds", str(timeout),
    ])
    output = json.loads(capsys.readouterr().out)
    return status, output


def test_private_directory_rejects_symlink_ancestor_and_final_component(tmp_path: Path) -> None:
    parent = tmp_path / "real"
    parent.mkdir(mode=0o700)
    run = parent / "run"
    run.mkdir(mode=0o700)
    (tmp_path / "link-parent").symlink_to(parent, target_is_directory=True)
    (tmp_path / "link-run").symlink_to(run, target_is_directory=True)
    with pytest.raises(audit.AuditError, match="symlink"):
        audit._private_directory(tmp_path / "link-parent" / "run")
    with pytest.raises(audit.AuditError, match="symlink"):
        audit._private_directory(tmp_path / "link-run")
    assert audit._private_directory(run) == run


def test_fake_signed_digests_remain_engine_green_but_local_audit_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    available_sandbox: None,
) -> None:
    argv = _command()
    report = _report(argv, artifact_digest="1" * 64, stdout_digest="0" * 64)
    case = _signed_case(tmp_path, monkeypatch, argv, report)
    before = (case / "organon.json").read_bytes()
    assert engine.get_state(case)["items"]["t1"]["test_execution_status"] == "signed_passed"

    process = subprocess.run([
        sys.executable, str(SCRIPTS / "audit_signed_test_execution.py"),
        str(case), "t1", str(_run_dir(tmp_path)),
        "--executable-sha256", EXECUTABLE_SHA256,
    ], capture_output=True, text=True, check=False, timeout=30)
    assert process.returncode == 1, process.stderr
    result = json.loads(process.stdout)
    assert result["signature_verified"] is True
    assert result["observed_locally"] is False
    assert result["observed_passed"] is False
    assert result["checks"]["stdout_sha256"] is False
    assert result["checks"]["artifacts"] is False
    assert (case / "organon.json").read_bytes() == before


def test_matching_repeat_reads_input_and_hashes_artifact_and_streams(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], available_sandbox: None,
) -> None:
    argv = _command()
    case = _signed_case(tmp_path, monkeypatch, argv, _report(argv))
    run = _run_dir(tmp_path)
    before = (case / "organon.json").read_bytes()
    status, result = _cli(case, run, capsys)
    assert status == 0, result
    assert result["signature_verified"] and result["observed_locally"] and result["observed_passed"]
    assert result["declared_executable_sha256_pin"] == EXECUTABLE_SHA256
    assert result["sealed_executable_sha256"] == EXECUTABLE_SHA256
    assert result["exact_argv_reproduced"] is False
    assert result["executed_argv0_form"] == "/proc/self/fd/<sealed-fd>"
    assert all(result["checks"].values())
    assert result["artifact_checks"] == [{
        "path": "results/output.txt", "matches": True,
        "observed_sha256": hashlib.sha256(GOOD).hexdigest(),
    }]
    assert (run / "artifacts" / "results" / "output.txt").read_bytes() == GOOD
    assert (case / "organon.json").read_bytes() == before


@pytest.mark.parametrize("kind", ["missing", "altered", "symlink"])
def test_missing_altered_or_symlink_artifact_is_not_observed(
    kind: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], available_sandbox: None,
) -> None:
    artifact = None if kind == "missing" else b"altered\n" if kind == "altered" else GOOD
    argv = _command(artifact=artifact)
    case = _signed_case(tmp_path, monkeypatch, argv, _report(argv))
    run = _run_dir(tmp_path)
    if kind == "symlink":
        original = audit.run_sandboxed
        outside = tmp_path / "outside.txt"
        outside.write_bytes(GOOD)

        def swap_artifact(**kwargs: object) -> sandbox.SandboxResult:
            result = original(**kwargs)
            target = run / "artifacts" / "results" / "output.txt"
            target.unlink()
            target.symlink_to(outside)
            return result

        monkeypatch.setattr(audit, "run_sandboxed", swap_artifact)
    status, result = _cli(case, run, capsys)
    assert status == 1
    assert result["signature_verified"] is True
    assert result["observed_locally"] is False
    assert result["checks"]["artifacts"] is False
    if kind == "symlink":
        assert "error" in result["artifact_checks"][0]


def test_wrong_executable_pin_and_changed_argv_fail_before_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], available_sandbox: None,
) -> None:
    argv = _command()
    case = _signed_case(tmp_path, monkeypatch, argv, _report(argv))
    run = _run_dir(tmp_path)
    status, result = _cli(case, run, capsys, pin="0" * 64)
    assert status == 2
    assert result["signature_verified"] is True
    assert result["observed_locally"] is False
    assert not (run / "artifacts").exists()

    engine.put_item(case, "t1", "test", "Changed command", [], {
        "passed": True, "argv": [*argv, "other"],
        "command": shlex.join([*argv, "other"]),
    }, AUTHOR)
    status, result = _cli(case, run, capsys)
    assert status == 2
    assert result["signature_verified"] is False
    assert not (run / "artifacts").exists()


def test_modified_signed_executable_bytes_are_rejected_before_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    executable = tmp_path / "private-python"
    executable.write_bytes(EXECUTABLE.read_bytes())
    executable.chmod(0o700)
    original_pin = hashlib.sha256(executable.read_bytes()).hexdigest()
    argv = [str(executable), "-I", "-c", "print('synthetic')"]
    report = _report(argv, stdout_digest=hashlib.sha256(b"synthetic\n").hexdigest())
    report["artifacts"] = []
    report["stderr_sha256"] = hashlib.sha256(b"").hexdigest()
    case = _signed_case(tmp_path, monkeypatch, argv, report)
    run = _run_dir(tmp_path)
    with executable.open("r+b") as target:
        target.seek(0)
        target.write(b"X")
    status, result = _cli(case, run, capsys, pin=original_pin)
    assert status == 2
    assert result["signature_verified"] is True
    assert "does not match" in result["error"]
    assert not (run / "artifacts").exists()


def test_signed_nonzero_matches_but_cannot_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], available_sandbox: None,
) -> None:
    argv = _command(exit_code=3)
    case = _signed_case(tmp_path, monkeypatch, argv, _report(argv, exit_code=3))
    status, result = _cli(case, _run_dir(tmp_path), capsys)
    assert status == 1
    assert result["signature_verified"] is True
    assert result["observed_locally"] is True
    assert result["observed_passed"] is False
    assert result["checks"]["exit_code"] is True


def test_timeout_does_not_establish_matching_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], available_sandbox: None,
) -> None:
    argv = _command(sleep=5)
    case = _signed_case(tmp_path, monkeypatch, argv,
                        _report(argv, exit_code=124, timed_out=True))
    status, result = _cli(case, _run_dir(tmp_path), capsys, timeout=0.2)
    assert status == 1
    assert result["signature_verified"] is True
    assert result["sandbox"]["timed_out"] is True
    assert result["checks"]["timed_out"] is True
    assert result["checks"]["exit_code"] is False
    assert result["observed_locally"] is False


def test_unavailable_sandbox_fails_closed_before_creating_write_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    argv = _command()
    case = _signed_case(tmp_path, monkeypatch, argv, _report(argv))
    run = _run_dir(tmp_path)
    monkeypatch.setattr(audit, "probe_sandbox", lambda: sandbox.SandboxCapability(
        False, None, "Landlock unavailable"))
    status, result = _cli(case, run, capsys)
    assert status == 2
    assert not result["observed_locally"]
    assert "Landlock unavailable" in result["error"]
    assert not (run / "artifacts").exists()
    assert not (run / "stdout.bin").exists()
