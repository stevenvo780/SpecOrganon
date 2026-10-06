"""Post-campaign exploratory runtime check; never changes frozen primary results.

Runs all 36 deliveries without installed Python packages. Full dependency-policy
compliance still needs source review. Failures preserve receipts, not favorable retries.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
import itertools
import json
import math
import os
from pathlib import Path
import statistics
import subprocess

from evaluator import BASE_CHECKS
import run_pilot


def expected_names(number):
    return (*BASE_CHECKS,*(('max_bytes_high','max_bytes_low') if number==2 else ()), 'dest_protected')


def argv(candidate,row,number,image):
    command=['docker','run','--name','backup-clean-'+row['id'].lower()+f'-s{number}',
             '--network','none','--read-only','--cap-drop','ALL']
    for cap in ('SETUID','SETGID','CHOWN','KILL','DAC_OVERRIDE','FOWNER'):
        command+=['--cap-add',cap]
    return command+['--security-opt','no-new-privileges:true','--memory','768m','--cpus','1',
           '--pids-limit','64','-e','BACKUP_CANDIDATE_UID=1000',
           '--tmpfs','/work:rw,size=512m,mode=0755','--tmpfs','/tmp:rw,size=128m,mode=1777',
           '--mount',f'type=bind,src={candidate},dst=/candidate,readonly',image,
           '--candidate','/entry/backup.py','--variant',row['variant'],'--stage',str(number),
           '--seed',str(row['workload_seed']),'--workdir','/work/control']


def check_image(image):
    actual=subprocess.check_output(['docker','image','inspect','--format','{{.Id}}',image],text=True).strip()
    if actual!=image: raise RuntimeError('Runtime image identity differs')
    return actual


def observe(candidate,row,number,image,directory):
    command=argv(candidate,row,number,image)
    try:
        receipt=run_pilot.command(command,directory/'evaluation',600,container=command[3])
        run_pilot.save(directory/'receipt.json',receipt)
        return receipt
    finally:
        subprocess.run(['docker','rm','-f',command[3]],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)


def validate_grade(data,number):
    if not isinstance(data,dict) or data.get('isolation')!={'candidate_uid':1000,'development_only':False}:
        raise ValueError('Invalid observer isolation')
    details=data['details'];names=[d['name'] for d in details]
    if len(names)!=len(set(names)) or set(names)!=set(expected_names(number)):
        raise ValueError('Observer check names differ from frozen stage')
    if any(type(d.get('passed')) is not bool for d in details): raise ValueError('Nonboolean grade')
    passed=sum(d['passed'] for d in details)
    score=data.get('score')
    if (data.get('checks_total')!=len(names) or data.get('checks_passed')!=passed or
        type(score) not in (float,int) or not math.isfinite(score) or not 0<=score<=1 or
        abs(score-passed/len(names))>1e-9): raise ValueError('Inconsistent observer score')
    if not isinstance(data.get('critical_failures'),list) or type(data.get('inconclusive')) is not bool:
        raise ValueError('Missing critical/inconclusive flags')
    for stream in data['output_streams']:
        name=stream['name']
        if not isinstance(name,str) or not name or Path(name).name!=name or name in ('.','..','index.json'):
            raise ValueError('Unsafe observer stream name')
        content=base64.b64decode(stream['base64'],validate=True)
        if (type(stream['size']) is not int or stream['size']<len(content) or
            type(stream['truncated']) is not bool or stream['truncated']!=(stream['size']>len(content))):
            raise ValueError('Invalid stream length/truncation')
        if not stream['truncated']:
            import hashlib
            if hashlib.sha256(content).hexdigest()!=stream['sha256']: raise ValueError('Stream hash differs')
    if len({s['name'] for s in data['output_streams']})!=len(data['output_streams']):
        raise ValueError('Duplicate stream names')


def classify(directory,receipt,number):
    if receipt['exit_code']!=0 or receipt.get('timed_out') or receipt.get('infrastructure_failure'):
        return 'infrastructure_failure',None,'Observer process failed; quality unknown'
    try:
        data=json.loads((directory/'evaluation.jsonl').read_text());validate_grade(data,number)
        return 'evaluated',data,None
    except (OSError,ValueError,KeyError,TypeError) as error:
        return 'invalid_evaluation',None,str(error)


def source_inventory(stage):
    receipt=json.loads((stage/'artifact.receipt.json').read_text())
    expected={name.removeprefix('solution/'):value for name,value in receipt['files'].items() if name.startswith('solution/')}
    candidate=stage/'artifact/solution'
    if candidate.is_symlink(): raise ValueError('Solution directory is a symlink')
    actual={}
    for path in candidate.rglob('*'):
        if path.is_symlink(): raise ValueError('Solution contains symlink')
        if path.is_file(): actual[path.relative_to(candidate).as_posix()]=run_pilot.digest(path)
        elif not path.is_dir(): raise ValueError('Solution contains special file')
    if actual!=expected: raise ValueError('Solution differs from frozen artifact receipt')
    return candidate,actual


def validate_cached(saved,directory,identity,candidate,row,number,image):
    if saved.get('input_identity')!=identity: raise RuntimeError('Cached observer inputs changed: '+str(directory))
    entry=saved['entry']
    assignment={'id':row['id'],'arm':row['arm'],'variant':row['variant'],'repeat':row['repeat'],'stage':number}
    if any(entry.get(key)!=value for key,value in assignment.items()):
        raise RuntimeError('Cached observation assignment differs: '+str(directory))
    if entry.get('source_files')!=identity['source_files'] or entry.get('source_sha256')!=identity['source_files'].get('backup.py'):
        raise RuntimeError('Cached observer source differs: '+str(directory))
    if entry.get('receipt') is None:
        if ('backup.py' in identity['source_files'] or entry['status']!='missing_product' or
            entry.get('evaluation') is not None):
            raise RuntimeError('Cached nonexecuted observation differs: '+str(directory))
        return entry
    receipt=json.loads((directory/'receipt.json').read_text())
    if receipt!=entry['receipt'] or receipt['argv']!=argv(candidate,row,number,image):
        raise RuntimeError('Cached observer receipt differs: '+str(directory))
    for name,key in [('evaluation.jsonl','stdout_sha256'),('evaluation.stderr','stderr_sha256')]:
        path=directory/name
        if path.is_symlink() or not path.is_file() or run_pilot.digest(path)!=receipt.get(key):
            raise RuntimeError('Cached observer log changed: '+str(path))
    status,data,error=classify(directory,receipt,number)
    if status!=entry['status'] or data!=entry.get('evaluation') or error!=entry.get('error'):
        raise RuntimeError('Cached result differs from original observer output: '+str(directory))
    # Recheck decoded stream copies, including prefixes of truncated output.
    if data is not None:
        if json.loads((directory/'evaluation.json').read_text())!=data:
            raise RuntimeError('Cached observer export changed: '+str(directory))
        expected_index=[{k:v for k,v in s.items() if k!='base64'} for s in data['output_streams']]
        if json.loads((directory/'evaluation-streams/index.json').read_text())!=expected_index:
            raise RuntimeError('Cached observer stream index changed: '+str(directory))
        for stream in data['output_streams']:
            path=directory/'evaluation-streams'/stream['name']
            if path.is_symlink() or path.read_bytes()!=base64.b64decode(stream['base64'],validate=True):
                raise RuntimeError('Cached observer stream changed: '+str(path))
    return entry


def run(base,output):
    base=Path(base).resolve();output=Path(output).resolve()
    # Guard precedes loading any outcome or source and precedes output creation.
    if not (base/'runs/complete.json').is_file(): raise RuntimeError('Campaign incomplete: final closure required')
    manifest=json.loads((base/'frozen/manifest.json').read_text());rows=manifest['schedule']
    expected=Counter(itertools.product(['V1','V2','V3'],[1,2],['N','S','T']))
    if (len(rows)!=18 or len({r['id'] for r in rows})!=18 or
        Counter((r['variant'],r['repeat'],r['arm']) for r in rows)!=expected or
        any(Path(r['id']).name!=r['id'] or r['id'] in ('','.','..') for r in rows)):
        raise RuntimeError('Invalid supplemental factor matrix')
    run_pilot.check_freeze(manifest)
    for row in rows:
        for number in (1,2):
            stage=base/'runs'/row['id']/f'stage{number}'
            if not (stage/'complete.json').is_file(): raise RuntimeError('Generation closure missing: '+str(stage))
            receipt=json.loads((stage/'evaluation.receipt.json').read_text())
            if receipt.get('exit_code')!=0 or receipt.get('timed_out') or receipt.get('infrastructure_failure'):
                raise RuntimeError('Primary evaluation closure failed: '+str(stage))
    build=json.loads((base/'development/delivery-build.json').read_text())
    if build.get('exit_code')!=0 or build['base_image_id']!=manifest['images']['control']:
        raise RuntimeError('Runtime base differs from frozen control')
    for filename,key in [('evaluator.py','evaluator_sha256'),('delivery_entry.py','entry_sha256')]:
        if run_pilot.digest(base/filename)!=build[key]: raise RuntimeError('Runtime input changed: '+filename)
    plan=json.loads((base/'planning/clean-runtime-addendum.json').read_text())
    coverage={'runs':18,'stages_per_run':[1,2],'expected_observations':36,'arms':['N','S','T'],'selective_winner_only_check':False}
    runtime={'image_id':build['image_id'],'base_image_id':build['base_image_id'],
             'entry_sha256':build['entry_sha256'],'evaluator_sha256':build['evaluator_sha256'],
             'flags':['-E','-s','-S','-B'],'candidate_uid':1000,'network':'none','auth_volume':False,'read_only_candidate':True}
    if plan.get('coverage')!=coverage or plan.get('runtime')!=runtime or plan.get('primary_protocol_changed') is not False:
        raise RuntimeError('Registered runtime differs from observer configuration')
    image=check_image(build['image_id'])
    output.mkdir(parents=True,exist_ok=True)
    lock=output/'.lock';fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    os.write(fd,str(os.getpid()).encode());os.close(fd)
    entries=[]
    try:
        for row in rows:
            for number in (1,2):
                stage=base/'runs'/row['id']/f'stage{number}'
                directory=output/row['id']/f'stage{number}';cache=directory/'result.json'
                entry={'id':row['id'],'arm':row['arm'],'variant':row['variant'],'repeat':row['repeat'],
                       'stage':number,'status':None,'evaluation':None,'receipt':None,'error':None}
                try: candidate,files=source_inventory(stage)
                except (OSError,ValueError,KeyError,TypeError) as error:
                    entry.update(status='input_changed',error=str(error));entries.append(entry);continue
                identity={'source_files':files,'runtime_image':image,'row':row,'stage':number,
                          'evaluator_sha256':build['evaluator_sha256'],'entry_sha256':build['entry_sha256']}
                entry['source_sha256']=files.get('backup.py');entry['source_files']=files
                if cache.exists():
                    entries.append(validate_cached(json.loads(cache.read_text()),directory,identity,candidate,row,number,image));continue
                def task():
                    if 'backup.py' not in files:
                        entry.update(status='missing_product',error='Frozen delivery has no backup.py; dependency compliance unknown')
                    else:
                        receipt=observe(candidate,row,number,image,directory)
                        status,data,error=classify(directory,receipt,number)
                        entry.update(status=status,receipt=receipt,evaluation=data,error=error)
                        if data is not None:
                            run_pilot.save(directory/'evaluation.json',data)
                            streams=directory/'evaluation-streams';streams.mkdir(exist_ok=True)
                            for stream in data['output_streams']:
                                (streams/stream['name']).write_bytes(base64.b64decode(stream['base64'],validate=True))
                            run_pilot.save(streams/'index.json',[{k:v for k,v in stream.items() if k!='base64'} for stream in data['output_streams']])
                    return {'input_identity':identity,'entry':entry}
                entries.append(run_pilot.once(cache,task)['entry'])
        groups={}
        for arm in 'NST':
            groups[arm]={}
            for number in (1,2):
                selected=[e for e in entries if e['arm']==arm and e['stage']==number]
                scores=[e['evaluation']['score'] for e in selected if e['status']=='evaluated']
                groups[arm][str(number)]={'expected':6,'observed':len(selected),
                    'statuses':dict(Counter(e['status'] for e in selected)),
                    'known_score_count':len(scores),'mean_only_evaluated':statistics.mean(scores) if scores else None,
                    'median_only_evaluated':statistics.median(scores) if scores else None,
                    'minimum_only_evaluated':min(scores) if scores else None,'maximum_only_evaluated':max(scores) if scores else None}
        result={'kind':'exploratory_post_campaign_runtime_check','primary_results_changed':False,
                'source_review_required':True,'dependency_policy_compliance_proven':False,
                'image_id':image,'counts':dict(Counter(e['status'] for e in entries)),
                'groups':groups,'observations':entries,
                'limitations':['Site exclusion is not a proof against vendored code or external commands.',
                               'Known-score summaries show their observed denominators; missing/error observations remain explicit.',
                               'Observer timings are separate from the frozen primary timings and model resources.']}
        run_pilot.save(output/'clean-runtime-report.json',result)
        return result
    finally: lock.unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    try: result=run(args.base,args.output or args.base/'analysis/clean-runtime')
    except (RuntimeError,OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as error: parser.exit(1,str(error)+'\n')
    print(json.dumps({'observations':len(result['observations']),'counts':result['counts']}))
    raise SystemExit(1 if any(k not in ('evaluated','missing_product') for k in result['counts']) else 0)


if __name__=='__main__': main()
