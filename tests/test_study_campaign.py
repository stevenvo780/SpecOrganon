"""Campaign controls with explicit synthetic runners: zero native study cells."""
import datetime as dt
from pathlib import Path
import pytest

from scripts.study_campaign import Campaign,CampaignPause,AccountStop,current_quota,export_delivery,native_failure_kind
from scripts.software_study_harness import StudyHarnessError
from specorganon.software_controller import ControllerError
from specorganon.role_jobs import canonical,digest,_json,_write


def quota(path,remaining=75):
    now=dt.datetime.now(dt.timezone.utc).isoformat()
    value={'schema':1,'captured_at':now,
           'accounts':{'codex':'original_lab_profile','gemini':'original_primary_profile'},
           'providers':{'codex':{'status':'unknown','remaining_percent':[],
                                'reason':'Synthetic unavailable quota, no capacity inferred'},
                        'gemini':{'status':'observed','remaining_percent':[remaining],
                                  'observed_at':now,'source':'synthetic fixture only'}}}
    _write(path,value);return value


def test_quota_unknown_is_explicit_but_zero_or_stale_refuses_admission(tmp_path):
    path=tmp_path/'quota.json'; value=quota(path)
    result=current_quota(path)
    assert not result['capacity_guaranteed'] and result['observations']['codex']['status']=='unknown'
    quota(path,0)
    with pytest.raises(CampaignPause,match='depleted'): current_quota(path)
    value=quota(path);value['captured_at']='2020-01-01T00:00:00+00:00';_write(path,value)
    with pytest.raises(CampaignPause,match='older'): current_quota(path)
    value=quota(path);value['providers']['gemini']['unrequested_profile_metadata']='must not propagate'
    _write(path,value)
    with pytest.raises(CampaignPause,match='malformed'): current_quota(path)


class FixtureCell:
    def __init__(self,root,mode): self.root=root;self.mode=mode;root.mkdir(parents=True,exist_ok=True)
    def step(self):
        path=self.root/'synthetic-count.json'; n=_json(path)['count'] if path.exists() else 0
        _write(path,{'count':n+1,'classification':'synthetic fixture, zero native calls'})
        if self.mode=='account': raise AccountStop('synthetic actual native failure control')
        if self.mode=='invalid': raise ControllerError('synthetic invalid model contribution')
        return {'action':'complete' if n else 'program','complete':bool(n)}


def campaign(tmp_path,mode='okay'):
    cells=[{'id':'fixture-one','method':'N','task':'routeplan','family':'codex','repetition':1},
           {'id':'fixture-two','method':'S','task':'treemap','family':'gemini','repetition':1}]
    value={'status':'synthetic_fixture','cells':cells}
    c=Campaign(tmp_path/'campaign',value,'a'*64,source=tmp_path,quota_snapshot=tmp_path/'quota.json',
               fixture_mode=True,cell_factory=lambda cell,root:FixtureCell(root,mode))
    return c


def test_exact_order_same_cell_resume_and_closed_reuse(tmp_path):
    c=campaign(tmp_path)
    with pytest.raises(StudyHarnessError,match='next'): c.step('fixture-two')
    assert not (c.root/'cells').exists()
    assert c.step('fixture-one')['status']=='running'
    assert c.step('fixture-one')['status']=='complete'
    count=c.root/'cells/fixture-one/synthetic-count.json'
    before=count.read_bytes();assert c.step('fixture-one')['status']=='complete'
    assert count.read_bytes()==before
    assert c.step('fixture-two')['status']=='running'
    with pytest.raises(StudyHarnessError,match='order changed'):
        Campaign(c.root,c.value,'b'*64,source=tmp_path,quota_snapshot=tmp_path/'quota.json',
                 fixture_mode=True,cell_factory=c.cell_factory)


def test_invalid_cell_terminal_is_preserved_without_retry(tmp_path):
    c=campaign(tmp_path,'invalid')
    record=c.step('fixture-one');assert record['status']=='failed'
    assert record['steps'][0]['failure']['grade'] is None
    count=c.root/'cells/fixture-one/synthetic-count.json';before=count.read_bytes()
    assert c.step('fixture-one')['status']=='failed' and count.read_bytes()==before
    assert c.step('fixture-two')['status']=='failed'


def test_actual_unclassified_native_failure_stops_other_cells_and_never_changes_route(tmp_path):
    c=campaign(tmp_path,'account')
    assert c.step('fixture-one')['status']=='infra_inconclusive'
    before=(c.root/'cells/fixture-one/synthetic-count.json').read_bytes()
    assert c.step('fixture-one')['status']=='infra_inconclusive'
    assert (c.root/'cells/fixture-one/synthetic-count.json').read_bytes()==before
    with pytest.raises(CampaignPause,match='no automatic resume'):c.step('fixture-two')
    assert not (c.root/'cells/fixture-two').exists()
    assert _json(c.root/'progress.json')['paused']['actual_native_failure']
    assert _json(c.root/'progress.json')['next_index']==0


def test_quota_pause_does_not_consume_call_or_close_cell(tmp_path):
    c=campaign(tmp_path)
    def no_quota(): raise CampaignPause('synthetic stale quota')
    c.validate=no_quota
    with pytest.raises(CampaignPause):c.step('fixture-one')
    state=_json(c.root/'progress.json');assert state['next_index']==0 and not state['cells']
    assert not (c.root/'cells').exists()
    c.validate=lambda:{'classification':'synthetic new observation'}
    assert c.step('fixture-one')['status']=='running'


def test_opaque_export_includes_only_delivery_and_is_immutable_on_reuse(tmp_path):
    c=campaign(tmp_path);cell=c.value['cells'][0]
    private=c.root/'cells'/cell['id'];private.mkdir(parents=True)
    files={'fixture.py':"print('synthetic control')\n",'README.md':'Synthetic export control only'}
    result=export_delivery(c.root,cell,c.sha,files=files,
        process={'unaccepted-process.md':'Synthetic process'},outcome={'status':'failed','grade':None})
    exported=c.root/'deliveries'/result['opaque_id']
    payload=_json(exported/'delivery.json')
    assert set(payload)=={'schema','opaque_id','task','files','files_sha256'}
    assert 'method' not in payload and 'process' not in payload
    assert (exported/'files/fixture.py').read_text()==files['fixture.py']
    assert not (exported/'files/unaccepted-process.md').exists()
    assert export_delivery(c.root,cell,c.sha,files=files,
        process={'unaccepted-process.md':'Synthetic process'},outcome={'status':'failed','grade':None})==result
    with pytest.raises(StudyHarnessError,match='sealed export changed'):
        export_delivery(c.root,cell,c.sha,files={**files,'fixture.py':'changed'},process={},outcome={})
    (exported/'files/fixture.py').chmod(0o600);(exported/'files/fixture.py').write_text('tampered')
    with pytest.raises(StudyHarnessError,match='exported file changed'):
        export_delivery(c.root,cell,c.sha,files=files,
            process={'unaccepted-process.md':'Synthetic process'},outcome={'status':'failed','grade':None})


def test_unsealed_copy_can_recover_same_bytes_without_regeneration(tmp_path,monkeypatch):
    import scripts.study_campaign as module
    c=campaign(tmp_path);cell=c.value['cells'][0]
    (c.root/'cells'/cell['id']).mkdir(parents=True)
    files={'fixture.py':'synthetic fixture bytes\n'}
    original=module._write
    def interrupted(path,value):
        if path.name=='delivery.json':raise OSError('synthetic export checkpoint interruption')
        return original(path,value)
    monkeypatch.setattr(module,'_write',interrupted)
    with pytest.raises(OSError):export_delivery(c.root,cell,c.sha,files=files,process={},outcome={'status':'complete'})
    monkeypatch.setattr(module,'_write',original)
    result=export_delivery(c.root,cell,c.sha,files=files,process={},outcome={'status':'complete'})
    assert _json(c.root/'deliveries'/result['opaque_id']/'delivery.json')['files']==files
    assert not (c.root/'cells'/cell['id']/'synthetic-count.json').exists()


def test_failure_classifier_uses_failed_diagnostic_not_prompt_or_successful_review(tmp_path):
    root=tmp_path/'transport'
    for job_id,ended,message in [('later',20,'invalid review result contract'),
                                ('earlier',10,'native process failed, timed out, truncated or could not receive full input')]:
        folder=root/'jobs'/job_id;folder.mkdir(parents=True)
        _write(folder/'launch.json',{'role':'review','job_id':job_id})
        journal=root/'host-journal'/job_id;journal.mkdir(parents=True)
        _write(journal/'receipt.json',{'exit_code':2,'timed_out':False,'truncated_streams':[],
                                      'finished_epoch':ended,'classification':'synthetic receipt only'})
        (journal/'stderr.bin').write_text('native role inconclusive: NativeRoleError: '+message+'\n')
    assert native_failure_kind(root)=='invalid_native_role_format'
    (root/'host-journal/later/stderr.bin').write_text('unclassified failure\n')
    assert native_failure_kind(root)=='unclassified_native_failure'


def test_export_contract_failure_closes_checkpoint_without_regenerating(tmp_path):
    c=campaign(tmp_path,'invalid')
    def invalid_export(*args): raise StudyHarnessError('synthetic invalid partial export')
    c._export=invalid_export
    result=c.step('fixture-one')
    assert result['status']=='failed' and result['export']['status']=='inconclusive'
    count=c.root/'cells/fixture-one/synthetic-count.json';before=count.read_bytes()
    assert c.step('fixture-one')==result and count.read_bytes()==before
    assert _json(c.root/'progress.json')['next_index']==1


def test_clock_pause_keeps_pending_cell_and_never_admits_replacement(tmp_path):
    from scripts.study_cell_budget import StudyClockPause
    c=campaign(tmp_path)
    def factory(cell,root): raise StudyClockPause('synthetic boot discontinuity')
    c.cell_factory=factory
    with pytest.raises(StudyClockPause):c.step('fixture-one')
    state=_json(c.root/'progress.json')
    assert state['next_index']==0 and state['cells']['fixture-one']['status']=='running'
    assert not state['paused']['actual_native_failure']
    assert not (c.root/'cells').exists()


def test_runtime_catalog_rejects_route_registry_and_checks_actual_fixed_model_effort(tmp_path):
    from scripts.study_campaign import validate_model_catalog
    root=Path(__file__).parents[1]
    routes='goals/autonomous-software-v1/evidence/comparison-current-public-catalog.json'
    official='goals/autonomous-software-v1/evidence/codex0160-public-models.json'
    value={'public_catalog':routes,'routes':{'codex':{'model':'gpt-6.1-sol'}},'codex_reasoning_effort':'low'}
    with pytest.raises(StudyHarnessError,match='before admission'):validate_model_catalog(value,root)
    value['public_catalog']=official
    assert validate_model_catalog(value,root)==digest((root/official).read_bytes())
    value['routes']['codex']['model']='nonexistent-model'
    with pytest.raises(StudyHarnessError,match='before admission'):validate_model_catalog(value,root)
    value['routes']['codex']['model']='gpt-6.1-sol';value['codex_reasoning_effort']='unlisted-effort'
    with pytest.raises(StudyHarnessError,match='support registered'):validate_model_catalog(value,root)
