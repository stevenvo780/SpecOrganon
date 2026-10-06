import json
import os
import hashlib
import pytest
from pathlib import Path
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from analyze import analyze

BASE_CHECKS = (
    'roundtrip_create', 'source_intact', 'roundtrip_verify', 'roundtrip_match',
    'roundtrip_list', 'list_empty', 'version_snapshots', 'duplicate_id_mutation',
    'invalid_ids', 'nonexistent_id', 'overlap_rejected', 'symlink_source',
    'symlink_dest', 'symlink_repo', 'special_files', 'snapshot_corruption',
    'sigkill_interrupt_intact', 'sigkill_recovery', 'symlink_snapshot', 'dest_protected'
)

def get_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()

def write_mock_run(base, run_id, arm, s1_passed, s2_passed, missing=False, critical=False, inc=False, s2_high=True, s2_low=False):
    run_dir = base / 'runs' / run_id
    if missing:
        return
    run_dir.mkdir(parents=True, exist_ok=True)
    for s, passed_count in [(1, s1_passed), (2, s2_passed)]:
        stage_dir = run_dir / f'stage{s}'
        stage_dir.mkdir(exist_ok=True)
        
        author_receipt = {'duration_seconds': 100, 'usage': [{'input_tokens': 10, 'output_tokens': 20}], 'exit_code': 0, 'timed_out': False, 'errors': []}
        review_receipt = {'duration_seconds': 10, 'usage': [{'input_tokens': 5, 'output_tokens': 10}], 'exit_code': 0, 'timed_out': False, 'errors': []}
        
        method_receipt = None
        if arm == 'T':
            method_receipt = {'duration_seconds': 20, 'usage': [{'input_tokens': 5, 'output_tokens': 5}], 'exit_code': 0, 'timed_out': False, 'errors': []}

        sol_dir = stage_dir / 'artifact' / 'solution'
        sol_dir.mkdir(parents=True, exist_ok=True)
        backup_content = b"fake code"
        h = get_hash(backup_content)
        
        if not critical:
            (sol_dir / 'backup.py').write_bytes(backup_content)
        else:
            h = None

        artifact_receipt = {'files': {}}
        if h:
            artifact_receipt['files']['solution/backup.py'] = h
        
        complete_data = {
            'author': author_receipt,
            'review': review_receipt,
            'artifact': artifact_receipt
        }
        if arm == 'T':
            complete_data['method'] = method_receipt

        (stage_dir / 'complete.json').write_text(json.dumps(complete_data))
        (stage_dir / 'author.receipt.json').write_text(json.dumps(author_receipt))
        (stage_dir / 'review.receipt.json').write_text(json.dumps(review_receipt))
        (stage_dir / 'artifact.receipt.json').write_text(json.dumps(artifact_receipt))
        if arm == 'T':
            (stage_dir / 'method.receipt.json').write_text(json.dumps(method_receipt))

        eval_receipt = {'exit_code': 0, 'timed_out': False, 'infrastructure_failure': False}
        (stage_dir / 'evaluation.receipt.json').write_text(json.dumps(eval_receipt))

        details = []
        checks_total = 20 if s == 1 else 22
        
        for i, name in enumerate(BASE_CHECKS):
            details.append({'name': name, 'passed': (i < passed_count)})
            
        if s == 2:
            details.append({'name': 'max_bytes_high', 'passed': s2_high})
            details.append({'name': 'max_bytes_low', 'passed': s2_low})
            
        checks_passed = sum(1 for d in details if d['passed'])
        
        eval_data = {
            'score': checks_passed / checks_total,
            'checks_passed': checks_passed,
            'checks_total': checks_total,
            'inconclusive': inc,
            'critical_failures': ['boom'] if critical else [],
            'details': details,
            'isolation': {'candidate_uid': 1000, 'development_only': False}
        }
        (stage_dir / 'evaluation.json').write_text(json.dumps(eval_data))

def make_fixture(tmp_path, missing_run=False, omit_complete_marker=False):
    frozen = tmp_path / 'frozen'
    frozen.mkdir(exist_ok=True)
    schedule = []
    variants = ['V1', 'V2', 'V3']
    arms = ['N', 'S', 'T']
    
    idx = 0
    for v in variants:
        for r in [1, 2]:
            for a in arms:
                run_id = f"{v}-r{r}-{a}"
                schedule.append({'id': run_id, 'variant': v, 'repeat': r, 'arm': a})
                idx += 1
                
    (frozen / 'manifest.json').write_text(json.dumps({'schedule': schedule}))
    
    (tmp_path / 'runs').mkdir(exist_ok=True)
    if not omit_complete_marker:
        (tmp_path / 'runs' / 'complete.json').write_text(json.dumps({'finished_at': 'now'}))
    
    for i, row in enumerate(schedule):
        miss = missing_run and (i == 0)
        s1_p = {'N': 10, 'S': 20, 'T': 16}[row['arm']]
        s2_p = s1_p + 2
        if s2_p > 20: s2_p = 20
        high = True
        low = (row['arm'] == 'S')
        write_mock_run(tmp_path, row['id'], row['arm'], s1_p, s2_p, missing=miss, critical=(row['arm'] == 'N' and i == 2), inc=False, s2_high=high, s2_low=low)
        
    return schedule

def test_missing_run_complete_marker(tmp_path):
    make_fixture(tmp_path, omit_complete_marker=True)
    with pytest.raises(RuntimeError, match="Missing runs/complete.json"):
        analyze(tmp_path)

def test_missing_receipt_even_embedded(tmp_path):
    make_fixture(tmp_path)
    # Remove author.receipt.json but keep it embedded in complete.json
    (tmp_path / 'runs' / 'V1-r1-N' / 'stage1' / 'author.receipt.json').unlink()
    with pytest.raises(RuntimeError, match="Missing author.receipt.json but present in complete.json"):
        analyze(tmp_path)

def test_malbalanced_matrix(tmp_path):
    schedule = make_fixture(tmp_path)
    # Add a 19th item
    schedule.append({'id': 'EXTRA-r1-N', 'variant': 'EXTRA', 'repeat': 1, 'arm': 'N'})
    (tmp_path / 'frozen' / 'manifest.json').write_text(json.dumps({'schedule': schedule}))
    with pytest.raises(RuntimeError, match="Expected exactly 18 entries in schedule"):
        analyze(tmp_path)

def test_score_detail_mismatch(tmp_path):
    make_fixture(tmp_path)
    eval_path = tmp_path / 'runs' / 'V1-r1-N' / 'stage1' / 'evaluation.json'
    data = json.loads(eval_path.read_text())
    data['score'] = 1.0 # Mismatch with checks_passed
    eval_path.write_text(json.dumps(data))
    with pytest.raises(RuntimeError, match="score incongruent"):
        analyze(tmp_path)

def test_missing_usage_duration_unknown(tmp_path):
    make_fixture(tmp_path)
    r_dir = tmp_path / 'runs' / 'V1-r1-N' / 'stage1'
    data = json.loads((r_dir / 'complete.json').read_text())
    data['author']['duration_seconds'] = None
    (r_dir / 'complete.json').write_text(json.dumps(data))
    (r_dir / 'author.receipt.json').write_text(json.dumps(data['author']))
    
    res = analyze(tmp_path)
    dur = res['runs']['V1-r1-N']['stages'][1]['resources']['duration_seconds']
    assert dur['author'] is None
    assert dur['total'] is None # total must be None if any required is None

def test_selection_tie_breaker_order(tmp_path):
    # 'S' arm is perfect. Let's make 'N' also perfect.
    make_fixture(tmp_path)
    for run_dir in (tmp_path / 'runs').glob('*-N'):
        # Make N perfect in stage 2
        eval_path = run_dir / 'stage2' / 'evaluation.json'
        data = json.loads(eval_path.read_text())
        data['score'] = 1.0
        data['checks_passed'] = 22
        for d in data['details']: d['passed'] = True
        eval_path.write_text(json.dumps(data))
        # Ensure it has a candidate hash
        art = json.loads((run_dir / 'stage2' / 'artifact.receipt.json').read_text())
        (run_dir / 'stage2' / 'artifact' / 'solution').mkdir(parents=True, exist_ok=True)
        (run_dir / 'stage2' / 'artifact' / 'solution' / 'backup.py').write_text("fixed")
        h = get_hash(b"fixed")
        art['files']['solution/backup.py'] = h
        (run_dir / 'stage2' / 'artifact.receipt.json').write_text(json.dumps(art))
        comp = json.loads((run_dir / 'stage2' / 'complete.json').read_text())
        comp['artifact'] = art
        (run_dir / 'stage2' / 'complete.json').write_text(json.dumps(comp))
        
    res = analyze(tmp_path)
    # The tie breaker should pick the one with lowest duration, or by position.
    # We didn't change duration, both have 100 author + 10 review. 
    # N is position 0, S is position 1, T is position 2 in V1-r1
    assert res['selection'] == 'V1-r1-N' # Position 0 wins!


def test_correct_pairs_and_delta_common_checks(tmp_path):
    make_fixture(tmp_path)
    res = analyze(tmp_path)
    
    for ad in res['adaptation']['T']:
        assert ad['delta_common_passed'] == 2
        assert ad['max_bytes_high'] is True
        assert ad['max_bytes_low'] is False

def test_missing_tokens_remain_unknown(tmp_path):
    make_fixture(tmp_path)
    r_dir = tmp_path / 'runs' / 'V1-r1-N' / 'stage1'
    data = json.loads((r_dir / 'complete.json').read_text())
    data['author']['usage'] = [{'input_tokens': None, 'output_tokens': 20}]
    (r_dir / 'complete.json').write_text(json.dumps(data))
    (r_dir / 'author.receipt.json').write_text(json.dumps(data['author']))
    
    res = analyze(tmp_path)
    usage = res['runs']['V1-r1-N']['stages'][1]['resources']['usage']['author']
    assert usage['input_tokens'] is None
    assert usage['output_tokens'] == 20
    assert usage['complete'] is False

def test_critical_failures_exclude_product(tmp_path):
    make_fixture(tmp_path)
    for run_dir in (tmp_path / 'runs').glob('*-T'):
        data = json.loads((run_dir / 'stage2' / 'evaluation.json').read_text())
        data['critical_failures'] = ['test_crit']
        (run_dir / 'stage2' / 'evaluation.json').write_text(json.dumps(data))
        
    res = analyze(tmp_path)
    assert res['selection'] is not None
    assert 'T' not in res['selection']
    assert 'S' in res['selection']
