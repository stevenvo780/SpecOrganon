"""Ejemplo contractual V2 reproducible: tres versiones y fuente eliminada."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


SOLUTION = Path(__file__).resolve().parents[1]
WORK = SOLUTION / "examples" / "work"
WORK.mkdir(exist_ok=True)


def inventory(root):
    result = {}
    for current, directories, files in os.walk(root):
        for name in directories:
            result[str((Path(current) / name).relative_to(root))] = {"type": "directory"}
        for name in files:
            path = Path(current) / name
            result[str(path.relative_to(root))] = {"size": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return result


with tempfile.TemporaryDirectory(prefix="v2-", dir=WORK) as workspace:
    root = Path(workspace)
    source = root / "fuente Unicode 日本語"
    repo = root / "repo"
    source.mkdir()
    (source / "vacío").mkdir()
    (source / "documento con espacios.txt").write_text("primera versión\n", encoding="utf-8")
    (source / "binario").write_bytes(bytes(range(256)))
    versions = {}

    def run(command, **arguments):
        cli = [sys.executable, str(SOLUTION / "backup.py"), command]
        for key, value in arguments.items():
            cli.extend(["--" + key, str(value)])
        print("$ " + " ".join(json.dumps(word, ensure_ascii=False) for word in cli), flush=True)
        completed = subprocess.run(cli, capture_output=True, text=True, check=True)
        print(completed.stdout.strip(), flush=True)
        if completed.stderr:
            raise AssertionError(completed.stderr)
        return json.loads(completed.stdout)

    assert run("list", repo=repo) == {"snapshots": []}
    for identifier in ("v1", "v2", "v3"):
        if identifier == "v2":
            (source / "documento con espacios.txt").write_text("segunda versión modificada\n", encoding="utf-8")
            (source / "binario").unlink()
            (source / "añadido").write_bytes(b"\0\xffnuevo")
        if identifier == "v3":
            (source / "añadido").unlink()
            (source / "documento con espacios.txt").unlink()
            (source / "nuevo vacío").mkdir()
            (source / "tercera versión").write_bytes(b"final\0")
        versions[identifier] = inventory(source)
        assert run("create", source=source, repo=repo, id=identifier) == {"id": identifier}
        assert inventory(source) == versions[identifier]
    shutil.rmtree(source)
    print("Fuente original eliminada; las restauraciones siguientes dependen solo del repositorio.", flush=True)
    assert run("list", repo=repo) == {"snapshots": ["v1", "v2", "v3"]}
    for identifier, expected in versions.items():
        assert run("verify", repo=repo, id=identifier) == {"id": identifier, "valid": True}
        destination = root / ("restauración " + identifier)
        assert run("restore", repo=repo, id=identifier, dest=destination) == {"id": identifier}
        assert inventory(destination) == expected
        print(json.dumps({"version": identifier, "exact_match": True, "inventory": expected}, ensure_ascii=False, sort_keys=True), flush=True)
    print("Ejemplo V2: PASS (3/3 restauraciones exactas).", flush=True)
