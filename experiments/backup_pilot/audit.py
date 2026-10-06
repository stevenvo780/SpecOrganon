"""Post-campaign evidence audit. No candidate execution; no early result inspection.

Hashes show local consistency, not authenticated identity or independent custody.
The analytical validator separately checks score denominators and the factor matrix.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import datetime, timedelta
import hashlib
import itertools
import json
from pathlib import Path

import run_pilot
import schedule


def sha(path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''): value.update(chunk)
    return value.hexdigest()


def evaluation_argv(base,row,number,manifest):
    candidate=base/'runs'/row['id']/f'stage{number}/artifact/solution'
    argv=['docker','run','--name','backup-eval-'+row['id'].lower()+f'-s{number}',
          '--network','none','--read-only','--cap-drop','ALL']
    for cap in ['SETUID','SETGID','CHOWN','KILL','DAC_OVERRIDE','FOWNER']:
        argv+=['--cap-add',cap]
    return argv+['--security-opt','no-new-privileges:true','--memory','768m','--cpus','1',
                 '--pids-limit','64','-e','BACKUP_CANDIDATE_UID=1000',
                 '--tmpfs','/work:rw,size=512m,mode=0755','--tmpfs','/tmp:rw,size=128m,mode=1777',
                 '--mount',f'type=bind,src={candidate},dst=/candidate,readonly',
                 manifest['images']['evaluator'],'--candidate','/candidate/backup.py',
                 '--variant',row['variant'],'--stage',str(number),'--seed',str(row['workload_seed']),
                 '--workdir','/work/control']


def audit(base):
    base=Path(base).resolve()
    # This guard precedes any opening of real artifacts, event logs, or scores.
    if not (base/'runs/complete.json').is_file():
        raise RuntimeError('Campaign incomplete: runs/complete.json required before audit')
    manifest=json.loads((base/'frozen/manifest.json').read_text())
    rows=manifest['schedule']
    expected=Counter(itertools.product(['V1','V2','V3'],[1,2],['N','S','T']))
    if (len(rows)!=18 or len({r['id'] for r in rows})!=18 or
        Counter((r['variant'],r['repeat'],r['arm']) for r in rows)!=expected or
        any(Path(r['id']).name!=r['id'] or r['id'] in ('','.','..') for r in rows)):
        raise RuntimeError('Invalid 18-run factor matrix')
    result={'valid':False,'issues':[],'stages':[],'session_count':0,
            'unknown_usage_sessions':0,'initialization_seconds':0,
            'initialization_duration_missing':0,'truncated_streams':0,
            'independent_custody':False,'provider_snapshot_verified':False,
            'limitations':['Local hashes and CLI thread IDs are consistency evidence, not authenticated custody.',
                           'Truncated streams retain a prefix and a declared full hash; their full bytes cannot be rechecked.',
                           'MCP event counts describe recorded calls, not semantic adherence to all method phases.',
                           'Score validity and product behavior require analyze.py and the reserved evaluator.']}
    sessions={}; generation_ends=[]; generation_starts=[]; evaluation_starts=[]

    def issue(kind,path,note):
        result['issues'].append({'kind':kind,'path':str(path),'note':note})

    expected_config={'model':schedule.MODEL,'effort':schedule.EFFORT,
                     'author_seconds':schedule.AUTHOR_SECONDS,'method_seconds':schedule.METHOD_SECONDS,
                     'functional_review_seconds':schedule.REVIEW_SECONDS}
    for key,expected_value in expected_config.items():
        if manifest.get(key)!=expected_value: issue('manifest_configuration',base/'frozen/manifest.json',key+' differs from frozen scheduling module')
    completed=json.loads((base/'runs/complete.json').read_text())
    if completed.get('runs')!=18 or completed.get('stages')!=36:
        issue('completion_marker',base/'runs/complete.json','Expected exactly 18 runs and 36 stages')

    def regular(path):
        if path.is_symlink() or not path.is_file():
            raise ValueError('Required evidence must be a regular, non-symlink file: '+str(path))
        return path

    def load(path): return json.loads(regular(path).read_text())

    def compare_hash(path,expected,kind):
        if not expected or sha(regular(path))!=expected: issue(kind,path,'SHA256 differs from receipt')

    def safe_relative(name,root):
        p=Path(name)
        if not isinstance(name,str) or p.is_absolute() or any(part in ('.','..') for part in p.parts) or not p.parts:
            issue('unsafe_path',root,str(name)); return None
        target=root/p
        if any(parent.is_symlink() for parent in [target,*target.parents] if parent!=root.parent):
            issue('unsafe_path',target,'Symlink in evidence path'); return None
        return target

    def inventory(root):
        paths={}
        for path in root.rglob('*'):
            if path.is_symlink(): issue('unsafe_path',path,'Unexpected symlink in archived evidence')
            elif path.is_file(): paths[path.relative_to(root).as_posix()]=path
        return paths

    for name,expected_hash in manifest['files'].items():
        try: compare_hash(Path(name),expected_hash,'frozen_hash')
        except (OSError,ValueError) as error: issue('frozen_hash',name,str(error))

    def logs(stage,role,receipt,model=True):
        compare_hash(stage/f'{role}.jsonl',receipt.get('stdout_sha256'),'log_hash')
        compare_hash(stage/f'{role}.stderr',receipt.get('stderr_sha256'),'log_hash')
        if receipt.get('errors'): issue('provider_error',stage/role,'Receipt contains provider/turn errors, including during timeout')
        if not receipt.get('timed_out') and receipt.get('exit_code')!=0:
            issue('process_failure',stage/role,'Non-timeout process failure')
        if not model: return {}
        ids=[]; raw_errors=[]; calls=Counter(); malformed=0; usage=[]
        for line in (stage/f'{role}.jsonl').read_text().splitlines():
            try: event=json.loads(line)
            except ValueError: malformed+=1; continue
            if not isinstance(event,dict): malformed+=1; continue
            if event.get('type')=='thread.started': ids.append(event.get('thread_id'))
            if event.get('type') in ('error','turn.failed'): raw_errors.append(event)
            if 'usage' in event: usage.append(event['usage'])
            item=event.get('item',{})
            if event.get('type')=='item.completed' and isinstance(item,dict) and item.get('type')=='mcp_tool_call':
                calls[str(item.get('server'))+'/'+str(item.get('tool'))]+=1
        if raw_errors!=receipt.get('errors',[]): issue('event_receipt',stage/role,'Errors in events and receipt differ')
        if usage!=receipt.get('usage',[]): issue('event_receipt',stage/role,'Usage in events and receipt differs')
        if raw_errors and not receipt.get('errors'): issue('provider_error',stage/role,'Unreported provider error in events')
        if len(ids)!=1 or not isinstance(ids[0],str) or not ids[0]:
            issue('session_identity',stage/role,'Exactly one nonempty CLI thread ID required')
        else:
            if ids[0] in sessions: issue('session_reuse',stage/role,'Thread ID already recorded at '+sessions[ids[0]])
            sessions[ids[0]]=str(stage/role)
        result['session_count']+=1
        last=usage[-1] if usage else None
        if not isinstance(last,dict) or last.get('input_tokens',last.get('prompt_tokens')) is None or last.get('output_tokens',last.get('completion_tokens')) is None:
            result['unknown_usage_sessions']+=1
        end=datetime.fromisoformat(receipt['finished_at'])
        generation_ends.append(end)
        generation_starts.append(end-timedelta(seconds=receipt['duration_seconds']))
        return {'thread_ids':ids,'mcp_completed_calls':dict(calls),'malformed_event_lines':malformed,
                'duration_seconds':receipt.get('duration_seconds'),'timed_out':receipt.get('timed_out')}

    for row in rows:
        root=base/'runs'/row['id']
        for number in (1,2):
            stage=root/f'stage{number}'
            summary={'id':row['id'],'stage':number,'roles':{}}
            result['stages'].append(summary)
            try:
                complete=load(stage/'complete.json')
                image=manifest['images']['method' if row['arm']=='T' else 'control']
                name='backup-pilot-'+row['id'].lower()+f'-s{number}'
                specs=[('author',run_pilot.docker_model(image,root/'work',schedule.author_argv(row['arm'],number),name),schedule.author_prompt(row,number)),
                       ('review',run_pilot.docker_model(manifest['images']['control'],stage/'review-work',schedule.review_argv(),name+'-review',True),(schedule.BASE/'planning/reviewer-neutral.txt').read_text())]
                if row['arm']=='T':
                    specs.append(('method',run_pilot.docker_model(image,root/'work',run_pilot.method_argv(),name+'-method'),run_pilot.METHOD_PROMPT))
                elif complete.get('method') is not None: issue('unexpected_method',stage,'Control arm has method receipt')
                for role,argv,prompt in specs:
                    receipt=load(stage/f'{role}.receipt.json')
                    if complete.get(role)!=receipt: issue('embedded_receipt',stage/role,'Embedded and standalone receipt differ')
                    if receipt.get('argv')!=argv: issue('model_configuration',stage/role,'Command differs from frozen model, sandbox, mount, or resource configuration')
                    if regular(stage/f'{role}.prompt.txt').read_text()!=prompt: issue('prompt',stage/role,'Prompt differs from frozen assignment')
                    summary['roles'][role]=logs(stage,role,receipt)
                if row['arm']=='T' and number==1:
                    receipt=load(stage/'init.receipt.json'); logs(stage,'init',receipt,False)
                    if receipt.get('duration_seconds') is None: result['initialization_duration_missing']+=1
                    else: result['initialization_seconds']+=receipt['duration_seconds']
                artifact=load(stage/'artifact.receipt.json')
                if complete.get('artifact')!=artifact: issue('embedded_receipt',stage/'artifact','Inventory receipt differs')
                archived=inventory(stage/'artifact')
                if set(archived)!=set(artifact['files']): issue('artifact_inventory',stage/'artifact','Archived files differ from recorded inventory')
                for name,expected_hash in artifact['files'].items():
                    path=safe_relative(name,stage/'artifact')
                    if path: compare_hash(path,expected_hash,'artifact_hash')
                for input_name,text in schedule.author_files(row['arm'],number).items():
                    if artifact['files'].get(input_name)!=hashlib.sha256(text.encode()).hexdigest():
                        issue('assignment_changed',stage/'artifact'/input_name,'Provided assignment or method input was removed or modified')
                if artifact.get('bytes')!=sum(p.stat().st_size for p in archived.values()): issue('artifact_size',stage/'artifact','Inventory total bytes differ')
                summary['artifact_omissions']={k:artifact.get(k,[]) for k in ('omitted_links','omitted_oversize')}
                expected_review={'CONTRACT.md':hashlib.sha256(schedule.contract(number).encode()).hexdigest()}
                expected_review.update({key:value for key,value in artifact['files'].items() if key.startswith('solution/')})
                actual_review=inventory(stage/'review-work')
                if set(actual_review)!=set(expected_review): issue('review_inventory',stage/'review-work','Reviewer has extra or missing files')
                for name,expected_hash in expected_review.items():
                    path=safe_relative(name,stage/'review-work')
                    if path: compare_hash(path,expected_hash,'review_hash')
                receipt=load(stage/'evaluation.receipt.json');logs(stage,'evaluation',receipt,False)
                if receipt.get('argv')!=evaluation_argv(base,row,number,manifest): issue('evaluation_configuration',stage/'evaluation','Evaluator command differs from frozen isolation or workload')
                if receipt.get('timed_out') or receipt.get('infrastructure_failure') or receipt.get('exit_code')!=0:
                    issue('evaluation_failure',stage/'evaluation','Infrastructure failure cannot be assigned a quality score')
                evaluation_starts.append((stage,datetime.fromisoformat(receipt['finished_at'])-timedelta(seconds=receipt['duration_seconds'])))
                evaluated=load(stage/'evaluation.json')
                if load(stage/'evaluation.jsonl')!=evaluated: issue('evaluation_export',stage/'evaluation.json','Export differs from original graded stdout')
                if evaluated.get('isolation')!={'candidate_uid':1000,'development_only':False}: issue('evaluation_isolation',stage/'evaluation','Candidate UID isolation differs')
                streams=evaluated['output_streams']; streamroot=stage/'evaluation-streams'
                expected_index=[{k:v for k,v in stream.items() if k!='base64'} for stream in streams]
                if load(streamroot/'index.json')!=expected_index: issue('stream_index',streamroot,'Index differs from original output')
                names=[s['name'] for s in streams]
                if len(names)!=len(set(names)): issue('stream_index',streamroot,'Duplicate stream names')
                if set(inventory(streamroot))!=set(names)|{'index.json'}: issue('stream_inventory',streamroot,'Unexpected or missing stream files')
                for stream in streams:
                    if Path(stream['name']).name!=stream['name']: issue('unsafe_path',streamroot,stream['name']); continue
                    path=safe_relative(stream['name'],streamroot)
                    if path is None: continue
                    raw=base64.b64decode(stream['base64'],validate=True)
                    saved=regular(path).read_bytes()
                    if saved!=raw: issue('stream_content',path,'Saved output differs from encoded grader output')
                    if type(stream['truncated']) is not bool or stream['size']<len(raw) or stream['truncated']!=(stream['size']>len(raw)):
                        issue('stream_metadata',path,'Size/truncation metadata is inconsistent')
                    if stream['truncated']: result['truncated_streams']+=1
                    elif len(raw)!=stream['size'] or hashlib.sha256(raw).hexdigest()!=stream['sha256']:
                        issue('stream_hash',path,'Complete stream hash or length differs')
            except (OSError,ValueError,KeyError,TypeError,IndexError) as error:
                issue('invalid_evidence',stage,str(error))
    if generation_ends:
        last_generation=max(generation_ends)
        for stage,start in evaluation_starts:
            # UTC start reconstructed from monotonic duration; tolerate 2s clock rounding.
            if start<last_generation-timedelta(seconds=2): issue('evaluation_timing',stage,'Evaluation began before every generation session had closed')
        frozen=datetime.fromisoformat(manifest['frozen_at'])
        if generation_starts and min(generation_starts)<frozen-timedelta(seconds=2):
            issue('freeze_timing',base/'frozen','Recorded generation began before inputs froze')
    result['valid']=not result['issues']
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    try: result=audit(args.base)
    except (RuntimeError,OSError,ValueError,KeyError,TypeError) as error: parser.exit(1,str(error)+'\n')
    text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(text)
    else: print(text,end='')
    raise SystemExit(0 if result['valid'] else 1)


if __name__=='__main__': main()
