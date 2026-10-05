from pathlib import Path
import time,json,sys
from specorganon import engine
from specorganon.role_jobs import _write,digest
from specorganon.docker_roles import DockerRoles
from specorganon.software_controller import Controller
root=Path('/datos/workspaces/personal/SpecOrganon');base=Path('/datos/workspaces/personal/specorganon-validation/autonomous-software-v1');e=root/'goals/autonomous-software-v1/evidence';case=root/'cases/autonomous_software_v1';run=base/'resource-design-review-02'
if run.exists():raise SystemExit('refuse engineering repair overwrite/restart')
s=engine.get_state(case);assert s['revision']==56 and s['items']['d1']['approved'] and s['items']['req1']['version']==3 and s['items']['cr1']['version']==3
plan={'schema':1,'case_revision':56,'engineering_version':3,'max_native_calls':2,'prior_candidate_trials_terminal':True,'scope':'Separate conformity for d_resource and specify review of new resource items. Existing d1/req1/cr1 and terminal candidate trials retained. Static design only, no test execution or reserved-study generation.','provider':'Gemini/Antigravity','model':'gemini-3.1-pro-high','account':'original_primary_profile','timeout_seconds':180,'proposal_sha256':digest((root/'goals/autonomous-software-v1/resource-contract-v2.md').read_bytes()),'automatic_replacement':False,'new_case_generation':False}
_write(e/'resource-native-review-02-plan.json',plan)
t=DockerRoles(run/'transport',native_image='sha256:aa4eae810628bd2b78bd48ed3059c284a497bdc7c92d81daacdfe906a3bae3ae',test_image='sha256:cc229ddddcf2cca004204d4d8d3a724be348022d9f353cf10c1ffe516daed06e',source_root=root,public_catalog=base/'codex0160-public-models.json',seccomp=root/'docker/codex/seccomp-codex.json')
c=Controller(case,run/'controller',t,contract=(root/'goals/autonomous-software-v1/resource-contract-v2.md').read_text(),mandate=(root/'goals/autonomous-software-v1/loglens-existing-mandate.md').read_text(),executor=t)
start=time.monotonic();result=None;code=0
try:
 results=[]
 for index in range(2):
  result=c.step();results.append(result);print(json.dumps(result,ensure_ascii=False),flush=True)
  if result.get('verdict')!='accept':code=2;break
  if engine.get_state(case)['phases']['specify']['accepted']:break
except (ValueError,OSError) as ex:
 code=2;_write(e/'resource-native-review-02-error.json',{'type':type(ex).__name__,'reason':str(ex),'automatic_replacement':False})
s=engine.get_state(case);_write(e/'resource-native-review-02-final-state.json',s);_write(e/'resource-native-review-02-receipt.json',{**plan,'duration_seconds':time.monotonic()-start,'exit_code':code,'result':result,'revision':s['revision'],'specify_accepted':s['phases']['specify']['accepted'],'whole_delivery_accepted':False});sys.exit(code)
