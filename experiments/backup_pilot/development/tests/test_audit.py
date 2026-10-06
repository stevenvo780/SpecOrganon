"""Synthetic campaign evidence; never opens live candidate artifacts."""
import base64
import hashlib
import json
import sys
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))
import run_pilot
import schedule
from audit import audit, evaluation_argv


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fixture(base):
    manifest = {'schedule': schedule.make_schedule(17863), 'files': {},
                'images': {'method': 'sha256:method', 'control': 'sha256:control',
                           'evaluator': 'sha256:evaluator'},
                'model': schedule.MODEL, 'effort': schedule.EFFORT,
                'author_seconds': schedule.AUTHOR_SECONDS,
                'method_seconds': schedule.METHOD_SECONDS,
                'functional_review_seconds': schedule.REVIEW_SECONDS,
                'frozen_at': '2026-10-03T00:00:00+00:00'}
    save(base/'frozen/manifest.json', manifest)
    save(base/'runs/complete.json', {'runs': 18, 'stages': 36})
    for row in manifest['schedule']:
        root = base/'runs'/row['id']
        for number in (1, 2):
            stage = root/f'stage{number}'
            image = manifest['images']['method' if row['arm']=='T' else 'control']
            name = 'backup-pilot-'+row['id'].lower()+f'-s{number}'
            body = b'print("example")\n'
            candidate = stage/'artifact/solution/backup.py'
            candidate.parent.mkdir(parents=True)
            candidate.write_bytes(body)
            review = stage/'review-work'
            (review/'solution').mkdir(parents=True)
            (review/'solution/backup.py').write_bytes(body)
            (review/'CONTRACT.md').write_text(schedule.contract(number))
            inventory = {'files': {'solution/backup.py': sha(body)}, 'bytes': len(body),
                         'omitted_links': [], 'omitted_oversize': []}
            for input_name, text in schedule.author_files(row['arm'],number).items():
                path=stage/'artifact'/input_name
                path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
                inventory['files'][input_name]=sha(text.encode())
                inventory['bytes']+=len(text.encode())
            embedded = {'artifact': inventory, 'method': None}
            specs = [('author', run_pilot.docker_model(image, root/'work',
                      schedule.author_argv(row['arm'],number),name), schedule.author_prompt(row,number)),
                     ('review', run_pilot.docker_model(manifest['images']['control'],review,
                      schedule.review_argv(),name+'-review',True),
                      (BASE/'planning/reviewer-neutral.txt').read_text())]
            if row['arm']=='T':
                specs.append(('method',run_pilot.docker_model(image,root/'work',
                              run_pilot.method_argv(),name+'-method'),run_pilot.METHOD_PROMPT))
            for role, argv, prompt in specs:
                content = (json.dumps({'type':'thread.started','thread_id':f'{row["id"]}-{number}-{role}'})+'\n').encode()
                (stage/f'{role}.jsonl').write_bytes(content)
                (stage/f'{role}.stderr').write_bytes(b'')
                (stage/f'{role}.prompt.txt').write_text(prompt)
                receipt = {'argv':argv, 'exit_code':0, 'timed_out':False,
                           'duration_seconds':1, 'finished_at':'2026-10-03T00:01:00+00:00',
                           'errors':[], 'usage':[], 'stdout_sha256':sha(content), 'stderr_sha256':sha(b'')}
                save(stage/f'{role}.receipt.json',receipt)
                embedded[role]=receipt
            if row['arm']=='T' and number==1:
                (stage/'init.jsonl').write_bytes(b'')
                (stage/'init.stderr').write_bytes(b'')
                save(stage/'init.receipt.json',{'exit_code':0,'timed_out':False,'errors':[],
                     'duration_seconds':0.1,'stdout_sha256':sha(b''),'stderr_sha256':sha(b'')})
            save(stage/'artifact.receipt.json',inventory)
            save(stage/'complete.json',embedded)
            stream = {'name':'example.stdout','size':2,'sha256':sha(b'{}'),
                      'truncated':False,'base64':base64.b64encode(b'{}').decode()}
            result = {'isolation':{'candidate_uid':1000,'development_only':False},
                      'output_streams':[stream]}
            raw = json.dumps(result).encode()
            (stage/'evaluation.jsonl').write_bytes(raw)
            (stage/'evaluation.stderr').write_bytes(b'')
            save(stage/'evaluation.json',result)
            (stage/'evaluation-streams').mkdir()
            (stage/'evaluation-streams/example.stdout').write_bytes(b'{}')
            save(stage/'evaluation-streams/index.json',[{k:v for k,v in stream.items() if k!='base64'}])
            save(stage/'evaluation.receipt.json',{'argv':evaluation_argv(base,row,number,manifest),
                 'exit_code':0,'timed_out':False,'duration_seconds':1,
                 'finished_at':'2026-10-03T00:02:00+00:00','errors':[],
                 'stdout_sha256':sha(raw),'stderr_sha256':sha(b'')})
    return manifest


def first_stage(base, manifest):
    return base/'runs'/manifest['schedule'][0]['id']/'stage1'


def test_incomplete_campaign_refused_before_reading_artifacts(tmp_path):
    with pytest.raises(RuntimeError,match='incomplete'):
        audit(tmp_path)


def test_complete_evidence_and_unknown_usage_are_not_zero_tokens(tmp_path):
    fixture(tmp_path)
    result = audit(tmp_path)
    assert result['valid'] and len(result['stages'])==36
    assert result['session_count']==84
    assert result['unknown_usage_sessions']==84
    assert result['initialization_seconds']==pytest.approx(0.6)


def test_changed_artifact_and_stdout_detected(tmp_path):
    manifest=fixture(tmp_path); stage=first_stage(tmp_path,manifest)
    (stage/'artifact/solution/backup.py').write_bytes(b'changed')
    (stage/'author.jsonl').write_bytes(b'changed')
    kinds={i['kind'] for i in audit(tmp_path)['issues']}
    assert {'artifact_hash','log_hash'}<=kinds


def test_unsafe_stream_name_and_changed_stream_detected(tmp_path):
    manifest=fixture(tmp_path); stage=first_stage(tmp_path,manifest)
    (stage/'evaluation-streams/example.stdout').write_bytes(b'changed')
    result=audit(tmp_path)
    assert any(i['kind']=='stream_content' for i in result['issues'])
    data=json.loads((stage/'evaluation.json').read_text())
    data['output_streams'][0]['name']='../escape'
    save(stage/'evaluation.json',data)
    assert any(i['kind']=='unsafe_path' for i in audit(tmp_path)['issues'])


def test_duplicate_session_and_timeout_api_error_remain_invalid(tmp_path):
    manifest=fixture(tmp_path); stage=first_stage(tmp_path,manifest)
    content=(stage/'author.jsonl').read_bytes()
    (stage/'review.jsonl').write_bytes(content)
    receipt=json.loads((stage/'review.receipt.json').read_text())
    receipt['stdout_sha256']=sha(content); receipt['timed_out']=True
    receipt['errors']=[{'type':'error','message':'provider error'}]
    save(stage/'review.receipt.json',receipt)
    embedded=json.loads((stage/'complete.json').read_text());embedded['review']=receipt
    save(stage/'complete.json',embedded)
    kinds={i['kind'] for i in audit(tmp_path)['issues']}
    assert {'session_reuse','provider_error'}<=kinds


def test_configuration_and_early_evaluation_detected(tmp_path):
    manifest=fixture(tmp_path);stage=first_stage(tmp_path,manifest)
    receipt=json.loads((stage/'author.receipt.json').read_text())
    receipt['argv'].append('--dangerously-bypass-approvals-and-sandbox')
    save(stage/'author.receipt.json',receipt)
    receipt=json.loads((stage/'evaluation.receipt.json').read_text())
    receipt['finished_at']='2026-10-03T00:00:10+00:00'
    save(stage/'evaluation.receipt.json',receipt)
    kinds={i['kind'] for i in audit(tmp_path)['issues']}
    assert {'model_configuration','evaluation_timing'}<=kinds


def test_review_contamination_and_frozen_drift_detected(tmp_path):
    manifest=fixture(tmp_path);stage=first_stage(tmp_path,manifest)
    (stage/'review-work/AGENTS.md').write_text('treatment revealed')
    frozen=tmp_path/'input.txt';frozen.write_text('old')
    manifest['files']={str(frozen):sha(b'old')};save(tmp_path/'frozen/manifest.json',manifest)
    frozen.write_text('new')
    kinds={i['kind'] for i in audit(tmp_path)['issues']}
    assert {'review_inventory','frozen_hash'}<=kinds


def test_contract_modified_even_when_inventory_and_embedded_hashes_agree(tmp_path):
    manifest=fixture(tmp_path);stage=first_stage(tmp_path,manifest)
    (stage/'artifact/CONTRACT.md').write_bytes(b'relaxed requirements')
    inventory=json.loads((stage/'artifact.receipt.json').read_text())
    old_size=len(schedule.contract(1).encode())
    inventory['files']['CONTRACT.md']=sha(b'relaxed requirements')
    inventory['bytes']+=len(b'relaxed requirements')-old_size
    save(stage/'artifact.receipt.json',inventory)
    complete=json.loads((stage/'complete.json').read_text());complete['artifact']=inventory
    save(stage/'complete.json',complete)
    assert any(i['kind']=='assignment_changed' for i in audit(tmp_path)['issues'])


def test_mcp_calls_count_completed_items_once_and_compare_raw_errors(tmp_path):
    manifest=fixture(tmp_path);stage=first_stage(tmp_path,manifest)
    path=stage/'author.jsonl'
    events=[{'type':'item.started','item':{'id':'tool1','type':'mcp_tool_call','server':'specorganon','tool':'status'}},
            {'type':'item.completed','item':{'id':'tool1','type':'mcp_tool_call','server':'specorganon','tool':'status'}},
            {'type':'turn.failed','error':{'message':'transport failure'}}]
    content=path.read_bytes()+b''.join((json.dumps(e)+'\n').encode() for e in events)
    path.write_bytes(content)
    receipt=json.loads((stage/'author.receipt.json').read_text());receipt['stdout_sha256']=sha(content)
    save(stage/'author.receipt.json',receipt)
    complete=json.loads((stage/'complete.json').read_text());complete['author']=receipt
    save(stage/'complete.json',complete)
    result=audit(tmp_path)
    assert result['stages'][0]['roles']['author']['mcp_completed_calls']=={'specorganon/status':1}
    assert {'event_receipt','provider_error'}<={i['kind'] for i in result['issues']}


def test_generation_start_before_freeze_is_detected(tmp_path):
    manifest=fixture(tmp_path);stage=first_stage(tmp_path,manifest)
    receipt=json.loads((stage/'author.receipt.json').read_text());receipt['duration_seconds']=80
    save(stage/'author.receipt.json',receipt)
    complete=json.loads((stage/'complete.json').read_text());complete['author']=receipt
    save(stage/'complete.json',complete)
    assert any(i['kind']=='freeze_timing' for i in audit(tmp_path)['issues'])


def test_truncated_stream_is_explicitly_partial_not_a_full_hash_verification(tmp_path):
    manifest=fixture(tmp_path);stage=first_stage(tmp_path,manifest)
    data=json.loads((stage/'evaluation.json').read_text())
    stream=data['output_streams'][0]
    stream.update(size=100,truncated=True,sha256=sha(b'{}'+b'x'*98))
    raw=json.dumps(data).encode()
    (stage/'evaluation.jsonl').write_bytes(raw)
    save(stage/'evaluation.json',data)
    save(stage/'evaluation-streams/index.json',[{k:v for k,v in stream.items() if k!='base64'}])
    receipt=json.loads((stage/'evaluation.receipt.json').read_text());receipt['stdout_sha256']=sha(raw)
    save(stage/'evaluation.receipt.json',receipt)
    result=audit(tmp_path)
    assert result['valid'] and result['truncated_streams']==1
    assert any('full bytes cannot be rechecked' in note for note in result['limitations'])
