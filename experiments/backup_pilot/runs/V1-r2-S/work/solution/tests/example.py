"""Executable V1 example. Prints commands, JSON results and independent checks."""

import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

from test_backup import BACKUP, SOLUTION, regular_bytes, tree_signature


def main():
    with tempfile.TemporaryDirectory(prefix="example-v1-", dir=SOLUTION / "tests") as temporary:
        root = Path(temporary)
        source, repo, dest = (root / name for name in ("fuente", "repo", "restaurado"))
        source.mkdir()
        (source / "Documentos con espacios").mkdir()
        (source / "Documentos con espacios" / "Vacío 日本語").mkdir()
        (source / "notas.txt").write_text("Backup V1: café y 世界\n", encoding="utf-8")
        (source / "Documentos con espacios" / "bytes.bin").write_bytes(bytes(range(256)))
        expected = tree_signature(source)

        def run(*args, code=0):
            command = [sys.executable, str(BACKUP), *map(str, args)]
            print("$ " + shlex.join(command), flush=True)
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            print(f"exit={result.returncode}")
            if result.stdout:
                print("stdout: " + result.stdout.rstrip())
            if result.stderr:
                print("stderr: " + result.stderr.rstrip())
            assert result.returncode == code, result
            if code == 0:
                return json.loads(result.stdout)
            assert result.stdout == ""

        assert run("list", "--repo", repo) == {"snapshots": []}
        assert run("create", "--source", source, "--repo", repo, "--id", "V1-demo",
                   "--max-bytes", 100000) == {"id": "V1-demo"}
        assert tree_signature(source) == expected
        print("CHECK: fuente intacta")
        used = regular_bytes(repo)
        assert used <= 100000
        assert used > regular_bytes(source)
        print(f"CHECK: {used} bytes totales, incluidos manifiesto y sello, <= 100000")
        unchanged = tree_signature(repo)
        run("create", "--source", source, "--repo", repo, "--id", "sin-capacidad",
            "--max-bytes", used - 1, code=1)
        assert tree_signature(repo) == unchanged
        assert regular_bytes(repo) == used
        print("CHECK: límite inferior al uso existente rechazado sin crecimiento ni cambios")
        assert run("verify", "--repo", repo, "--id", "V1-demo") == {"id": "V1-demo", "valid": True}
        shutil.rmtree(source)
        print("CHECK: fuente retirada antes de restaurar")
        assert run("restore", "--repo", repo, "--id", "V1-demo", "--dest", dest) == {"id": "V1-demo"}
        assert tree_signature(dest) == expected
        print("CHECK: árbol, directorios vacíos y bytes restaurados exactamente")
        assert run("list", "--repo", repo) == {"snapshots": ["V1-demo"]}
        protected = tree_signature(dest)
        run("restore", "--repo", repo, "--id", "V1-demo", "--dest", dest, code=1)
        assert tree_signature(dest) == protected
        print("CHECK: destino no vacío preservado")
        data = repo / "snapshots" / "V1-demo" / "data" / "notas.txt"
        data.write_bytes(b"CORRUPCION")
        run("verify", "--repo", repo, "--id", "V1-demo", code=1)
        run("restore", "--repo", repo, "--id", "V1-demo", "--dest", root / "rechazado", code=1)
        assert not (root / "rechazado").exists()
        print("CHECK: corrupción rechazada sin publicar destino")
        print("EXAMPLE PASS")


if __name__ == "__main__":
    main()
