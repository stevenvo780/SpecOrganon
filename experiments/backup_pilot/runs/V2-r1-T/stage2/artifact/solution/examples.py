"""Reproducible V2 example, using only private synthetic files."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'evidence' / 'v2-budget'


def contents(path):
    return {str(p.relative_to(path)): None if p.is_dir() else p.read_bytes()
            for p in path.rglob('*')}


def total(path):
    return sum(p.stat().st_size for p in path.rglob('*') if p.is_file())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    records = []
    with tempfile.TemporaryDirectory(dir=OUT, prefix='example-') as temporary:
        base = Path(temporary)
        source, repo = base / 'source', base / 'repo'
        source.mkdir()
        (source / 'vacío').mkdir()
        (source / 'texto 日本語').write_bytes(b'version one\0\xff')
        expected = {'v1': contents(source)}

        def cli(operation, expected_code=0, **options):
            argv = [sys.executable, str(ROOT / 'backup.py'), operation, '--repo', str(repo)]
            for key, value in options.items():
                argv += ['--' + key.replace('_', '-'), str(value)]
            p = subprocess.run(argv, capture_output=True, text=True, timeout=30)
            records.append({'argv': argv, 'exit_code': p.returncode, 'stdout': p.stdout,
                            'stderr': p.stderr, 'timeout_seconds': 30, 'timed_out': False})
            assert p.returncode == expected_code, p.stderr
            if expected_code == 0:
                obj = json.loads(p.stdout)
                print(json.dumps({'operation': operation, 'result': obj}, ensure_ascii=True))
                return obj
            assert not p.stdout
            print(json.dumps({'operation': operation, 'rejected': True, 'stderr': p.stderr.strip()}))

        cli('create', source=source, id='v1', max_bytes=100000)
        first_bytes = total(repo)
        (source / 'texto 日本語').write_bytes(b'version two')
        (source / 'new.bin').write_bytes(bytes(range(256)))
        expected['v2'] = contents(source)
        cli('create', source=source, id='v2', max_bytes=100000)
        (source / 'texto 日本語').unlink()
        expected['v3'] = contents(source)
        before = contents(repo)
        used = total(repo)
        cli('create', expected_code=1, source=source, id='v3', max_bytes=used - 1)
        assert total(repo) == used and contents(repo) == before
        cli('create', source=source, id='v3', max_bytes=100000)
        final_bytes = total(repo)
        assert final_bytes <= 100000
        shutil.rmtree(source)
        assert cli('list') == {'snapshots': ['v1', 'v2', 'v3']}
        for snapshot_id in expected:
            assert cli('verify', id=snapshot_id) == {'id': snapshot_id, 'valid': True}
            dest = base / ('restore-' + snapshot_id)
            assert cli('restore', id=snapshot_id, dest=dest) == {'id': snapshot_id}
            assert contents(dest) == expected[snapshot_id]
        print(json.dumps({'first_repository_bytes': first_bytes,
                          'final_repository_bytes': final_bytes, 'max_bytes': 100000,
                          'exact_versions_restored_without_source': 3}))
    (OUT / 'example-commands.json').write_text(json.dumps(records, indent=2) + '\n')


if __name__ == '__main__':
    main()
