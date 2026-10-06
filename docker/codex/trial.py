"""Run a real Codex inference turn and verify MCP calls plus its persisted ledger."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from specorganon.engine import get_state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', help='Optional model override; otherwise use the Codex default')
    parser.add_argument('--timeout', type=int, default=300)
    args = parser.parse_args()
    login = subprocess.run(['codex', 'login', 'status'], capture_output=True, text=True, timeout=30)
    if login.returncode:
        sys.exit('Autentica primero: docker compose run --rm codex codex login --device-auth')
    run = Path('/workspace/results') / f'codex-trial-{uuid4().hex}'
    run.mkdir()
    case = Path('/workspace/cases') / run.name
    prompt = f'''Prueba técnica acotada de integración Codex/MCP, autorizada por el dueño.
Usa únicamente las herramientas del MCP specorganon para el caso {case}.
1. init: title="Codex Docker MCP integration", domain="software", actor="human:owner",
   approval_policy="local".
2. put p1 kind=problem text="Verificar Codex con MCP real" actor="agent:codex".
3. put a1 kind=actor text="Operador del laboratorio" refs=["p1"] actor="agent:codex".
4. put b1 kind=boundary text="Solo integración técnica en Docker" refs=["p1"] actor="agent:codex".
5. Llama status, gate(phase="frame"), trace(id="b1"), next_task y report.
No ejecutes comandos de shell ni edites archivos directamente. No apruebes normas,
no registres revisiones y no avances fases. Esta prueba termina con frame pendiente
de revisión independiente. Informa las llamadas realizadas y sus resultados reales.'''
    (run / 'prompt.txt').write_text(prompt + '\n')
    argv = ['codex', 'exec', '--skip-git-repo-check', '--json',
            '--sandbox', 'workspace-write', '-c', 'approval_policy="never"',
            '--output-last-message', str(run / 'final.txt')]
    # This owner-authorized integration test permits only its seven MCP tools.
    # `never` rejects tools whose normal policy requires an interactive approval.
    allowed_tools = ['init', 'put', 'status', 'gate', 'trace', 'next_task', 'report']
    argv += ['-c', 'mcp_servers.specorganon.enabled_tools=' + json.dumps(allowed_tools)]
    for tool in allowed_tools:
        argv += ['-c', f'mcp_servers.specorganon.tools.{tool}.approval_mode="approve"']
    if args.model:
        argv += ['--model', args.model]
    argv += ['-']
    timed_out = False
    with (run / 'events.jsonl').open('w') as stdout, (run / 'stderr.txt').open('w') as stderr:
        try:
            process = subprocess.run(argv, input=prompt, text=True, stdout=stdout,
                                     stderr=stderr, timeout=args.timeout)
            exit_code = process.returncode
        except subprocess.TimeoutExpired:
            timed_out, exit_code = True, None
    events = [json.loads(line) for line in (run / 'events.jsonl').read_text().splitlines() if line]
    calls = [e['item'] for e in events if e.get('type') == 'item.completed'
             and e.get('item', {}).get('type') == 'mcp_tool_call'
             and e['item'].get('server') == 'specorganon']
    successful = [c for c in calls if c.get('status') == 'completed'
                  and not c.get('error') and not (c.get('result') or {}).get('isError', False)]
    seen = {c['tool'] for c in successful}
    expected = {'init', 'put', 'status', 'gate', 'trace', 'next_task', 'report'}
    state = get_state(case) if (case / 'organon.json').exists() else None
    passed = (exit_code == 0 and not timed_out and expected <= seen
              and state is not None and set(state['items']) == {'p1', 'a1', 'b1'}
              and state['project']['approval_policy'] == 'local'
              and not state['phases']['frame']['accepted'])
    receipt = {'passed': passed, 'timestamp': datetime.now(timezone.utc).isoformat(),
               'argv': argv, 'exit_code': exit_code, 'timed_out': timed_out,
               'case': str(case), 'successful_mcp_tools': sorted(seen),
               'successful_mcp_call_count': len(successful),
               'events_sha256': hashlib.sha256((run / 'events.jsonl').read_bytes()).hexdigest(),
               'scope': 'Real inference and MCP transport; no field impact or method superiority claim'}
    (run / 'receipt.json').write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'passed': passed, 'results': str(run), 'case': str(case),
                      'successful_mcp_tools': sorted(seen)}, indent=2))
    sys.exit(0 if passed else 1)


if __name__ == '__main__':
    main()
