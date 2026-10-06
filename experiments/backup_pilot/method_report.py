"""Post-campaign mechanical method diagnostics, separate from product scoring.

Uses the frozen method image with the artifact mounted read-only, without auth or
network. A historical acceptance is not treated as current gate acceptance.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import itertools
import json
from pathlib import Path

import run_pilot


INSPECTOR=r'''
import hashlib,json,sys
from collections import Counter
from pathlib import Path
from specorganon import engine
from specorganon.ledger import read_project
try:
    case=Path(sys.argv[1])
    state=engine.get_state(case)
    ledger=read_project(case)
    phases={key:{k:value[k] for k in ('ready','accepted','reviewed','independent_review',
             'review_signature_verified','review_identity_authenticated','review_provenance',
             'blockers','snapshot','advance_seq')} for key,value in state['phases'].items()}
    result={'ok':True,'revision':state['revision'],'approval_policy':state['project']['approval_policy'],
            'approval_identity_authenticated':state['approval_identity_authenticated'],
            'phase_review_trust':state['phase_review_trust'],
            'test_execution_trust':state['test_execution_trust'],
            'test_execution_records':len(state['test_execution_history']),
            'test_observation_records':len(state['test_observation_history']),
            'item_kind_counts':dict(Counter(item['kind'] for item in state['items'].values())),
            'event_actor_counts':dict(Counter(event['actor'] for event in ledger['events'])),
            'phases':phases,'accepted_phases':[key for key,value in phases.items() if value['accepted']],
            'phase_review_history':state['phase_review_history'],
            'ledger_sha256':hashlib.sha256((case/'organon.json').read_bytes()).hexdigest(),
            'engine_sha256':hashlib.sha256(Path(engine.__file__).read_bytes()).hexdigest()}
except Exception as error:
    print(json.dumps({'ok':False,'error_type':type(error).__name__,'error':str(error)}))
    raise SystemExit(1)
print(json.dumps(result,ensure_ascii=False))
'''


def inspection_argv(artifact,image,name):
    return ['docker','run','--rm','--name',name,'--network','none','--read-only',
            '--user','1000:1000','--cap-drop','ALL','--security-opt','no-new-privileges:true',
            '--memory','256m','--cpus','1','--pids-limit','64',
            '--mount',f'type=bind,src={artifact},dst=/trial,readonly',
            '--entrypoint','/opt/specorganon/.venv/bin/python',image,
            '-c',INSPECTOR,'/trial/case']


def inspect_artifact(artifact,image,directory,name):
    artifact=Path(artifact);directory=Path(directory)
    stem=directory/'inspection'
    receipt=run_pilot.command(inspection_argv(artifact,image,name),stem,30,container=name)
    try: observation=json.loads(stem.with_suffix('.jsonl').read_text())
    except (ValueError,OSError): observation={'ok':False,'error_type':'InvalidInspectorOutput'}
    # No failure is converted into a zero for accepted phases or product quality.
    if receipt['exit_code']!=0 or receipt['timed_out']:
        observation['ok']=False
        observation.pop('accepted_phases',None)
    return {'receipt':receipt,'observation':observation,
            'inspector_sha256':hashlib.sha256(INSPECTOR.encode()).hexdigest()}


def validate_cached(saved,directory,artifact,image,name):
    data=saved['result'];receipt=data['receipt']
    if receipt.get('argv')!=inspection_argv(artifact,image,name):
        raise RuntimeError('Cached observer configuration changed: '+str(directory))
    for filename,key in [('inspection.jsonl','stdout_sha256'),('inspection.stderr','stderr_sha256')]:
        path=directory/filename
        if path.is_symlink() or not path.is_file() or run_pilot.digest(path)!=receipt.get(key):
            raise RuntimeError('Cached observer log changed: '+str(path))
    try: original=json.loads((directory/'inspection.jsonl').read_text())
    except ValueError: original={'ok':False,'error_type':'InvalidInspectorOutput'}
    if receipt['exit_code']!=0 or receipt['timed_out']:
        original['ok']=False;original.pop('accepted_phases',None)
    if original!=data['observation']:
        raise RuntimeError('Cached observation differs from preserved stdout: '+str(directory))


def report(base,output):
    base=Path(base).resolve();output=Path(output).resolve()
    if not (base/'runs/complete.json').is_file():
        raise RuntimeError('Campaign incomplete: method diagnostics require final closure')
    manifest=json.loads((base/'frozen/manifest.json').read_text())
    rows=manifest['schedule']
    expected=Counter(itertools.product(['V1','V2','V3'],[1,2],['N','S','T']))
    if (len(rows)!=18 or len({r['id'] for r in rows})!=18 or
        Counter((r['variant'],r['repeat'],r['arm']) for r in rows)!=expected or
        any(Path(r['id']).name!=r['id'] or r['id'] in ('','.','..') for r in rows)):
        raise RuntimeError('Invalid 18-run method reporting matrix')
    run_pilot.check_freeze(manifest)
    # Validate generation closure for all arms, not just the treatment snapshots.
    for row in rows:
        for number in (1,2):
            if not (base/'runs'/row['id']/f'stage{number}/complete.json').is_file():
                raise RuntimeError('Missing generation receipt: '+row['id'])
    result={'method_image':manifest['images']['method'],'observations':[],
            'observer_kind':'post_campaign_non_model_read_only',
            'limitations':['Mechanical gate state is not an independent semantic method review.',
                           'Local declared actors and approvals do not authenticate identities.',
                           'Recorded test execution counts are not independent proof of test results.',
                           'Observer diagnostics are outside treatment budgets and product scoring; receipts retain their cost.']}
    for row in rows:
        if row['arm']!='T': continue
        for number in (1,2):
            stage=base/'runs'/row['id']/f'stage{number}'
            entry={'id':row['id'],'stage':number}
            ledger=stage/'artifact/case/organon.json'
            inventory=json.loads((stage/'artifact.receipt.json').read_text())
            if (ledger.is_symlink() or not ledger.is_file() or
                inventory['files'].get('case/organon.json')!=run_pilot.digest(ledger)):
                entry['observation']={'ok':False,'error_type':'MissingOrChangedLedger'}
            else:
                directory=output/(row['id']+f'-s{number}')
                cache=directory/'result.json'
                identity={'ledger_sha256':run_pilot.digest(ledger),'method_image':manifest['images']['method'],
                          'inspector_sha256':hashlib.sha256(INSPECTOR.encode()).hexdigest()}
                if cache.exists():
                    saved=json.loads(cache.read_text())
                    if saved.get('input_identity')!=identity:
                        raise RuntimeError('Cached method diagnostic inputs changed: '+str(cache))
                    validate_cached(saved,directory,stage/'artifact',manifest['images']['method'],
                                    'backup-method-observer-'+row['id'].lower()+f'-s{number}')
                    entry.update(saved['result'])
                else:
                    entry.update(inspect_artifact(stage/'artifact',manifest['images']['method'],directory,
                                                'backup-method-observer-'+row['id'].lower()+f'-s{number}'))
                    run_pilot.save(cache,{'input_identity':identity,'result':entry})
            result['observations'].append(entry)
    result['successful_observations']=sum(e['observation'].get('ok') is True for e in result['observations'])
    result['failed_observations']=len(result['observations'])-result['successful_observations']
    run_pilot.save(output/'method-report.json',result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    try:
        result=report(args.base,args.output or args.base/'analysis/method')
    except (RuntimeError,OSError,ValueError,KeyError,TypeError) as error:
        parser.exit(1,str(error)+'\n')
    print(json.dumps({'successful_observations':result['successful_observations'],
                      'failed_observations':result['failed_observations']}))
    raise SystemExit(1 if result['failed_observations'] else 0)


if __name__=='__main__': main()
