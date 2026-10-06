"""Reproducible V1 examples, with retained fixtures and checked outputs."""

import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys


HERE = Path(__file__).absolute().parent
BASE = HERE / "example-data"


def inventory(path):
    return {
        item.relative_to(path).as_posix(): None if item.is_dir() else hashlib.sha256(item.read_bytes()).hexdigest()
        for item in path.rglob("*")
    }


def command(*args, expected=None, failure=False):
    argv = [sys.executable, str(HERE / "backup.py"), *map(str, args)]
    print("$ " + shlex.join(argv), flush=True)
    result = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    print(f"exit={result.returncode}")
    if result.stdout:
        print("stdout: " + result.stdout.rstrip())
    if result.stderr:
        print("stderr: " + result.stderr.rstrip())
    if failure:
        assert result.returncode != 0 and result.stdout == "", result
        assert "error" in json.loads(result.stderr), result
    else:
        assert result.returncode == 0 and not result.stderr, result
        assert len(result.stdout.splitlines()) == 1, result
        assert json.loads(result.stdout) == expected, result


def main():
    if BASE.exists():
        shutil.rmtree(BASE)
    BASE.mkdir()
    source = BASE / "árbol fuente"
    source.mkdir()
    (source / "vacío" / "anidado").mkdir(parents=True)
    (source / "documento 日本語.txt").write_text("Primera versión V1.\n¡Bytes verificables!\n", encoding="utf-8")
    (source / "arbitrary.bin").write_bytes(bytes(range(256)) * 4)
    (source / "zero.bin").touch()
    expected = inventory(source)
    (BASE / "expected.json").write_text(json.dumps(expected, ensure_ascii=True, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    repo = BASE / "repo"
    dest = BASE / "restored"
    empty_repo = BASE / "empty-repo"
    empty_repo.mkdir()
    command("list", "--repo", empty_repo, expected={"snapshots": []})
    command("create", "--source", source, "--repo", repo, "--id", "V1", expected={"id": "V1"})
    assert inventory(source) == expected
    command("create", "--source", source, "--repo", repo, "--id", "V1", failure=True)
    command("verify", "--repo", repo, "--id", "V1", expected={"id": "V1", "valid": True})
    command("list", "--repo", repo, expected={"snapshots": ["V1"]})
    shutil.rmtree(source)
    print("Fixture action: source deleted; subsequent restore has no source access.")
    command("restore", "--repo", repo, "--id", "V1", "--dest", dest, expected={"id": "V1"})
    assert inventory(dest) == expected
    before = inventory(dest)
    command("restore", "--repo", repo, "--id", "V1", "--dest", dest, failure=True)
    assert inventory(dest) == before
    corrupt = BASE / "corrupt-repo"
    shutil.copytree(repo, corrupt)
    victim = corrupt / "snapshots" / "V1" / "data" / "arbitrary.bin"
    content = victim.read_bytes()
    victim.write_bytes(bytes([content[0] ^ 1]) + content[1:])
    print("Fixture action: one payload byte flipped in a separate repository copy.")
    command("verify", "--repo", corrupt, "--id", "V1", failure=True)
    command("restore", "--repo", corrupt, "--id", "V1", "--dest", BASE / "never-published", failure=True)
    assert not (BASE / "never-published").exists()
    print("PASS: 9 CLI examples; source unchanged, exact independent restore, protected destination and corruption rejection checked.")


if __name__ == "__main__":
    main()
