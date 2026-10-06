"""Synthetic proof cases; never inspect or populate the real run directory."""
import json
import subprocess
import sys
from pathlib import Path
import pytest
from test_analysis import make_fixture
from analyze import analyze


def test_duplicate_factor_blocks_are_not_six_independent_pairs(tmp_path):
    schedule=make_fixture(tmp_path)
    for row in schedule: row['variant']='V1'; row['repeat']=1
    (tmp_path/'frozen/manifest.json').write_text(json.dumps({'schedule':schedule}))
    with pytest.raises(RuntimeError,match='factor|Variant|schedule'): analyze(tmp_path)


def test_absent_artifact_receipt_is_missing_even_when_embedded_field_removed(tmp_path):
    make_fixture(tmp_path)
    stage=tmp_path/'runs/V1-r1-N/stage1'
    (stage/'artifact.receipt.json').unlink()
    data=json.loads((stage/'complete.json').read_text());data.pop('artifact')
    (stage/'complete.json').write_text(json.dumps(data))
    with pytest.raises(RuntimeError,match='artifact'): analyze(tmp_path)


def test_all_unknown_group_times_are_never_imputed_zero(tmp_path):
    make_fixture(tmp_path)
    for stage in (tmp_path/'runs').glob('*/stage*'):
        data=json.loads((stage/'complete.json').read_text())
        for role in ['author','method','review']:
            if data.get(role):
                data[role]['duration_seconds']=None
                (stage/f'{role}.receipt.json').write_text(json.dumps(data[role]))
        (stage/'complete.json').write_text(json.dumps(data))
    result=analyze(tmp_path)
    for arm in 'NST':
        assert result['resource_stats'][arm]['author_method_duration']['median'] is None
        assert result['resource_stats'][arm]['total_duration']['range']==(None,None)


def test_nonfinite_scores_cannot_pass_consistency_check(tmp_path):
    make_fixture(tmp_path)
    path=tmp_path/'runs/V1-r1-N/stage1/evaluation.json'
    data=json.loads(path.read_text());data['score']=float('nan');path.write_text(json.dumps(data))
    with pytest.raises(RuntimeError,match='score|finite'): analyze(tmp_path)


def test_cli_missing_completion_does_not_export_partial_results(tmp_path):
    make_fixture(tmp_path,omit_complete_marker=True)
    script=Path(__file__).resolve().parents[2]/'analyze.py'
    output=tmp_path/'analysis'
    result=subprocess.run([sys.executable,str(script),'--base',str(tmp_path),'--output',str(output)],capture_output=True)
    assert result.returncode!=0
    assert not (output/'results.json').exists() and not (output/'report.md').exists()

def test_token_cache_is_separate_and_absent_values_remain_visible(tmp_path):
    from analyze import generate_report
    schedule=make_fixture(tmp_path)
    stage=tmp_path/'runs/V1-r1-N/stage1'
    data=json.loads((stage/'complete.json').read_text())
    data['author']['usage']=[{'input_tokens':100,'output_tokens':50,'cached_input_tokens':80,'reasoning_output_tokens':30}]
    (stage/'complete.json').write_text(json.dumps(data))
    (stage/'author.receipt.json').write_text(json.dumps(data['author']))
    result=analyze(tmp_path)
    tokens=result['resource_by_stage']['N'][1]['roles']['author']['tokens']
    assert tokens['input_tokens']['known_sum']==150
    assert tokens['output_tokens']['known_sum']==150
    assert tokens['cached_input_tokens']['known_sum']==80
    assert tokens['cached_input_tokens']['missing']==5
    report=generate_report(result,schedule)
    assert 'Recursos por etapa y rol' in report and 'desconocido' in report


def set_model_receipt(base,role,**updates):
    stage=base/'runs/V1-r1-T/stage1'
    complete=json.loads((stage/'complete.json').read_text())
    complete[role].update(updates)
    (stage/f'{role}.receipt.json').write_text(json.dumps(complete[role]))
    (stage/'complete.json').write_text(json.dumps(complete))


@pytest.mark.parametrize('role',['author','method','review'])
@pytest.mark.parametrize('timed_out',[False,True])
def test_provider_error_never_becomes_comparative_quality(tmp_path,role,timed_out):
    make_fixture(tmp_path)
    set_model_receipt(tmp_path,role,errors=[{'type':'error','message':'synthetic provider failure'}],timed_out=timed_out)
    with pytest.raises(RuntimeError,match='infrastructure.*'+role): analyze(tmp_path)


@pytest.mark.parametrize('role',['author','method','review'])
def test_non_timeout_model_failure_refuses_comparative_quality(tmp_path,role):
    make_fixture(tmp_path)
    set_model_receipt(tmp_path,role,exit_code=1,timed_out=False)
    with pytest.raises(RuntimeError,match='infrastructure.*'+role): analyze(tmp_path)


@pytest.mark.parametrize('role',['author','method','review'])
def test_plain_budget_timeout_remains_a_valid_quality_outcome(tmp_path,role):
    make_fixture(tmp_path)
    set_model_receipt(tmp_path,role,exit_code=124,timed_out=True,errors=[],usage=[])
    data=analyze(tmp_path)['runs']['V1-r1-T']['stages'][1]
    assert data['evaluation']['score']==16/20
    assert data['resources']['usage'][role]['input_tokens'] is None


def test_cli_provider_error_does_not_export_partial_comparison(tmp_path):
    make_fixture(tmp_path)
    set_model_receipt(tmp_path,'author',errors=[{'type':'turn.failed'}],timed_out=True)
    output=tmp_path/'comparison'
    script=Path(__file__).resolve().parents[2]/'analyze.py'
    result=subprocess.run([sys.executable,str(script),'--base',str(tmp_path),'--output',str(output)],capture_output=True)
    assert result.returncode!=0 and not output.exists()


@pytest.mark.parametrize('role',['author','method','review'])
def test_explicit_infrastructure_flag_overrides_a_timeout(tmp_path,role):
    make_fixture(tmp_path)
    set_model_receipt(tmp_path,role,infrastructure_failure=True,exit_code=124,timed_out=True)
    with pytest.raises(RuntimeError,match='infrastructure.*'+role): analyze(tmp_path)
