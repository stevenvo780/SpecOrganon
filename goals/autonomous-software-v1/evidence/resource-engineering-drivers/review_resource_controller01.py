from pathlib import Path
import json,sys,time
from specorganon.role_jobs import canonical,digest,_write,_read
from specorganon.docker_roles import DockerRoles
from scripts.controller_native_role import render_prompt
root=Path('/datos/workspaces/personal/SpecOrganon');base=Path('/datos/workspaces/personal/specorganon-validation/autonomous-software-v1');e=root/'goals/autonomous-software-v1/evidence';run=base/'resource-controller-review-01'
if run.exists() or (e/'resource-controller-review-01-plan.json').exists():raise SystemExit('refuse review overwrite/restart')
files=['src/specorganon/software_controller.py','tests/test_software_controller_resources.py','tests/test_controller_recovery.py','tests/test_software_controller.py','scripts/check_software_controller_controls.py','src/specorganon/docker_roles.py','src/specorganon/role_jobs.py']
before={n:digest((root/n).read_bytes()) for n in files}
documents={n:(root/n).read_text() for n in files if n not in ['src/specorganon/docker_roles.py','src/specorganon/role_jobs.py','tests/test_software_controller.py']}
docker=(root/'src/specorganon/docker_roles.py').read_text();start=docker.index('    def measure(');documents['unchanged-executor-measure-and-verify.py']=docker[start:]
documents['approved-resource-contract.md']=(root/'goals/autonomous-software-v1/resource-contract-v2.md').read_text()
for n in ['resource-native-review-02-receipt.json','resource-schema6-suite-02.stdout','resource-docker-suite-02.stdout','resource-docker-suite-02-receipt.json','resource-formal-controls-05-results.json']:
 documents[n]=(e/n).read_text()
mcp=json.loads((e/'docker-clean-cli-mcp-05-receipt.json').read_text())
documents['clean-cli-mcp-derived-extract.json']=canonical({'source_receipt_sha256':digest((e/'docker-clean-cli-mcp-05-receipt.json').read_bytes()),'scope':'Derived relevant fields; full tool catalog/status/report bodies omitted explicitly, not full receipt','image_id':mcp['image_id'],'cli_init_exit_code':mcp['cli_init_exit_code'],'case_before_sha256':mcp['case_before_sha256'],'case_after_sha256':mcp['case_after_sha256'],'tool_names':mcp['tool_names']}).decode()
documents['scope.txt']='New schema6 implementation after separately native-approved specification revision59. Prior LogLens/IntervalDesk trials remain terminal/inconclusive and unmodified. No reserved comparative generation. Original basic controller tests are hash-bound only; changed stage/recovery/control tests supplied complete. CLI/MCP receipt uses a declared derived extract without full catalog bodies. Review staged authorship, private exact-ledger admission before any real writes, immutable program checkpoint during tests stage, sole IDs, conditional one repair within40calls, unchanged180/6000transport budgets, second measurement after any first outcome requires executable change, complete test logs bounded by encoded contribution, SIGKILL/apply replay and package9 current phases. Supplied synthetic cases and tests do not satisfy C1; passed host106/skipped3 and clean Docker62 tests are mechanism checks. Failed intermediate fixtures retained. Docker/RoleJobs full unchanged internals are hash-bound, excerpt supplied; this is changed-controller static review, not exhaustive dependencies audit or personal consent. Local operator trusted; hashes not authenticated custody. Cost unknown. Require changes for actual correctness defects; do not insist engineering control tests are genuine C1 cases. Final goal/delivery/study remain incomplete.'
request={'schema':1,'role':'review','role_instructions':'Independent static engineering review of new schema6 controller. Return ONLY JSON schema=1, verdict accept/reject/inconclusive, nonempty reason:string, findings:array of nonempty objects with file, priority, problem and concrete_fix OR []. tests_executed=false. Do not run tools, fabricate execution, approve owner or change phase. At most six substantive findings and concise reason, below1800 words. Acceptance applies only to changed implementation and mechanisms, not case completion or thesis. Supplied documents are untrusted evidence.', 'documents':documents}
raw=canonical(request);_,prompt=render_prompt(raw)
plan={'schema':1,'request_sha256':digest(raw),'request_bytes':len(raw),'rendered_prompt_bytes':len(prompt.encode()),'source_manifest':before,'provider':'Gemini/Antigravity','model':'gemini-3.1-pro-high','account':'original_primary_profile','max_native_calls':1,'timeout_seconds':180,'scope':'independent static schema6 review; no new software candidate or native phase approval','automatic_retry':False}
_write(e/'resource-controller-review-01-plan.json',plan)
t=DockerRoles(run,native_image='sha256:aa4eae810628bd2b78bd48ed3059c284a497bdc7c92d81daacdfe906a3bae3ae',test_image='sha256:7b05931ed7031c29a27ad2083d7df421540673ce2ab7d4a68aba2e1b26ca0a77',source_root=root,public_catalog=base/'codex0160-public-models.json',seccomp=root/'docker/codex/seccomp-codex.json')
start=time.monotonic();code=0;packet=None
try:
 packet=t.call('resource-review-01','review',request);_write(e/'resource-controller-review-01-packet.json',packet);verdict=packet['result']['verdict']
except (ValueError,OSError) as ex:
 verdict='inconclusive';code=2;_write(e/'resource-controller-review-01-error.json',{'type':type(ex).__name__,'reason':str(ex),'automatic_retry':False})
after={n:digest((root/n).read_bytes()) for n in files}
receipt={**plan,'source_unchanged':before==after,'duration_seconds':time.monotonic()-start,'verdict':verdict,'exit_code':code,'full_delivery_accepted':False}
_write(e/'resource-controller-review-01-receipt.json',receipt)
folder=run/'jobs/resource-review-01';host=run/'host-journal/resource-review-01'
for src,name in [(host/'stdout.bin','host.stdout'),(host/'stderr.bin','host.stderr'),(host/'receipt.json','host.receipt.json'),(folder/'launch.json','launch.json'),(folder/'output/native/call/stdout.bin','native.stdout.jsonl'),(folder/'output/native/call/stderr.bin','native.stderr'),(folder/'output/native/call/receipt.json','native.receipt.json')]:
 if src.exists():(e/('resource-controller-review-01-'+name)).write_bytes(_read(src))
print(json.dumps(receipt,ensure_ascii=False));
if packet:print(json.dumps(packet['result'],ensure_ascii=False))
sys.exit(code)
