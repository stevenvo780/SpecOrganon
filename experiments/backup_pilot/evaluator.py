"""Deterministic external grader. Never mounted in a pilot author workspace."""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
import random
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TIMEOUT_S=20
BASE_CHECKS=('roundtrip_create','source_intact','roundtrip_verify','roundtrip_match',
             'roundtrip_list','list_empty','version_snapshots','duplicate_id_mutation',
             'invalid_ids','nonexistent_id','overlap_rejected','symlink_source',
             'symlink_dest','symlink_repo','special_files','snapshot_corruption',
             'sigkill_interrupt_intact','sigkill_recovery','symlink_snapshot')


def hash_file(path):
    sha=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''): sha.update(block)
    return sha.hexdigest()


def inventory(root):
    result={}
    if not root.exists(): return result
    for path in sorted(root.rglob('*')):
        mode=path.lstat().st_mode; name=path.relative_to(root).as_posix()
        if stat.S_ISLNK(mode): result[name]=['link',os.readlink(path)]
        elif stat.S_ISDIR(mode): result[name]=['dir']
        elif stat.S_ISREG(mode): result[name]=['file',path.stat().st_size,hash_file(path)]
        else: result[name]=['special',mode]
    return result


class Evaluator:
    def __init__(self,candidate,variant,stage,seed,workdir):
        self.candidate=Path(candidate).resolve(); self.variant=variant; self.stage=stage
        self.seed=seed; self.rng=random.Random(seed); self.workdir=workdir
        self.names=BASE_CHECKS+(('max_bytes_high','max_bytes_low') if stage==2 else ())
        self.records={}; self.critical=[]; self.receipts=[]; self.workloads=[]
        self.logs=workdir/'.receipts'; self.logs.mkdir(mode=0o700)
        self.uid=int(os.environ['BACKUP_CANDIDATE_UID']) if 'BACKUP_CANDIDATE_UID' in os.environ else None
        if self.uid is not None and os.geteuid()!=0: raise RuntimeError('root controller required for UID isolation')
        if self.uid is not None: workdir.chmod(0o711)
        self.metrics={'space':None,'create_seconds':None,'restore_seconds':None}

    def record(self,name,passed,info=None,critical=False,inconclusive=False):
        if name in self.records and not self.records[name]['passed'] and passed:
            return
        self.records[name]={'name':name,'passed':bool(passed) and not inconclusive,
                            'inconclusive':inconclusive,'info':info}
        if not passed and critical and name not in self.critical: self.critical.append(name)

    def env(self,prefix):
        return Path(tempfile.mkdtemp(prefix=prefix+'-',dir=self.workdir))

    def permit(self,root):
        if self.uid is None: return
        os.chown(root,self.uid,self.uid)
        for path in root.rglob('*'): os.chown(path,self.uid,self.uid,follow_symlinks=False)

    def spawn(self,args,root):
        self.permit(root)
        argv=[sys.executable,str(self.candidate),*map(str,args)]
        number=len(self.receipts)
        out=self.logs/f'{number:04d}.stdout'; err=self.logs/f'{number:04d}.stderr'
        stdout=out.open('wb'); stderr=err.open('wb')
        kwargs={'user':self.uid,'group':self.uid,'extra_groups':[]} if self.uid is not None else {}
        process=subprocess.Popen(argv,cwd=root,stdout=stdout,stderr=stderr,
                                 env={'PATH':os.environ.get('PATH',''),'PYTHONDONTWRITEBYTECODE':'1'},
                                 start_new_session=True,**kwargs)
        return process,argv,out,err,stdout,stderr,time.monotonic()

    def finish(self,handle,timeout=TIMEOUT_S):
        process,argv,out,err,stdout,stderr,started=handle; timed_out=False
        try: process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out=True; os.killpg(process.pid,signal.SIGKILL); process.wait()
        # A synchronous CLI must not retain writers after its parent exits.
        # Reap same-process-group descendants before reading final state/streams.
        try: os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError: pass
        stdout.close(); stderr.close()
        stdout_size=out.stat().st_size; stderr_size=err.stat().st_size
        with out.open('rb') as stream: raw=stream.read(4*1024*1024)
        with err.open('rb') as stream: error=stream.read(4096)
        try:
            value=json.loads(raw) if stdout_size<4*1024*1024 else None
        except (ValueError,UnicodeError): value=None
        receipt={'argv':argv,'exit_code':process.returncode,'timed_out':timed_out,
                 'duration_seconds':time.monotonic()-started,'stdout_sha256':hash_file(out),
                 'stderr_sha256':hash_file(err),'stdout_bytes':stdout_size,'stderr_bytes':stderr_size,
                 'result':value,'stderr':error[:4096].decode(errors='replace')}
        self.receipts.append(receipt)
        return receipt

    def run(self,args,root): return self.finish(self.spawn(args,root))
    def ok(self,result,value=None):
        return (result['exit_code']==0 and not result['timed_out']
                and type(result['result']) is dict and (value is None or result['result']==value))
    def create(self,root,src,repo,identifier,extra=()):
        before=inventory(Path(src))
        result=self.run(['create','--source',src,'--repo',repo,'--id',identifier,*extra],root)
        changed=inventory(Path(src))!=before
        self.record('source_intact',not changed,critical=changed)
        return result
    def verify(self,root,repo,identifier):
        return self.run(['verify','--repo',repo,'--id',identifier],root)
    def restore(self,root,repo,identifier,dest):
        return self.run(['restore','--repo',repo,'--id',identifier,'--dest',dest],root)

    def tree(self,src):
        src.mkdir(); (src/'vacío').mkdir(); (src/'nested').mkdir()
        (src/'zero-byte').write_bytes(b'')
        count={'V1':5,'V2':9,'V3':13}[self.variant]
        for index in range(count):
            (src/('nested' if index%2 else '')/f'α space {index}.bin').write_bytes(self.rng.randbytes(256+index*19))
        self.workloads.append(inventory(src))
        return inventory(src)

    def roundtrip(self):
        root=self.env('roundtrip'); src=root/'source'; repo=root/'repo'; repo.mkdir()
        before=self.tree(src)
        listed=self.run(['list','--repo',repo],root)
        self.record('list_empty',self.ok(listed,{'snapshots':[]}))
        created=self.create(root,src,repo,'round-1')
        self.record('roundtrip_create',self.ok(created,{'id':'round-1'}),created)
        self.record('source_intact',inventory(src)==before,critical=inventory(src)!=before)
        if not self.ok(created): return
        # A backup must be independent of its original source location.
        src.rename(root/'source-unavailable')
        verified=self.verify(root,repo,'round-1')
        self.record('roundtrip_verify',self.ok(verified,{'id':'round-1','valid':True}),verified)
        dest=root/'dest'; restored=self.restore(root,repo,'round-1',dest)
        self.record('roundtrip_match',self.ok(restored,{'id':'round-1'}) and inventory(dest)==before,restored)
        listed=self.run(['list','--repo',repo],root)
        self.record('roundtrip_list',self.ok(listed,{'snapshots':['round-1']}),listed)
        self.metrics.update(space=sum(p.stat().st_size for p in repo.rglob('*') if p.is_file() and not p.is_symlink()),
                            create_seconds=created['duration_seconds'],restore_seconds=restored['duration_seconds'])

    def versions(self):
        root=self.env('versions'); src=root/'source'; repo=root/'repo'; self.tree(src)
        expected={}; success=True
        for index in range(3):
            (src/'version').write_bytes(self.rng.randbytes(128))
            if index==0: (src/'removed-later').write_bytes(b'present')
            if index==2: (src/'removed-later').unlink()
            expected[f'v{index}']=inventory(src)
            result=self.create(root,src,repo,f'v{index}'); success=success and self.ok(result,{'id':f'v{index}'})
        src.rename(root/'source-unavailable')
        for identifier,state in expected.items():
            dest=root/f'dest-{identifier}'; result=self.restore(root,repo,identifier,dest)
            success=success and self.ok(result,{'id':identifier}) and inventory(dest)==state
        listed=self.run(['list','--repo',repo],root)
        success=success and self.ok(listed,{'snapshots':['v0','v1','v2']})
        self.record('version_snapshots',success)

    def rejections(self):
        root=self.env('rejections'); src=root/'source'; repo=root/'repo'; self.tree(src)
        initial=self.create(root,src,repo,'existing'); before=inventory(repo)
        duplicate=self.create(root,src,repo,'existing')
        mutated=inventory(repo)!=before
        self.record('duplicate_id_mutation',self.ok(initial) and duplicate['exit_code']!=0 and not mutated,critical=mutated)
        invalid=True
        for identifier in ['-bad','../escape','a!b','x'*65,'']:
            result=self.create(root,src,repo,identifier); invalid=invalid and result['exit_code']!=0 and inventory(repo)==before
        self.record('invalid_ids',invalid)
        missing=self.verify(root,repo,'missing'); missing_restore=self.restore(root,repo,'missing',root/'dest')
        self.record('nonexistent_id',missing['exit_code']!=0 and missing_restore['exit_code']!=0 and inventory(repo)==before)
        dest=root/'protected'; dest.mkdir(); (dest/'precious').write_bytes(b'preserve')
        state=inventory(dest); rejected=self.restore(root,repo,'existing',dest); changed=inventory(dest)!=state
        # Kept as its own critical flag; fixed denominator includes this requirement.
        self.record('dest_protected',self.ok(initial) and rejected['exit_code']!=0 and not changed,critical=changed)

    def boundaries(self):
        root=self.env('boundaries'); src=root/'source'; self.tree(src)
        src_before=inventory(src); outcomes=[]
        for repo in [src,src/'nested-repo',root]:
            outcomes.append(self.create(root,src,repo,'overlap')['exit_code']!=0)
        self.record('overlap_rejected',all(outcomes) and inventory(src)==src_before)
        outside=root/'outside'; outside.mkdir(); (outside/'precious').write_bytes(b'keep')
        preserved=inventory(outside); repo=root/'repo'
        (src/'link').symlink_to(outside,target_is_directory=True)
        res=self.create(root,src,repo,'linked')
        changed=inventory(outside)!=preserved
        self.record('symlink_source',res['exit_code']!=0 and not changed,critical=changed)
        (src/'link').unlink()
        link_repo=root/'repo-link'; link_repo.symlink_to(outside,target_is_directory=True)
        res=self.create(root,src,link_repo,'linked')
        changed=inventory(outside)!=preserved
        self.record('symlink_repo',res['exit_code']!=0 and not changed,critical=changed)
        created=self.create(root,src,repo,'good')
        dest=root/'dest-link'; target=root/'empty'; target.mkdir(); dest.symlink_to(target,target_is_directory=True)
        res=self.restore(root,repo,'good',dest)
        changed=bool(inventory(target))
        self.record('symlink_dest',self.ok(created) and res['exit_code']!=0 and not changed,critical=changed)
        os.mkfifo(src/'pipe')
        res=self.create(root,src,root/'special-repo','special')
        self.record('special_files',res['exit_code']!=0 and not res['timed_out'])

    def snapshot_links(self):
        root=self.env('snapshot-links'); src=root/'source'; repo=root/'repo'; self.tree(src)
        created=self.create(root,src,repo,'linked')
        if not self.ok(created): return
        src.rename(root/'source-unavailable')
        files=sorted(p for p in repo.rglob('*') if p.is_file() and not p.is_symlink())
        if not files: self.record('symlink_snapshot',False,'no stored regular files'); return
        # Identical external bytes prevent checksum rejection from hiding link following.
        target=files[0]; external=root/'external'; external.mkdir()
        payload=external/'same-bytes'; shutil.copyfile(target,payload); original=inventory(external)
        target.unlink(); target.symlink_to(payload)
        verified=self.verify(root,repo,'linked'); restored=self.restore(root,repo,'linked',root/'dest')
        changed=inventory(external)!=original
        self.record('symlink_snapshot',verified['exit_code']!=0 and restored['exit_code']!=0 and not changed,
                    {'verify':verified,'restore':restored},critical=changed)

    def corruption(self):
        root=self.env('corruption'); src=root/'source'; repo=root/'repo'; state=self.tree(src)
        result=self.create(root,src,repo,'corrupt')
        if not self.ok(result): return
        src.rename(root/'source-unavailable')
        files=sorted(p.relative_to(repo) for p in repo.rglob('*') if p.is_file() and not p.is_symlink())
        if not files:
            self.record('snapshot_corruption',False,'No payload files found'); return
        selected=files if len(files)<=32 else self.rng.sample(files,32)
        failures=[]; detected=0
        for index,relative in enumerate(selected):
            trial=root/f'copy-{index}'; shutil.copytree(repo,trial)
            target=trial/relative; raw=target.read_bytes()
            target.write_bytes(bytes([raw[0]^0xFF])+raw[1:] if raw else b'changed')
            verified=self.verify(root,trial,'corrupt')
            dest=root/f'restore-{index}'; restored=self.restore(root,trial,'corrupt',dest)
            if verified['exit_code']!=0:
                detected+=1
                if restored['exit_code']==0: failures.append({'file':str(relative),'reason':'restore accepted after detected corruption'})
            elif not self.ok(verified,{'id':'corrupt','valid':True}):
                failures.append({'file':str(relative),'reason':'malformed verify success'})
            elif not self.ok(restored,{'id':'corrupt'}) or inventory(dest)!=state:
                failures.append({'file':str(relative),'reason':'verify falsely asserted intact data'})
            # Mutation of an incidental lock or nonessential index is harmless only
            # if verify and exact restoration still agree; it cannot hide bad bytes.
        incomplete=len(files)>32
        self.record('snapshot_corruption',not failures and detected>0 and not incomplete,
                    {'mutations':len(selected),'detected':detected,'failures':failures},
                    critical=bool(failures),inconclusive=incomplete and not failures)

    def crash(self):
        root=self.env('crash'); src=root/'source'; repo=root/'repo'; before=self.tree(src)
        initial=self.create(root,src,repo,'previous')
        if not self.ok(initial): return
        large=src/'large.bin'
        with large.open('wb') as stream:
            for _ in range(64): stream.write(self.rng.randbytes(1024*1024))
        expected=inventory(src)
        self.workloads.append({'crash_sha256':expected['large.bin'][2]})
        handle=self.spawn(['create','--source',src,'--repo',repo,'--id','interrupted'],root)
        process=handle[0]; observed=False; original_paths=set(repo.rglob('*')); deadline=time.monotonic()+10
        while process.poll() is None and time.monotonic()<deadline:
            new=list(set(repo.rglob('*'))-original_paths)
            try: observed=any(p.is_file() and p.stat().st_size>0 for p in new)
            except FileNotFoundError: observed=False
            if observed:
                os.killpg(process.pid,signal.SIGKILL); break
            time.sleep(0.005)
        result=self.finish(handle,timeout=1)
        killed=observed and result['exit_code']==-signal.SIGKILL
        if not killed:
            for name in ['sigkill_interrupt_intact','sigkill_recovery']:
                self.record(name,False,{'reason':'no live write window observed','receipt':result},inconclusive=True)
            return
        verified=self.verify(root,repo,'previous'); dest=root/'previous-restored'; restored=self.restore(root,repo,'previous',dest)
        intact=self.ok(verified,{'id':'previous','valid':True}) and self.ok(restored) and inventory(dest)==before
        self.record('sigkill_interrupt_intact',intact,result,critical=not intact)
        listed=self.run(['list','--repo',repo],root)
        if self.ok(listed) and 'interrupted' in listed['result'].get('snapshots',[]):
            verify_new=self.verify(root,repo,'interrupted'); dest2=root/'published-restored'
            restore_new=self.restore(root,repo,'interrupted',dest2)
            recovered=self.ok(verify_new,{'id':'interrupted','valid':True}) and self.ok(restore_new) and inventory(dest2)==expected
        else:
            retry=self.create(root,src,repo,'interrupted'); verify_new=self.verify(root,repo,'interrupted')
            dest2=root/'retry-restored'; restore_new=self.restore(root,repo,'interrupted',dest2)
            recovered=self.ok(retry,{'id':'interrupted'}) and self.ok(verify_new,{'id':'interrupted','valid':True}) and self.ok(restore_new) and inventory(dest2)==expected
        self.record('sigkill_recovery',recovered,critical=not recovered)

    def quota(self):
        root=self.env('quota'); src=root/'source'; repo=root/'repo'; self.tree(src)
        high=self.create(root,src,repo,'high',['--max-bytes','1048576'])
        count=sum(p.stat().st_size for p in repo.rglob('*') if p.is_file() and not p.is_symlink()) if repo.exists() else 0
        self.record('max_bytes_high',self.ok(high,{'id':'high'}) and 0<count<=1048576,high)
        before=inventory(repo); low=self.create(root,src,repo,'low',['--max-bytes','1'])
        unchanged=inventory(repo)==before
        verified=self.verify(root,repo,'high')
        self.record('max_bytes_low',self.ok(high) and low['exit_code']!=0 and unchanged and self.ok(verified,{'id':'high','valid':True}),low,critical=not unchanged)

    def evaluate(self):
        # Always retain all requirements in the denominator, including unmet
        # prerequisites and inconclusive crash windows.
        if not self.candidate.is_file():
            for name in (*self.names,'dest_protected'): self.record(name,False,'candidate missing')
            self.critical.append('candidate_exists')
        for check in ([] if not self.candidate.is_file() else [self.roundtrip,self.versions,self.rejections,self.boundaries,self.snapshot_links,self.corruption,self.crash]+([self.quota] if self.stage==2 else [])):
            # Independent streams keep repository-layout sampling from changing later inputs.
            self.rng=random.Random(f"{self.seed}:{self.variant}:{check.__name__}")
            try: check()
            except (OSError,ValueError,KeyError,TypeError) as error:
                self.receipts.append({'test_section':check.__name__,'error':repr(error)})
        names=(*self.names,'dest_protected')
        for name in names:
            if name not in self.records: self.record(name,False,'prerequisite failed or check could not execute')
        details=[self.records[name] for name in names]
        passed=sum(d['passed'] for d in details)
        streams=[]; remaining=8*1024*1024
        for path in sorted(self.logs.iterdir()):
            limit=min(65536,remaining)
            with path.open('rb') as stream: content=stream.read(limit)
            remaining-=len(content)
            streams.append({'name':path.name,'size':path.stat().st_size,'sha256':hash_file(path),
                            'truncated':path.stat().st_size>len(content),
                            'base64':base64.b64encode(content).decode('ascii')})
        return {'output_streams':streams,'score':passed/len(details),'checks_passed':passed,'checks_total':len(details),
                'inconclusive':any(d['inconclusive'] for d in details),'critical_failures':self.critical,
                'metrics':self.metrics,'details':details,'receipts':self.receipts,
                'workload_sha256':hashlib.sha256(json.dumps(self.workloads,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
                'isolation':{'candidate_uid':self.uid,'development_only':self.uid is None}}


def evaluate(candidate:Path,variant='V1',stage=1,seed=42,workdir=None):
    if variant not in {'V1','V2','V3'} or stage not in {1,2}: raise ValueError('invalid variant/stage')
    if workdir is None:
        with tempfile.TemporaryDirectory(prefix='backup-eval-') as directory:
            return Evaluator(candidate,variant,stage,seed,Path(directory)).evaluate()
    root=Path(workdir); root.mkdir(parents=True,exist_ok=True)
    return Evaluator(candidate,variant,stage,seed,root).evaluate()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path,required=True); parser.add_argument('--variant',default='V1')
    parser.add_argument('--stage',type=int,default=1); parser.add_argument('--seed',type=int,default=42)
    parser.add_argument('--output',type=Path); parser.add_argument('--workdir',type=Path)
    args=parser.parse_args(); result=evaluate(args.candidate,args.variant,args.stage,args.seed,args.workdir)
    body=json.dumps(result,indent=2,ensure_ascii=False)+'\n'
    if args.output: args.output.write_text(body)
    else: print(body)


if __name__=='__main__': main()
