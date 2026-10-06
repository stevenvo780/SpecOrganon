"""Standalone byte audit, never an execution, native generation or attestation."""
import argparse
import hashlib
import json
from pathlib import Path
import stat


def read(path):
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError('symlink evidence path')
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 2097152:
        raise ValueError('bounded regular singly linked evidence required')
    return path.read_bytes()


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--check-source', action='store_true')
    a = p.parse_args(); base = Path(__file__).absolute().parent; count = 0; total = 0
    for sequence in ('01', '03', '05'):
        manifest = json.loads(read(base / ('docker-' + sequence + '-archive-manifest.json')))
        for name, expected in manifest['files'].items():
            rel = Path(name)
            if rel.is_absolute() or '..' in rel.parts: raise ValueError('unsafe manifest path')
            raw = read(base / ('docker-' + sequence + '-archive') / rel)
            assert hashlib.sha256(raw).hexdigest() == expected, name
            count += 1; total += len(raw)
        assert len(manifest['files']) == manifest['count']
    if a.check_source:
        root = base.parents[3]
        for name, expected in json.loads(read(base / 'source-review-03.json'))['sources'].items():
            assert hashlib.sha256(read(root / name)).hexdigest() == expected, name
    print(json.dumps({'archive_files': count, 'archive_bytes': total, 'source_pins_checked': a.check_source,
                      'scope': 'Byte-consistent copies only; no execution or attestation', 'model_calls': 0}))


if __name__ == '__main__': main()
