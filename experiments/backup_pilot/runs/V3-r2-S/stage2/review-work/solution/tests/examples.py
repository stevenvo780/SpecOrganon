"""Ejemplos CLI reproducibles; conserva comandos, códigos y respuestas."""

import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys
import tempfile


SOLUTION = Path(__file__).resolve().parents[1]
WORK = SOLUTION / "tests" / "work"
WORK.mkdir(exist_ok=True)


def run(*args, code=0):
    command = [sys.executable, str(SOLUTION / "backup.py"), *map(str, args)]
    print("$ " + shlex.join(command), flush=True)
    result = subprocess.run(command, text=True, capture_output=True, timeout=30)
    print(f"exit={result.returncode}")
    if result.stdout:
        print("stdout: " + result.stdout.rstrip())
    if result.stderr:
        print("stderr: " + result.stderr.rstrip())
    assert result.returncode == code, result
    if code == 0:
        assert isinstance(json.loads(result.stdout), dict)
    else:
        assert not result.stdout


with tempfile.TemporaryDirectory(prefix="examples-", dir=WORK) as raw:
    base = Path(raw)
    source, repo = base / "fuente ñ", base / "repo"
    source.mkdir()
    (source / "vacío").mkdir()
    content = bytes(range(256))
    (source / "datos con espacios.bin").write_bytes(content)
    run("list", "--repo", repo)
    run("create", "--source", source, "--repo", repo, "--id", "v1", "--max-bytes", 10000)
    size = sum(p.lstat().st_size for p in repo.rglob("*") if stat.S_ISREG(p.lstat().st_mode))
    print(f"Conteo independiente (datos + metadata): {size} bytes <= 10000")
    run("verify", "--repo", repo, "--id", "v1")
    before = {str(p.relative_to(repo)): p.read_bytes() for p in repo.rglob("*") if p.is_file()}
    run("create", "--source", source, "--repo", repo, "--id", "v2", "--max-bytes", size - 1, code=1)
    after = {str(p.relative_to(repo)): p.read_bytes() for p in repo.rglob("*") if p.is_file()}
    assert before == after
    print("Rechazo comprobado: mismos archivos/bytes; ningún .pending residual")
    assert not list(repo.glob(".pending-*"))
    run("list", "--repo", repo)
    os.rename(source, base / "fuente fuera de ruta")
    run("restore", "--repo", repo, "--id", "v1", "--dest", base / "destino")
    assert (base / "destino" / "datos con espacios.bin").read_bytes() == content
    assert (base / "destino" / "vacío").is_dir()
    print("Restore autosuficiente: bytes y directorio vacío comprobados")
    (repo / "v1" / "data" / "datos con espacios.bin").write_bytes(b"corrupto")
    run("verify", "--repo", repo, "--id", "v1", code=1)
    run("restore", "--repo", repo, "--id", "v1", "--dest", base / "no_publicado", code=1)
    assert not (base / "no_publicado").exists()
    print("Corrupción rechazada; destino ausente")

print("Ejemplos: OK")
