"""Ejemplos reproducibles; comandos y resultados impresos en stdout."""

import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys


BASE = Path(__file__).resolve().parents[1]
ROOT = BASE / "results" / "example"
if ROOT.exists():
    shutil.rmtree(ROOT)
ROOT.mkdir(parents=True)
source = ROOT / "fuente"
source.mkdir()
(source / "vacío ñ").mkdir()
(source / "bytes y espacios.bin").write_bytes(bytes(range(256)))


def run(*args, expected=0):
    command = [sys.executable, str(BASE / "backup.py"), *map(str, args)]
    print("$ " + shlex.join(command), flush=True)
    result = subprocess.run(command, capture_output=True, text=True, timeout=20)
    print(json.dumps({"returncode": result.returncode, "stdout": result.stdout,
                      "stderr": result.stderr}, ensure_ascii=True), flush=True)
    assert result.returncode == expected
    if expected == 0:
        return json.loads(result.stdout)
    assert not result.stdout


repo = ROOT / "repo"
assert run("list", "--repo", repo) == {"snapshots": []}
assert run("create", "--source", source, "--repo", repo, "--id", "ejemplo",
           "--max-bytes", 100_000) == {"id": "ejemplo"}
assert run("verify", "--repo", repo, "--id", "ejemplo") == {"id": "ejemplo", "valid": True}
assert run("list", "--repo", repo) == {"snapshots": ["ejemplo"]}
shutil.rmtree(source)
print("Fuente eliminada antes de restore.", flush=True)
dest = ROOT / "restaurado"
assert run("restore", "--repo", repo, "--id", "ejemplo", "--dest", dest) == {"id": "ejemplo"}
assert (dest / "bytes y espacios.bin").read_bytes() == bytes(range(256))
assert (dest / "vacío ñ").is_dir()
occupied = sum(p.stat().st_size for p in repo.rglob("*") if p.is_file())
print(json.dumps({"repo_regular_bytes": occupied}), flush=True)
source.mkdir()
run("create", "--source", source, "--repo", repo, "--id", "no-cabe",
    "--max-bytes", occupied - 1, expected=1)
assert sum(p.stat().st_size for p in repo.rglob("*") if p.is_file()) == occupied
assert run("verify", "--repo", repo, "--id", "ejemplo") == {"id": "ejemplo", "valid": True}
assert list((repo / ".staging").iterdir()) == []
print("Comparación exacta y rechazo sin crecimiento residual: OK", flush=True)
