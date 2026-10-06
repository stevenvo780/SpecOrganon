"""One globally gated opaque functional evaluation, no repair/native feedback.

Generation must be fully terminal and a physically proved T9 must exist. This
coordinator retains the private mapping; Subjects receives opaque roots/task/files
and frozen recipes only, never model/method/history. Same-handle outcomes are
re-read, never rerun when observation is uncertain or a receipt is missing.
"""
from __future__ import annotations

from pathlib import Path

from specorganon.role_jobs import UncertainJob,JobError,_json,_read,_write,canonical,digest
from experiments.software_comparison_v3.subjects import Subjects,SubjectError
from experiments.software_comparison_v3.reserved import recipes,TASK_FILES
from experiments.software_comparison_v3.analysis import functional_summary,descriptive_differences
from experiments.software_comparison_v3.rubric import rubric
from experiments.software_comparison_v3.audit_evidence import verify_locators


class EvaluationError(ValueError):pass


def require(condition,message):
    if not condition:raise EvaluationError(message)


def score_points(points):
    n=len(points);passed=sum(p['status']=='pass' for p in points.values())
    unknown=sum(p['status']=='inconclusive' for p in points.values())
    return {'applicable':bool(n),'pass':passed,'fail':n-passed-unknown,'inconclusive':unknown,
            'denominator':n,'lower':passed/n if n else None,'upper':(passed+unknown)/n if n else None}


def comparison_groups(rows,*,nst_blocks,a_blocks):
    """Fixed cell pairs, including unknown intervals, within one design stratum."""
    result={}
    for group in ('F','D','G','H'):
        for control in ('N','S','A'):
            if group=='H' and control=='N':continue
            pairs=[]
            for block in sorted({r['block_id'] for r in rows}):
                members=[r for r in rows if r['block_id']==block]
                cells={r['method']:r for r in members}
                require(len(cells)==len(members) and set(cells) in ({'N','S','T'},{'N','S','T','A'}),
                        'fixed distinct methods required in every paired block')
                if control not in cells:continue
                def interval(item):
                    score=item['functional']['F_total'] if group=='F' else item['qualitative']['scores'][group]
                    return {k:score[k] for k in ('lower','upper')}
                pairs.append((block,interval(cells['T']),interval(cells[control])))
            require(len(pairs)==(a_blocks if control=='A' else nst_blocks),'all fixed paired blocks required')
            result[group+'_T-'+control]=descriptive_differences(pairs)
    return result


class Evaluation:
    def __init__(self,campaign):self.campaign=campaign;self.root=campaign.root/'evaluation'

    def exports(self):
        c=self.campaign;progress=_json(c.journal.root/'progress.json');manifest={};payloads={}
        for row in c.value['cells']:
            seal=progress['cells'][row['id']]['terminal']
            require(seal is not None,'all42fixed generations must close first')
            path=c.root/'exports'/row['opaque_id']/'delivery.json';value=_json(path)
            require(set(value)=={'schema','opaque_id','task','files','delivery_sha256'}
                    and type(value['schema']) is int and value['schema']==1 and value['opaque_id']==row['opaque_id'] and value['task']==row['task']
                    and digest(canonical(value['files']))==value['delivery_sha256']==seal['delivery_sha256'],
                    'opaque export differs from terminal generation seal')
            manifest[row['opaque_id']]=digest(_read(path));payloads[row['opaque_id']]=value
        return manifest,payloads

    def prepare(self):
        c=self.campaign;c.registration.validate()
        gate=c.journal.evaluation_gate(c.verify_milestone)
        require(gate['reserved_evaluation_allowed'] is True and gate['status']=='released_once',
                'actual T9 prerequisite missing/inconclusive; no reserved subject permitted')
        manifest,payloads=self.exports();self.root.mkdir(parents=True,mode=0o700,exist_ok=True)
        policy={'schema':1,'registration_sha256':c.registration.sha,'gate_sha256':digest(canonical(gate)),
                'opaque_exports_sha256':manifest,'subject_image':c.value['images']['test']}
        path=self.root/'policy.json'
        require(not path.exists() or _json(path)==policy,'released evaluation source/exports changed')
        if not path.exists():_write(path,policy)
        path=self.root/'progress.json'
        if not path.exists():_write(path,{'schema':1,'policy_sha256':digest(canonical(policy)),
            'cells':{r['opaque_id']:{'rows':{},'complete':False} for r in c.value['cells']},'complete':False})
        progress=_json(path)
        require(progress['policy_sha256']==digest(canonical(policy)) and set(progress['cells'])==set(manifest),
                'fixed evaluator population changed')
        return payloads,progress

    def step(self):
        c=self.campaign
        with c.lock():
            payloads,progress=self.prepare()
            if progress['complete']:return {'action':'all_evaluation_terminal','cells':42,'native_authors_invoked':False}
            row=next(r for r in c.value['cells'] if not progress['cells'][r['opaque_id']]['complete'])
            opaque=row['opaque_id'];export=payloads[opaque];matrix=recipes(export['task']);cell=progress['cells'][opaque]
            require(set(cell['rows'])<=set(r['id'] for r in matrix),'unexpected frozen recipe result')
            recipe=next((r for r in matrix if r['id'] not in cell['rows']),None)
            if recipe is not None:
                files=export['files']
                if TASK_FILES[export['task']] not in files:
                    result={'id':recipe['id'],'public':recipe['public'],'status':'fail','reason':'programme absent from sealed terminal delivery',
                            'receipt_ref':None,'subject_executed':False}
                else:
                    # Private mapping and method are not supplied to this runner.
                    subjects=Subjects(self.root/'subjects'/opaque,c.value['images']['test'],export['task'])
                    try:result=subjects.run(recipe['id'],recipe,files)
                    except UncertainJob:
                        # A specific existing handle remains the only recovery
                        # target. No new subject or fabricated fail/pass result.
                        raise
                    except (SubjectError,JobError):
                        # Binding errors and missing evidence need inspection;
                        # they are not a behavioural failure of the programme.
                        raise
                cell['rows'][recipe['id']]=result
            if len(cell['rows'])==len(matrix):cell['complete']=True
            progress['complete']=all(v['complete'] for v in progress['cells'].values())
            _write(self.root/'progress.json',progress)
            return {'opaque_id':opaque,'recipe_id':recipe['id'] if recipe else None,'cell_complete':cell['complete'],
                    'all_evaluation_terminal':progress['complete'],'feedback_to_authors':False}

    def qualitative(self,row,snapshot):
        c=self.campaign;definition=rubric(row['method']);audit=None;native_proof=None
        if snapshot['status']=='complete':
            runner,evidence=c.cell(row)
            if row['method']=='T':
                packet=_json(runner.root/'common-final-review.json');request=_json(runner.root/'common-final-request.json');identity='common-final-review'
                runner.controller.package_gate()
            else:
                state=_json(runner.root/'progress.json');runner.validate_closed(state);identity=state['history'][-1]['job_id']
                packet=_json(runner.root/(identity+'-packet.json'));request=_json(runner.root/(identity+'-request.json'))
            native_proof=evidence.role(identity,'review',request=request,packet=packet)
            audit=packet['result']['audit'];binding=_json_text(request['documents']['audit-binding.json'])
            verify_locators(audit,row['method'],binding,request['documents'])
            require(binding['delivery_sha256']==snapshot['delivery_sha256'],'qualitative audit delivery changed')
        status='inconclusive' if snapshot['status']=='infra_inconclusive' else 'fail'
        points={group:(audit[group] if audit else {identity:{'status':status,
            'reason':'native final audit missing after '+snapshot['status'],'evidence':[]} for identity in definition[group]}) for group in ('D','G','H')}
        return {'scores':{group:score_points(p) for group,p in points.items()},'points':points,
                'native_final_receipt_sha256':native_proof['native_receipt_sha256'] if native_proof else None,
                'semantic_scope':'judgments of actual separate native auditor; locator presence alone is not truth or field efficacy'}

    def resources(self,row):
        """Keep provider-declared usage verbatim; do not infer tokens or money."""
        c=self.campaign;record=_json(c.journal.root/'progress.json')['cells'][row['id']]
        usages=[];physical=c.root/'cells'/row['id']/'transport'
        from experiments.software_comparison_v3.provenance import journal_receipt
        for identity,entry in record['roles'].items():
            if entry['outcome'] is None:raise EvaluationError('terminal role outcome still pending')
            path=physical/'jobs'/identity/'output/native'
            if (path/'call/receipt.json').exists():
                receipt,request,streams=journal_receipt(path,'call')
                # A failed native process has no valid usage result to infer.
                if receipt['exit_code']==0 and not receipt['timed_out'] and not receipt['truncated_streams']:
                    # Successful bridge packets were physically validated before
                    # budget closure. Read exactly their captured outer stdout.
                    _,_,captured=journal_receipt(physical/'host-journal',identity)
                    try:value=_json_text(captured['stdout'].decode())
                    except ValueError:value=None
                    if type(value) is dict and 'usage_reported' in value:
                        usages.append({'job_id':identity,'provider':value['provider'],'model':value['model'],
                            'usage_reported':value['usage_reported'],'scope':'provider-declared raw quantities, not normalized'})
        return {'admitted_native_attempts':len(record['roles']),'admitted_own_tests':len(record['tests']),
            'rendered_input_bytes':sum(r['binding']['rendered_input_bytes'] for r in record['roles'].values()),
            'elapsed_seconds':record['terminal']['elapsed_seconds'],'campaign_elapsed_seconds':record['terminal']['campaign_elapsed_seconds'],
            'usage_per_native_job':usages,'native_tokens_normalized':None,'monetary_cost':None,
            'coordinator_steps':len(_json(c.root/'progress.json')['steps'].get(row['id'],[])),
            'interventions':'automatic registered coordinator steps; no manual programme repairs authorized'}

    def report(self):
        c=self.campaign
        with c.lock():
            c.registration.validate();gate=c.journal.evaluation_gate(c.verify_milestone)
            require(gate['status'] in ('released_once','not_evaluated_by_prerequisite'),
                    'inconclusive prerequisite retains pending report; no immutable final evaluation claim')
            evaluated=gate['status']=='released_once' and gate['reserved_evaluation_allowed'] is True
            manifest,payloads=self.exports()
            if evaluated:
                payloads,progress=self.prepare();require(progress['complete'],'report requires every frozen recipe row of all42cells')
            rows=[]
            for row in c.value['cells']:
                snapshot=_json(c.root/'cells'/row['id']/'terminal-snapshot.json')
                require(snapshot['delivery_sha256']==payloads[row['opaque_id']]['delivery_sha256'], 'report terminal snapshot changed')
                recipe_rows=list(progress['cells'][row['opaque_id']]['rows'].values()) if evaluated else []
                functional=functional_summary(recipes(row['task']),recipe_rows,evaluated=evaluated)
                # No new native reviews or repairs: reuse only the actual final
                # audit already charged during generation, or missing/unknown.
                qualitative=self.qualitative(row,snapshot)
                points_ok=all(score['fail']==score['inconclusive']==0 for score in qualitative['scores'].values())
                rows.append({**row,'generation_status':snapshot['status'],
                    'evaluation_status':'evaluated' if evaluated else gate['status'],'functional':functional,
                    'qualitative':qualitative,'full_package':functional['contract_complete'] and points_ok,
                    'resources':self.resources(row)})
            comparisons=comparison_groups(rows,nst_blocks=12,a_blocks=6)
            strata={}
            for dimension,nst_count,a_count in (('task',4,2),('family',6,3)):
                strata[dimension]={identity:comparison_groups([r for r in rows if r[dimension]==identity],
                    nst_blocks=nst_count,a_blocks=a_count) for identity in sorted({r[dimension] for r in rows})}
            result={'schema':1,'registration_sha256':c.registration.sha,'gate':gate,'cells':rows,'comparisons':comparisons,'strata':strata,
                'generation_cells':42,'evaluation_complete':evaluated,'design_denominator':42,
                'field_or_general_thesis_proven':False,'native_replicate_unit':'author/task/family/rep cell, not each recipe'}
            path=c.root/'report.json'
            require(not path.exists() or _json(path)==result,'final immutable report changed')
            if not path.exists():_write(path,result)
            return result


def _json_text(text):
    from specorganon.ledger import strict_json_loads
    return strict_json_loads(text)
