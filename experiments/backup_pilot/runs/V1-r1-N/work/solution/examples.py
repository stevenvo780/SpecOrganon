"""Ejemplo ejecutable V1 con registro de comandos y comprobación de bytes."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from test_backup import inventory, record, regular_bytes


script = Path(__file__).with_name("backup.py")
with tempfile.TemporaryDirectory(prefix="backup-example-", dir=script.parent.parent) as temporary:
    base = Path(temporary)
    source = base / "documentos"
    source.mkdir()
    (source / "vacío").mkdir()
    (source / "café 日本語.txt").write_bytes("Documento con Unicode\n".encode())
    (source / "binario con espacios.bin").write_bytes(bytes(range(256)))
    (source / "cero").touch()
    expected = inventory(source)
    repo = base / "repo"
    dest = base / "restauración"
    commands = [
        ["create", "--source", str(source), "--repo", str(repo), "--id", "ejemplo_V1",
         "--max-bytes", "4096"],
        ["verify", "--repo", str(repo), "--id", "ejemplo_V1"],
        ["list", "--repo", str(repo)],
        ["restore", "--repo", str(repo), "--id", "ejemplo_V1", "--dest", str(dest)],
    ]
    for arguments in commands:
        if arguments[0] == "restore":
            used = regular_bytes(repo)
            assert used <= 4096
            print(f"Bytes regulares totales, incluida metadata: {used} <= 4096", flush=True)
            before = inventory(repo)
            rejected_command = [sys.executable, str(script), "create", "--source", str(source),
                                "--repo", str(repo), "--id", "no_cabe",
                                "--max-bytes", str(used - 1)]
            rejected = subprocess.run(rejected_command, capture_output=True, text=True, timeout=30)
            record(rejected_command, rejected)
            assert rejected.returncode != 0 and rejected.stdout == ""
            assert inventory(repo) == before
            print("PASS: límite inferior a bytes existentes rechazado sin crecimiento.", flush=True)
            assert inventory(source) == expected
            shutil.rmtree(source)
            print("Fuente original eliminada antes de restaurar.", flush=True)
        command = [sys.executable, str(script), *arguments]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        record(command, result)
        assert result.returncode == 0, result.stderr
        assert isinstance(json.loads(result.stdout), dict)
    assert inventory(dest) == expected
    print("PASS: bytes y directorios exactos; restauración sin fuente original.", flush=True)
