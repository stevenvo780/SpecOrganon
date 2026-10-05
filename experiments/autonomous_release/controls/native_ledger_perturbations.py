from pathlib import Path
import json,hashlib,shutil,copy,sysconfig
from specorganon import engine
from specorganon.report import case_report
from specorganon.runner import describe_task
import specorganon
assert Path(specorganon.__file__).is_relative_to(Path(sysconfig.get_paths()['purelib']))
seed=Path('/seed/organon.json');initial=seed.read_bytes();root=Path('/runs')
result={'schema':1,'scope':'Synthetic perturbations on copied real ledger; no new native review, cohort author, subject invocation or acceptance. Engine blocks explicit challenges; this does not prove automatic semantic contradiction detection.','version':specorganon.__version__,'installed_origin':specorganon.__file__,'seed_sha256':hashlib.sha256(initial).hexdigest(),'scenarios':{}}

def baseline(name):
 p=root/name;p.mkdir();shutil.copyfile(seed,p/'organon.json')
 before=(p/'organon.json').read_bytes();state=engine.get_state(p);report=case_report(p);task=describe_task(state)
 assert all(v['accepted'] for v in state['phases'].values()) and task['status']=='done'
 assert (p/'organon.json').read_bytes()==before
 return p,state

def rejected_advance(p,phase):
 before=(p/'organon.json').read_bytes()
 try:engine.advance(p,phase,'control:synthetic-runner')
 except engine.MethodError as e:reason=str(e)
 else:raise AssertionError('unjustified advance admitted')
 assert (p/'organon.json').read_bytes()==before
 return {'rejected':True,'reason':reason,'rejected_write_preserved_ledger':True}

p,state=baseline('explicit-contradiction')
event=engine.challenge(p,'impl1','t1','Synthetic objection: this isolated control postulates P and not-P to test a contradiction gate; it makes no factual allegation about the sealed delivery.','control:synthetic-observer')
s=engine.get_state(p);gate=engine.gate(p,'build')
assert event['seq'] in [x['seq'] for x in s['open_challenges']] and not gate['ready'] and not gate['accepted']
result['scenarios']['explicit_contradiction']={'challenge_seq':event['seq'],'open_challenges':len(s['open_challenges']),'build_ready':gate['ready'],'build_accepted':gate['accepted'],**rejected_advance(p,'build')}

p,state=baseline('insufficient-receipt');item=state['items']['t1'];data=copy.deepcopy(item['data']);data.pop('receipt')
engine.put_item(p,'t1',item['kind'],item['text']+' Synthetic perturbation: receipt intentionally removed.',list(item['deps']),data,'control:synthetic-writer',expected_version=item['version'],expected_deps=item['deps'])
s=engine.get_state(p);gate=engine.gate(p,'build');assert not gate['ready']
assert any('structured execution receipt' in v for v in s['items']['t1']['issues'])
result['scenarios']['insufficient_evidence']={'passed_claim_retained':data.get('passed'),'receipt_removed':True,'issues':s['items']['t1']['issues'],'build_ready':gate['ready'],**rejected_advance(p,'build')}

p,state=baseline('changed-premise');item=state['items']['p1'];refs=list(item['deps'])
engine.put_item(p,'p1',item['kind'],item['text']+' Synthetic premise change for dependency invalidation control.',refs,item['data'],'control:synthetic-writer',expected_version=item['version'],expected_deps=item['deps'])
s=engine.get_state(p);stale=[k for k,v in s['items'].items() if v['stale']];assert s['items']['impl1']['stale'] and s['items']['t1']['stale'] and not s['phases']['validate']['accepted']
block=rejected_advance(p,'build')
# Restoring text is still a new version; stale descendants do not regain approval.
engine.put_item(p,'p1',item['kind'],item['text'],refs,item['data'],'control:synthetic-writer',expected_version=s['items']['p1']['version'],expected_deps={i:s['items'][i]['version'] for i in refs})
restored=engine.get_state(p);assert restored['items']['p1']['version']==item['version']+2 and restored['items']['impl1']['stale'] and not restored['phases']['validate']['accepted']
result['scenarios']['changed_premise']={'stale_items':stale,'implementation_stale':True,'test_stale':True,'validation_reopened':True,'restoring_text_does_not_restore_acceptance':True,'blocked_after_change':block,'blocked_after_text_restoration':rejected_advance(p,'build'),'next_task':describe_task(restored)['phase']}
assert seed.read_bytes()==initial;result['original_native_ledger_unchanged']=True;result['provider_calls']=0;result['reserved_subjects']=0
(root/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False))
