"""Installed component probe only; no model invocation, credentials or F."""
import asyncio
import hashlib
import json
from pathlib import Path
import subprocess

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent
IMAGE = 'specorganon-release:0.2.0rc3.dev12'
FLAGS = ['run', '--rm', '--network=none', '--read-only', '--tmpfs', '/tmp:rw,mode=1777']


def run(args, *, stdin=None):
    result = subprocess.run(['docker', *args], input=stdin, text=True, capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError(result.stderr[-4000:])
    return result.stdout


async def main():
    installed = json.loads(run([*FLAGS, IMAGE, 'python', '-I', '-B', '-c',
        "import specorganon, pathlib,hashlib,json,importlib.metadata; "
        "root=pathlib.Path(specorganon.__file__).parent; "
        "print(json.dumps({'version':importlib.metadata.version('specorganon'), 'path':str(root), "
        "'modules':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('*.py')}}))"]))
    expected = {Path(name).name: sha for name, sha in json.loads(
        (ROOT / 'final-1-installed-source-pins.json').read_text()).items()}
    assert installed['modules'] == expected
    assert installed['version'] == '0.2.0rc3.dev12'
    assert '/site-packages/specorganon' in installed['path']
    help_text = run([*FLAGS, IMAGE, 'organon', '--help'])
    assert 'usage:' in help_text
    args = [*FLAGS, '--tmpfs', '/runs:rw,uid=1000,gid=1000,mode=0700',
            '-e', 'ORGANON_ROOT=/runs', '-i', IMAGE, 'organon-mcp']
    async with stdio_client(StdioServerParameters(command='docker', args=args)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [tool.name for tool in tools.tools]
            assert len(names) == 24
    receipt = {'schema': 1, 'scope': 'installed components only, not native qualification',
        'image': run(['image', 'inspect', IMAGE, '--format', '{{.Id}}']).strip(),
        'installed': installed, 'cli_help': True, 'mcp_tool_names': names,
        'network': 'none', 'read_only': True, 'credential_mounts': [],
        'native_model_calls': 0, 'native_T_admission': False,
        'external_F': None, 'goal_achieved': False}
    (ROOT / 'final-1-installed-release-receipt.json').write_text(json.dumps(receipt, sort_keys=True, indent=2)+'\n')
    print(json.dumps({'installed_modules':len(expected), 'CLI':True, 'MCP_tools':len(names)}))


if __name__ == '__main__':
    asyncio.run(main())
