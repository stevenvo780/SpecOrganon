"""Portable byte verification only; does not rerun Docker or authenticate operators."""
import argparse,hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent

def raw(root,name):
    rel=Path(name)
    if rel.is_absolute() or '..' in rel.parts:raise ValueError('unsafe archive name')
    p=root/rel
    if p.is_symlink() or not p.resolve().is_relative_to(root) or p.stat().st_nlink!=1:
        raise ValueError('unsafe archive file')
    return p.read_bytes()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-source',action='store_true',help='Also compare final recorded sources against this checkout')
    args=parser.parse_args()
    total=0;bytes_total=0
    for index,count in [(2,207),(3,243),(7,372),(9,535),(11,605)]:
        receipt=json.loads(raw(HERE,f'docker-controls-{index:02}-archive.json'))
        root=(HERE/f'docker-controls-{index:02}-raw').resolve()
        assert len(receipt['files'])==count
        names=set()
        for item in receipt['files']:
            assert item['path'] not in names;names.add(item['path'])
            data=raw(root,item['path']);assert len(data)==item['bytes']
            assert hashlib.sha256(data).hexdigest()==item['sha256']
        actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
        assert actual==names
        assert sum(r['bytes'] for r in receipt['files'])==receipt['bytes']
        total+=count;bytes_total+=receipt['bytes']
    receipt=json.loads(raw(HERE,'engineering-receipt.json'))
    if args.check_source:
        source=HERE.parents[3]
        for name,expected in receipt['source_sha256'].items():assert hashlib.sha256(raw(source,name)).hexdigest()==expected
    print(json.dumps({'schema':1,'files_verified':total,'bytes_verified':bytes_total,
                      'current_sources_verified':len(receipt['source_sha256']) if args.check_source else 0,
                      'scope':'Copied byte manifests only; no transport/model execution or independence attestation',
                      'new_model_or_test_calls':0,'goal_achieved':False},indent=2))

if __name__=='__main__':main()
