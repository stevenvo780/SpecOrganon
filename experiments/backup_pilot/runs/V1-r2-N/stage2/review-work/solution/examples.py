"""Run and record CLI examples against disposable fixtures inside /trial."""

import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parent


def main():
    with tempfile.TemporaryDirectory(prefix=".backup-example-", dir=HERE.parent) as work:
        root = Path(work)
        source = root / "documentos"
        repo = root / "repositorio"
        dest = root / "restaurado"
        source.mkdir()
        (source / "vacío").mkdir()
        (source / "saludo ñ.txt").write_text("Hola, mundo.\n", encoding="utf-8")
        (source / "datos.bin").write_bytes(bytes(range(256)))
        expected = {path.name: path.read_bytes() for path in source.iterdir() if path.is_file()}

        def run(*args, expected_code=0):
            command = [sys.executable, str(HERE / "backup.py"), *map(str, args)]
            print("$ " + shlex.join(command), flush=True)
            process = subprocess.run(command, text=True, capture_output=True, timeout=30)
            print("exit=" + str(process.returncode))
            if process.stdout:
                print("stdout: " + process.stdout.rstrip())
            if process.stderr:
                print("stderr: " + process.stderr.rstrip())
            assert process.returncode == expected_code
            if expected_code == 0:
                return json.loads(process.stdout)

        run("list", "--repo", repo)
        run("create", "--source", source, "--repo", repo, "--id", "ejemplo",
            "--max-bytes", "10000")
        run("verify", "--repo", repo, "--id", "ejemplo")
        run("list", "--repo", repo)
        run("restore", "--repo", repo, "--id", "ejemplo", "--dest", dest)
        assert (dest / "vacío").is_dir()
        assert {path.name: path.read_bytes() for path in dest.iterdir() if path.is_file()} == expected
        before = {path.name: path.read_bytes() for path in repo.iterdir()}
        size = sum(path.stat().st_size for path in repo.rglob("*") if path.is_file())
        print("Bytes regulares del repositorio (incluye metadata): " + str(size))
        run("create", "--source", source, "--repo", repo, "--id", "no_cabe",
            "--max-bytes", str(size - 1), expected_code=1)
        assert {path.name: path.read_bytes() for path in repo.iterdir()} == before
        run("verify", "--repo", repo, "--id", "ejemplo")
        print("OK: restauración exacta; límite bajo rechazado sin crecimiento ni cambios.")


if __name__ == "__main__":
    main()
