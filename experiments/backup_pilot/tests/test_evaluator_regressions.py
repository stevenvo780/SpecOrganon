from pathlib import Path
import importlib.util
import shutil

BASE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('backup_eval',BASE/'evaluator.py')
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
REF=BASE/'development/reference/backup.py'

def test_fixed_denominator_and_source_critical_on_false_success():
    good=module.evaluate(REF,stage=1,seed=31)
    bad=module.evaluate(BASE/'tests/fixtures/false_success.py',stage=1,seed=31)
    assert good['checks_total']==bad['checks_total']
    assert good['checks_total']>=16
    assert bad['score']<1

def test_verify_that_skips_payload_cannot_pass_corruption(tmp_path):
    candidate=tmp_path/'backup.py'
    code=REF.read_text().replace("if scan(root/'files')!=data['entries']:","if False:")
    candidate.write_text(code)
    result=module.evaluate(candidate,stage=1,seed=31)
    assert 'snapshot_corruption' in result['critical_failures']

def test_symlink_acceptance_is_contract_failure(tmp_path):
    candidate=tmp_path/'backup.py'; shutil.copy(REF,candidate)
    code=candidate.read_text().replace("dest=path_checked(args.dest)","dest=Path(args.dest).resolve()")
    candidate.write_text(code)
    result=module.evaluate(candidate,stage=1,seed=31)
    details={d['name']:d for d in result['details']}
    assert details['symlink_dest']['passed'] is False

def test_seeded_workloads_are_reproducible():
    a=module.evaluate(REF,stage=1,seed=113)
    b=module.evaluate(REF,stage=1,seed=113)
    assert a['workload_sha256']==b['workload_sha256']

def test_snapshot_symlink_following_is_rejected_even_with_identical_bytes(tmp_path):
    candidate=tmp_path/'backup.py'
    candidate.write_text(REF.read_text().replace('mode=path.lstat().st_mode','mode=path.stat().st_mode'))
    result=module.evaluate(candidate,stage=1,seed=31)
    details={d['name']:d for d in result['details']}
    assert 'symlink_snapshot' in details
    assert details['symlink_snapshot']['passed'] is False

def test_candidate_children_cannot_keep_writing_after_command_exit(tmp_path):
    import time
    candidate=tmp_path/'backup.py'
    candidate.write_text('import subprocess,sys\nsubprocess.Popen([sys.executable,"-c", "import time,pathlib;time.sleep(0.3);pathlib.Path(\\\"late\\\").write_text(\\\"changed\\\")"])\nprint(\\\"{}\\\")\n'.replace('print(\\\"{}\\\")','print("{}")'))
    work=tmp_path/'control'; work.mkdir()
    grader=module.Evaluator(candidate,'V1',1,31,work)
    case=grader.env('one'); result=grader.run([],case)
    assert result['exit_code']==0
    time.sleep(0.5)
    assert not (case/'late').exists()

def test_repository_layout_does_not_change_paired_crash_payload(tmp_path):
    candidate=tmp_path/'backup.py'
    code=REF.read_text().replace("    return {'id':args.id}\n\n\nclass directory_fd:","    for index in range(40): (repo/f'aux-{index}').write_bytes(b'')\n    return {'id':args.id}\n\n\nclass directory_fd:")
    assert code!=REF.read_text()
    candidate.write_text(code)
    normal=module.evaluate(REF,stage=1,seed=113)
    auxiliary=module.evaluate(candidate,stage=1,seed=113)
    assert normal['workload_sha256']==auxiliary['workload_sha256']
