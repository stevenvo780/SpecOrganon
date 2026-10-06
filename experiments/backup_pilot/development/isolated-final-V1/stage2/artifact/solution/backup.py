#!/usr/bin/env python3
"""Development oracle for the backup contract; never supplied to pilot authors."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from pathlib import Path, PurePosixPath


def path_checked(value):
    path=Path(os.path.abspath(value))
    for parent in reversed([path,*path.parents]):
        if parent.is_symlink():
            raise ValueError('symlinks are not supported')
    return path


def digest(path):
    sha=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            sha.update(block)
    return sha.hexdigest()


def scan(root):
    if not root.is_dir() or root.is_symlink():
        raise ValueError('directory required')
    entries=[]
    for path in sorted(root.rglob('*')):
        mode=path.lstat().st_mode
        name=path.relative_to(root).as_posix()
        if stat.S_ISDIR(mode):
            entries.append({'path':name,'kind':'dir'})
        elif stat.S_ISREG(mode):
            entries.append({'path':name,'kind':'file','size':path.stat().st_size,'sha256':digest(path)})
        else:
            raise ValueError('special files and symlinks are not supported')
    return entries


def size(root):
    return sum(entry.get('size',0) for entry in scan(root))


def valid_id(identifier):
    if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',identifier) is None:
        raise ValueError('invalid snapshot ID')


def checked_snapshot(repo,identifier):
    valid_id(identifier)
    root=path_checked(repo/identifier)
    if not root.is_dir() or {p.name for p in root.iterdir()} != {'files','manifest.json','manifest.sha256'}:
        raise ValueError('snapshot is incomplete')
    scan(root)  # Validate all entry types before opening metadata.
    manifest=root/'manifest.json'
    expected=(root/'manifest.sha256').read_text().strip()
    if re.fullmatch('[0-9a-f]{64}',expected) is None or digest(manifest)!=expected:
        raise ValueError('metadata checksum mismatch')
    data=json.loads(manifest.read_text())
    if not isinstance(data,dict) or set(data)!={'schema','entries'} or data['schema']!=1:
        raise ValueError('invalid manifest')
    if not isinstance(data['entries'],list):
        raise ValueError('invalid entries')
    names=set()
    for entry in data['entries']:
        name=entry['path']; relative=PurePosixPath(name)
        if not name or relative.is_absolute() or '..' in relative.parts or relative.as_posix()!=name or name in names:
            raise ValueError('invalid manifest path')
        names.add(name)
    if scan(root/'files')!=data['entries']:
        raise ValueError('snapshot checksum mismatch')
    return root/'files'


def create(args):
    valid_id(args.id)
    src=path_checked(args.source); repo=path_checked(args.repo)
    if src==repo or src.is_relative_to(repo) or repo.is_relative_to(src):
        raise ValueError('source and repo overlap')
    original=scan(src)
    if repo.exists():
        scan(repo)
    if (repo/args.id).exists():
        raise ValueError('snapshot ID already exists')
    if args.max_bytes is not None and args.max_bytes<0:
        raise ValueError('negative quota')
    repo.mkdir(parents=True,exist_ok=True)
    # Reserved staging namespace, independent from all completed snapshot IDs.
    for leftover in repo.glob(f'.pending-{args.id}-*'):
        scan(leftover)
        shutil.rmtree(leftover)
    with tempfile.TemporaryDirectory(prefix=f'.pending-{args.id}-',dir=repo) as temporary:
        staging=Path(temporary)
        shutil.copytree(src,staging/'files')
        if scan(staging/'files')!=original or scan(src)!=original:
            raise ValueError('source changed during backup')
        manifest=staging/'manifest.json'
        manifest.write_text(json.dumps({'schema':1,'entries':original},sort_keys=True,ensure_ascii=False))
        (staging/'manifest.sha256').write_text(digest(manifest)+'\n')
        # Flush all payload and metadata before publication. SIGKILL is covered;
        # physical power-loss durability depends on filesystem and hardware.
        for file in staging.rglob('*'):
            if file.is_file():
                with file.open('rb') as stream:
                    os.fsync(stream.fileno())
        if args.max_bytes is not None and size(repo)>args.max_bytes:
            raise ValueError('storage limit exceeded')
        os.rename(staging,repo/args.id)
        with directory_fd(repo) as fd:
            os.fsync(fd)
    return {'id':args.id}


class directory_fd:
    def __init__(self,path): self.path=path
    def __enter__(self): self.fd=os.open(self.path,os.O_RDONLY|os.O_DIRECTORY); return self.fd
    def __exit__(self,*args): os.close(self.fd)


def restore(args):
    repo=path_checked(args.repo); source=checked_snapshot(repo,args.id)
    dest=path_checked(args.dest)
    if dest==repo or dest.is_relative_to(repo) or repo.is_relative_to(dest):
        raise ValueError('destination and repo overlap')
    if dest.exists() and (not dest.is_dir() or any(dest.iterdir())):
        raise ValueError('destination is not empty')
    dest.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.restore-',dir=dest.parent) as temporary:
        staging=Path(temporary)/'files'
        shutil.copytree(source,staging)
        if scan(staging)!=scan(source): raise ValueError('restore checksum mismatch')
        if dest.exists(): dest.rmdir()
        os.rename(staging,dest)
    return {'id':args.id}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    for name in ['create','verify','restore','list']:
        command=commands.add_parser(name); command.add_argument('--repo',required=True)
        if name!='list': command.add_argument('--id',required=True)
        if name=='create':
            command.add_argument('--source',required=True)
            command.add_argument('--max-bytes',type=int)
        if name=='restore': command.add_argument('--dest',required=True)
    args=parser.parse_args()
    try:
        if args.command=='create': result=create(args)
        elif args.command=='restore': result=restore(args)
        elif args.command=='verify':
            checked_snapshot(path_checked(args.repo),args.id); result={'id':args.id,'valid':True}
        else:
            repo=path_checked(args.repo); scan(repo)
            ids=[]
            for path in sorted(repo.iterdir()):
                if path.name.startswith('.pending-'): continue
                try: checked_snapshot(repo,path.name)
                except (ValueError,OSError,KeyError,TypeError): continue
                ids.append(path.name)
            result={'snapshots':ids}
        print(json.dumps(result,ensure_ascii=False))
    except (ValueError,OSError,KeyError,TypeError,json.JSONDecodeError) as error:
        print(str(error),file=sys.stderr); sys.exit(1)


if __name__=='__main__': main()
