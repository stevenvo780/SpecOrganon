const fs=require('fs');const path=require('path');const crypto=require('crypto');
const {chromium}=require('/home/stev/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const base=__dirname;const origin='http://127.0.0.1:4178';
(async()=>{
 const browser=await chromium.launch({headless:true});let checks=[];
 try{
  for(const [name,width,height] of [['desktop',1440,1000],['mobile',390,844]]){
   const context=await browser.newContext({viewport:{width,height},reducedMotion:'reduce'});const page=await context.newPage();let errors=[];page.on('pageerror',e=>errors.push(String(e)));
   await page.route('**/*',route=>route.request().url().startsWith(origin+'/') ? route.continue():route.abort());
   const response=await page.goto(origin+'/#software-autonomo',{waitUntil:'networkidle'});if(response.status()!==200)throw Error('preview failed');
   const section=page.locator('#software-autonomo');await section.getByText('Las 42 celdas: estado, recursos y dimensiones',{exact:true}).click();
   const table=section.getByRole('table').filter({has:page.getByText('Celda / tarea',{exact:true})});
   const rows=await table.locator('tbody tr').count();if(rows!==42)throw Error('42 fixed cells required');
   const headers=await table.locator('thead th').allTextContents();for(const dimension of ['F','D','G','H'])if(!headers.includes(dimension))throw Error('missing '+dimension);
   const nRows=table.locator('tbody tr').filter({hasText:'Trabajo libre'});if(await nRows.count()!==12)throw Error('N design changed');
   for(const row of await nRows.all())if(await row.locator('td').last().innerText()!=='No aplica')throw Error('H unfairly imposed on N');
   const payload=await (await page.request.get(origin+'/resultados/software/campana-v3.json')).json();if(payload.rows.length!==42 || payload.F_evaluated!==false)throw Error('draft data invalid');
   if(payload.rows.some(r=>Object.values(r.scores).some(s=>s!==null)))throw Error('premature draft score');
   const tableOverflows=await table.evaluate(el=>el.scrollWidth>el.parentElement.clientWidth);const bodyWidth=await page.locator('body').evaluate(el=>el.scrollWidth);if(bodyWidth>width+2)throw Error('page overflow '+bodyWidth+' at '+width);
   const screenshot=path.join(base,name+'.png');await section.getByText('Las 42 celdas: estado, recursos y dimensiones',{exact:true}).click();await page.locator('section[aria-labelledby="software-campaign-title"]').screenshot({path:screenshot});if(errors.length)throw Error('page errors '+errors.join(';'));
   checks.push({viewport:name,width,height,fixed_rows:rows,N_rows:12,H_not_applicable_for_N:true,reserved_scores_withheld:true,body_width:bodyWidth,table_scrolls:tableOverflows,page_errors:errors,screenshot_sha256:crypto.createHash('sha256').update(fs.readFileSync(screenshot)).digest('hex')});await context.close();
  }
 }finally{await browser.close()}
 const value={schema:1,scope:'Actual isolated local browser check; not Vercel publication or completed campaign',url:origin,checked_at:new Date().toISOString(),checks};fs.writeFileSync(path.join(base,'view-checks.json'),JSON.stringify(value,null,2)+'\n');console.log(JSON.stringify(value));
})().catch(e=>{console.error(e.stack);process.exitCode=1});
