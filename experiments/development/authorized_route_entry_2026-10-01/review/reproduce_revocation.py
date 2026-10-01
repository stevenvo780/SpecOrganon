"""Pure fake-transport reproduction of scheduling-time operator revocation."""

import hashlib
import json
from pathlib import Path
import sys
import threading
from unittest.mock import patch


def main():
    root = Path(__file__).resolve().parents[4]
    sys.path.insert(0, str(root / "scripts"))
    import authorized_coordinated_runtime as entry

    called = []
    state = {"approved": True}

    class Transport:
        def send(self, payload, *, timeout_seconds):
            called.append({"approved_at_IO": state["approved"]})
            return {"synthetic": "result"}

    def guard():
        if not state["approved"]:
            raise entry.AuthorizedRouteError("declaration_changed")

    original_thread = threading.Thread

    class RevokingThread:
        def __init__(self, *args, **kwargs):
            self.thread = original_thread(*args, **kwargs)

        def start(self):
            state["approved"] = False
            self.thread.start()

    with patch.object(entry.threading, "Thread", RevokingThread):
        try:
            entry.BoundedResponsesTransport(Transport(), guard, max_wait_seconds=1).send(
                {"model": "fixture"}, timeout_seconds=1)
            outcome = "accepted"
        except entry.AuthorizedRouteError as error:
            outcome = str(error)
    print(json.dumps({"probe": "operator gate revoked between outer guard and worker operation",
                      "fake_send_calls": called, "result_error": outcome,
                      "source_sha256": hashlib.sha256((root / "scripts/authorized_coordinated_runtime.py").read_bytes()).hexdigest(),
                      "scope": "PURE protocol proxy with fake transport; no API, credentials, runtime or real authorization accessed"}))


if __name__ == "__main__":
    main()
