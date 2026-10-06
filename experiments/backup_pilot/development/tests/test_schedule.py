import importlib.util
from collections import Counter
from pathlib import Path

BASE=Path(__file__).resolve().parents[2]

def module():
    spec=importlib.util.spec_from_file_location('pilot_schedule',BASE/'schedule.py')
    loaded=importlib.util.module_from_spec(spec); spec.loader.exec_module(loaded); return loaded

def test_18_independent_runs_paired_inputs_and_balanced_positions():
    plan=module().make_schedule(17863)
    assert len(plan)==18 and len({r['id'] for r in plan})==18
    assert Counter((r['variant'],r['arm']) for r in plan)=={(v,a):2 for v in ['V1','V2','V3'] for a in ['N','S','T']}
    assert Counter((r['arm'],r['position']) for r in plan)=={(a,p):2 for a in ['N','S','T'] for p in range(3)}
    for variant in ['V1','V2','V3']:
        for repeat in [1,2]:
            rows=[r for r in plan if r['variant']==variant and r['repeat']==repeat]
            assert len({r['workload_seed'] for r in rows})==1
    assert module().make_schedule(17863)==plan

def test_mcp_and_skills_do_not_leak_into_control_arms():
    for arm in ['N','S','T']:
        files=module().author_files(arm,1)
        argv=module().author_argv(arm,1)
        assert '--ignore-user-config' in argv and '--ephemeral' in argv
        if arm!='T':
            assert not any('.agents' in p for p in files)
            assert not any('mcp_servers' in x for x in argv)
        else:
            assert any('.agents' in p for p in files)
            assert any('mcp_servers.specorganon' in x for x in argv)
