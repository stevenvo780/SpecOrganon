"""Reproducible CLI examples with their exact argv/output/return codes."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="example-", dir=root / "testing") as temporary:
    base = Path(temporary)
    source, repo, dest = [base / n for n in ("source", "repo", "dest")]
    source.mkdir()
    (source / "empty dir").mkdir()
    (source / "hola 日本語.txt").write_bytes(b"hello\x00\xff")
    for command in ("list", "create", "verify", "restore", "list"):
        argv = [sys.executable, str(root / "backup.py"), command, "--repo", str(repo)]
        if command != "list":
            argv += ["--id", "example"]
        if command == "create":
            argv += ["--source", str(source)]
        if command == "restore":
            argv += ["--dest", str(dest)]
        result = subprocess.run(argv, capture_output=True, text=True, timeout=10)
        print(json.dumps({"argv": argv, "exit_code": result.returncode,
                          "stdout": result.stdout, "stderr": result.stderr}, ensure_ascii=False))
        assert result.returncode == 0, result.stderr
        assert isinstance(json.loads(result.stdout), dict)
    assert (dest / "hola 日本語.txt").read_bytes() == b"hello\x00\xff"
    assert (dest / "empty dir").is_dir()
