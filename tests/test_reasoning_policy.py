"""Bounded explicit Codex reasoning-effort transport/launcher plumbing.

These tests exercise the policy/launch plumbing for the new --codex-reasoning-effort
without invoking native models, real provider calls, Docker image execution or
credential/auth operations. Schema2 transport roots must refuse silent resume;
effort changes in a persisted schema3 policy must also refuse to reuse an old
container. Docker CLI calls are mocked so unit tests do not require an image
registry or daemon.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from scripts.autonomous_software_controller import main as launcher_cli
from specorganon.docker_roles import DockerRoles, DockerRoleError
from specorganon.role_jobs import digest, _json, _write


NATIVE_IMAGE = "sha256:" + "a" * 64
TEST_IMAGE = "sha256:" + "b" * 64
SOURCE_ROOT = str(Path(__file__).resolve().parents[1])


def _completed(stdout=b"", stderr=b"", returncode=0):
    command = ["/usr/bin/docker", "mocked"]
    return subprocess.CompletedProcess(command, returncode, stdout, stderr)


def _docker_cli_factory(images, inspect_records=None):
    """Replace DockerRoles._cli so constructor/prepare do not touch Docker."""

    def _cli(argv, *, allow_failure=False):
        if isinstance(argv, list) and argv and argv[0] == "image":
            ref = argv[2]
            return _completed(stdout=(ref + "\n").encode())
        if isinstance(argv, list) and argv and argv[0] == "inspect":
            name = argv[2] if len(argv) > 2 else ""
            record = (inspect_records or {}).get(name, {
                "Id": name, "Image": images["native"], "State": {"Running": False, "ExitCode": 0,
                                                                    "OOMKilled": False},
                "Config": {"Labels": {}, "Cmd": [], "Entrypoint": []},
                "HostConfig": {"NetworkMode": "none", "ReadonlyRootfs": True, "Mounts": []},
            })
            return _completed(stdout=json.dumps([record]).encode(), returncode=400)
        return _completed(returncode=1)

    return _cli


@pytest.fixture
def docker_cli_patched(monkeypatch, tmp_path):
    """Patch DockerRoles._cli so DockerRoles() works without a daemon."""
    catalog = tmp_path / "public-catalog.json"
    catalog.write_text(json.dumps({
        "models": [
            {"slug": "gpt-6.1-sol",
             "supported_reasoning_levels": [
                 {"effort": "low"}, {"effort": "medium"},
                 {"effort": "high"}, {"effort": "xhigh"}]},
        ],
    }))
    monkeypatch.setattr(DockerRoles, "_cli", staticmethod(_docker_cli_factory(
        {"native": NATIVE_IMAGE, "test": TEST_IMAGE})))
    executable = tmp_path / 'synthetic-agy'; executable.write_bytes(b'fixture only; never executed')
    profile = tmp_path / 'synthetic-profile'; profile.mkdir()
    return {"catalog": catalog, "source_root": SOURCE_ROOT,
            'gemini_executable': str(executable), 'gemini_profile': str(profile)}


def _options(docker_ctx):
    return {"native_image": NATIVE_IMAGE, "test_image": TEST_IMAGE,
            "source_root": SOURCE_ROOT, "public_catalog": str(docker_ctx["catalog"]),
            'gemini_executable': docker_ctx['gemini_executable'], 'gemini_profile': docker_ctx['gemini_profile']}


def test_transport_policy_is_persisted_with_schema4_and_effort(docker_cli_patched, tmp_path):
    DockerRoles(tmp_path / "transport", **_options(docker_cli_patched))
    policy = _json(tmp_path / "transport" / "transport-policy.json")
    assert policy["schema"] == 4
    assert policy["codex_reasoning_effort"] == "low"


def test_transport_policy_accepts_explicit_effort_and_round_trips(docker_cli_patched, tmp_path):
    DockerRoles(tmp_path / "transport", codex_reasoning_effort="high", **_options(docker_cli_patched))
    DockerRoles(tmp_path / "transport", codex_reasoning_effort="high", **_options(docker_cli_patched))
    policy = _json(tmp_path / "transport" / "transport-policy.json")
    assert policy["codex_reasoning_effort"] == "high" and policy["schema"] == 4


def test_transport_policy_refuses_schema2_silent_resume(docker_cli_patched, tmp_path):
    root = tmp_path / "transport"
    policy_path = root / "transport-policy.json"
    # Plant a schema=2 policy that mirrors the earlier transport contract but
    # lacks the new field. The transport must refuse to resume silently.
    fake = {"schema": 2, "images": {"native": NATIVE_IMAGE, "test": TEST_IMAGE},
            "routes": {"author": ("codex", "gpt-6.1-sol"), "review": ("gemini", "gemini-3.1-pro-high")},
            "test_timeout_seconds": 60, "source_root": SOURCE_ROOT,
            "public_catalog_sha256": "deadbeef" * 8, "codex_original_volume": "specorganon-lab_codex-home",
            "gemini_original_profile": "/home/stev/.gemini",
            "gemini_executable_sha256": "deadbeef" * 8, "seccomp_sha256": None}
    root.mkdir(parents=True, mode=0o700)
    _write(policy_path, fake)
    with pytest.raises(DockerRoleError, match="schema4"):
        DockerRoles(root, **_options(docker_cli_patched))


def test_transport_policy_refuses_effort_change(docker_cli_patched, tmp_path):
    root = tmp_path / "transport"
    DockerRoles(root, codex_reasoning_effort="low", **_options(docker_cli_patched))
    with pytest.raises(DockerRoleError, match="policy"):
        DockerRoles(root, codex_reasoning_effort="high", **_options(docker_cli_patched))


def test_transport_rejects_unsupported_effort_at_construction(docker_cli_patched, tmp_path):
    for bad in ("min", "max", "ultra", "default", "", None, 5):
        with pytest.raises(DockerRoleError):
            DockerRoles(tmp_path / "transport", codex_reasoning_effort=bad,
                        **_options(docker_cli_patched))


def test_launcher_accepts_explicit_effort_and_forwards_to_docker(monkeypatch, tmp_path):
    captured = {}

    class _FakeRoles:
        _CODEX_REASONING_EFFORTS = DockerRoles._CODEX_REASONING_EFFORTS

        def __init__(self, root, **kwargs):
            captured["kwargs"] = kwargs
            self.root = root

    monkeypatch.setattr("scripts.autonomous_software_controller.DockerRoles", _FakeRoles)
    monkeypatch.setattr("scripts.autonomous_software_controller.engine.get_state",
                        lambda case: {"project": {"approval_policy": "local"}})
    monkeypatch.setattr("scripts.autonomous_software_controller.case_report",
                        lambda case: {"schema": 1})
    monkeypatch.setattr("scripts.autonomous_software_controller._write", lambda *a, **k: None)
    monkeypatch.setattr("scripts.autonomous_software_controller.Controller",
                        lambda *a, **k: type("C", (), {"step": lambda self: {"action": "complete",
                                                                                "package_allowed": True},
                                                        "delivery": None})())
    fake_args = [
        "--case", "/tmp/case",
        "--run-root", str(tmp_path / "run"),
        "--contract", str(tmp_path / "contract.md"),
        "--mandate", str(tmp_path / "mandate.md"),
        "--native-image", NATIVE_IMAGE,
        "--test-image", TEST_IMAGE,
        "--public-catalog", str(tmp_path / "catalog.json"),
        "--codex-reasoning-effort", "high",
        "--steps", "1",
    ]
    (tmp_path / "run").mkdir(parents=True)
    (tmp_path / "contract.md").write_text("contract")
    (tmp_path / "mandate.md").write_text("mandate")
    (tmp_path / "catalog.json").write_text("{}")
    monkeypatch.setattr("sys.argv", ["autonomous_software_controller.py", *fake_args])
    assert launcher_cli() == 0
    assert captured["kwargs"]["codex_reasoning_effort"] == "high"


def test_launcher_default_effort_is_low(monkeypatch, tmp_path):
    captured = {}

    class _FakeRoles:
        _CODEX_REASONING_EFFORTS = DockerRoles._CODEX_REASONING_EFFORTS

        def __init__(self, root, **kwargs):
            captured["kwargs"] = kwargs
            self.root = root

    monkeypatch.setattr("scripts.autonomous_software_controller.DockerRoles", _FakeRoles)
    monkeypatch.setattr("scripts.autonomous_software_controller.engine.get_state",
                        lambda case: {"project": {"approval_policy": "local"}})
    monkeypatch.setattr("scripts.autonomous_software_controller.case_report",
                        lambda case: {"schema": 1})
    monkeypatch.setattr("scripts.autonomous_software_controller._write", lambda *a, **k: None)
    monkeypatch.setattr("scripts.autonomous_software_controller.Controller",
                        lambda *a, **k: type("C", (), {"step": lambda self: {"action": "complete",
                                                                                "package_allowed": True},
                                                        "delivery": None})())
    fake_args = [
        "--case", "/tmp/case",
        "--run-root", str(tmp_path / "run"),
        "--contract", str(tmp_path / "contract.md"),
        "--mandate", str(tmp_path / "mandate.md"),
        "--native-image", NATIVE_IMAGE,
        "--test-image", TEST_IMAGE,
        "--public-catalog", str(tmp_path / "catalog.json"),
        "--steps", "1",
    ]
    (tmp_path / "run").mkdir(parents=True)
    (tmp_path / "contract.md").write_text("contract")
    (tmp_path / "mandate.md").write_text("mandate")
    (tmp_path / "catalog.json").write_text("{}")
    monkeypatch.setattr("sys.argv", ["autonomous_software_controller.py", *fake_args])
    assert launcher_cli() == 0
    assert captured["kwargs"]["codex_reasoning_effort"] == "low"


def test_launcher_rejects_unknown_effort_value(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.autonomous_software_controller.engine.get_state",
                        lambda case: {"project": {"approval_policy": "local"}})
    (tmp_path / "contract.md").write_text("contract")
    (tmp_path / "mandate.md").write_text("mandate")
    fake_args = [
        "--case", "/tmp/case",
        "--run-root", str(tmp_path),
        "--contract", str(tmp_path / "contract.md"),
        "--mandate", str(tmp_path / "mandate.md"),
        "--native-image", NATIVE_IMAGE,
        "--test-image", TEST_IMAGE,
        "--public-catalog", str(tmp_path / "catalog.json"),
        "--codex-reasoning-effort", "ultra",
        "--steps", "1",
    ]
    monkeypatch.setattr("sys.argv", ["autonomous_software_controller.py", *fake_args])
    with pytest.raises(SystemExit):
        launcher_cli()


def _stub_identity(monkeypatch):
    """Bypass execution_identity() file resolution so main() can be exercised
    without the real /usr/local/bin/codex or /usr/local/bin/agy executable."""
    monkeypatch.setenv("SPECORGANON_ROLE_IMAGE_ID", "sha256:" + "a" * 64)
    from scripts.controller_native_role import execution_identity
    def _fake(provider, executable, _real=execution_identity):
        try:
            return _real(provider, executable)
        except (OSError, ValueError):
            return {
                "schema": 1, "image_id": "sha256:" + "a" * 64,
                "executable_path": executable, "executable_sha256": digest(b"synthetic"),
                "known_configuration_path": str(Path(executable).parent / "config.toml"),
                "known_configuration_sha256": None,
                "other_effective_configuration": "unknown; trusted launcher/profile boundary"}
    monkeypatch.setattr("scripts.controller_native_role.execution_identity", _fake)


def test_native_bridge_receives_explicit_low_effort_for_codex_role(
        docker_cli_patched, monkeypatch, tmp_path):
    # The bridge must:
    #   (a) parse --codex-reasoning-effort as a CLI argument,
    #   (b) validate against the public model's supported_reasoning_levels,
    #   (c) emit -c model_reasoning_effort="<value>" in the native argv,
    #   (d) record requested_reasoning_effort in catalog_metadata so the
    #       execution_identity comparison excludes it (we never claim the
    #       remote server honored the override).
    from scripts.controller_native_role import main as bridge_main, native_argv
    from pathlib import Path

    request_payload = {"schema": 1, "role": "review", "role_instructions": "fixture",
                       "documents": {}}
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request_payload))
    catalog = docker_cli_patched["catalog"]
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    _stub_identity(monkeypatch)
    captured = {}

    def _capture(provider, model, prompt, *, model_catalog=None, reasoning_effort=None):
        captured["reasoning_effort"] = reasoning_effort
        captured["provider"] = provider
        captured["argv"] = native_argv(provider, model, prompt,
                                         model_catalog=model_catalog,
                                         reasoning_effort=reasoning_effort)
        return captured["argv"]

    monkeypatch.setattr("scripts.controller_native_role.native_argv", _capture)

    # Stop the bridge at the dispatch boundary; we only need argv to be built.
    def _explode(*args, **kwargs):
        raise RuntimeError("captured argv before native execution")
    monkeypatch.setattr("scripts.controller_native_role.JobStore", _explode)

    with pytest.raises(RuntimeError, match="captured argv"):
        bridge_main(["--provider", "codex", "--model", "gpt-6.1-sol",
                     "--request", str(request_path),
                     "--output-dir", str(tmp_path / "out"),
                     "--model-catalog", str(catalog),
                     "--codex-reasoning-effort", "low"])
    # native_argv() was invoked with the CLI value; the bridge did not silently
    # fall back to a default effort.
    assert captured["reasoning_effort"] == "low"
    assert captured["provider"] == "codex"
    assert 'model_reasoning_effort="low"' in captured["argv"]


def test_native_bridge_argv_emits_model_reasoning_effort_override(docker_cli_patched, tmp_path, monkeypatch):
    from scripts.controller_native_role import native_argv
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    args = native_argv("codex", "gpt-6.1-sol", "fixture", reasoning_effort="high")
    assert 'model_reasoning_effort="high"' in args
    # The preflight feature argv (no native exec command) must also carry it,
    # so the preflight proves the same override the model call will use.
    from scripts.controller_native_role import codex_feature_argv
    assert 'model_reasoning_effort="high"' in codex_feature_argv(args)


def test_native_bridge_records_requested_effort_in_catalog_metadata(
        docker_cli_patched, monkeypatch, tmp_path):
    # The bridge records requested_reasoning_effort in catalog_metadata, which
    # is excluded from the execution_identity comparison. This is a metadata
    # record, not a claim that the remote server observed/honored it.
    from scripts.controller_native_role import main as bridge_main
    from pathlib import Path

    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps({"schema": 1, "role": "review",
                                         "role_instructions": "fixture", "documents": {}}))
    catalog = docker_cli_patched["catalog"]
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    _stub_identity(monkeypatch)
    captured_calls = []

    class _FakeStore:
        def __init__(self, *args, **kwargs):
            pass

        def execute(self, *args, **kwargs):
            captured_calls.append((args, dict(kwargs)))
            raise RuntimeError("captured metadata before dispatch")

    monkeypatch.setattr("scripts.controller_native_role.JobStore", _FakeStore)

    with pytest.raises(RuntimeError):
        bridge_main(["--provider", "codex", "--model", "gpt-6.1-sol",
                     "--request", str(request_path),
                     "--output-dir", str(tmp_path / "out"),
                     "--model-catalog", str(catalog),
                     "--codex-reasoning-effort", "xhigh"])
    assert captured_calls, "bridge did not reach the dispatch boundary"
    metadata_used = captured_calls[0][1].get("metadata") or {}
    assert metadata_used.get("requested_reasoning_effort") == "xhigh"
    # The remote-effective value is NOT observed; the bridge must not fabricate
    # an outcome it did not measure.
    assert metadata_used.get("effective_remote_reasoning_effort") == "not observed"


def test_native_bridge_rejects_effort_for_gemini_role(docker_cli_patched, tmp_path, monkeypatch):
    from scripts.controller_native_role import NativeRoleError, main as bridge_main
    _stub_identity(monkeypatch)
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps({"schema": 1, "role": "review", "role_instructions": "fixture",
                                         "documents": {}}))
    with pytest.raises(NativeRoleError, match="Gemini"):
        bridge_main(["--provider", "gemini", "--model", "gemini-3.1-pro-high",
                     "--request", str(request_path), "--output-dir", str(tmp_path / "out"),
                     "--codex-reasoning-effort", "low"])


@pytest.mark.parametrize('role,codex_role',[('author','author'),('review','review'),('review','author')])
def test_actual_prepared_role_arguments_pin_only_codex_role(docker_cli_patched,tmp_path,role,codex_role):
    opts=_options(docker_cli_patched)
    if codex_role=='review':
        opts.update(author_provider='gemini',author_model='gemini-3.1-pro-high',
                    reviewer_provider='codex',reviewer_model='gpt-6.1-sol')
    t=DockerRoles(tmp_path/'transport',codex_reasoning_effort='medium',**opts)
    request={'schema':1,'role':'review' if role=='review' else 'author',
             'role_instructions':'Synthetic preparation only; never execute a model','documents':{}}
    _,plan=t._prepare('prepared-role',role,request)
    if role==codex_role:
        index=plan['create_argv'].index('--codex-reasoning-effort')
        assert plan['create_argv'][index+1]=='medium'
        assert plan['codex_reasoning_effort']=='medium'
    else:
        assert '--codex-reasoning-effort' not in plan['create_argv']
        assert plan['codex_reasoning_effort'] is None
    assert plan['container_id'] is None
