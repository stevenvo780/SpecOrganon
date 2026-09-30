import os
import signal
from pathlib import Path
from specorganon import engine
_append = engine.append_event
_case = Path(os.environ["ORGANON_TEST_CRASH_CASE"]).resolve(strict=True)
def _crash(directory, kind, payload, actor, *, expected_seq=None):
    event = _append(directory, kind, payload, actor, expected_seq=expected_seq)
    if (Path(directory).resolve(strict=True) == _case and kind == "item_put"
            and event["seq"] == 16 and payload["id"] == os.environ["ORGANON_TEST_CRASH_ITEM"]):
        os.kill(os.getpid(), signal.SIGKILL)
    return event
engine.append_event = _crash
