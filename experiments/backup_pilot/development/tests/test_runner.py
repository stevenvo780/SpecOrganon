import importlib.util
import json
from pathlib import Path
import pytest

BASE=Path(__file__).resolve().parents[2]

def module():
    spec=importlib.util.spec_from_file_location('pilot_runner',BASE/'run_pilot.py')
    loaded=importlib.util.module_from_spec(spec); spec.loader.exec_module(loaded); return loaded

def test_freeze_detects_changed_input(tmp_path):
    r=module(); source=tmp_path/'contract.md'; source.write_text('before')
    manifest={'files':{str(source):r.digest(source)}}
    r.check_freeze(manifest)
    source.write_text('after')
    with pytest.raises(RuntimeError,match='Frozen input changed'): r.check_freeze(manifest)

def test_completed_and_interrupted_steps_are_never_silently_replayed(tmp_path):
    r=module(); marker=tmp_path/'receipt.json'; calls=[]
    def task(): calls.append(1); return {'exit_code':0}
    r.once(marker,task)
    r.once(marker,task)
    assert calls==[1]
    marker.unlink(); marker.with_suffix('.started.json').write_text('{}')
    with pytest.raises(RuntimeError,match='Interrupted step'): r.once(marker,task)
    assert calls==[1]

def test_snapshot_refuses_external_links_and_bounds_artifact_size(tmp_path):
    r=module(); source=tmp_path/'source'; source.mkdir(); (source/'code.py').write_text('print(1)')
    (source/'stolen').symlink_to('/etc/passwd')
    dest=tmp_path/'snapshot'
    report=r.snapshot(source,dest)
    assert (dest/'code.py').read_text()=='print(1)'
    assert not (dest/'stolen').exists()
    assert report['omitted_links']==['stolen']

def test_receipts_accept_multiline_json_with_scalar_lines(tmp_path):
    import sys
    r=module()
    argv=[sys.executable,'-c','import json; print(json.dumps({"paths":["last"],"value":True},indent=2))']
    receipt=r.command(argv,tmp_path/'output',5)
    assert receipt['exit_code']==0 and receipt['errors']==[]
