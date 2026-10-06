"""Finite reconnection event fixtures; no provider is called by these tests."""
import json
import pytest
from scripts.controller_native_role import parse_native, NativeRoleError
from test_controller_native_role import codex_transcript


def warning(n=2):
    return {'type':'error','message':f'Reconnecting... {n}/5 (unexpected status 403 Forbidden: synthetic fixture)'}


def stream(events): return '\n'.join(map(json.dumps,events))


def test_same_turn_completion_after_ordered_reconnection_diagnostics_keeps_rejection():
    events=codex_transcript();events[2:2]=[warning(n) for n in range(2,6)]
    diagnostics=[]
    result,usage=parse_native('codex',stream(events),diagnostics=diagnostics)
    assert result=={'verdict':'reject'} and usage=={'input_tokens':12}
    assert [x['attempt'] for x in diagnostics]==[2,3,4,5]
    assert all(x['limit']==5 and len(x['message_sha256'])==64 for x in diagnostics)


@pytest.mark.parametrize('fault',['terminal','arbitrary','extra','after_final','after_complete','before_turn','missing_final','missing_completion','backwards','duplicate','over_limit','different_limit','multiline','tool','invalid_json'])
def test_reconnection_does_not_make_terminal_unknown_or_unbound_stream_successful(fault):
    events=codex_transcript();events.insert(2,warning())
    if fault=='terminal':events.insert(3,{'type':'turn.failed','error':{'message':'Synthetic failure'}})
    elif fault=='arbitrary':events[2]['message']='fatal authentication error'
    elif fault=='extra':events[2]['recoverable']=True
    elif fault=='after_final':events[2],events[3]=events[3],events[2]
    elif fault=='after_complete':events.append(warning(3))
    elif fault=='before_turn':events[1],events[2]=events[2],events[1]
    elif fault=='missing_final':events.pop(3)
    elif fault=='missing_completion':events.pop()
    elif fault=='backwards':events.insert(3,warning(1))
    elif fault=='duplicate':events.insert(3,warning())
    elif fault=='over_limit':events[2]=warning(6)
    elif fault=='different_limit':events[2]['message']=events[2]['message'].replace('/5','/6')
    elif fault=='multiline':events[2]['message']=events[2]['message'].replace('synthetic','synthetic\n')
    elif fault=='invalid_json':events[3]['item']['text']='{"schema":1,invalid}'
    else:events.insert(3,{'type':'item.completed','item':{'id':'tool1','type':'command_execution','text':'synthetic'}})
    diagnostics=[]
    with pytest.raises(NativeRoleError):parse_native('codex',stream(events),diagnostics=diagnostics)
    assert diagnostics==[]
