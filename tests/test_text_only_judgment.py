"""Text-only judgment guard controls, not genuine model reviews."""
import pytest
from scripts.controller_native_role import validate_result, NativeRoleError
from specorganon import engine
from specorganon.role_jobs import _json
from specorganon.software_controller import ControllerError
from test_software_controller import controller, SyntheticTransport, frame_response


@pytest.mark.parametrize('claimed',['absent',True,0,None,'false',[],{}])
def test_bridge_and_controller_reject_invented_or_missing_test_execution_claim(tmp_path,claimed):
    c=controller(tmp_path,SyntheticTransport(frame_response()));c.step()
    response={'schema':1,'verdict':'accept','reason':'Synthetic text-only judgment','findings':[]}
    if claimed!='absent':response['tests_executed']=claimed
    with pytest.raises(NativeRoleError):validate_result(response,'review')
    c.transport.result=response;before=(c.case/'organon.json').read_bytes()
    with pytest.raises(ControllerError,match='tests_executed=false'):c.step()
    assert (c.case/'organon.json').read_bytes()==before
    assert not engine.get_state(c.case)['phases']['frame']['accepted']
    assert len(_json(c.root/'progress.json')['history'])==1
