"""Dependent private presentation preparation; never deploys or changes originals."""
from pathlib import Path
import json,os,time,datetime,subprocess,fcntl
base=Path(__file__).parent;run=base.parent/'software-comparison-v3';report=run/'report.json';lockfd=os.open(base/'dependent-private-preparation-01.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600);fcntl.flock(lockfd,fcntl.LOCK_EX|fcntl.LOCK_NB)

def record(value):
 value={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),**value};fd=os.open(base/'prepare-after-evaluation-01.jsonl',os.O_CREAT|os.O_APPEND|os.O_WRONLY|os.O_NOFOLLOW,0o600)
 try:os.write(fd,(json.dumps(value,sort_keys=True)+'\n').encode())
 finally:os.close(fd)
 print(json.dumps(value),flush=True)

def evaluator_running():
 p=Path('/proc/634878')
 if not p.exists() or (p/'stat').read_text().split(') ',1)[1].split()[0]=='Z':return False
 assert b'evaluate-after-fixed-generation-01.py' in (p/'cmdline').read_bytes(),'unexpected evaluator identity'
 return True
record({'action':'dependent_private_preparation_started','pid':os.getpid(),'evaluation_pid':634878,'no_deployment':True,'model_or_subject_calls':0})
while not report.exists() or evaluator_running():
 if not evaluator_running():raise RuntimeError('original evaluator exited without immutable report; inspect original same handles')
 time.sleep(30)
value=json.loads(report.read_text());assert value['evaluation_complete'] is True and value['design_denominator']==42
for name in ['export_campaign.py','package_final_evidence.py','summarize_final_report.py']:
 p=subprocess.run(['/usr/bin/python3',str(base/name)],cwd=base,capture_output=True,timeout=120);(base/(name+'.final.stdout')).write_bytes(p.stdout);(base/(name+'.final.stderr')).write_bytes(p.stderr);record({'action':'private_final_script_closed','name':name,'exit_code':p.returncode,'published':False});assert p.returncode==0,'private final script failed: '+name
record({'action':'private_final_preparation_complete','published':False,'source_or_auth_profiles_changed':False,'model_or_subject_calls':0})
