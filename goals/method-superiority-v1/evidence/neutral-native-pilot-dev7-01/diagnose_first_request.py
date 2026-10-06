"""Read-only reconstruction of a closed failed request; never a pilot retry."""
from pathlib import Path
import copy,json
import specorganon.neutral_controller as base
from specorganon.neutral_autonomy import AutonomousNeutralController
from specorganon.role_jobs import canonical,digest
B=Path(__file__).resolve().parent
root=Path('/datos/workspaces/personal/specorganon-validation/method-superiority-v1/neutral-public-native-dev7-01/attempt-01/controller')
assert (root.parent/'closure.json').exists()
past=[];pins={}
def read(p):
 raw=p.read_bytes();pins[str(p)]=digest(raw);return json.loads(raw)
for i in range(1,5):
 n=f'{i:04d}.json';r=read(root/'reservations'/n);v=read(root/'results'/n);g=read(root/'generations'/n)
 past.append({'reservation':r,'result':v,'state':g['state']})
state=copy.deepcopy(past[-1]['state']);state['stage']='program'
obj=object.__new__(AutonomousNeutralController);obj.policy=read(root/'initial.json')['policy']
# Diagnostic subprocess ONLY: bypass request/prompt ceilings in this process's
# memory to obtain bytes the original guard refused. No files/constants/driver
# are changed, no constructor/dispatch/audit/measurement is called.
original_limit=base.LIMITS['request_bytes'];base.LIMITS['request_bytes']=10000000;base.render_prompt=lambda raw:None
req,ref=base.NeutralController._request(obj,state,past,5);assert ref is None
report={'schema':1,'scope':'Offline read-only reconstruction of the refused base free request, not an admitted request, retry or model call','attempt':'attempt-01','failed_reservation':'0005.json','original_request_limit':original_limit,'reconstructed_canonical_bytes':len(canonical(req)),'document_bytes_before_outer_JSON':{name:len(text.encode()) for name,text in req['documents'].items()},'history_records':len(past),'current_files_encoded_bytes':len(canonical(state['files'])),'current_documents_encoded_bytes':len(canonical(state['documents'])),'role_packet_bytes_in_history':sum(len(canonical(p['result'])) for p in past),'capture_bytes_in_history':sum(len(canonical({'files':p['state']['files'],'documents':p['state']['documents']})) for p in past),'input_sha256':pins,'source_files_modified':False,'new_model_calls':0,'new_native_generations':0,'goal_achieved':False}
assert report['reconstructed_canonical_bytes']>original_limit
(B/'first-request-diagnostic.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k] for k in ['original_request_limit','reconstructed_canonical_bytes','document_bytes_before_outer_JSON','role_packet_bytes_in_history','capture_bytes_in_history']}))
