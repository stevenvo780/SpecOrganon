"""Frozen author materials and balanced paired design; no evaluator import."""
from __future__ import annotations
import itertools
import random
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
MODEL = 'gpt-6.1-sol'
EFFORT = 'high'
AUTHOR_SECONDS = {'N': 600, 'S': 600, 'T': 480}
METHOD_SECONDS = 120
REVIEW_SECONDS = 120


def make_schedule(seed):
    rng = random.Random(seed)
    blocks = list(itertools.product(['V1', 'V2', 'V3'], [1, 2]))
    orders = list(itertools.permutations('NST'))
    rng.shuffle(blocks); rng.shuffle(orders)
    rows = []
    for block, ((variant, repeat), order) in enumerate(zip(blocks, orders)):
        workload_seed = rng.randrange(1, 2**31)
        for position, arm in enumerate(order):
            rows.append(dict(id=f'{variant}-r{repeat}-{arm}', variant=variant,
                             repeat=repeat, arm=arm, block=block, position=position,
                             workload_seed=workload_seed))
    return rows


def contract(stage):
    text = (BASE/'planning/contract.md').read_text()
    if stage == 1:
        before, rest = text.split('## Cambio común tras la primera entrega', 1)
        text = before + '## Criterios' + rest.split('## Criterios', 1)[1]
    return text


def author_files(arm, stage):
    if arm not in 'NST' or stage not in (1, 2): raise ValueError('invalid arm/stage')
    common = '''Trabaja únicamente en /trial. Lee CONTRACT.md. Entrega solution/backup.py
y solution/README.md. Python 3.12 y biblioteca estándar. Ejecuta ejemplos y
pruebas propias y conserva sus comandos/resultados. No hay intervención humana
durante esta etapa. Puedes decidir detalles técnicos dentro del contrato.
No leas credenciales ni busques otros proyectos, sesiones o soluciones.
No instales dependencias ni investigues en internet. Preserva el contrato.
La revisión técnica externa sucede después de esta entrega y no proporciona
correcciones antes del cierre de la etapa. El siguiente encargo será independiente.
'''
    method = {
        'N': 'Organiza y resuelve el trabajo libremente. No hay método de desarrollo impuesto.\n',
        'S': '''Aplica SDD: documenta especificación, plan, tareas, implementación y
verificación en documentos propios. Deriva criterios antes de implementar y
conserva su trazabilidad y pruebas. Ajusta especificación/plan/tareas si el encargo cambia.
''',
        'T': '''Aplica la skill .agents/skills/specorganon/SKILL.md y sus contratos.
El caso /trial/case ya registra el mandato real del dueño en modo local. Consulta
status, report y next_task mediante el MCP specorganon, registra tu trabajo con
actor agent:author. Usa el MCP para el ledger. Organon está instalado, sin uv run.
No inventes aprobaciones, revisiones ni pruebas. Una sesión independiente revisará
las fases al terminar. Puedes redactar ramas anticipadas mientras los gates están
pendientes; informa las fases bloqueadas sin simular avance. Las decisiones técnicas
son delegadas: declara esa procedencia, no afirmes que el dueño eligió tu arquitectura.
La validación disponible es técnica local; eficacia general o de campo no demostrada.
'''
    }
    files = {'CONTRACT.md': contract(stage), 'AGENTS.md': common + method[arm]}
    if arm == 'T':
        files['.agents/skills/specorganon/SKILL.md'] = (ROOT/'.agents/skills/specorganon/SKILL.md').read_text().replace('uv run organon', 'organon')
        for name in ['metodologia.md', 'workflow_operativo.md', 'uso_local.md']:
            files[f'docs/{name}'] = (ROOT/'docs'/name).read_text()
    return files


def author_argv(arm, stage):
    argv = ['codex', 'exec', '--ephemeral', '--ignore-user-config', '--skip-git-repo-check',
            '--sandbox', 'workspace-write', '-C', '/trial', '--json',
            '-c', f'model="{MODEL}"', '-c', f'model_reasoning_effort="{EFFORT}"',
            '-c', 'approval_policy="never"', '-c', 'web_search="disabled"',
            '-c', 'features.apps=false', '-c', 'features.browser_use=false',
            '-c', 'features.multi_agent_v2=false', '-c', 'features.skip_host_skill_discovery=true']
    if arm == 'T':
        argv += ['-c', 'mcp_servers.specorganon.command="/opt/specorganon/.venv/bin/organon-mcp"',
                 '-c', 'mcp_servers.specorganon.cwd="/trial"',
                 '-c', 'mcp_servers.specorganon.env.ORGANON_ROOT="/trial"']
        for tool in ['put', 'status', 'report', 'next_task', 'gate', 'trace', 'challenge', 'show', 'list_items']:
            argv += ['-c', f'mcp_servers.specorganon.tools.{tool}.approval_mode="approve"']
    return argv + ['-']


def author_prompt(row, stage):
    base = f"Lee AGENTS.md y CONTRACT.md y realiza la entrega. Variante {row['variant']}. "
    if stage == 1:
        return base + 'Construye la primera versión funcional desde cero.\n'
    return base + '''Ahora cambia el requisito: create debe aceptar --max-bytes N,
contando todos los archivos regulares y metadata persistente del repositorio.
Lee el contrato actualizado completo. Conserva las garantías anteriores y adapta
tu solución y las pruebas. No recibes resultados de evaluación reservada.
'''


def review_argv():
    return ['codex', 'exec', '--ephemeral', '--ignore-user-config', '--skip-git-repo-check',
            '--sandbox', 'read-only', '-C', '/trial', '--json', '-c', f'model="{MODEL}"',
            '-c', f'model_reasoning_effort="{EFFORT}"', '-c', 'approval_policy="never"',
            '-c', 'web_search="disabled"', '-c', 'features.apps=false',
            '-c', 'features.browser_use=false', '-c', 'features.multi_agent_v2=false',
            '-c', 'features.skip_host_skill_discovery=true', '-']
