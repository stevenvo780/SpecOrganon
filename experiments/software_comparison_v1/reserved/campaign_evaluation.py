"""Post-generation fixed evaluation; no author/reviewer dispatch or feedback.

The coordinator reads cell identity and rubric observations. ReservedDocker
receives only opaque delivery code and the current input, in an uncredentialed
subject process. Missing or uncertain executions are retained, never rerun with
a replacement invocation ID.
"""
from __future__ import annotations

import argparse
import copy
import fcntl
import os
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from specorganon.role_jobs import canonical,digest,_read,_json,_write,JobError
from scripts.software_study_harness import registration,StudyHarnessError
from scripts.study_campaign import validate_configuration
from specorganon.software_controller import safe_file
from .docker_evaluator import ReservedDocker,EvaluationError,audit_case


def public_examples(task):
    """Fixed public recipes, not arbitrary shell commands extracted from README."""
    if task=='routeplan':
        graphs=[{'nodes':['A','B','C','D'],'edges':[
            {'source':'A','target':'D','cost':4},{'source':'A','target':'C','cost':2},
            {'source':'C','target':'D','cost':2},{'source':'A','target':'B','cost':1},
            {'source':'B','target':'D','cost':3}],'query':{'source':'A','target':'D'}},
            {'nodes':['West','East'],'edges':[],'query':{'source':'West','target':'East'}}]
        expected=[{'reachable':True,'cost':4,'path':['A','B','D']},
                  {'reachable':False,'cost':None,'path':[]}]
        return [{'id':'public-'+str(i+1),'task':task,'group':'public-example',
                 'argv':[],'stdin_hex':canonical(graph).hex(),'expected':expected[i]}
                for i,graph in enumerate(graphs)]
    if task!='treemap':raise EvaluationError('unknown public example task')
    entries=[{'kind':'file','path':'a.txt','size':2},
             {'kind':'file','path':'z.bin','size':1},
             {'kind':'dir','path':'sub'}, {'kind':'file','path':'sub/b.txt','size':3},
             {'kind':'link','path':'shortcut','target':'sub'}]
    return [{'id':'public-'+str(i+1),'task':task,'group':'public-example',
             'entries':entries,'argv':['--root','/fixture/root','--max-depth',str(depth),'--suffix','.txt'],
             'stdin_hex':'','expected':{'files':[{'path':'a.txt','bytes':2}]+(
                 [{'path':'sub/b.txt','bytes':3}] if depth==2 else []),
                 'total_bytes':5 if depth==2 else 2,'symlinks':['shortcut']}}
            for i,depth in enumerate((2,1))]


def generation_closed(progress,cells):
    terminal={'complete','failed','infra_inconclusive'}
    records=progress['cells']
    if any(r['status'] not in terminal for r in records.values()):
        raise EvaluationError('generation still pending; reserved feedback unavailable')
    all_closed=progress['next_index']==len(cells) and set(records)=={c['id'] for c in cells}
    stopped=bool(progress.get('paused') and progress['paused'].get('actual_native_failure'))
    if not (all_closed or stopped):raise EvaluationError('fixed campaign is not terminal')


def counts(rows):
    n=len(rows);values={s:sum(r['verdict']['status']==s for r in rows)
                       for s in ('pass','fail','inconclusive')}
    return {**values,'denominator':n,'conservative_fraction':values['pass']/n if n else None,
            'descriptive_bounds':[values['pass']/n,(values['pass']+values['inconclusive'])/n] if n else None,
            'statistical_confidence_interval':False,
            'all_passed':bool(n and values['pass']==n)}


def functional_delivery(packet,root,image,cases,*,runner_factory=ReservedDocker,absence_status='fail'):
    """No method, process, rubric or native credentials enter this function."""
    if set(packet)!={'schema','opaque_id','task','files','files_sha256'} or packet['schema']!=1:
        raise EvaluationError('invalid opaque delivery packet')
    files=packet['files'];task=packet['task']
    if absence_status not in {'fail','inconclusive'}:raise EvaluationError('absence cannot imply success')
    if digest(canonical(files))!=packet['files_sha256']:raise EvaluationError('opaque delivery hash mismatch')
    selected=[c for c in cases if c['task']==task]
    expected_n={'routeplan':61,'treemap':52}.get(task)
    if len(selected)!=expected_n or len({c['id'] for c in selected})!=expected_n:
        raise EvaluationError('fixed reserved denominator changed')
    recipes=selected+([audit_case()] if task=='treemap' else [])+public_examples(task)
    (root/'closed-results').mkdir(parents=True,mode=0o700,exist_ok=True)
    runner=None;results=[]
    if task+'.py' in files:runner=runner_factory(root,image)
    for case in recipes:
        path=root/'closed-results'/(case['id']+'.json')
        binding={'delivery_sha256':packet['files_sha256'],'case_sha256':digest(canonical(case))}
        if path.exists():
            row=_json(path)
            if row['binding']!=binding:raise EvaluationError('closed evaluation binding changed')
        else:
            if runner is None:
                measured={'verdict':{'status':absence_status,'reason':'contractual program absent'},
                          'execution_occurred':False,'native_model_calls':0}
            else:
                try:measured=runner.run(case['id'],case,files)
                except (EvaluationError,JobError,OSError) as exc:
                    measured={'verdict':{'status':'inconclusive','reason':str(exc)},
                              'error_type':type(exc).__name__,'automatic_retry':False,'native_model_calls':0}
            row={'id':case['id'],'group':case['group'],'binding':binding,**measured}
            _write(path,row)
        results.append(row)
    reserved=results[:expected_n]
    probe=results[expected_n] if task=='treemap' else None
    examples=results[-2:]
    return {'schema':1,'opaque_id':packet['opaque_id'],'delivery_sha256':packet['files_sha256'],
            'reserved':{'summary':counts(reserved),'groups':{
                g:counts([r for r in reserved if r['group']==g]) for g in sorted({r['group'] for r in reserved})},
                'invocations':reserved},'content_probe':probe,
            'public_examples':{'recipe_source_sha256':digest(Path(__file__).read_bytes()),
                'readme_shell_commands_executed':False,'path_substitution':'/input/tree -> /fixture/root',
                'summary':counts(examples),'invocations':examples},
            'behavior_satisfied':counts(reserved)['all_passed'] and (probe is None or probe['verdict']['status']=='pass')}


def corroborate_documentation(observation,examples):
    """Keep independent README judgments; require execution too for D3/D4."""
    result=copy.deepcopy(observation)
    if result.get('status')!='observed':return result
    dimension=result['dimensions']['documentation']
    for id,execution in zip(('D3','D4'),examples):
        point=next(p for p in dimension['points'] if p['id']==id)
        point['public_example_execution']=execution['verdict']
        if point['verdict']=='satisfied' and execution['verdict']['status']!='pass':
            point['verdict']='unsatisfied' if execution['verdict']['status']=='fail' else 'inconclusive'
            point['reason']+='; documented example execution did not pass'
    for status in ('satisfied','unsatisfied','inconclusive'):
        dimension[status]=sum(p['verdict']==status for p in dimension['points'])
    result['post_execution_corroboration']=True
    result['independent_judgment_sha256']=result.pop('judgment_sha256')
    result['corroborated_observation_sha256']=digest(canonical(result['dimensions']))
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registration',type=Path,required=True)
    parser.add_argument('--source-root',type=Path,default=Path(__file__).resolve().parents[3])
    args=parser.parse_args(argv)
    value,sha=registration(args.registration,args.source_root)
    root=validate_configuration(value,args.source_root)
    fd=os.open(root/'.campaign.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:raise EvaluationError('campaign/evaluation already has a writer') from exc
        evaluate_campaign(value,sha,root,args.source_root)
    finally:os.close(fd)


def evaluate_campaign(value,sha,root,source):
    progress=_json(root/'progress.json');generation_closed(progress,value['cells'])
    evaluation=root/'evaluation';evaluation.mkdir(mode=0o700,exist_ok=True)
    policy={'schema':1,'registration_sha256':sha,'generation_checkpoint_sha256':digest(canonical(progress))}
    bound=evaluation/'policy.json'
    if bound.exists() and _json(bound)!=policy:raise EvaluationError('generation changed after evaluation began')
    if not bound.exists():_write(bound,policy)
    cases=_json(source/'experiments/software_comparison_v1/reserved/suite-draft.json')['cases']
    rows=[]
    for cell in value['cells']:
        record=progress['cells'].get(cell['id']); row={'cell':cell,'status':'not_started'}
        if record:
            row['status']=record['status']; exported=record.get('export',{})
            if 'opaque_id' not in exported:
                row.update(functional=None,assessment=None,evaluation_status='inconclusive_export')
            else:
                folder=root/'deliveries'/exported['opaque_id'];packet=_json(folder/'delivery.json')
                if (packet['opaque_id']!=exported['opaque_id'] or packet['task']!=cell['task']
                        or packet['files_sha256']!=exported['delivery_sha256']):
                    raise EvaluationError('export and opaque delivery bindings differ')
                for name,text in packet['files'].items():
                    safe_file(name)
                    if _read(folder/'files'/name).decode()!=text:raise EvaluationError('sealed delivery file changed')
                functional=functional_delivery(packet,evaluation/packet['opaque_id'],value['images']['test'],cases,
                    absence_status='inconclusive' if record['status']=='infra_inconclusive' else 'fail')
                observed=root/'cells'/cell['id']/'generation/assessment.json'
                assessment=_json(observed) if observed.exists() else {'status':'inconclusive','reason':'no final independent rubric judgment','dimensions':None}
                row.update(functional=functional,assessment=corroborate_documentation(assessment,
                    functional['public_examples']['invocations']),evaluation_status='evaluated')
        rows.append(row)
        _write(evaluation/'results.json',{'schema':1,'registration_sha256':sha,'planned_denominator':28,
            'rows':rows,'finished':len(rows)==28,'combined_winner':None,'causal_verdict':None})
    print('Fixed population evaluation closed; see '+str(evaluation/'results.json'))


if __name__=='__main__':main()
