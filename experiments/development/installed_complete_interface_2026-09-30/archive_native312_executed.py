import ast
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path

out=Path('/workspace/SpecOrganon/experiments/development/installed_complete_interface_2026-09-30')
source=(out/'archive_final_executed.py').read_bytes()
tree=ast.parse(source)
# Reuse only frozen imports/constants/functions; the first aggregation's
# top-level execution is not repeated and its seven workspaces remain intact.
selected=[n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom,ast.FunctionDef))
          or isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in ('REPO','OUT','D102') for t in n.targets)]
namespace={}
exec(compile(ast.Module(body=selected,type_ignores=[]),str(out/'archive_final_executed.py'),'exec'),namespace)
bundle,cp,js=namespace['bundle'],namespace['cp'],namespace['js']
root=Path('/tmp/specorganon-D103-native-312-7o8846h5')
archive=bundle(root,'native/312/workspace.tar.gz')
for name in ('preparation.json','release.json','verification.json','verification-transports.json',
             'verification.stdout','verification.stderr'):
    cp(root/name,'native/312/'+name)
for role in ('A','B'):
    for name in ('ready.json','receipt.json','calls.json','checks.json'):
        cp(root/('writer-'+role)/name,'native/312/'+role+'/'+name)
    for stream in ('stdout','stderr'):
        cp(root/('writer-'+role+'.'+stream),'native/312/'+role+'/writer.'+stream)
old=(out/'archives.json').read_bytes()
js('archives_before_native312.json',json.loads(old))
archives=json.loads(old);assert len(archives)==7
archives.append(archive)
(out/'archives.json').write_text(json.dumps(archives,indent=2)+'\n')
old=(out/'critical_checks.json').read_bytes()
js('critical_checks_first_snapshot.json',json.loads(old))
checks=json.loads(old)
for v in ('311','312'):
    name='native/verification.json' if v=='311' else 'native/312/verification.json'
    verification=json.loads((out/name).read_text());assert verification['passed']
    checks['per_python'][v]['native_verification']=name
    checks['per_python'][v]['native_guarded_items']=verification['guarded_native_items']
    checks['per_python'][v]['native_overlap_ns']=verification['native_activity_overlap_ns']
checks['native_both_environments_complete']=True
checks['native_verification']={'311':'native/verification.json','312':'native/312/verification.json'}
(out/'critical_checks.json').write_text(json.dumps(checks,indent=2)+'\n')
freeze=json.loads((out/'source_freeze_amendment.json').read_text())
assert all(hashlib.sha256((Path('/workspace/SpecOrganon')/n).read_bytes()).hexdigest()==p['sha256'] for n,p in freeze['files'].items())
js('native/312/source_post_execution.json',{'recorded_at_utc':datetime.now(timezone.utc).isoformat(),
                                        'all15_amended_pins_match':True,'files':freeze['files'],
                                        'verifier_sha256':hashlib.sha256((out/'native/312/verifier_executed.py').read_bytes()).hexdigest()})
cp(__file__,'archive_native312_executed.py')
print(json.dumps({'archives':len(archives),'native_environments':2,'thresholds_changed':False}))
