"""A delivery check must exclude ambient packages while preserving normal CLI/PID behavior."""
import json
import os
from pathlib import Path
import subprocess
import sys

BASE=Path(__file__).resolve().parents[2]


def launch(candidate,*args,env=None):
    merged=dict(os.environ);merged.update(env or {})
    merged['PYTHONPATH']=str(BASE)+os.pathsep+merged.get('PYTHONPATH','')
    return subprocess.Popen([sys.executable,'-c',
        'import sys; from delivery_entry import launch; launch(sys.argv[1],sys.argv[2:])',
        str(candidate),*args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=merged)


def test_stdlib_own_helpers_arguments_and_pid_survive(tmp_path):
    (tmp_path/'helper.py').write_text('VALUE="local helper"\n')
    candidate=tmp_path/'backup.py'
    candidate.write_text('import os,sys,json,helper\nprint(json.dumps({"pid":os.getpid(),"args":sys.argv[1:],"helper":helper.VALUE}))\n')
    proc=launch(candidate,'create','--id','α space');out,err=proc.communicate(timeout=10)
    assert proc.returncode==0,err.decode()
    assert json.loads(out)=={'pid':proc.pid,'args':['create','--id','α space'],'helper':'local helper'}


def test_ambient_pythonpath_dependency_is_rejected(tmp_path):
    extras=tmp_path/'extras';extras.mkdir();(extras/'ambient_dependency.py').write_text('VALUE=1\n')
    candidate=tmp_path/'backup.py';candidate.write_text('import ambient_dependency\nprint(ambient_dependency.VALUE)\n')
    env=dict(os.environ,PYTHONPATH=str(extras))
    normal=subprocess.run([sys.executable,str(candidate)],capture_output=True,env=env,timeout=10)
    assert normal.returncode==0 and normal.stdout==b'1\n'
    proc=launch(candidate,env={'PYTHONPATH':str(extras)});out,err=proc.communicate(timeout=10)
    assert proc.returncode!=0 and b'ambient_dependency' in err and not out


def test_site_initialization_is_disabled(tmp_path):
    candidate=tmp_path/'backup.py'
    candidate.write_text('import sys,json\nprint(json.dumps({"no_site":sys.flags.no_site,"ignore_environment":sys.flags.ignore_environment,"no_user_site":sys.flags.no_user_site,"site_loaded":"site" in sys.modules}))\n')
    proc=launch(candidate);out,err=proc.communicate(timeout=10)
    assert proc.returncode==0,err.decode()
    assert json.loads(out)=={'no_site':1,'ignore_environment':1,'no_user_site':1,'site_loaded':False}


def test_missing_product_is_an_error(tmp_path):
    proc=launch(tmp_path/'missing.py');out,err=proc.communicate(timeout=10)
    assert proc.returncode!=0 and not out
