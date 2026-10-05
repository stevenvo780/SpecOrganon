"""Private dependent evaluation: no Subjects until fixed generation ends and gate permits.
No model dispatch, feedback, author repair, new generation or uncertainty rerun.
"""
from pathlib import Path
import os,json,time,datetime,fcntl
from experiments.software_comparison_v3.registration import Registration
from experiments.software_comparison_v3.campaign import Campaign
from experiments.software_comparison_v3.evaluation import Evaluation
from specorganon.role_jobs import _json,canonical
base=Path(__file__).absolute().parent;source=Path('/home/stev/.codex/worktrees/comparison-v3-budget/SpecOrganon');run=base.parent/'software-comparison-v3'
assert Path.cwd()==source
registration=Registration(base/'registration-04.json',source);registration.validate();assert registration.sha=='0bc7182ab4713080db3120183e11ca45ad1f6f1ed752c856dc4028b24b728ed5'
lockfd=os.open(base/'dependent-evaluation-01.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600);fcntl.flock(lockfd,fcntl.LOCK_EX|fcntl.LOCK_NB)
log=base/'evaluate-after-fixed-generation-01.jsonl';last=None

def record(value):
 value={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),**value};fd=os.open(log,os.O_CREAT|os.O_APPEND|os.O_WRONLY|os.O_NOFOLLOW,0o600)
 try:os.write(fd,canonical(value)+b'\n')
 finally:os.close(fd)
 print(json.dumps(value),flush=True)

def generation_running():
 path=Path('/proc/3895058')
 if not path.exists():return False
 state=(path/'stat').read_text().split(') ',1)[1].split()[0]
 if state=='Z':return False
 cmd=(path/'cmdline').read_bytes()
 assert b'continue-fixed-generation-01.py' in cmd,'unexpected process identity; preserve without evaluation'
 return True

record({'action':'dependent_evaluator_started','pid':os.getpid(),'generation_pid':3895058,'registration_sha256':registration.sha,'model_calls':0,'reserved_subjects_started':False})
try:
 while True:
  progress=_json(run/'budget/progress.json');terminal=sum(v['terminal'] is not None for v in progress['cells'].values());alive=generation_running()
  if terminal!=last:
   record({'action':'waiting_for_original_generation','terminal':terminal,'population':42,'original_generator_alive':alive,'reserved_subjects_started':False});last=terminal
  if terminal==42 and not alive:break
  if not alive:raise RuntimeError('original generation stopped before fixed42 closed; inspect same original handles; no evaluation')
  time.sleep(30)
 # No model admission occurs below; the existing quota path is retained without
 # substituting accounts or refreshing a model observation for this evaluation.
 c=Campaign(registration,base/'quota-admission-06.json');gate=c.gate()
 record({'action':'gate_observed_after_original_generation','gate':gate,'model_calls':0})
 assert gate['status']=='released_once' and gate['reserved_evaluation_allowed'] is True,'prerequisite pending; no reserved subjects'
 evaluator=Evaluation(c);steps=0
 while True:
  result=evaluator.step();steps+=1
  if result.get('cell_complete'):record({'action':'evaluation_cell_complete','opaque_id':result['opaque_id'],'steps':steps,'feedback_to_authors':False})
  if result.get('all_evaluation_terminal') or result.get('action')=='all_evaluation_terminal':break
 report=evaluator.report();record({'action':'immutable_report_written','cells':len(report['cells']),'evaluation_complete':report['evaluation_complete'],'report_ref':str(run/'report.json'),'new_native_calls':0,'original_generations_repaired':False})
except Exception as exc:
 record({'action':'dependent_evaluator_stopped','exception_type':type(exc).__name__,'reason':str(exc),'rerun_or_repair':False,'same_existing_handle_only':True});raise
