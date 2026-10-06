"""Ejemplos CLI reproducibles; todos los datos se crean debajo de /trial."""

import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

from test_backup import regular_bytes, tree


def main():
    solution = Path(__file__).resolve().parent
    work = solution / ".examples-work"
    work.mkdir(exist_ok=True)
    print("Comando: python3 solution/run_examples.py", flush=True)
    with tempfile.TemporaryDirectory(dir=work) as temporary:
        base = Path(temporary)
        source, repo = base / "fuente con espacios", base / "repo"
        source.mkdir()
        (source / "vacío ü").mkdir()
        (source / "nota.txt").write_bytes(b"primera\n")
        (source / "binario").write_bytes(bytes(range(256)))

        def command(operation, expected_status=0, **arguments):
            arguments.setdefault("repo", repo)
            argv = [sys.executable, str(solution / "backup.py"), operation]
            for name, value in arguments.items():
                argv.extend(["--" + name.replace("_", "-"), str(value)])
            print("$ " + shlex.join(argv), flush=True)
            result = subprocess.run(argv, capture_output=True, text=True, timeout=30)
            print("exit=" + str(result.returncode), flush=True)
            if result.stdout:
                print("stdout: " + result.stdout.rstrip(), flush=True)
            if result.stderr:
                print("stderr: " + result.stderr.rstrip(), flush=True)
            assert result.returncode == expected_status
            if expected_status == 0:
                return json.loads(result.stdout)
            assert not result.stdout

        versions = {"v1": tree(source)}
        command("create", source=source, id="v1", max_bytes=1000000)
        command("verify", id="v1")
        (source / "nota.txt").write_bytes(b"segunda\x00\xff")
        (source / "binario").unlink()
        (source / "añadido.txt").write_text("nuevo\n", encoding="utf-8")
        versions["v2"] = tree(source)
        command("create", source=source, id="v2", max_bytes=1000000)
        before = tree(repo)
        used = regular_bytes(repo)
        print("Suma independiente de st_size: " + str(used), flush=True)
        command("create", expected_status=1, source=source, id="v3", max_bytes=used - 1)
        assert tree(repo) == before
        print("Rechazo: bytes y snapshots anteriores preservados; crecimiento=0", flush=True)
        command("list")
        (source / "nota.txt").unlink()
        (source / "otro vacío").mkdir()
        versions["v3"] = tree(source)
        command("create", source=source, id="v3", max_bytes=1000000)
        source.rename(base / "fuente retirada")
        assert command("list") == {"snapshots": ["v1", "v2", "v3"]}
        for snapshot_id, expected in versions.items():
            command("verify", id=snapshot_id)
            dest = base / ("restaurado-" + snapshot_id)
            command("restore", id=snapshot_id, dest=dest)
            assert tree(dest) == expected
            print(snapshot_id + ": restauración exacta sin fuente original", flush=True)
        assert regular_bytes(repo) <= 1000000
        print("Suma final independiente de st_size: " + str(regular_bytes(repo)), flush=True)
        print("Ejemplos: OK", flush=True)


if __name__ == "__main__":
    main()
