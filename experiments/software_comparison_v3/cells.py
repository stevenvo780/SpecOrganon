"""Prospective N/S/T/A execution candidates. No registration/admission CLI yet.

Reuse existing replay/sealed-program controller mechanics without reopening old
campaigns. Typed A drafts retain versions/refs, with no intermediate reviews or
acceptance/advance events. Native final assertions require separate verification.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
import json
import fcntl
import os
from pathlib import Path
import re
import sys

from specorganon import engine
from specorganon.docker_roles import DockerRoles, DockerRoleError
from specorganon.report import case_report
from specorganon.runner import describe_task
from specorganon.role_jobs import canonical, digest, _read, _json, _write, _safe, UncertainJob
from specorganon.software_controller import Controller, ControllerError, encoded_contribution, safe_file
from specorganon.workflow import PHASES
from scripts.controller_native_role import render_prompt, validate_result, NativeRoleError
from scripts.study_cell_budget import CellBudget, StudyBudgetError
from experiments.software_comparison_v3.budget import BudgetError
from experiments.software_comparison_v3.rubric import rubric as rubric_definition, validate_response
from experiments.software_comparison_v3.reserved import TASK_FILES
from specorganon.artifact_guidance import phase_guidance, data_contract


class StudyHarnessError(ValueError):
    pass


def audit_documents(method, contract, files, history):
    binding={'contract_sha256':digest(contract.encode()),'delivery_sha256':digest(canonical(files)),
             'history_sha256':digest(canonical(history))}
    return {'audit-binding.json':canonical(binding).decode(),
            'audit-rubric.json':canonical(rubric_definition(method)).decode(),
            'audit-history.json':canonical(history).decode()}


def audit_instructions():
    return (' Additionally include audit={schema:1,binding:EXACT audit-binding.json,D:{d1..d8},G:{g1..g6},'
            'H:EXACT IDs of audit-rubric.json.H,reason:nonempty,tests_executed:false}. '
            'Each checklist point={status:pass/fail/inconclusive,reason:concrete nonempty,evidence:[locators]}. '
            'For pass supply concrete document#/JSONpointer locators to existing supplied evidence. '
            'Plain text documents can use document# with empty pointer. This native audit is method-aware. '
            'Assess substantive reasoning/alternatives/current traces, not just shapes or filenames. '
            'No new tests, reserved feedback, compensating totals or field-effect claim.')


def common_request(role, contract, documents, instructions):
    value = {'schema':1,'role':role,'role_instructions':instructions,
             'documents':{'contract.md':contract, **documents}}
    render_prompt(canonical(value))
    return value


class BasicCell:
    """N/S/A routes, with common sealed code/tests and one final review."""
    def __init__(self, root, transport, *, method, task, contract, sdd_guide,
                 protocol_sha256, fixture_mode=False, rubric='', mandate=''):
        if method not in {'N','S','A'} or task not in set(TASK_FILES):
            raise StudyHarnessError('unsupported basic route')
        self.root = _safe(root); self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.transport = transport; self.method = method; self.task = task
        self.contract = contract; self.sdd = sdd_guide; self.fixture = fixture_mode
        self.rubric=rubric; self.mandate=mandate
        policy = {'schema':3,'method':method,'task':task,'contract_sha256':digest(contract.encode()),
                  'sdd_sha256':digest(sdd_guide.encode()),'protocol_sha256':protocol_sha256,
                  'rubric_sha256':digest(rubric.encode()),'mandate_sha256':digest(mandate.encode()),
                  'fixture_mode':fixture_mode}
        with self._lock():
            path = self.root/'policy.json'
            if path.exists() and _json(path) != policy: raise StudyHarnessError('cell binding changed')
            if not path.exists(): _write(path, policy)
            if not (self.root/'progress.json').exists():
                stages = []
                if method == 'S': stages = ['spec','design','tasks']
                if method == 'A': stages = [p.id for p in PHASES if p.id not in {'build','validate'}]
                stages += ['program','tests','measure']
                if method == 'A': stages += ['validate']
                if method == 'S': stages += ['verification']
                stages += ['final-review']
                _write(self.root/'progress.json', {'schema':1,'stages':stages,'index':0,
                    'history':[],'process':{},'files':{},'measurements':[],'argv':None,'complete':False,'candidate_items':{},'program_id':None,'test_id':None})

    @contextmanager
    def _lock(self):
        fd = os.open(self.root/'.lock', os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW, 0o600)
        try: fcntl.flock(fd, fcntl.LOCK_EX); yield
        finally: os.close(fd)

    def _request(self, state, stage):
        docs = {'process-documents.json':canonical(state['process']).decode(),
                'delivery-files.json':canonical(state['files']).decode(),
                'public-measurements.json':canonical(state['measurements']).decode(),
                'stage.txt':stage}
        if not self.fixture:
            for number, result in enumerate(state['measurements']):
                streams = {}
                for name in ('stdout','stderr'):
                    raw = _read(Path(result['test_job_ref']).parent/(name+'.bin'),2_097_152)
                    if digest(raw)!=result[name+'_sha256']:
                        raise StudyHarnessError('public measured stream changed')
                    text=raw.decode(errors='replace')
                    if encoded_contribution(text)>4000:
                        raise StudyHarnessError('common public stream input ceiling')
                    streams[name]=text
                docs['public-streams-'+str(number)+'.json']=canonical(streams).decode()
        instructions = ('Return schema=1, manifest={schema:1,steps:[]}, files={relative_path:complete_text}, '
            'reason. No approvals, engine mutations, claimed tests or reserved feedback. '
            'Only supplied actual measurements support execution claims. '
            'Code/files map has <=20000 encoded bytes; process <=6elements/6000 double-JSON-encoded bytes per complete stored stage map; include metadata/escape room. ')
        if stage == 'spec':
            docs['sdd-guide.md'] = self.sdd
            instructions += 'Before any code, return only SPEC.md with identified requirements/criteria from the fixed SDD guide.'
        elif stage in {'design','tasks'}:
            docs['sdd-guide.md'] = self.sdd
            instructions += 'Before code return only '+stage.upper()+'.md, following the fixed SDD guide and already sealed prerequisite documents.'
        elif stage == 'verification':
            docs['sdd-guide.md'] = self.sdd
            instructions += 'Return only VERIFY.md, judging supplied actual measurements against prespecified criteria and retaining failures/uncertainty.'
        elif stage in {p.id for p in PHASES}:
            phase = next(p for p in PHASES if p.id == stage)
            docs['phase-contract.json'] = canonical(phase.__dict__).decode()
            instructions += ('Ablation: propose substantive current phase reasoning as '+stage+'.md. '
                'Earlier documents are unaccepted drafts; no intermediate review or engine gate operates. '
                'Do not invent accepted phases, approvals, measurements or effects. '
                'Only return this markdown document. Explain assumptions, alternatives, trace links and limits as applicable.')
        elif stage == 'program':
            instructions += ('Return the complete '+TASK_FILES[self.task]+' and README.md, optional standard-library helpers, '
                'no test files yet. README >=200 characters with installation, both public examples, formats/errors/limits/test command. '
                'For N the work process is your choice; optional process notes may be included in manifest.process_notes as text. '
                'For S follow the sealed SDD documents; for A follow your phase drafts. Do not change the public contract.')
        elif stage == 'tests':
            instructions += ('Program/README are sealed. Return ONLY new test_*.py files, using standard library unittest. '
                'Pertinent tests should detect plausible defects and exercise examples, limits and errors. '
                'Add manifest.test_argv as a nonempty explicit vector starting /opt/specorganon/venv/bin/python, '
                'delivery at /input/delivery readonly; /tmp scratch permitted. No invented passed/receipt.')
        elif stage == 'repair':
            instructions += ('The supplied first measurement actually failed. Return the COMPLETE changed delivery map '
                'and manifest.test_argv. Repair within contract; change executable Python bytes/argv before the second test. '
                'Original process documents remain sealed; explain deviations in reason. No third execution.')
        elif stage == 'final-review':
            docs.pop('process-documents.json')
            docs.pop('public-measurements.json')
            docs['process-locator.txt']='audit-history.json#/process'
            docs['public-measurements-locator.txt']='audit-history.json#/measurements'
            docs['method.txt']=self.method
            docs['assessment-rubric.md']=self.rubric
            if self.method=='S': docs['sdd-guide.md']=self.sdd
            if self.method=='A': docs['phase-contracts.json']=canonical([p.__dict__ for p in PHASES]).decode()
            instructions = ('Independent FINAL review, once, no repairs afterwards. Judge public contract, delivery, '
                'substantive process adherence and only actual supplied public tests. Return schema=1, '
                'verdict accept/reject/inconclusive, nonempty reason, findings as array of nonempty objects, '
                'tests_executed=false. No reserved tests, expected outputs or results are supplied. '
                'Do not infer field benefits, comparative superiority or accepted engine phases from these files.')
            docs.update(audit_documents(self.method,self.contract,state['files'],{'process':state['process'],'candidate_items':state['candidate_items'],'history':state['history'],'measurements':state['measurements']}))
            instructions += audit_instructions()
        if self.method=='A' and stage!='final-review':
            docs,instructions=self._candidate_request(state,stage,docs,instructions)
        return common_request('review' if stage == 'final-review' else 'author', self.contract, docs, instructions)

    def _audit_binding(self,state):
        history={'process':state['process'],'candidate_items':state['candidate_items'],
                 'history':[h for h in state['history'] if h['stage']!='final-review'],
                 'measurements':state['measurements']}
        return json.loads(audit_documents(self.method,self.contract,state['files'],history)['audit-binding.json'])

    def _candidate_request(self,state,stage,docs,instructions):
        phase='build' if stage in {'program','tests','repair'} else stage
        docs['state.json']=canonical({'items':state['candidate_items']}).decode()
        docs['artifact-data-contract.json']=canonical(data_contract()).decode()
        docs['artifact-format-guidance.txt']=phase_guidance(phase)
        docs['phase-contract.json']=canonical(next(p.__dict__ for p in PHASES if p.id==phase)).decode()
        docs['existing-mandate.md']=self.mandate
        docs['resource-accounting.json']=canonical(Controller._resource_accounting(None,{'items':state['candidate_items']},state['files'])).decode()
        instructions=('Ablation: current '+phase+' candidate phase, no intermediate reviews/approval gates or acceptance/advance. '
            'Return schema=1, manifest={schema:1,steps:[puts only]}, files={relative_path:complete_text}, reason. '
            'Each put has op=put,id,kind,text,refs:[existing current IDs],data, optional expected_version/expected_deps. '
            'Use substantive artifact-format-guidance and data contract. Trace current prerequisites with real versions. '
            'No fabricated passed/receipt/test_job_ref or effects. 6items/6000double-encoded bytes per complete STORED phase '
            'including metadata/deps/versions; files total<=20000double-encoded bytes. resource-accounting.json is current costs. '
            'Earlier artifacts are unaccepted candidates. Choices are technically delegated under supplied owner mandate. ')
        if stage=='program':
            instructions+='Build program: one NEW implementation put; complete '+TASK_FILES[self.task]+' and README>=200characters, no tests yet.'
        elif stage=='tests':
            instructions+='Build tests: only new test_*.py files, one NEW test draft with explicit absolute argv starting /opt/specorganon/venv/bin/python; update SAME implementation ID with refs to test. Program/README stay byte-identical.'
        elif stage=='repair':
            instructions+='Actual first test failed: only SAME implementation/test IDs; COMPLETE changed delivery map and changed executable bytes/argv. No third execution. Original candidate history remains.'
        else:
            instructions+='Only current phase puts; no delivery files. Use supplied actual public measurements for validation; documentary/assumed evidence must be labeled accurately.'
        return docs,instructions

    def _apply_candidate(self,state,stage,packet,response):
        phase='build' if stage in {'program','tests','repair'} else stage
        pending={'source_state':{'items':state['candidate_items']},'source_files':state['files'],
                 'phase':phase,'repair_after_rejection':stage=='repair'}
        manifest=Controller._author_manifest(None,pending,response)
        steps=manifest['steps']; files=response['files']; items=copy.deepcopy(state['candidate_items'])
        if stage=='program':
            if (len(steps)!=1 or steps[0]['kind']!='implementation' or steps[0]['id'] in items
                    or TASK_FILES[self.task] not in files or len(files.get('README.md','').strip())<200
                    or any(Path(n).name.startswith('test_') for n in files)):
                raise StudyHarnessError('A program needs sole new implementation and sealed program/README')
            program_id=steps[0]['id'];test_id=state['test_id'];candidate={**state['files'],**files}
        elif stage=='tests':
            impl=[s for s in steps if s['kind']=='implementation'];tests=[s for s in steps if s['kind']=='test']
            if (len(steps)!=2 or len(impl)!=1 or len(tests)!=1 or impl[0]['id']!=state['program_id']
                    or tests[0]['id'] in items or tests[0]['id'] not in impl[0]['refs'] or not files
                    or any(not Path(n).name.startswith('test_') or not n.endswith('.py') for n in files)
                    or files.keys() & state['files'].keys()):
                raise StudyHarnessError('A tests need sole new test and SAME implementation, program sealed')
            program_id=state['program_id'];test_id=tests[0]['id'];candidate={**state['files'],**files}
        elif stage=='repair':
            if (len(steps)!=2 or {s['id'] for s in steps}!={state['program_id'],state['test_id']}
                    or {s['kind'] for s in steps}!={'implementation','test'} or TASK_FILES[self.task] not in files
                    or not any(Path(n).name.startswith('test_') and n.endswith('.py') for n in files)
                    or len(files.get('README.md','').strip())<200):
                raise StudyHarnessError('A repair needs sole SAME implementation/test IDs and full delivery')
            program_id=state['program_id'];test_id=state['test_id'];candidate=files
        else:
            if files: raise StudyHarnessError('A candidate phase cannot write executable files')
            program_id=state['program_id'];test_id=state['test_id'];candidate=state['files']
        for step in steps:
            old=items.get(step['id'])
            if old is not None and old['kind'] != step['kind']:
                raise StudyHarnessError('A artifact identity cannot change kind or erase an earlier phase')
            items[step['id']]={'id':step['id'],'kind':step['kind'],'text':step['text'].strip(),
                'data':step['data'],'deps':step['expected_deps'],'version':step['expected_version']+1,
                'author':packet['actor'],'seq':sum(h['stage']!='final-review' for h in state['history'])+1,
                'status':'candidate'}
        Controller._limits(None,{'items':items},candidate)
        if stage in {'tests','repair'}:
            argv=items[test_id]['data']['argv']
            if argv[0]!='/opt/specorganon/venv/bin/python':raise StudyHarnessError('A explicit bounded Python test argv required')
            state['argv']=argv
        state['candidate_items']=items;state['files']=candidate;state['program_id']=program_id;state['test_id']=test_id

    def _apply(self, state, stage, packet):
        if packet.get('provenance') != ('synthetic' if self.fixture else 'native'):
            raise StudyHarnessError('actual isolated role provenance required')
        response = validate_result(packet['result'], 'review' if stage=='final-review' else 'author')
        if stage == 'final-review':
            audit=validate_response(response.get('audit'),self.method,self._audit_binding(state))
            _write(self.root/'assessment.json',audit)
            state['final_review'] = response; state['complete'] = True
            return
        if self.method == 'A':
            self._apply_candidate(state,stage,packet,response)
            return
        allowed={'schema','steps'}
        if stage in {'tests','repair'}: allowed.add('test_argv')
        if self.method=='N' and stage=='program': allowed.add('process_notes')
        if (type(response['manifest'].get('schema')) is not int or response['manifest'].get('schema') != 1
                or response['manifest'].get('steps') != [] or set(response['manifest'])-allowed):
            raise StudyHarnessError('basic route cannot apply engine steps or approvals')
        files = response['files']
        for name in files: safe_file(name)
        if stage not in {'program','tests','repair'}:
            expected = {'SPEC.md'} if stage=='spec' else ({stage.upper()+'.md'} if stage in {'design','tasks'} else {'VERIFY.md'} if stage=='verification' else {stage+'.md'})
            if set(files) != expected or any(not text.strip() for text in files.values()):
                raise StudyHarnessError('process stage files changed or missing')
            if encoded_contribution(files) > 6000:
                raise StudyHarnessError('process stage byte ceiling')
            state['process'].update(files)
        else:
            if stage=='program':
                if (TASK_FILES[self.task] not in files or len(files.get('README.md','').strip())<200
                        or any(Path(n).name.startswith('test_') for n in files)):
                    raise StudyHarnessError('program/README required before tests')
                notes = response['manifest'].get('process_notes')
                if notes is not None:
                    if self.method!='N' or type(notes) is not str or encoded_contribution({'free-process.txt':notes})>6000:
                        raise StudyHarnessError('invalid optional free-process notes')
                    state['process']['free-process.txt'] = notes
                candidate = files
            elif stage=='tests':
                if (not files or any(not Path(n).name.startswith('test_') or not n.endswith('.py') for n in files)
                        or files.keys() & state['files'].keys()):
                    raise StudyHarnessError('tests cannot replace sealed program/README')
                candidate = {**state['files'], **files}
            else:
                if (TASK_FILES[self.task] not in files or len(files.get('README.md','').strip())<200
                        or not any(Path(n).name.startswith('test_') and n.endswith('.py') for n in files)):
                    raise StudyHarnessError('repair needs complete delivery')
                candidate = files
            if encoded_contribution(candidate)>20000: raise StudyHarnessError('common delivery byte ceiling')
            if stage in {'tests','repair'}:
                argv = response['manifest'].get('test_argv')
                if (type(argv) is not list or not argv or argv[0]!='/opt/specorganon/venv/bin/python'
                        or any(type(v) is not str or not v or '\0' in v for v in argv)):
                    raise StudyHarnessError('bounded explicit public test argv required')
                state['argv'] = argv
            state['files'] = candidate
        if stage not in {'program','tests','repair'} and (len(files)>6 or encoded_contribution(files)>6000):
            raise StudyHarnessError('common stage six-element/6000byte ceiling')
        if encoded_contribution(state['process'])>54000:
            raise StudyHarnessError('common process document ceiling')

    def _step(self):
        with self._lock():
            state = _json(self.root/'progress.json')
            if state.get('terminal_failure'):
                return {'action':'failed','complete':False,'failure':state['terminal_failure']}
            if state['complete']:
                self.validate_closed(state)
                return {'action':'complete','classification':'synthetic' if self.fixture else 'native-cell'}
            stage = state['stages'][state['index']]
            job_id = 'step-'+str(state['index']+1).zfill(2)+'-'+stage
            # Input snapshot is durable before dispatch. Closed transport packets
            # are replayed on recovery; no new job ID is allocated for failures.
            if stage=='measure':
                result = self.transport.measure(job_id, state['argv'], state['files'])
                self.transport.verify_test({'test_job_ref':result['test_job_ref'],'argv':state['argv']},
                                           state['files'],require_passed=False)
                state['measurements'].append(result)
                if not result['passed'] and len(state['measurements'])==1:
                    state['stages'][state['index']+1:state['index']+1] = ['repair','measure']
                packet_sha = digest(canonical(result))
            else:
                request = self._request(state, stage)
                path = self.root/(job_id+'-request.json')
                if path.exists() and _json(path)!=request: raise StudyHarnessError('prepared request changed')
                if not path.exists(): _write(path,request)
                packet = self.transport.call(job_id,request['role'],request)
                if packet.get('request_sha256') != digest(canonical(request)):
                    raise StudyHarnessError('role request binding diverged')
                _write(self.root/(job_id+'-packet.json'),packet)
                self._apply(state,stage,packet); packet_sha=digest(canonical(packet))
            state['history'].append({'stage':stage,'job_id':job_id,'packet_sha256':packet_sha})
            state['index']+=1
            _write(self.root/'progress.json',state)
            return {'action':stage,'complete':state['complete']}

    def validate_closed(self,state):
        last=state['history'][-1]
        if last['stage']!='final-review': raise StudyHarnessError('completion lacks final review')
        packet=_json(self.root/(last['job_id']+'-packet.json'))
        request=_json(self.root/(last['job_id']+'-request.json'))
        if (digest(canonical(packet))!=last['packet_sha256']
                or packet['request_sha256']!=digest(canonical(request))
                or request['documents']['delivery-files.json']!=canonical(state['files']).decode()
                or packet['result']!=state['final_review']
                or json.loads(request['documents']['audit-binding.json'])!=self._audit_binding(state)):
            raise StudyHarnessError('completed delivery differs from reviewed snapshot')

    def step(self):
        try: return self._step()
        except (StudyHarnessError,StudyBudgetError,BudgetError,ControllerError,NativeRoleError,DockerRoleError) as exc:
            # Start from the last committed snapshot, not a partially mutated
            # in-memory candidate. Native/raw packets stay in their journals.
            # Filesystem failures propagate for same-job recovery; they never
            # receive an invented model failure or a new call ID.
            with self._lock():
                state=_json(self.root/'progress.json')
                stage=state['stages'][state['index']] if state['index']<len(state['stages']) else 'closed_snapshot'
                failure={'status':'generation_failed','stage':stage,
                         'error_type':type(exc).__name__,'reason':str(exc),
                         'automatic_retry':False,'grade':None}
                state['terminal_failure']=failure
                _write(self.root/'progress.json',state)
                _write(self.root/'terminal-failure.json',failure)
                return {'action':'failed','complete':False,'failure':failure}


class ToolkitCell:
    """Real T engine/controller route plus the same one-time final review."""
    def __init__(self, root, transport, *, task, contract, mandate, protocol_sha256, rubric=''):
        if (task not in set(TASK_FILES) or type(protocol_sha256) is not str
                or re.fullmatch('[0-9a-f]{64}',protocol_sha256) is None):
            raise StudyHarnessError('explicit toolkit cell identity required')
        self.root=_safe(root); self.root.mkdir(parents=True,mode=0o700,exist_ok=True)
        self.transport=transport; self.contract=contract; self.mandate=mandate
        self.rubric=rubric
        policy={'schema':3,'task':task,'protocol_sha256':protocol_sha256,
                'rubric_sha256':digest(rubric.encode()),
                'contract_sha256':digest(contract.encode()),'mandate_sha256':digest(mandate.encode())}
        path=self.root/'toolkit-policy.json'
        if path.exists() and _json(path)!=policy: raise StudyHarnessError('toolkit cell identity changed')
        if not path.exists(): _write(path,policy)
        self.case=self.root/'case'
        if not self.case.exists():
            engine.create_case(self.case,'Registered '+task+' software cell','development',
                               'human:owner',approval_policy='local')
        # These are current reads before any controller case writes, as required
        # by the local skill. The label records the existing delegated mandate.
        state=engine.get_state(self.case)
        _write(self.root/'last-read-status.json',state)
        _write(self.root/'last-read-report.json',case_report(self.case))
        _write(self.root/'last-read-next-task.json',describe_task(state))
        self.controller=Controller(self.case,self.root/'controller',transport,
                                   contract=contract,mandate=mandate,executor=transport)

    def _step(self):
        path=self.root/'common-final-review.json'
        if path.exists():
            self.controller.package_gate()
            packet=_json(path);request=_json(self.root/'common-final-request.json')
            if (packet.get('provenance')!='native' or packet.get('request_sha256')!=digest(canonical(request))
                    or request['documents']['delivery-files.json']!=canonical(self.controller._files()).decode()):
                raise StudyHarnessError('completed toolkit delivery differs from final review')
            validate_response(packet['result'].get('audit'),'T',json.loads(request['documents']['audit-binding.json']))
            _write(self.root/'assessment.json',packet['result']['audit'])
            return {'action':'complete','final_review':packet['result'],'nine_phase_package_allowed':True}
        result=self.controller.step()
        if result['action']!='complete': return result
        files=self.controller._files()
        state=engine.get_state(self.case)
        records={}
        for item in state['items'].values():
            if item['kind']=='test':
                # Engine state contains the current version of the sole sealed
                # test ID. Historical failed receipts stay in controller history;
                # they are not reinterpreted as tests of the final delivery.
                data=item['data']; self.transport.verify_test(data,files)
                records[item['id']]={'current_test_job_ref':data['test_job_ref'],
                                    'delivery_tree_sha256':digest(canonical(files))}
        records['all_public_attempts']=self.public_attempts(files)
        request=self.final_request(state,files,records)
        prepared=self.root/'common-final-request.json'
        if prepared.exists() and _json(prepared)!=request: raise StudyHarnessError('final snapshot changed')
        if not prepared.exists(): _write(prepared,request)
        packet=self.transport.call('common-final-review','review',request)
        if packet.get('provenance')!='native' or packet.get('request_sha256')!=digest(canonical(request)):
            raise StudyHarnessError('final native review provenance/binding invalid')
        validate_result(packet['result'],'review')
        _write(path,packet)
        validate_response(packet['result'].get('audit'),'T',json.loads(request['documents']['audit-binding.json']))
        _write(self.root/'assessment.json',packet['result']['audit'])
        return {'action':'complete','nine_phase_package_allowed':result['package_allowed'],
                'final_review':packet['result']}

    def public_attempts(self,files):
        attempts={}
        for entry in _json(self.controller.root/'progress.json')['history']:
            if entry['action']!='test':continue
            measured=self.transport.test_record(entry['job_id'])
            data={'test_job_ref':measured['test_job_ref'],'argv':measured['subject_argv'],
                  'delivery_tree_sha256':measured['delivery_tree_sha256']}
            self.transport.verify_test(data,files,require_passed=False,require_current=False)
            if measured['delivery_tree_sha256']!=entry['source_files_sha256']:
                raise StudyHarnessError('historical measured test differs from sealed source snapshot')
            attempts[entry['job_id']]={'measurement':measured,
                'applies_to_current_delivery':measured['delivery_tree_sha256']==digest(canonical(files)),
                'receipt':_json(Path(measured['test_job_ref'])),
                'streams':self.controller._test_streams(measured['test_job_ref'],measured)}
        return attempts

    def step(self):
        terminal=self.root/'terminal-failure.json'
        if terminal.exists():return _json(terminal)
        try:return self._step()
        except (ControllerError,StudyBudgetError,BudgetError,StudyHarnessError,NativeRoleError,DockerRoleError) as exc:
            result={'action':'failed','complete':False,'failure':{'error_type':type(exc).__name__,'reason':str(exc),
                    'automatic_retry':False,'grade':None}}
            _write(terminal,result)
            return result

    def final_request(self,state,files,records):
        return common_request('review',self.contract,{
            'assessment-rubric.md':self.rubric,
            'method.txt':'T','state-locator.txt':'audit-history.json#/state',
            'delivery-files.json':canonical(files).decode(),
            'public-measurements-locator.txt':'audit-history.json#/public_attempts',
            **audit_documents('T',self.contract,files,{'state':state,'controller_history':_json(self.controller.root/'progress.json')['history'],'public_attempts':records})},
            'One independent common FINAL review, no regeneration afterwards. Judge contract, useful README, '
            'pertinent code/tests, substantive nine accepted phases and valid traceability. Only supplied '
            'public measurements were executed; no reserved results or field benefit. Return schema=1, '
            'verdict accept/reject/inconclusive, nonempty reason, findings as array of objects, tests_executed=false.'
            +audit_instructions())
