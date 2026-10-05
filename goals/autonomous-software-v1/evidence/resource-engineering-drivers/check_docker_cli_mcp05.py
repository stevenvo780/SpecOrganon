import pathlib,subprocess,asyncio,json,time,hashlib
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
root=pathlib.Path('/datos/workspaces/personal/SpecOrganon');base=pathlib.Path('/datos/workspaces/personal/specorganon-validation/autonomous-software-v1');e=root/'goals/autonomous-software-v1/evidence'
image=subprocess.check_output(['docker','image','inspect','specorganon-release:candidate-10','--format','{{.Id}}'],text=True).strip()
assert not (e/'docker-clean-cli-mcp-05-receipt.json').exists(), 'refuse prior clean measurement overwrite'
(base/'docker-clean-cli-mcp-05').mkdir(mode=0o755)
mount='type=bind,src='+str(base/'docker-clean-cli-mcp-05')+',dst=/runs'
argv=['docker','run','--rm','--network','none','--mount',mount,image,'organon','init','/runs/mi-caso','--title','Prueba local','--domain','desarrollo','--approval-policy','local','--actor','human:owner']
r=subprocess.run(argv,capture_output=True,timeout=30);(e/'docker-cli-init-05.stdout').write_bytes(r.stdout);(e/'docker-cli-init-05.stderr').write_bytes(r.stderr);assert r.returncode==0,r.stderr
case=base/'docker-clean-cli-mcp-05/mi-caso/organon.json';before=hashlib.sha256(case.read_bytes()).hexdigest()
async def main():
 args=['run','--rm','-i','--name','specorganon-clean-mcp-05','--network','none','--read-only','--cap-drop=ALL','--security-opt','no-new-privileges','--mount',mount,'-e','ORGANON_ROOT=/runs','-e','TMPDIR=/runs',image,'organon-mcp']
 params=StdioServerParameters(command='docker',args=args)
 with (e/'docker-clean-mcp-05.stderr').open('w') as stderr:
  async with stdio_client(params,errlog=stderr) as (read,write):
   async with ClientSession(read,write) as session:
    initialized=await session.initialize();listing=await session.list_tools();assert any(t.name=='status' for t in listing.tools)
    status=await session.call_tool('status',{'path':'/runs/mi-caso'});assert not status.is_error,status
    report=await session.call_tool('report',{'path':'/runs/mi-caso'});assert not report.is_error,report
    output={'schema':1,'image_id':image,'cli_init_argv':argv,'cli_init_exit_code':r.returncode,'mcp_command':'docker','mcp_args':args,'mcp_initialize':initialized.model_dump(mode='json'),'tool_names':[t.name for t in listing.tools],'status_response':status.model_dump(mode='json'),'report_response':report.model_dump(mode='json'),'case_before_sha256':before,'case_after_sha256':hashlib.sha256(case.read_bytes()).hexdigest(),'scope':'actual installed wheel CLI and stdio MCP; empty local case, not method completion'}
    assert output['case_before_sha256']==output['case_after_sha256']
    (e/'docker-clean-cli-mcp-05-receipt.json').write_text(json.dumps(output,indent=2)+'\n');print('installed CLI and real stdio MCP: PASS; read operations did not mutate ledger')
asyncio.run(main())
