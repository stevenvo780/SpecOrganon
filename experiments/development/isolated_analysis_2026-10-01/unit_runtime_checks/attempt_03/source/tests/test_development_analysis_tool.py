"""Offline contract checks for the fixed analysis launcher."""

from __future__ import annotations

import hashlib
import json
import stat
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import development_analysis_tool as analyzer  # noqa: E402


def _stage(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    stage = tmp_path / "stage"
    case, inputs, work = (stage / name for name in ("case", "inputs", "work"))
    for path in (case, inputs, work):
        path.mkdir(parents=True, mode=0o700)
    tool = tmp_path / "analysis_tool"
    analyzer.build_analysis_tool(tool)
    return tool, case, inputs, work


def _call(tool: Path, case: Path, inputs: Path, work: Path,
          sha: str) -> subprocess.CompletedProcess[str]:
    args = json.dumps({"script_sha256": sha}, sort_keys=True, separators=(",", ":"))
    return subprocess.run([str(tool), str(case), str(inputs), str(work), args],
                          capture_output=True, text=True, check=False, timeout=5)


def test_builder_is_new_private_executable_with_fixed_entrypoint(tmp_path: Path) -> None:
    tool, _, _, _ = _stage(tmp_path)
    original = tool.read_bytes()
    assert original.startswith(b"#!")
    assert stat.S_IMODE(tool.stat().st_mode) == 0o500
    with pytest.raises(FileExistsError):
        analyzer.build_analysis_tool(tool)
    assert tool.read_bytes() == original


def test_launcher_pins_source_and_case_argument(tmp_path: Path) -> None:
    tool, case, inputs, work = _stage(tmp_path)
    script = work / "analysis.py"
    script.write_text("import json, sys\nprint(json.dumps({'case': sys.argv[1]}))\n",
                      encoding="utf-8")
    script.chmod(0o600)
    digest = hashlib.sha256(script.read_bytes()).hexdigest()
    result = _call(tool, case, inputs, work, digest)
    assert result.returncode == 0 and result.stderr == ""
    assert json.loads(result.stdout) == {"case": str(case)}
    before = script.read_bytes()
    stale = _call(tool, case, inputs, work, "0" * 64)
    assert stale.returncode == 79 and stale.stdout == ""
    assert script.read_bytes() == before


def test_launcher_rejects_symlink_and_nonprivate_script(tmp_path: Path) -> None:
    tool, case, inputs, work = _stage(tmp_path)
    outside = tmp_path / "outside.py"
    outside.write_text("print('{}')\n", encoding="utf-8")
    script = work / "analysis.py"
    script.symlink_to(outside)
    digest = hashlib.sha256(outside.read_bytes()).hexdigest()
    assert _call(tool, case, inputs, work, digest).returncode == 79
    script.unlink()
    script.write_bytes(outside.read_bytes())
    script.chmod(0o644)
    assert _call(tool, case, inputs, work, digest).returncode == 79
