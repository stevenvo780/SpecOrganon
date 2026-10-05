from pathlib import Path
import copy,json
from experiments.software_comparison_v3.reserved import recipes,TASK_FILES,ERROR
from experiments.software_comparison_v3.subjects import Subjects,SubjectError
from specorganon.role_jobs import _json,_write,_read,digest,canonical
root=Path(__file__).parent
image='sha256:98723123de528a5f0201a1c341fe044f88d885345b2e1bedd6a89574c4796d92'
controls=[]
def output(row):
    target=row['expected']
    if row['task']=='fractionmix':
        text='{"numerator":'+target['numerator_decimal']+',"denominator":'+target['denominator_decimal']+',"term_count":'+str(target['term_count'])+'}\n'
        return text.encode()
    return json.dumps(target,ensure_ascii=False,separators=(',',':')).encode()+b'\n'
def run(task,label,row,code,status):
    folder=root/task/label
    subject=Subjects(folder,image,task)
    files={TASK_FILES[task]:code}
    actual=subject.run(row['id'],row,files)
    assert actual['status']==status,(task,label,actual)
    controls.append({'task':task,'control':label,'actual_subject':True,**actual})
    _write(root/'progress.json',{'classification':'synthetic transport fixtures, not cohort deliveries','controls':controls,'complete':False})
    return subject,files,actual
for task in TASK_FILES:
    matrix=recipes(task)
    public=next(r for r in matrix if r['public'])
    success="import sys\nsys.stdout.buffer.write("+repr(output(public))+")\n"
    subject,files,first=run(task,'good-public-stream',public,success,'pass')
    before={str(p.relative_to(subject.root)):digest(p.read_bytes()) for p in (subject.root/'journal').rglob('receipt.json')}
    again=subject.run(public['id'],public,files)
    after={str(p.relative_to(subject.root)):digest(p.read_bytes()) for p in (subject.root/'journal').rglob('receipt.json')}
    assert first==again and before==after and len(after)==1
    controls.append({'task':task,'control':'closed-replay','actual_subject':False,'pass':True,'receipt_count':len(after)})
    for label,mutated_recipe,mutated_files in [
        ('changed-recipe',{**public,'expected':{}},files),
        ('changed-delivery',public,{TASK_FILES[task]:success+'# changed\n'})]:
        try:subject.run(public['id'],mutated_recipe,mutated_files)
        except SubjectError:controls.append({'task':task,'control':label,'actual_subject':False,'pass':True})
        else:raise AssertionError(label+' silently admitted')
    run(task,'wrong-public-stream',public,"print('{}')\n",'fail')
    invalid=next(r for r in matrix if r['group']=='format' and r['expected'] is None)
    exact="import sys\nsys.stderr.buffer.write("+repr(ERROR)+")\nraise SystemExit(2)\n"
    run(task,'exact-invalid-error',invalid,exact,'pass')
    run(task,'wrong-invalid-error',invalid,"import sys\nsys.stderr.write('invalid_input\\n')\nraise SystemExit(2)\n",'fail')
    held=next(r for r in matrix if r['stdin_mode']=='held_open')
    _,_,good=run(task,'argv-before-read',held,exact,'pass')
    report=_json(Path(good['observer_ref']))
    assert not report['observed_stdin_syscalls'] and report['exit_code']==2
    _,_,blocking=run(task,'argv-blocking-read',held,"import sys\nsys.stdin.buffer.read()\n"+exact,'fail')
    assert blocking['exit_code']==124 and _json(Path(blocking['observer_ref']))['observed_stdin_syscalls']
    nonblock="import os,fcntl\nfcntl.fcntl(0,fcntl.F_SETFL,fcntl.fcntl(0,fcntl.F_GETFL)|os.O_NONBLOCK)\ntry: os.read(0,1)\nexcept BlockingIOError: pass\n"+exact
    _,_,nonblocking=run(task,'argv-nonblocking-read',held,nonblock,'fail')
    assert nonblocking['exit_code']==125 and _json(Path(nonblocking['observer_ref']))['observed_stdin_syscalls']
    if task=='fractionmix':
        big=next(r for r in matrix if '7331-digit' in r['id'])
        run(task,'large-integer-stream',big,"import sys\nsys.stdout.buffer.write("+repr(output(big))+")\n",'pass')
result={'schema':1,'classification':'synthetic evaluator transport/observer controls, not generated comparison software','image':image,'controls':controls,'complete':True,
        'total_controls':len(controls),'actual_Docker_subjects':sum(r['actual_subject'] for r in controls),
        'native_author_calls':0,'comparison_generated_cells':0,'nine_phase_deliveries':0,'registration_ready':False,
        'oracle_correctness_proven_by_canned_streams':False,'observer_scope':'finite listed stdin syscalls, conformance instrument; not hostile anti-tamper proof'}
_write(root/'summary.json',result)
print(json.dumps({'complete':True,'controls':len(controls),'actual_Docker_subjects':result['actual_Docker_subjects'],'comparison_generated_cells':0,'native_author_calls':0}),flush=True)

