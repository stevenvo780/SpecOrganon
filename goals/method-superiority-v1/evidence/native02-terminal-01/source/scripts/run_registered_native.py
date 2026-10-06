"""Trusted bootstrap: compile registered driver/package bytes without pyc reuse.

Standard-library/dependency runtime remains the trusted installed environment.
No package code is imported before the registration and source hashes match.
"""
import argparse
import hashlib
import importlib.abc
import importlib.util
import json
from pathlib import Path
import sys


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_bound(root, name, expected):
    rel=Path(name)
    if rel.is_absolute() or '..' in rel.parts:
        raise ValueError('unsafe registered source path')
    path=(root/rel).resolve(strict=True)
    if not path.is_relative_to(root):
        raise ValueError('registered source escaped root')
    raw=path.read_bytes()
    if sha(raw)!=expected:
        raise ValueError('registered source hash differs: '+name)
    return path,raw


class RegisteredLoader(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self,root,bindings):
        self.modules={}
        for name,expected in bindings.items():
            p=Path(name)
            if p.parent!=Path('src/specorganon') or p.suffix!='.py':
                continue
            path,raw=read_bound(root,name,expected)
            module='specorganon' if p.name=='__init__.py' else 'specorganon.'+p.stem
            self.modules[module]=(path,raw,expected)
        if 'specorganon' not in self.modules:
            raise ValueError('registered package initializer required')

    def find_spec(self,fullname,path=None,target=None):
        if fullname=='specorganon' or fullname.startswith('specorganon.'):
            if fullname not in self.modules:
                raise ImportError('unregistered package module: '+fullname)
            return importlib.util.spec_from_loader(fullname,self,is_package=fullname=='specorganon')
        return None

    def create_module(self,spec):
        return None

    def exec_module(self,module):
        path,raw,expected=self.modules[module.__name__]
        module.__file__=str(path)
        if module.__name__=='specorganon':
            module.__path__=[str(path.parent)]
        # Compile the same immutable bytes checked before importing; never read pyc.
        exec(compile(raw,str(path),'exec',dont_inherit=True),module.__dict__)
        module.__registered_source_sha256__=expected


def launch(registration,expected,operation):
    if any(n=='specorganon' or n.startswith('specorganon.') for n in sys.modules):
        raise ValueError('fresh process required; package already imported')
    raw=registration.read_bytes()
    if sha(raw)!=expected:
        raise ValueError('registration digest differs before imports')
    # The full finite/exact validation happens in the bound driver before dispatch.
    r=json.loads(raw)
    if type(r) is not dict or type(r.get('schema')) is not int or r['schema']!=2:
        raise ValueError('bootstrap requires versioned schema2 registration')
    root=Path(r['source_root']).resolve(strict=True)
    bindings=r['source_sha256']
    this=Path(__file__).resolve()
    bootstrap_name='scripts/run_registered_native.py'
    if this!=root/bootstrap_name:
        raise ValueError('bootstrap outside registered source root')
    read_bound(root,bootstrap_name,bindings[bootstrap_name])
    driver_name='scripts/native_reliability.py'
    driver,driver_raw=read_bound(root,driver_name,bindings[driver_name])
    # Check all remaining registered inputs before importing the package.
    for name,expected_sha in bindings.items():
        read_bound(root,name,expected_sha)
    loader=RegisteredLoader(root,bindings)
    sys.meta_path.insert(0,loader)
    sys.argv=[str(driver),operation,str(registration),'--registration-sha256',expected]
    namespace={'__name__':'__main__','__file__':str(driver),
               '__registered_runtime__':{'driver_sha256':sha(driver_raw),'source_root':str(root)}}
    exec(compile(driver_raw,str(driver),'exec',dont_inherit=True),namespace)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation',choices=['run','report'])
    p.add_argument('registration',type=Path)
    p.add_argument('--registration-sha256',required=True)
    a=p.parse_args();launch(a.registration,a.registration_sha256,a.operation)


if __name__=='__main__':
    main()
