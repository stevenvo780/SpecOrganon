"""Fixed prospective diagnostic calls; never project generation or approval.

All three original identities close once, including native/format failures.
No retries, historical response adoption, account switching or ledger writes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

from specorganon.docker_roles import DockerRoles
from specorganon.role_jobs import _read, canonical, digest, _json, _write


def load_plan(path, sha):
    if digest(_read(path)) != sha:
        raise ValueError('diagnostic registration digest differs')
    p = _json(path)
    if (p.get('classification') != 'prospective provider syntax diagnostics only'
            or p.get('fixture_mode') is not True or p.get('automatic_replacement') is not False
            or [c['id'] for c in p['cases']] != ['review-missing-receipt', 'approval-outside-mandate', 'author-items']):
        raise ValueError('requires the three original diagnostic identities')
    source = Path(p['source_root'])
    for rel, expected in p['source_sha256'].items():
        q = Path(rel)
        if q.is_absolute() or '..' in q.parts or digest(_read(source/q)) != expected:
            raise ValueError('diagnostic bound source changed')
    return p


def run(path, sha):
    plan = load_plan(path, sha); root = Path(plan['run_root'])
    if root.exists():
        raise ValueError('diagnostic run already exists; inspect original handles, never restart')
    root.mkdir(mode=0o700, parents=True)
    _write(root/'registration.json', plan)
    transport = DockerRoles(root/'transport', native_image=plan['native_image'], test_image=plan['test_image'],
        source_root=plan['source_root'], public_catalog=Path(plan['source_root'])/plan['public_catalog'],
        author_provider='gemini', author_model=plan['model'], reviewer_provider='gemini', reviewer_model=plan['model'],
        gemini_profile=plan['original_profile'], gemini_executable=plan['executable'],
        seccomp=Path(plan['source_root'])/plan['seccomp'])
    rows=[]
    for case in plan['cases']:
        load_plan(path, sha)
        started=time.monotonic()
        try:
            result=transport.call(case['id'],case['role'],case['request'])
            row={'id':case['id'],'status':'bridge_contract_valid','result':result}
        except Exception as exc:
            # Raw native output/receipts remain in their original owned journal.
            row={'id':case['id'],'status':'failed_or_inconclusive','error_type':type(exc).__name__,
                 'reason':str(exc)}
        row['elapsed_seconds']=time.monotonic()-started
        row['registration_sha256']=sha
        _write(root/(case['id']+'-outcome.json'),row)
        rows.append(row)
        print(json.dumps({k:row[k] for k in ['id','status','elapsed_seconds']}) ,flush=True)
    load_plan(path, sha)
    report={'schema':1,'classification':plan['classification'],'registration_sha256':sha,
            'rows':rows,'planned_calls':3,'closed_cases':len(rows),
            'valid_bridge_contracts':sum(r['status']=='bridge_contract_valid' for r in rows),
            'software_generations':0,'reserved_subjects':0,'phase_acceptances':0,
            'goal_achieved':False,'automatic_replacements':0,
            'scope':'CLI/schema/stream diagnostic fixtures only; no efficacy, approvals or software superiority'}
    _write(root/'report.json',report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('registration',type=Path); parser.add_argument('--sha256',required=True)
    args=parser.parse_args()
    run(args.registration,args.sha256)
