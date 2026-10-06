"""Executable V2 examples, using private test data entirely below /trial."""

from __future__ import annotations

import json
from pathlib import Path
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parent
PROGRAM = HERE.parent / "backup.py"
WORK = HERE / ".work"


def tree(root: Path) -> dict:
    return {path.relative_to(root).as_posix():
            ("dir",) if path.is_dir() else ("file", path.read_bytes())
            for path in sorted(root.rglob("*"))}


def byte_count(repo: Path) -> int:
    return sum(info.st_size for path in repo.rglob("*")
               if stat.S_ISREG((info := path.lstat()).st_mode))


def cli(command: str, *, success: bool = True, **options) -> dict:
    args = [sys.executable, str(PROGRAM), command]
    for key, value in options.items():
        args.extend(["--" + key.replace("_", "-"), str(value)])
    print("$ " + shlex.join(args), flush=True)
    result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    print(f"exit={result.returncode}")
    if result.stdout:
        print("stdout: " + result.stdout.rstrip())
    if result.stderr:
        print("stderr: " + result.stderr.rstrip())
    if success:
        assert result.returncode == 0, result.stderr
        assert result.stderr == ""
        assert len(result.stdout.splitlines()) == 1
        return json.loads(result.stdout)
    assert result.returncode != 0
    assert result.stdout == ""
    error = json.loads(result.stderr)
    assert "error" in error
    return error


def main() -> None:
    WORK.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="examples-", dir=WORK) as raw:
        root = Path(raw)
        source, repo = root / "source", root / "repo"
        source.mkdir()
        (source / "vacío 空").mkdir()
        (source / "cambia.txt").write_bytes(b"primera version\n")
        (source / "eliminado.bin").write_bytes(bytes(range(256)))
        expected = {"v1": tree(source)}
        print("Preparación: fuente V1 con bytes 0..255 y directorio vacío Unicode.")
        assert cli("list", repo=repo) == {"snapshots": []}
        assert cli("create", source=source, repo=repo, id="v1", max_bytes=100_000) == {"id": "v1"}
        assert tree(source) == expected["v1"]
        print(f"Bytes regulares tras v1: {byte_count(repo)} <= 100000")
        assert byte_count(repo) <= 100_000

        (source / "cambia.txt").write_bytes(b"segunda version\0\xff")
        (source / "eliminado.bin").unlink()
        (source / "nuevo con espacios.bin").write_bytes(b"nuevo\0")
        expected["v2"] = tree(source)
        print("Preparación V2: modificación, eliminación y adición.")
        assert cli("create", source=source, repo=repo, id="v2", max_bytes=100_000) == {"id": "v2"}
        assert tree(source) == expected["v2"]

        (source / "cambia.txt").unlink()
        (source / "vacío 空").rmdir()
        (source / "otro vacío").mkdir()
        expected["v3"] = tree(source)
        before = tree(repo)
        used = byte_count(repo)
        print(f"Preparación V3. Repo previo: {used} bytes; límite de rechazo: {used - 1}.")
        cli("create", source=source, repo=repo, id="v3", max_bytes=used - 1, success=False)
        assert tree(repo) == before
        assert byte_count(repo) == used
        assert tree(source) == expected["v3"]
        print("Comprobado: rechazo sin cambios ni crecimiento residual.")
        assert cli("create", source=source, repo=repo, id="v3", max_bytes=100_000) == {"id": "v3"}
        assert tree(source) == expected["v3"]
        assert byte_count(repo) <= 100_000
        print(f"Bytes regulares tras v3: {byte_count(repo)} <= 100000")
        assert cli("list", repo=repo) == {"snapshots": ["v1", "v2", "v3"]}
        shutil.rmtree(source)
        print("Fuente eliminada: verificaciones y restauraciones autosuficientes.")
        for snapshot_id in ("v3", "v1", "v2"):
            assert cli("verify", repo=repo, id=snapshot_id) == {"id": snapshot_id, "valid": True}
            dest = root / ("restored-" + snapshot_id)
            assert cli("restore", repo=repo, id=snapshot_id, dest=dest) == {"id": snapshot_id}
            assert tree(dest) == expected[snapshot_id]
            print(f"Comprobado: {snapshot_id} restaura exactamente archivos, bytes y directorios.")
        protected = root / "restored-v1"
        before = tree(protected)
        cli("restore", repo=repo, id="v2", dest=protected, success=False)
        assert tree(protected) == before
        print("Comprobado: destino no vacío conserva todos sus bytes.")
    print("Ejemplos V2: todas las comprobaciones pasan; datos temporales eliminados.")


if __name__ == "__main__":
    main()
