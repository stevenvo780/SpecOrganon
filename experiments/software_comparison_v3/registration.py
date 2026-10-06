"""Read-only full v3 registration and fixed original private schedule validation.

Constructing infrastructure or a review label does not register this campaign.
The coordinator must persist the complete accepted snapshot before any author.
Trust is the operator/filesystem boundary, not cryptographic reviewer identity.
"""
from __future__ import annotations

import datetime as dt
import importlib
from pathlib import Path
import re
import time

from specorganon.role_jobs import canonical,digest,_json,_read,_safe
from specorganon.ledger import strict_json_loads
from experiments.software_comparison_v3.budget import CELL_LIMITS,CAMPAIGN_LIMITS
from experiments.software_comparison_v3.reserved import recipes,TASK_COUNTS
from scripts.controller_native_role import role_model_catalog

IDENTITY='software-comparison-v3'
SCHEDULE_SHA='33e47d210e98909c81fbe3df099cf4d7994faba7c205703dcb251f9d6d448245'
MODELS={'codex':{'provider':'codex','model':'gpt-6.1-sol','effort':'medium'},
        'gemini':{'provider':'gemini','model':'Gemini 3.8 Flash (Medium)','effort':'medium'}}
PROFILES={'codex_volume':'specorganon-lab_codex-home','gemini_profile':'/home/stev/.gemini',
          'gemini_executable':'/home/stev/.local/bin/agy'}
IMAGES={'native':'sha256:aa4eae810628bd2b78bd48ed3059c284a497bdc7c92d81daacdfe906a3bae3ae',
        'test':'sha256:98723123de528a5f0201a1c341fe044f88d885345b2e1bedd6a89574c4796d92'}
PUBLIC='experiments/software_comparison_v3/public/'
CONTRACTS={task:PUBLIC+task+'-contract-candidate.md' for task in TASK_COUNTS}
MANDATE=PUBLIC+'existing-mandate-candidate.md'
SDD=PUBLIC+'sdd-guide-candidate.md'
PROTOCOL='experiments/software_comparison_v3/protocol-draft.md'
RUBRIC='experiments/software_comparison_v3/analysis-plan-candidate.md'
STOP='all42_fixed_order_no_replacements_gate_reserved_after_actual_T9_and_all_terminal_stop_on_unknown_native_failure'


class RegistrationError(ValueError):pass


def require(condition,message):
    if not condition:raise RegistrationError(message)


def source_file(name):
    """Repository paths include hidden skill directories and dependency locks.

    Delivery-file extensions/hidden-directory restrictions do not apply here;
    relative canonical paths and path-traversal rejection still do.
    """
    require(type(name) is str and 0<len(name)<=4096
        and all(part not in ('.','..') and re.fullmatch(r'[A-Za-z0-9_.-]+',part)
                for part in name.split('/')),'unsafe registered source name')
    return name


def utc(value):
    require(type(value) is str,'UTC timestamp text required')
    try:parsed=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError as exc:raise RegistrationError('invalid UTC timestamp') from exc
    require(parsed.utcoffset()==dt.timedelta(0),'UTC timestamp required')
    return parsed.timestamp()


def fixed_schedule(path):
    """Validate existing original bytes, never shuffle or allocate new IDs."""
    raw=_read(_safe(path));require(digest(raw)==SCHEDULE_SHA,'original private schedule changed')
    schedule=_json(path)
    require(schedule['identity']==IDENTITY and schedule['scheduler_seed']==731
            and schedule['native_author_calls']==0 and schedule['registered'] is False,'original before-author schedule required')
    rows=schedule['rows'];blocks=schedule['blocks']
    require(type(rows) is list and len(rows)==42 and type(blocks) is list and len(blocks)==12,'complete original42 schedule required')
    cells=[];seen=set();index=0
    for block in blocks:
        require(block['block_id']==f'block-{len({r["block_id"] for r in rows[:index]})+1:02d}'
                and block['family'] in MODELS and block['task'].lower() in TASK_COUNTS
                and block['rep'] in (1,2),'original block identity invalid')
        for method in block['sequence']:
            row=rows[index];index+=1;other='gemini' if row['family']=='codex' else 'codex'
            require(row['sequence']==index and all(row[k]==block[k] for k in ('block_id','task','family','rep'))
                    and row['method']==method and row['author']==MODELS[row['family']] and row['reviewer']==MODELS[other]
                    and row['limits']=={'max_calls':40,'max_elapsed_seconds':6000,'max_total_input_bytes':3145728},'fixed row/route/budget changed')
            opaque=row['opaque_delivery_id']
            require(type(opaque) is str and re.fullmatch(r'delivery-[0-9a-f]{32}',opaque) and opaque not in seen,'unique original opaque ID required')
            seen.add(opaque)
            cells.append({'id':f'cell-{index:02d}','task':row['task'].lower(),'family':row['family'],
                          'rep':row['rep'],'method':method,'block_id':row['block_id'],'opaque_id':opaque})
    require(index==42 and cells[0]['method']=='T' and cells[0]['task']=='fractionmix'
            and cells[0]['family']=='codex' and cells[0]['rep']==1,'fixed primaryT changed')
    require({m:sum(c['method']==m for c in cells) for m in 'NSTA'}=={'N':12,'S':12,'T':12,'A':6},'fixed treatment population changed')
    return cells


def required_sources(source):
    """Minimum executable/doc snapshot; registration may bind more files."""
    source=_safe(source)
    required={str(p.relative_to(source)) for base,glob in [('src/specorganon','*.py'),('experiments/software_comparison_v3','*.py'),('tests','test_software_comparison_v3_*.py')] for p in (source/base).rglob(glob)}
    required|=set(CONTRACTS.values())|{MANDATE,SDD,PROTOCOL,RUBRIC,'scripts/controller_native_role.py',
        'scripts/study_cell_budget.py','pyproject.toml','uv.lock','docs/metodologia.md','docs/workflow_operativo.md','.agents/skills/specorganon/SKILL.md'}
    return required


def review_result(text):
    """Engineering reviews may be fenced; exact single JSON remains required."""
    require(type(text) is str,'actual native review text required')
    text=text.strip()
    if text.startswith('```json\n') and text.endswith('\n```'):text=text[8:-4]
    try:value=strict_json_loads(text)
    except ValueError as exc:raise RegistrationError('native full review is not exact JSON') from exc
    require(type(value) is dict and type(value.get('schema')) is int and value['schema']==1,'native full review schema1 required')
    return value


def runtime_sources(source):
    modules=['specorganon.'+n for n in ('engine','ledger','workflow','runner','role_jobs','docker_roles','software_controller')]
    modules+=['experiments.software_comparison_v3.'+n for n in ('registration','budget','cells','provenance','reserved','subjects','rubric','analysis','audit_evidence','campaign','evaluation')]
    modules+=['scripts.controller_native_role','scripts.study_cell_budget']
    for name in modules:
        module=importlib.import_module(name);expected=(source/'src' if name.startswith('specorganon.') else source)/Path(*name.split('.')).with_suffix('.py')
        require(Path(module.__file__).absolute()==expected,'runtime module imported from different checkout: '+name)


class Registration:
    def __init__(self,path,source):
        self.path=_safe(path);self.source=_safe(source)
        self.raw=_read(self.path);self.sha=digest(self.raw);self.value=_json(self.path)
        self.validate()

    def validate(self):
        require(_read(self.path)==self.raw,'immutable registration changed')
        value=self.value;source=self.source
        require(value.get('schema')==1 and type(value.get('schema')) is int and value.get('status')=='registered'
                and value.get('identity')==IDENTITY,'full registered v3 snapshot required')
        require(value['source_root']==str(source),'source checkout differs')
        root=_safe(value['run_root']);require(Path(value['run_root']).is_absolute() and source!=root and source not in root.parents,'private run root outside source required')
        require(value['profiles']==PROFILES and value['routes']==MODELS and value['images']==IMAGES
                and value['cell_limits']==CELL_LIMITS and value['campaign_limits']==CAMPAIGN_LIMITS
                and value['stopping_rule']==STOP,'fixed accounts/routes/images/budgets/stopping rule differ')
        require(0<utc(value['registered_at'])<=time.time(),'registration must precede author admission')
        cells=fixed_schedule(value['private_schedule'])
        require(value['private_schedule_sha256']==SCHEDULE_SHA and value['cells']==cells
                and value['primary_T']=='cell-01','original fixed cohort/primary differs')
        bindings=value['source_sha256'];review_name=source_file(value['accepted_review'])
        require(type(bindings) is dict and required_sources(source)|{review_name,value['public_catalog']}<=set(bindings),
                'full executable/protocol/rubric/contract/test/dependency snapshot required')
        for name,sha in bindings.items():
            require(type(sha) is str and re.fullmatch('[0-9a-f]{64}',sha),'source SHA256 required')
            require(digest(_read(source/source_file(name)))==sha,'registered source changed: '+name)
        review=_json(source/review_name)
        require(review.get('schema')==1 and review.get('verdict')=='accept'
                and review.get('scope')=='full_v3_protocol_harness_provenance_rubric_evaluator_and_registration'
                and review.get('provider') in ('codex','gemini','muse') and type(review.get('job_id')) is str and review['job_id'],
                'full actual native review receipt required, not scoped draft acceptance')
        require(review['source_sha256']=={n:h for n,h in bindings.items() if n!=review_name}
                and utc(review['completed_at'])<=utc(value['registered_at'])
                and review.get('tests_executed') is False and review.get('native_receipt_ref'),
                'full review must bind exact source snapshot before registration')
        native=_json(_safe(review['native_receipt_ref']))
        require(native.get('job_id')==review['job_id'] and native.get('status')=='succeeded'
                and type(native.get('text')) is str and native['text'].strip(),'actual terminal native review missing')
        require(digest(_read(review['native_receipt_ref']))==review['native_receipt_sha256'],
                'native review receipt changed')
        require(native.get('meta',{}).get('provider')==review['provider']
                and native.get('meta',{}).get('model')==review['model'],
                'actual native review provider/model attribution differs')
        judgment=review_result(native['text']);expected_review={n:h for n,h in bindings.items() if n!=review_name}
        require(judgment.get('verdict')=='accept' and judgment.get('tests_executed') is False
                and judgment.get('scope')==review['scope']
                and judgment.get('source_manifest_sha256')==digest(canonical(expected_review)),
                'actual native judgment rejects/differs from full reviewed manifest')
        require(type(native.get('finished_at')) in (int,float) and 0<native['finished_at']<=utc(value['registered_at'])
                and abs(native['finished_at']-utc(review['completed_at']))<1,
                'actual terminal native review must precede registration')
        require(value['contracts']==CONTRACTS and value['mandate']==MANDATE and value['sdd_guide']==SDD
                and value['protocol']==PROTOCOL and value['rubric']==RUBRIC,'registered public inputs differ')
        expected={t:{'count':TASK_COUNTS[t],'public':2,'sha256':digest(canonical(recipes(t)))} for t in TASK_COUNTS}
        require(value['matrices']==expected,'full deterministic250recipes changed')
        projected=role_model_catalog(_json(source/value['public_catalog']),'gpt-6.1-sol')
        require(any(entry.get('effort')=='medium' for entry in projected['models'][0]['supported_reasoning_levels']),
                'public Codex catalog does not list fixed medium effort')
        # A callback executed from another checkout may import unbound code even
        # when the frozen files exist. Require actual imported runtime location.
        runtime_sources(source)
        return {'registration_sha256':self.sha,'private_mapping_sha256':SCHEDULE_SHA,'source_bindings':len(bindings)}


def current_quota(path,*,now=None):
    """Fresh explicit original observations; unknown never means available."""
    raw=_read(_safe(path),128000);value=_json(path);now=time.time() if now is None else now
    require(type(value) is dict and type(value.get('schema')) is int and value.get('schema')==1
            and value.get('accounts')=={'codex':'original_lab_profile','gemini':'original_primary_profile'},'original-account quota observations required')
    require(0<=now-utc(value['captured_at'])<=600,'quota observation expired or future dated')
    providers=value['providers'];require(type(providers) is dict and set(providers)=={'codex','gemini'},'both original providers required')
    for provider,row in providers.items():
        require(type(row) is dict and row.get('status') in ('observed','unknown') and type(row.get('remaining_percent')) is list,'invalid quota observation')
        if row['status']=='unknown':
            require(set(row)=={'status','remaining_percent','reason'} and row['remaining_percent']==[] and type(row['reason']) is str and row['reason'].strip(),'unknown must remain explicit')
            require(provider=='codex','Gemini quota unknown/expired: hold fresh admissions on original route')
        else:
            require(set(row)=={'status','remaining_percent','source','observed_at'} and type(row['source']) is str and row['source'].strip()
                    and 0<=now-utc(row['observed_at'])<=600 and row['remaining_percent']
                    and all(type(n) in (int,float) and 0<n<=100 for n in row['remaining_percent']),
                    provider+' quota stale/depleted/malformed; no new admission')
    return {'quota_snapshot_sha256':digest(raw),'captured_at':value['captured_at'],
            'capacity_guaranteed':False,'observations':providers}
