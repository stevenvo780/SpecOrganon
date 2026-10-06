"""Reproducible CLI examples; all synthetic data lives temporarily in /trial."""

import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile


SCRIPT = Path(__file__).with_name("backup.py")
LOG = Path(__file__).with_name("EXAMPLE_COMMANDS.jsonl")


def contents(root):
    return {path.relative_to(root).as_posix():
            ("dir",) if path.is_dir() else ("file", hashlib.sha256(path.read_bytes()).hexdigest())
            for path in root.rglob("*")}


def run(command, repo, *, snapshot_id=None, source=None, dest=None, limit=None, ok=True):
    argv = [sys.executable, str(SCRIPT), command, "--repo", str(repo)]
    for option, value in (("--id", snapshot_id), ("--source", source),
                          ("--dest", dest), ("--max-bytes", limit)):
        if value is not None:
            argv += [option, str(value)]
    result = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    record = {"command": argv, "returncode": result.returncode,
              "stdout": result.stdout, "stderr": result.stderr}
    with LOG.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=True) + "\n")
    print("$ " + shlex.join(argv))
    print("exit=" + str(result.returncode))
    if result.stdout:
        print("stdout: " + result.stdout.strip())
    if result.stderr:
        print("stderr: " + result.stderr.strip())
    if ok:
        assert result.returncode == 0, result.stderr
        assert result.stderr == ""
        assert len(result.stdout.splitlines()) == 1
        return json.loads(result.stdout)
    assert result.returncode != 0
    assert result.stdout == ""


def main():
    with tempfile.TemporaryDirectory(prefix="backup-example-", dir="/trial") as temporary:
        root = Path(temporary)
        source, repo, dest = root / "fuente", root / "repo", root / "restaurado"
        source.mkdir()
        (source / "vacío ü").mkdir()
        (source / "datos 東京.bin").write_bytes(bytes(range(256)))
        (source / "texto con espacios.txt").write_text("Hola, café 😀\n", encoding="utf-8")
        first_version = contents(source)
        assert run("list", repo) == {"snapshots": []}
        assert run("create", repo, snapshot_id="v1", source=source, limit=100000) == {"id": "v1"}
        assert contents(source) == first_version
        assert run("verify", repo, snapshot_id="v1") == {"id": "v1", "valid": True}
        baseline = contents(repo)
        total = sum(path.stat().st_size for path in repo.rglob("*") if path.is_file())
        print(f"Suma st_size, datos y metadata de v1: {total} bytes <= 100000")
        run("create", repo, snapshot_id="v2", source=source, limit=total - 1, ok=False)
        assert contents(repo) == baseline
        print("Rechazo: repositorio previo idéntico; sin crecimiento residual.")
        (source / "texto con espacios.txt").write_bytes(b"segunda version\x00\xff")
        (source / "nuevo.txt").write_bytes(b"nuevo")
        second_version = contents(source)
        assert run("create", repo, snapshot_id="v2", source=source, limit=100000) == {"id": "v2"}
        assert run("list", repo) == {"snapshots": ["v1", "v2"]}
        shutil.rmtree(source)
        assert run("restore", repo, snapshot_id="v1", dest=dest) == {"id": "v1"}
        assert contents(dest) == first_version
        other_dest = root / "segunda restauración"
        assert run("restore", repo, snapshot_id="v2", dest=other_dest) == {"id": "v2"}
        assert contents(other_dest) == second_version
        print("Ambas versiones restauradas exactamente, sin la fuente original.")
        protected = contents(dest)
        run("restore", repo, snapshot_id="v2", dest=dest, ok=False)
        assert contents(dest) == protected
        print("Destino no vacío protegido: bytes y estructura idénticos.")
        clone = root / "repo-corrupto"
        shutil.copytree(repo, clone)
        checksum = clone / "snapshots" / "v1" / "manifest.sha256"
        checksum.write_bytes(b"x" + checksum.read_bytes()[1:])
        run("verify", clone, snapshot_id="v1", ok=False)
        run("restore", clone, snapshot_id="v1", dest=root / "fallido", ok=False)
        assert not (root / "fallido").exists()
        assert run("list", clone) == {"snapshots": ["v2"]}
        print("Corrupción de metadata rechazada; ninguna restauración publicada.")
        print("Ejemplos y comprobaciones: OK")


if __name__ == "__main__":
    main()
