"""Private staged N/S development controller, never an engine or external F.

Only this trusted host publishes generations. A generation is one atomic JSON
record containing the entire file/document map; no mutable delivery directory is
used. Durable reservations precede dispatch, and an interruption can only query
that exact transport job. DockerRoles' lost-receipt rule prevents re-execution.
fixture_mode is explicit and can never produce native_ready. Nine T phases and
historical registered attempts are unaffected. No comparative indicator is
inferred from this development package or its author's tests.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
import fcntl
import os
from pathlib import Path
import re
import stat
import time
import uuid

from .common_evidence import read_snapshot, validate_bound_audit
from .common_review import checklist
from .docker_roles import DockerRoles,ClosedResponseContractError,PendingCleanupError
from .native_response_contract import render_prompt, response_schema, validate_response_schema
from .neutral_author import neutral_author_content
from .role_jobs import JobStore, _safe, _read, _json, _write, _parent, canonical, digest
from .software_controller import encoded_contribution, safe_file


class NeutralControllerError(ValueError):
    pass


LIMITS={'roles':40,'build_authors':3,'authors_per_stage':2,'reviews_per_stage':2,
        'test_runs':2,'files_encoded_bytes':20000,'documents_encoded_bytes':54000,
        'test_stream_encoded_bytes':4000,'request_bytes':110000,'prompt_bytes':128000,
        'elapsed_admission_seconds':6000,'host_jobs':80}
AUTHOR_STAGES={'plan','program','tests','repair'}
BUILD_STAGES={'program','tests','repair'}
STAGES=AUTHOR_STAGES|{'plan-review','measure','audit'}


def _fingerprint(value): return digest(canonical(value))


def _clock():
    # CLOCK_BOOTTIME includes suspend and survives process restarts on this boot.
    return {'boot_id_sha256':JobStore._boot_id(),
            'host_id_sha256':digest(os.uname().nodename.encode()),
            'boottime_ns':time.clock_gettime_ns(time.CLOCK_BOOTTIME),'epoch_ns':time.time_ns()}


def _elapsed(start,end):
    if (start['boot_id_sha256']!=end['boot_id_sha256'] or start['host_id_sha256']!=end['host_id_sha256']
            or type(start['boottime_ns']) is not int or type(end['boottime_ns']) is not int
            or end['boottime_ns']<start['boottime_ns']):
        raise NeutralControllerError('attempt clock changed or became inconsistent')
    return (end['boottime_ns']-start['boottime_ns'])/1e9


class NeutralController:
    def __init__(self,root,*,attempt_id,method,contract,mandate,argv,test_file,
                 transport_policy,transport_factory,fixture_mode=False):
        if (type(attempt_id) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',attempt_id) is None
                or type(method) is not str or method not in ('N','S') or type(fixture_mode) is not bool
                or any(type(v) is not str or not v.strip() for v in (contract,mandate))
                or type(argv) is not list or not argv or len(canonical(argv))>16384
                or any(type(v) is not str or not v or '\0' in v for v in argv)
                or not argv[0].startswith('/') or type(transport_policy) is not dict
                or not callable(transport_factory)):
            raise NeutralControllerError('invalid explicit neutral controller policy')
        safe_file(test_file)
        if argv!=['/opt/specorganon/venv/bin/python','-I','-B','/input/delivery/'+test_file]:
            raise NeutralControllerError('fixed argv must be isolated Python -I -B with the original test script')
        if not fixture_mode and (transport_policy.get('schema')!=5
                or not transport_policy.get('registered_source_bindings_sha256')):
            raise NeutralControllerError('native transport needs explicitly registered sources')
        self.root=_safe(root);self.factory=transport_factory;self.transport=None
        self.fixture_mode=fixture_mode
        self.policy={'schema':1,'protocol':'staged-neutral-development-v1','attempt_id':attempt_id,
            'method':method,'contract':contract,'mandate':mandate,'argv':copy.deepcopy(argv),
            'test_file':test_file,'fixture_mode':fixture_mode,'limits':copy.deepcopy(LIMITS),
            'transport_policy':copy.deepcopy(transport_policy),
            'controller_source_sha256':digest(_read(Path(__file__),128000))}
        self.policy.update(self._policy_extra())
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        info=self.root.stat()
        if info.st_uid!=os.geteuid() or info.st_mode&0o077:
            raise NeutralControllerError('private owned mode0700 run root required')
        with self._lock():
            initial=self.root/'initial.json'
            if initial.exists():
                self.initial=_json(initial)
                if canonical(self.initial['policy'])!=canonical(self.policy):
                    raise NeutralControllerError('attempt policy changed; no silent replacement')
            else:
                if set(p.name for p in self.root.iterdir())!={'.neutral.lock'}:
                    raise NeutralControllerError('initialization uncertain; existing attempt cannot reset')
                self.initial={'schema':1,'policy':self.policy,'clock':_clock()}
                _write(initial,self.initial)
            for name in ('reservations','results','generations','snapshots'):
                (self.root/name).mkdir(exist_ok=True,mode=0o700)

    def _policy_extra(self):
        return {} # Subclasses must bind their distinct process and executable bytes.

    @contextmanager
    def _lock(self):
        fd=os.open(self.root/'.neutral.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:
                raise NeutralControllerError('invalid controller lock')
            fcntl.flock(fd,fcntl.LOCK_EX)
            named=(self.root/'.neutral.lock').lstat()
            if (named.st_ino,named.st_dev)!=(info.st_ino,info.st_dev):
                raise NeutralControllerError('controller lock replaced')
            yield
        finally:os.close(fd)

    def _get_transport(self):
        if self.transport is None:
            t=self.factory(self.root/'transport')
            if _safe(t.root)!=self.root/'transport':
                raise NeutralControllerError('transport journal must belong to this exact attempt root')
            if not self.fixture_mode and type(t) is not DockerRoles:
                raise NeutralControllerError('native controller requires the guarded Docker transport')
            if canonical(_json(t.root/'transport-policy.json'))!=canonical(self.policy['transport_policy']):
                raise NeutralControllerError('actual transport differs from frozen attempt policy')
            self.transport=t
        return self.transport

    @staticmethod
    def _initial_state():
        return {'stage':'plan','status':'running','files':{},'documents':{},'original_criteria':None,
                'original_tests':{},'counts':{'roles':0,'build_authors':0,'test_runs':0,'stages':{}},
                'history':[],'plan_accepted':False,'measure_job':None,'audit_job':None,
                'common_review_ready':False,'method_review_ready':False,'failure':None}

    def _records(self,name):
        entries=[]
        for p in sorted((self.root/name).iterdir()):
            info=p.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_uid!=os.getuid()):
                raise NeutralControllerError('unexpected controller journal entry')
            temporary=re.fullmatch(r'\.([0-9]{4})\.json\.[a-f0-9]{32}',p.name)
            if temporary and 1<=int(temporary[1])<=80:
                continue # Unpublished atomic-writer debris; never parse/promote its bytes.
            if not re.fullmatch(r'[0-9]{4}\.json',p.name):
                raise NeutralControllerError('unexpected controller journal entry')
            entries.append(p)
        if [p.name for p in entries]!=[f'{i:04d}.json' for i in range(1,len(entries)+1)]:
            raise NeutralControllerError('controller journal sequence gap')
        if len(entries)>80:raise NeutralControllerError('controller journal exceeds fixed budget')
        return entries

    def _load(self):
        if canonical(_json(self.root/'initial.json'))!=canonical(self.initial):
            raise NeutralControllerError('initial attempt record changed')
        state=self._initial_state();past=[];previous=digest(_read(self.root/'initial.json'))
        reservations=self._records('reservations');generations=self._records('generations');results=self._records('results')
        if not len(generations)<=len(results)<=len(reservations)<=len(generations)+1:
            raise NeutralControllerError('reservation/result/generation closure diverged')
        for i,path in enumerate(reservations,1):
            r=_json(path)
            if (set(r)!={'schema','sequence','previous_sha256','state_sha256','stage','job_id','counts','request','snapshot','halt'}
                    or type(r['schema']) is not int or r['schema']!=1 or type(r['sequence']) is not int or r['sequence']!=i
                    or r['previous_sha256']!=previous or r['state_sha256']!=_fingerprint(state)
                    or r['stage']!=state['stage'] or state['status']!='running'
                    or r['job_id']!=f"neutral-{i:04d}-{r['stage']}"):
                raise NeutralControllerError('reservation chain or stage diverged')
            if r['halt'] is None:
                counts=self._charged(state)
                if canonical(r['counts'])!=canonical(counts):raise NeutralControllerError('persistent counters diverged')
                req,snapshot=self._request(state,past,i)
                if canonical(req)!=canonical(r['request']) or canonical(snapshot)!=canonical(r['snapshot']):
                    raise NeutralControllerError('reserved request differs from captured stage inputs')
            elif (type(r['halt']) is not str or not r['halt'] or r['request'] is not None
                  or r['snapshot'] is not None or canonical(r['counts'])!=canonical(state['counts'])):
                raise NeutralControllerError('invalid terminal reservation')
            if i>len(generations):return state,past,previous,r
            result=_json(self.root/'results'/path.name)
            next_state=self._apply(state,r,result,past)
            generation=_json(self.root/'generations'/path.name)
            expected={'schema':1,'sequence':i,'previous_sha256':previous,
                'reservation_sha256':digest(_read(path)),
                'result_sha256':digest(_read(self.root/'results'/path.name)),'state':next_state}
            if canonical(generation)!=canonical(expected):raise NeutralControllerError('atomic generation diverged')
            previous=digest(_read(self.root/'generations'/path.name));state=next_state
            past.append({'reservation':r,'result':result,'state':copy.deepcopy(state)})
        return state,past,previous,None

    def _charged(self,state):
        stage=state['stage'];c=copy.deepcopy(state['counts'])
        key=stage;c['stages'][key]=c['stages'].get(key,0)+1
        if stage=='measure':
            c['test_runs']+=1
            if c['test_runs']>LIMITS['test_runs']:raise NeutralControllerError('own battery execution budget exhausted')
        else:
            c['roles']+=1
            ceiling=LIMITS['authors_per_stage'] if stage in AUTHOR_STAGES else LIMITS['reviews_per_stage']
            if c['roles']>LIMITS['roles'] or c['stages'][key]>ceiling:
                raise NeutralControllerError('role/stage budget exhausted')
            if stage in BUILD_STAGES:
                c['build_authors']+=1
                if c['build_authors']>LIMITS['build_authors']:raise NeutralControllerError('combined build author budget exhausted')
        return c

    def _put(self,root,name,raw):
        path=_safe(root/name);path.parent.mkdir(exist_ok=True,parents=True,mode=0o700)
        if path.exists():
            if _read(path,128000)!=raw:raise NeutralControllerError('immutable snapshot bytes changed')
        else:
            # Preserve authored bytes, including noncanonical JSON. Publish a
            # complete blob atomically; an interrupted temp is never evidence.
            parent_fd,leaf=_parent(path);temp='.'+leaf+'.'+uuid.uuid4().hex
            try:
                fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent_fd)
                with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
                os.replace(temp,leaf,src_dir_fd=parent_fd,dst_dir_fd=parent_fd);os.fsync(parent_fd)
            finally:
                try:os.unlink(temp,dir_fd=parent_fd)
                except FileNotFoundError:pass
                os.close(parent_fd)
        return {'path':name,'sha256':digest(raw)}

    def _snapshot(self,state,past,sequence):
        root=self.root/'snapshots'/f'{sequence:04d}';root.mkdir(exist_ok=True,mode=0o700)
        put=lambda name,raw:self._put(root,name,raw)
        manifest={'schema':2,'method':self.policy['method'],
            'contract':put('host/contract.txt',self.policy['contract'].encode()),
            'policy':put('host/policy.json',canonical(self.policy)),
            'delivery':{n:put('delivery/'+n,v.encode()) for n,v in state['files'].items()},
            'documents':{n:put('documents/'+n,v.encode()) for n,v in state['documents'].items()},
            'checkpoints':[],'captures':{},'receipts':{},'streams':{}}
        previous=None
        for item in past:
            cp=copy.deepcopy(item['state']['history'][-1]);cp['previous_sha256']=previous
            ref=put('checkpoints/'+cp['id']+'.json',canonical(cp))
            manifest['checkpoints'].append({'id':cp['id'],**ref});previous=ref['sha256']
            captured={'delivery':item['state']['files'],'documents':item['state']['documents']}
            sha=_fingerprint(captured)
            manifest['captures'][sha]=put('captures/'+sha+'.json',canonical(captured))
            result=item['result']
            if result['kind'] in ('role','test','response_error'):
                job=item['reservation']['job_id']
                manifest['receipts'][job]={**put('receipts/'+job+'.json',canonical(result['value'])),
                    'kind':'test' if result['kind']=='test' else 'role'}
                if result['kind']=='test':
                    for stream in ('stdout','stderr'):
                        raw=_read(self._get_transport().store.root/job/(stream+'.bin'),128000)
                        if encoded_contribution(raw.decode())>LIMITS['test_stream_encoded_bytes']:
                            raise NeutralControllerError('complete own test stream exceeds request evidence budget')
                        manifest['streams'][job+'/'+stream]=put('streams/'+job+'/'+stream+'.bin',raw)
        raw=canonical(manifest);self._put(root,'snapshot.json',raw)
        pin=digest(raw);snapshot=read_snapshot(root,pin)
        return snapshot,{'path':str(root),'manifest_sha256':pin}

    def _request(self,state,past,sequence):
        stage=state['stage']
        if stage=='measure':return {'argv':self.policy['argv'],'files':state['files']},None
        role='author' if stage in AUTHOR_STAGES else 'review'
        instructions={
            'plan':('Record substantive criteria, premises, assumptions and a strategy before programming. '
                    'Use documents only; no program or claimed execution. N chooses its own notes/structure. '
                    'S supplies SPEC.md, DESIGN.md and TASKS.md, comparing design alternatives and linking tasks. '
                    'If repairing a reviewed plan, preserve original criteria and address the supplied defects.'),
            'plan-review':('Independently review this S specification, alternatives, design and task links, '
                    'before any program. Judge substance and contract fidelity, not filenames alone. '
                    'Return schema1, verdict accept/reject/inconclusive, reason, findings objects, tests_executed=false. '
                    'This separate methodological verdict cannot reject a common D/G package by itself.'),
            'program':('Produce the complete program and README.md with environment, precise interface/bounds, '
                    'two reproducible examples including outputs, error/exit/atomicity behavior and scoped test limits. '
                    'Follow the supplied criteria/plan or document changes. Do not supply tests yet or claim execution.'),
            'tests':('The program and README are sealed. Add only NEW files for a pertinent test battery and fixtures; '
                    'never overwrite the sealed files. Supply the fixed test file invoked by the host argv. '
                    'Tests run under Python -I: use stdlib frameworks; load local program bytes by absolute '
                    'file path using runpy/importlib, never depend on sys.path or external installation. '
                    'Tests must cover the original substantive criteria, errors, atomicity and boundary cases. '
                    'No claimed test result. README corrections can only use the later shared repair budget.'),
            'repair':('One combined remaining build slot: correct program and documentation using actual defects. '
                    'The entire original test package is immutable and will run again with the same argv and policy. '
                    'Do not modify/remove its files, fixtures or configuration, or add any new files. '
                    'Preserve original criteria/notes in history, distinguish later changes, '
                    'and make no execution/F/superiority claim.'),
            'audit':('Independently audit this exact captured package using the supplied D/G/H checklist. '
                    'Check substantive truth, useful traceability, original criteria/test chronology and measured receipt scope. '
                    'D/G use the same criteria for N/S/T; judge H separately. H or root verdict never determines D/G readiness. '
                    'Use only available typed evidence locators; hashes alone do not make a semantic assertion true. '
                    'You did not execute tests. Report unknown monetary costs and incomparable provider counters honestly. '
                    'Author tests do not establish independent F. No forced verdict/status, no method-superiority claim.')
        }[stage]
        docs={'action.txt':role,'contract.txt':self.policy['contract'],'mandate.txt':self.policy['mandate'],
              'policy.json':canonical(self.policy).decode(),'stage.txt':stage,
              'fixed-test-argv.json':canonical(self.policy['argv']).decode(),
              'fixed-test-file.txt':self.policy['test_file']}
        if self.policy['protocol']=='staged-neutral-development-v1':
            charged=self._charged(state);counts=charged['stages']
            authors=(LIMITS['authors_per_stage']-counts.get('plan',0)
                     +LIMITS['build_authors']-charged['build_authors'])
            reviews=sum(LIMITS['reviews_per_stage']-counts.get(n,0) for n in ('plan-review','audit'))
            docs['remaining-budget.json']=canonical({
                'current_invocation_already_reserved':True,'charged':charged,
                'author_slots_upper_remaining':authors,'review_slots_upper_remaining':reviews,
                'effective_roles_upper_remaining':authors+reviews,
                'nominal_role_ceiling_remaining':LIMITS['roles']-charged['roles'],
                'test_runs_remaining':LIMITS['test_runs']-charged['test_runs'],
                'note':'SDD stage allocation still applies; unused prior plan slots cannot move to build.'}).decode()
        snapshot_ref=None
        if stage=='audit':
            snapshot,snapshot_ref=self._snapshot(state,past,sequence)
            declared={'schema':1,'format':'common-audit-v1','method':self.policy['method'],
                'binding':snapshot['binding'],'locators':sorted(snapshot['locators'])}
            from .common_review import declaration
            declared=declaration(declared)
            docs['review-response-format.json']=canonical(declared).decode()
            docs['checklist.json']=canonical(checklist(self.policy['method'])).decode()
            content={};index={}
            for name,raw in snapshot['locators'].items():
                sha=digest(raw);content[sha]=raw.decode();index[name]=sha
            docs['evidence.json']=canonical({'locator_index':index,'content_by_sha256':content}).decode()
        else:
            docs['current-files.json']=canonical(state['files']).decode()
            docs['current-documents.json']=canonical(state['documents']).decode()
            docs['history.json']=canonical([{'stage':i['reservation']['stage'],'job_id':i['reservation']['job_id'],
                'result':i['result'],'capture':{'files':i['state']['files'],'documents':i['state']['documents']}}
                for i in past]).decode()
        if role=='author':docs['author-response-format.json']=canonical({'schema':1,'format':'files-v1'}).decode()
        req={'schema':1,'role':role,'role_instructions':instructions,'documents':docs}
        if len(canonical(req))>LIMITS['request_bytes']:raise NeutralControllerError('exact canonical request exceeds budget')
        render_prompt(canonical(req)) # same implementation as the native bridge
        return req,snapshot_ref

    def _can_repair(self,state):
        c=state['counts']
        return (c['build_authors']<LIMITS['build_authors'] and c['roles']+2<=LIMITS['roles']
                and c['test_runs']<LIMITS['test_runs'] and c['stages'].get('audit',0)<2
                and c['stages'].get('repair',0)<2)

    def _failure(self,state,reason):
        state['status']='failed';state['failure']=reason;state['common_review_ready']=False
        state['method_review_ready']=False
        return state

    def _verify_result(self,r,result,state):
        if result['kind']=='error':return
        t=self._get_transport()
        if result['kind']=='response_error':
            if self.fixture_mode:
                if (result['value'].get('provenance')!='fixture_closed_invalid_response'
                        or result['value'].get('request_sha256')!=_fingerprint(r['request'])):
                    raise NeutralControllerError('invalid explicit closed response-error fixture')
            elif t.verify_response_failure(result['value'],r['job_id'],r['request']['role'],r['request']) is not True:
                raise NeutralControllerError('actual closed inadmissible native response proof required')
        elif result['kind']=='role':
            packet=result['value'];role=r['request']['role']
            if self.fixture_mode:
                if packet.get('provenance')!='fixture' or packet.get('request_sha256')!=_fingerprint(r['request']):
                    raise NeutralControllerError('invalid explicit fixture packet binding')
            elif t.verify_role(packet,r['job_id'],role,r['request']) is not True:
                raise NeutralControllerError('actual closed role verification required')
        elif result['kind']=='test':
            measured=result['value']
            if not self.fixture_mode and canonical(measured)!=canonical(t.recover_test(r['job_id'],self.policy['argv'],state['files'])):
                raise NeutralControllerError('captured measurement differs from actual host record')
            data={'argv':self.policy['argv'],'test_job_ref':measured['test_job_ref'],
                  'delivery_tree_sha256':_fingerprint(state['files'])}
            if t.verify_test(data,state['files'],require_passed=False,require_current=True) is not True:
                raise NeutralControllerError('actual current test receipt verification required')
        else:raise NeutralControllerError('unknown closed result kind')

    def _apply(self,state,r,result,past):
        if (type(result) is not dict or set(result)!={'schema','kind','value'}
                or type(result['schema']) is not int or result['schema']!=1
                or result['kind'] not in ('role','test','response_error','error')):
            raise NeutralControllerError('invalid closed result record')
        try:return self._apply_valid(state,r,result,past)
        except (ValueError,OSError) as exc:
            s=copy.deepcopy(state);s['counts']=copy.deepcopy(r['counts'])
            return self._failure(s,'closed package verification failed: '+type(exc).__name__+': '+str(exc))

    def _apply_valid(self,state,r,result,past):
        s=copy.deepcopy(state);s['counts']=copy.deepcopy(r['counts']);stage=r['stage']
        if result['kind']=='response_error':
            self._verify_result(r,result,state)
            if self.policy['method']=='S' and stage in ('plan','plan-review') and state['original_criteria'] is not None:
                s['stage']='program';s['plan_accepted']=False
                seq=len(s['history'])+1
                s['history'].append({'schema':1,'id':f'cp{seq:04d}','sequence':seq,'previous_sha256':None,
                    'kind':'planning' if stage=='plan' else 'review','job_id':r['job_id'],
                    'request_sha256':_fingerprint(r['request']),'delivery_sha256':_fingerprint(s['files']),
                    'documents_sha256':_fingerprint(s['documents'])})
                s['last_admission_failure']='Closed native response contract failed; previous criteria preserved, H not ready'
                return s
            return self._failure(s,'closed native response contract failed outside a recoverable S methodological branch')
        if r['halt'] is not None or result['kind']=='error':
            if result['kind']!='error' or type(result['value']) is not str:
                raise NeutralControllerError('terminal transport failure requires closed error record')
            return self._failure(s,r['halt'] or result['value'])
        expected_kind='test' if stage=='measure' else 'role'
        if result['kind']!=expected_kind:raise NeutralControllerError('stage/result role mismatch')
        self._verify_result(r,result,state)
        value=result['value'] if stage=='measure' else result['value']['result']
        admission_failure=None
        if stage in AUTHOR_STAGES:
            try:
                v=neutral_author_content(value)
                for name in v['files']:safe_file(name)
                if stage=='plan':
                    if v['files'] or not v['documents']:raise NeutralControllerError('planning requires criteria documents before code')
                elif stage=='program':
                    if self.policy['test_file'] in v['files'] or not v['files'].get('README.md','').strip() or not any(n.endswith('.py') for n in v['files']):
                        raise NeutralControllerError('program needs code/README before a separate test package')
                elif stage=='tests':
                    if (v['documents'] or set(v['files'])&set(state['files'])
                            or not v['files'].get(self.policy['test_file'],'').strip()):
                        raise NeutralControllerError('tests must add a separate complete immutable test package')
                elif (set(v['files'])-set(state['files']) or set(v['documents'])-set(state['documents'])
                      or any(name in state['original_tests'] and text!=state['original_tests'][name] for name,text in v['files'].items())):
                    raise NeutralControllerError('repair cannot add files/documents or replace original tests/fixtures/configuration')
                files={**state['files'],**v['files']};documents={**state['documents'],**v['documents']}
                if (len(files)>256 or len(documents)>256 or encoded_contribution(files)>LIMITS['files_encoded_bytes']
                        or encoded_contribution(documents)>LIMITS['documents_encoded_bytes']):
                    raise NeutralControllerError('complete candidate file/document map exceeds admission budget')
                if stage=='repair' and files==state['files'] and documents==state['documents']:
                    raise NeutralControllerError('unchanged repair consumes its slot without new verification')
                s['files']=files;s['documents']=documents
                if stage=='plan':
                    if s['original_criteria'] is None:s['original_criteria']=copy.deepcopy(documents)
                    s['stage']='plan-review' if self.policy['method']=='S' else 'program'
                elif stage=='program':s['stage']='tests'
                elif stage=='tests':s['original_tests']=copy.deepcopy(v['files']);s['stage']='measure'
                else:s['stage']='measure';s['measure_job']=None;s['audit_job']=None
            except ValueError as exc:
                admission_failure=type(exc).__name__+': '+str(exc)
                try:self._charged(s)
                except ValueError:
                    if stage=='plan' and self.policy['method']=='S' and state['original_criteria'] is not None:
                        s['stage']='program';s['plan_accepted']=False
                    else:self._failure(s,'author admission failed and accumulated budget exhausted')
        elif stage=='plan-review':
            if type(value) is not dict or type(value.get('schema')) is not int or value['schema']!=1:
                raise NeutralControllerError('review requires exact schema1')
            validate_response_schema(value,response_schema('review'))
            s['plan_accepted']=value['verdict']=='accept' and all(state['documents'].get(n,'').strip() for n in ('SPEC.md','DESIGN.md','TASKS.md'))
            if value['verdict']!='accept' and s['counts']['stages'].get('plan',0)<2:s['stage']='plan'
            else:s['stage']='program' # H-only refusal never gates common D/G
        elif stage=='measure':
            if type(value.get('passed')) is not bool:raise NeutralControllerError('measured test needs exact outcome')
            s['measure_job']=r['job_id']
            if value['passed']:s['stage']='audit'
            elif self._can_repair(s):s['stage']='repair'
            else:self._failure(s,'own execution failed; no complete repair/measurement/audit budget remains')
        else:
            snapshot=read_snapshot(r['snapshot']['path'],r['snapshot']['manifest_sha256'])
            from .ledger import strict_json_loads
            declared=strict_json_loads(r['request']['documents']['review-response-format.json'])
            def verify(name,kind,captured,_snapshot):
                item=next((i for i in past if i['reservation']['job_id']==name),None)
                if item is None or canonical(captured)!=canonical(item['result']['value']):
                    raise NeutralControllerError('snapshot receipt differs from private closed job')
                if kind!=('test' if item['reservation']['stage']=='measure' else 'role'):
                    raise NeutralControllerError('receipt provenance type diverged')
                self._verify_result(item['reservation'],item['result'],
                    {'files':item['reservation']['request']['files']} if kind=='test' else item['state'])
                return True
            validated=validate_bound_audit(snapshot,declared,value,verify_receipt=verify)
            dg=all(point['status']=='pass' for group in ('D','G') for point in validated['review']['audit'][group].values())
            # Chronology/current measurement and separate invocations are physical
            # gates; methodological H and root verdict are never dependencies.
            if (state['original_criteria'] is None or not state['original_tests'] or not state['measure_job']
                    or r['job_id']==state['measure_job'] or snapshot['delivery']!=state['files']
                    or snapshot['documents']!=state['documents']):
                raise NeutralControllerError('physical common package gates diverged')
            s['audit_job']=r['job_id']
            if dg:
                s['common_review_ready']=True;s['status']='review_ready'
                s['method_review_ready']=(self.policy['method']=='N' or state['plan_accepted'] and
                    all(p['status']=='pass' for p in value['audit']['H'].values()))
            elif self._can_repair(s):s['stage']='repair'
            else:self._failure(s,'common D/G review refused; verification resources exhausted')
        sequence=len(s['history'])+1
        kind={'plan':'criteria' if sequence==1 else 'planning','plan-review':'review','program':'delivery',
              'tests':'tests','repair':'delivery','measure':'execution','audit':'review'}[stage]
        cp={'schema':1,'id':f'cp{sequence:04d}','sequence':sequence,'previous_sha256':None,
            'kind':kind,'job_id':r['job_id'],'request_sha256':_fingerprint(r['request']),
            'delivery_sha256':_fingerprint(s['files']),'documents_sha256':_fingerprint(s['documents'])}
        s['history'].append(cp)
        # Admission defects are retained in the captured result/generation, not
        # manufactured as review or test failures, and still consume reservations.
        s['last_admission_failure']=admission_failure
        return s

    def _has_pending_launch(self,pending):
        folder=self.root/'transport/jobs'/pending['job_id']
        return ((folder/'create-attempt.json').exists() or (folder/'launch.json').exists()
                or (not self.fixture_mode and
                    (self.root/'transport/host-journal'/pending['job_id']/'started.json').exists()))

    def _cleanup_pending(self,transport,pending):
        try:
            confirmed=transport.reconcile_pending(pending['job_id'],
                'test' if pending['stage']=='measure' else pending['request']['role'],pending['request'])
            if self._has_pending_launch(pending) and confirmed is not True:
                raise PendingCleanupError('existing creation/dispatch cleanup not confirmed')
        except (ValueError,OSError) as exc:
            raise PendingCleanupError('pending cleanup not confirmed; retain exact reservation') from exc

    def step(self):
        with self._lock():
            state,past,previous,pending=self._load()
            if state['status']!='running':return self._report(state)
            if pending is None:
                seq=len(past)+1;halt=None;request=snapshot=None;counts=state['counts']
                try:
                    if _elapsed(self.initial['clock'],_clock())>=6000:raise NeutralControllerError('whole-attempt elapsed admission exhausted')
                    self._get_transport() # start clock was durably recorded before all transport preparation
                    counts=self._charged(state);request,snapshot=self._request(state,past,seq)
                except (ValueError,OSError) as exc:
                    halt=type(exc).__name__+': '+str(exc);counts=state['counts']
                pending={'schema':1,'sequence':seq,'previous_sha256':previous,'state_sha256':_fingerprint(state),
                    'stage':state['stage'],'job_id':f"neutral-{seq:04d}-{state['stage']}",
                    'counts':counts,'request':request if halt is None else None,
                    'snapshot':snapshot if halt is None else None,'halt':halt}
                _write(self.root/'reservations'/f'{seq:04d}.json',pending)
            seq=pending['sequence'];path=self.root/'results'/f'{seq:04d}.json'
            if path.exists():result=_json(path)
            else:
                try:
                    if pending['halt'] is not None:raise NeutralControllerError(pending['halt'])
                    t=self._get_transport()
                    closed=(t.recover_test(pending['job_id'],pending['request']['argv'],pending['request']['files'])
                            if pending['stage']=='measure' else
                            t.recover_role(pending['job_id'],pending['request']['role'],pending['request']))
                    if closed is not None:
                        result={'schema':1,'kind':'test' if pending['stage']=='measure' else 'role','value':closed}
                    elif _elapsed(self.initial['clock'],_clock())>=6000:
                        self._cleanup_pending(t,pending)
                        raise NeutralControllerError('whole-attempt elapsed admission exhausted; pending execution reconciled without restart')
                    elif pending['stage']=='measure':
                        measured=t.measure(pending['job_id'],pending['request']['argv'],pending['request']['files'])
                        result={'schema':1,'kind':'test','value':measured}
                    else:
                        packet=t.call(pending['job_id'],pending['request']['role'],pending['request'])
                        result={'schema':1,'kind':'role','value':packet}
                except PendingCleanupError:
                    raise # No terminal generation/cost while owned execution may still be live.
                except ClosedResponseContractError as exc:
                    result={'schema':1,'kind':'response_error','value':exc.proof}
                except (ValueError,OSError) as exc:
                    if self._has_pending_launch(pending):
                        if self.transport is None:
                            raise PendingCleanupError('transport unavailable for existing creation/dispatch; retain exact reservation') from exc
                        self._cleanup_pending(self.transport,pending)
                    result={'schema':1,'kind':'error','value':type(exc).__name__+': '+str(exc)}
                _write(path,result)
            next_state=self._apply(state,pending,result,past)
            generation={'schema':1,'sequence':seq,'previous_sha256':previous,
                'reservation_sha256':digest(_read(self.root/'reservations'/path.name)),
                'result_sha256':digest(_read(path)),'state':next_state}
            _write(self.root/'generations'/path.name,generation)
            return self._report(next_state)

    def _report(self,state):
        terminal=state['status']!='running';end=None;cost=None;clock_error=None
        path=self.root/'terminal-clock.json'
        if terminal:
            if not path.exists():_write(path,{'schema':1,'state_sha256':_fingerprint(state),'clock':_clock()})
            receipt=_json(path)
            if receipt['state_sha256']!=_fingerprint(state):raise NeutralControllerError('terminal clock differs from sealed terminal state')
            end=receipt['clock']
            try:cost=_elapsed(self.initial['clock'],end)
            except ValueError as exc:clock_error=str(exc)
        else:
            try:cost=_elapsed(self.initial['clock'],_clock())
            except ValueError as exc:clock_error=str(exc)
        return {'schema':1,'attempt_id':self.policy['attempt_id'],'method':self.policy['method'],
            'scope':'Public development controller; independent F and comparative completion not evaluated',
            'status':state['status'],'stage':state['stage'],'counts':copy.deepcopy(state['counts']),
            'common_review_ready':state['common_review_ready'] and clock_error is None,
            'method_review_ready':state['method_review_ready'] and clock_error is None,
            'native_ready':not self.fixture_mode and state['common_review_ready'] and clock_error is None,
            'fixture_mode':self.fixture_mode,'failure':state['failure'],'clock_error':clock_error,
            'whole_attempt_seconds':cost,'monetary_cost':None,'token_cost_comparability':'unknown',
            'external_F':None,'common_complete':None,'goal_achieved':False}

    def run(self):
        for _ in range(81):
            report=self.step()
            if report['status']!='running':return report
        raise NeutralControllerError('bounded controller failed to reach a terminal state')
