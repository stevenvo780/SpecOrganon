"""Compile synthetic registered bytes, rejecting drift and stale pyc; no native calls."""
from pathlib import Path
import hashlib,json,subprocess,sys,py_compile,os
import pytest


def setup(tmp_path):
    src=tmp_path/'source';(src/'scripts').mkdir(parents=True);(src/'src/specorganon').mkdir(parents=True)
    launcher=Path(__file__).parents[1]/'scripts/run_registered_native.py'
    (src/'scripts/run_registered_native.py').write_bytes(launcher.read_bytes())
    (src/'scripts/native_reliability.py').write_text('import specorganon.payload\nprint(specorganon.payload.VALUE)\n')
    (src/'src/specorganon/__init__.py').write_text('')
    (src/'src/specorganon/payload.py').write_text('VALUE="first"\n')
    return src


def run(src,tmp_path):
    files={str(p.relative_to(src)):hashlib.sha256(p.read_bytes()).hexdigest() for p in src.rglob('*.py')}
    r={'schema':2,'source_root':str(src),'source_sha256':files}
    p=tmp_path/'registration.json';p.write_text(json.dumps(r));sha=hashlib.sha256(p.read_bytes()).hexdigest()
    result=subprocess.run([sys.executable,str(src/'scripts/run_registered_native.py'),'report',str(p),
                           '--registration-sha256',sha],capture_output=True,text=True)
    return result,p,sha


def test_registered_bytes_override_same_size_same_mtime_stale_pyc(tmp_path):
    src=setup(tmp_path);p=src/'src/specorganon/payload.py';mtime=p.stat().st_mtime_ns
    py_compile.compile(str(p),doraise=True)
    p.write_text('VALUE="other"\n');os.utime(p,ns=(mtime,mtime))
    result,_,_=run(src,tmp_path)
    assert result.returncode==0,result.stderr
    assert result.stdout.strip()=='other'


def test_drift_before_import_rejected(tmp_path):
    src=setup(tmp_path);_,p,sha=run(src,tmp_path)
    (src/'src/specorganon/payload.py').write_text('raise RuntimeError("must not execute")')
    result=subprocess.run([sys.executable,str(src/'scripts/run_registered_native.py'),'report',str(p),
                           '--registration-sha256',sha],capture_output=True,text=True)
    assert result.returncode!=0 and 'hash differs' in result.stderr
    assert 'RuntimeError: must not execute' not in result.stderr


def test_unregistered_package_module_cannot_fall_back_to_filesystem(tmp_path):
    src=setup(tmp_path)
    (src/'scripts/native_reliability.py').write_text('import specorganon.unlisted\n')
    _,p,sha=run(src,tmp_path)
    (src/'src/specorganon/unlisted.py').write_text('print("must not execute")')
    result=subprocess.run([sys.executable,str(src/'scripts/run_registered_native.py'),'report',str(p),
                           '--registration-sha256',sha],capture_output=True,text=True)
    assert result.returncode!=0 and 'unregistered package module' in result.stderr
    assert 'must not execute' not in result.stdout
