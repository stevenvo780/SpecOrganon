"""Sequential, resumable pilot. Hidden evaluation starts after all author stages."""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE))
import schedule

HOME_VOLUME='specorganon-lab_codex-home'
METHOD_PROMPT='''Revisa las fases del caso /trial/case con actor agent:method-reviewer.
Eres una sesión independiente del autor. Lee los artefactos reales, los contratos
de metodología y las pruebas registradas. No escribas ni repares la solución ni
los artefactos del autor. No inventes observaciones, aprobaciones o pruebas.
Puedes registrar review_phase (accept/reject con motivos concretos) y advance
únicamente para fases realmente listas y revisadas, en orden. Usa status/gate/report
y distingue bloqueos, calidad semántica y cumplimiento mecánico. Nunca cambies el
mandato ni atribuyas al dueño decisiones personales. Las decisiones técnicas dentro
del contrato están delegadas: puedes registrar su aprobación local con actor
human:owner y motivo explícito de delegación existente, solo si las has leído y
no cambian propósito, cuentas, presupuesto o frontera. La procedencia es local declarada,
no autenticada. No sustituyas la revisión técnica neutral o los tests reservados.
Devuelve JSON con fases leídas, aceptadas/rechazadas, límites y bloqueos pendientes.
El presupuesto termina a los 120 segundos; no delegues ni uses internet.
'''


def now(): return datetime.now(timezone.utc).isoformat()


def digest(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''): result.update(block)
    return result.hexdigest()


def save(path,value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n'); temp.replace(path)


def check_freeze(manifest):
    for name, expected in manifest['files'].items():
        if not Path(name).is_file() or digest(name)!=expected:
            raise RuntimeError('Frozen input changed: '+name)


def once(marker,task):
    marker=Path(marker)
    if marker.exists(): return json.loads(marker.read_text())
    started=marker.with_suffix('.started.json')
    if started.exists(): raise RuntimeError('Interrupted step requires an explicit disposition: '+str(started))
    save(started,{'started_at':now()})
    value=task(); save(marker,value); started.unlink()
    return value


def snapshot(source,dest):
    source=Path(source); dest=Path(dest); dest.mkdir(parents=True,exist_ok=False)
    total=0; files={}; links=[]; large=[]
    for path in sorted(source.rglob('*')):
        relative=path.relative_to(source); output=dest/relative
        if path.is_symlink(): links.append(relative.as_posix()); continue
        if path.is_dir(): output.mkdir(parents=True,exist_ok=True)
        elif path.is_file():
            size=path.stat().st_size
            if size>16*1024*1024 or total+size>128*1024*1024:
                large.append(relative.as_posix()); continue
            output.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(path,output)
            total+=size; files[relative.as_posix()]=digest(output)
    return {'files':files,'bytes':total,'omitted_links':links,'omitted_oversize':large}


def command(argv,stem,timeout,prompt=None,container=None):
    stem=Path(stem); stem.parent.mkdir(parents=True,exist_ok=True)
    started=time.monotonic(); timed_out=False
    if prompt is not None: stem.with_suffix('.prompt.txt').write_text(prompt)
    with stem.with_suffix('.jsonl').open('wb') as out, stem.with_suffix('.stderr').open('wb') as err:
        process=subprocess.Popen(argv,stdin=subprocess.PIPE if prompt is not None else subprocess.DEVNULL,
                                 stdout=out,stderr=err,start_new_session=True)
        try: process.communicate(prompt.encode() if prompt is not None else None,timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out=True
            if container:
                subprocess.run(['docker','kill',container],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)
            if process.poll() is None: process.kill()
            process.wait(timeout=30)
    usage=[]; errors=[]; agent_text=[]
    with stem.with_suffix('.jsonl').open() as stream:
        for line in stream:
            try: event=json.loads(line)
            except (ValueError,UnicodeError): continue
            if not isinstance(event,dict): continue
            if 'usage' in event: usage.append(event['usage'])
            if event.get('type') in ('error','turn.failed'): errors.append(event)
            item=event.get('item',{})
            if item.get('type')=='agent_message': agent_text.append(item.get('text',''))
    return {'argv':argv,'exit_code':process.returncode,'timed_out':timed_out,
            'duration_seconds':time.monotonic()-started,'finished_at':now(),'usage':usage,
            'errors':errors,'agent_text':agent_text,
            'stdout_sha256':digest(stem.with_suffix('.jsonl')),
            'stderr_sha256':digest(stem.with_suffix('.stderr'))}


def docker_model(image,workspace,argv,name,readonly=False):
    return ['docker','run','--rm','--init','-i','--name',name,'--user','1000:1000',
            '--cap-drop','ALL','--security-opt','no-new-privileges:true','--memory','1g',
            '--cpus','1','--pids-limit','128',
            '--security-opt','apparmor=unconfined','--security-opt','seccomp='+str(schedule.ROOT/'docker/codex/seccomp-codex.json'),
            '--mount',f'type=volume,src={HOME_VOLUME},dst=/home/codex/.codex',
            '--mount',f'type=bind,src={workspace},dst=/trial'+(',readonly' if readonly else ''),
            '--entrypoint',argv[0],image,*argv[1:]]


def initialize_case(workspace,image,stem):
    # Case is initialized in-place. No credentials enter snapshots or host files.
    program='''from specorganon import engine
path='/trial/case'
engine.create_case(path,'Backup verificable','software local','human:owner',approval_policy='local')
engine.put_item(path,'problem','problem','Crear backups autosuficientes, restauración exacta, integridad y recuperación según CONTRACT.md.',[],{},'agent:orchestrator')
engine.put_item(path,'mandate','norm','El dueño autorizó construir backups y evaluar este piloto local; decisiones técnicas delegadas dentro del contrato. Sin datos reales ni nuevas cuentas ni copias de credenciales.',['problem'],{},'agent:orchestrator')
'''
    program += "engine.approve(path,'mandate','Mandato existente: el dueño pidió dale asignatelo como goal; no aprobación personal de una arquitectura.','human:owner')\n"
    argv=['/opt/specorganon/.venv/bin/python','-c',program]
    return command(docker_model(image,workspace,argv,stem.name+'-init'),stem,30)


def method_argv():
    argv=schedule.author_argv('T',1)[:-1]
    for tool in ['review_phase','advance','approve']:
        argv+=['-c',f'mcp_servers.specorganon.tools.{tool}.approval_mode="approve"']
    return argv+['-']


def stage(row,number,manifest,runroot):
    record=runroot/f'stage{number}'; record.mkdir(exist_ok=True)
    workspace=runroot/'work'; workspace.mkdir(exist_ok=True)
    for relative,body in schedule.author_files(row['arm'],number).items():
        path=workspace/relative; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(body)
    image=manifest['images']['method' if row['arm']=='T' else 'control']
    if row['arm']=='T' and number==1:
        init=once(record/'init.receipt.json',lambda:initialize_case(workspace,image,record/'init'))
        if init['exit_code']!=0: raise RuntimeError('case initialization failed: '+row['id'])
    name='backup-pilot-'+row['id'].lower()+f'-s{number}'
    author=once(record/'author.receipt.json',lambda:command(
        docker_model(image,workspace,schedule.author_argv(row['arm'],number),name),
        record/'author',schedule.AUTHOR_SECONDS[row['arm']],schedule.author_prompt(row,number),name))
    # Timeout is a budget outcome. Provider/transport errors remain infrastructure failures.
    if not author['timed_out'] and (author['exit_code']!=0 or author['errors']):
        raise RuntimeError('author infrastructure failure; no automatic retry/account switch: '+row['id'])
    if row['arm']=='T':
        audit=once(record/'method.receipt.json',lambda:command(
            docker_model(image,workspace,method_argv(),name+'-method'),record/'method',
            schedule.METHOD_SECONDS,METHOD_PROMPT,name+'-method'))
        if not audit['timed_out'] and audit['exit_code']!=0:
            raise RuntimeError('method reviewer infrastructure failure: '+row['id'])
    def archive():
        return snapshot(workspace,record/'artifact')
    inventory=once(record/'artifact.receipt.json',archive)
    # No author/method documents or arm names in the reviewer filesystem.
    reviewspace=record/'review-work'; reviewspace.mkdir(exist_ok=True)
    (reviewspace/'CONTRACT.md').write_text(schedule.contract(number))
    solution=record/'artifact/solution'
    if solution.is_dir() and not (reviewspace/'solution').exists(): snapshot(solution,reviewspace/'solution')
    prompt=(BASE/'planning/reviewer-neutral.txt').read_text()
    review=once(record/'review.receipt.json',lambda:command(
        docker_model(manifest['images']['control'],reviewspace,schedule.review_argv(),name+'-review',True),
        record/'review',schedule.REVIEW_SECONDS,prompt,name+'-review'))
    if not review['timed_out'] and review['exit_code']!=0:
        raise RuntimeError('functional reviewer infrastructure failure: '+row['id'])
    return {'author':author,'method':audit if row['arm']=='T' else None,'review':review,'artifact':inventory}


def evaluate_stage(row,number,manifest,runroot):
    record=runroot/f'stage{number}'
    candidate=record/'artifact/solution'
    # Missing candidates are intentional quality outcomes, not harness failures.
    if not candidate.exists(): candidate.mkdir(parents=True)
    name='backup-eval-'+row['id'].lower()+f'-s{number}'
    argv=['docker','run','--name',name,'--network','none','--read-only','--cap-drop','ALL']
    for cap in ['SETUID','SETGID','CHOWN','KILL','DAC_OVERRIDE','FOWNER']: argv+=['--cap-add',cap]
    argv+=['--security-opt','no-new-privileges:true','--memory','768m','--cpus','1','--pids-limit','64',
           '-e','BACKUP_CANDIDATE_UID=1000',
           '--tmpfs','/work:rw,size=512m,mode=0755','--tmpfs','/tmp:rw,size=128m,mode=1777',
           '--mount',f'type=bind,src={candidate},dst=/candidate,readonly',manifest['images']['evaluator'],
           '--candidate','/candidate/backup.py','--variant',row['variant'],'--stage',str(number),
           '--seed',str(row['workload_seed']),'--workdir','/work/control']
    def task():
        receipt=command(argv,record/'evaluation',600,container=name)
        if receipt['exit_code']==0 and not receipt['timed_out']:
            result=json.loads((record/'evaluation.jsonl').read_text())
            if result.get('isolation',{}).get('candidate_uid')!=1000 or result['isolation'].get('development_only'):
                raise RuntimeError('Evaluator UID isolation did not hold')
            save(record/'evaluation.json',result)
            target=record/'evaluation-streams'; target.mkdir(exist_ok=True)
            stream_receipts=[]
            for stream in result.get('output_streams',[]):
                filename=stream['name']
                if Path(filename).name!=filename: raise RuntimeError('invalid stream filename')
                content=base64.b64decode(stream['base64'],validate=True)
                (target/filename).write_bytes(content)
                stream_receipts.append({k:v for k,v in stream.items() if k!='base64'})
            save(target/'index.json',stream_receipts)
            receipt['streams_saved']=bool(stream_receipts)
            receipt['streams_truncated']=any(s['truncated'] for s in stream_receipts)
        else:
            receipt['infrastructure_failure']=True
        subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        return receipt
    receipt=once(record/'evaluation.receipt.json',task)
    if receipt.get('infrastructure_failure'): raise RuntimeError('evaluator infrastructure failure; result not scored: '+row['id'])
    return receipt


def freeze(seed):
    target=BASE/'frozen/manifest.json'
    if target.exists(): raise RuntimeError('already frozen')
    files=[BASE/'evaluator.py',BASE/'schedule.py',BASE/'run_pilot.py',BASE/'planning/contract.md',
           BASE/'planning/protocol.md',BASE/'planning/execution-isolation.md',BASE/'planning/reviewer-neutral.txt',
           BASE/'Dockerfile.control',BASE/'Dockerfile.evaluator',schedule.ROOT/'docker/codex/seccomp-codex.json',schedule.ROOT/'.agents/skills/specorganon/SKILL.md']
    files += [schedule.ROOT/'docs'/name for name in ['metodologia.md','workflow_operativo.md','uso_local.md']]
    files += sorted((BASE/'tests').rglob('*.py'))
    files += sorted((BASE/'development/tests').glob('*.py'))
    files += [BASE/'development/reference/backup.py',BASE/'development/all-prefreeze-final-tests.txt',
              BASE/'planning/runner_review_round01.md',BASE/'planning/runner_review_round02.md']
    files += [BASE/'development'/('isolated-frozen-'+v)/'stage2/evaluation.json' for v in ['V1','V2','V3']]
    images={}
    for key,tag in [('method','specorganon-codex:local'),('control','specorganon-backup-control:dev'),('evaluator','specorganon-backup-evaluator:dev')]:
        images[key]=subprocess.check_output(['docker','image','inspect','--format','{{.Id}}',tag],text=True).strip()
    manifest={'frozen_at':now(),'seed':seed,'schedule':schedule.make_schedule(seed),'model':schedule.MODEL,
              'effort':schedule.EFFORT,'images':images,'files':{str(path):digest(path) for path in files},
              'author_seconds':schedule.AUTHOR_SECONDS,'method_seconds':schedule.METHOD_SECONDS,
              'functional_review_seconds':schedule.REVIEW_SECONDS,'account':'existing Docker named volume; no credentials copied',
              'independent_custody':False,'provider_snapshot_verified':False}
    save(target,manifest)
    print('Frozen: '+str(target),flush=True)


def campaign():
    manifest=json.loads((BASE/'frozen/manifest.json').read_text()); check_freeze(manifest)
    lock=BASE/'runs/.lock'; lock.parent.mkdir(exist_ok=True)
    # A surviving lock means inspect the process, not silently start another writer.
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    os.write(fd,str(os.getpid()).encode()); os.close(fd)
    try:
        for row in manifest['schedule']:
            root=BASE/'runs'/row['id']; root.mkdir(exist_ok=True)
            for number in [1,2]:
                check_freeze(manifest)
                print(f"{now()} generation {row['id']} stage {number}",flush=True)
                once(root/f'stage{number}/complete.json',lambda row=row,number=number,root=root:stage(row,number,manifest,root))
        print('All 36 generation stages closed; hidden evaluation begins.',flush=True)
        for row in manifest['schedule']:
            root=BASE/'runs'/row['id']
            for number in [1,2]:
                check_freeze(manifest); print(f"{now()} evaluation {row['id']} stage {number}",flush=True)
                evaluate_stage(row,number,manifest,root)
        save(BASE/'runs/complete.json',{'finished_at':now(),'runs':18,'stages':36})
    finally: lock.unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['freeze','run']); parser.add_argument('--seed',type=int,default=17863)
    args=parser.parse_args()
    if args.action=='freeze': freeze(args.seed)
    else: campaign()


if __name__=='__main__': main()
