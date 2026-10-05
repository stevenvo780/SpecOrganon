const fs=require('fs'),path=require('path'),crypto=require('crypto');
const {chromium}=require('/home/stev/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const base=__dirname,reportPath=path.join(base,'../software-comparison-v3/report.json');
if(!fs.existsSync(reportPath)){console.error('No immutable original report: final browser check not started.');process.exit(1)}
const reportBytes=fs.readFileSync(reportPath),report=JSON.parse(reportBytes);
if(!report.evaluation_complete || report.cells.length!==42)throw Error('original report incomplete');
const origin=process.argv[2]||'http://127.0.0.1:4178';
if(!['http://127.0.0.1:4178','https://specorganon.stevenvallejo.com'].includes(origin))throw Error('unexpected target');
const label=origin.startsWith('https')?'public':'local';
const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const expectedText=s=>s.denominator===0?'No aplica':`${s.pass}/${s.denominator}${s.inconclusive?' · '+s.inconclusive+' inconclusos':''}`;
const difference=v=>`${(100*v.lower).toFixed(1)} a ${(100*v.upper).toFixed(1)} pp`;
(async()=>{
 const browser=await chromium.launch({headless:true});const checks=[];let downloads=[];
 try{
  for(const [viewport,width,height] of [['desktop',1440,1000],['mobile',390,844]]){
   const context=await browser.newContext({viewport:{width,height},reducedMotion:'reduce'});const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(String(e)));
   await page.route('**/*',r=>r.request().url().startsWith(origin+'/')?r.continue():r.abort());
   const response=await page.goto(origin+'/#software-autonomo',{waitUntil:'networkidle'});if(response.status()!==200)throw Error('page not200');
   const section=page.locator('#software-autonomo');await section.getByText('Las 42 celdas: estado, recursos y dimensiones',{exact:true}).click();
   const table=section.getByRole('table').filter({has:page.getByText('Celda / tarea',{exact:true})});if(await table.locator('tbody tr').count()!==42)throw Error('fixed42 rows missing');
   const headers=await table.locator('thead th').allTextContents();
   for(const row of report.cells){
    const tr=table.locator('tbody tr').filter({has:page.getByRole('rowheader',{name:new RegExp('^'+row.id+'\\b')})});if(await tr.count()!==1)throw Error('ambiguous original cell '+row.id);
    for(const d of ['F','D','G','H']){
     const expected=d==='H' && row.method==='N'?'No aplica':expectedText(d==='F'?row.functional.F_total:row.qualitative.scores[d]);
     if(await tr.locator('td').nth(headers.indexOf(d)-1).innerText()!==expected)throw Error('score differs from immutable report: '+row.id+'/'+d);
    }
    if(await tr.locator('td').nth(headers.indexOf('Paquete completo')-1).innerText()!==(row.full_package?'Sí':'No'))throw Error('full package mismatch '+row.id);
   }
   await section.getByText('Entradas válidas e inválidas: diagnóstico funcional',{exact:true}).click();
   const functional=section.getByRole('table').filter({has:page.getByText('Entradas válidas',{exact:true})});if(await functional.locator('tbody tr').count()!==42)throw Error('functional breakdown incomplete');
   for(const row of report.cells){
    const tr=functional.locator('tbody tr').filter({has:page.getByRole('rowheader',{name:new RegExp('^'+row.id+'\\b')})});
    for(const [i,key] of [[0,'F_valid_success'],[1,'F_invalid_rejection']])if(await tr.locator('td').nth(i).innerText()!==expectedText(row.functional[key]))throw Error('valid/invalid score mismatch '+row.id);
   }
   const global=section.getByRole('table').filter({has:page.getByText('Diferencias descriptivas apareadas · media de límites en puntos porcentuales',{exact:true})});if(await global.locator('tbody tr').count()!==Object.keys(report.comparisons).length)throw Error('global pairs missing');
   for(const [name,value] of Object.entries(report.comparisons)){
    const tr=global.locator('tbody tr').filter({has:page.getByRole('rowheader',{name,exact:true})});if(await tr.locator('td').nth(0).innerText()!==String(value.n_blocks)||await tr.locator('td').nth(1).innerText()!==difference(value.mean))throw Error('paired difference mismatch '+name);
   }
   for(const [dimension,text] of [['task','Comparaciones por tarea'],['family','Comparaciones por familia de modelos']]){
    await section.getByText(text,{exact:true}).click();
    for(const [identity,pairs] of Object.entries(report.strata[dimension])){
     const t=section.getByRole('table').filter({has:page.getByText(identity+' · todos los pares del estrato',{exact:true})});if(await t.locator('tbody tr').count()!==Object.keys(pairs).length)throw Error('stratum missing '+identity);
     for(const [name,value] of Object.entries(pairs)){
      const tr=t.locator('tbody tr').filter({has:page.getByRole('rowheader',{name,exact:true})});if(await tr.locator('td').nth(0).innerText()!==String(value.n_blocks)||await tr.locator('td').nth(1).innerText()!==difference(value.mean))throw Error('stratum value mismatch '+identity+'/'+name);
     }
    }
   }
   const dataResponse=await page.request.get(origin+'/resultados/software/campana-v3.json');const data=await dataResponse.json();if(data.rows.length!==42||data.F_evaluated!==true)throw Error('final data missing');
   const reportResponse=await page.request.get(origin+'/resultados/software/campana-v3-informe.json');if(reportResponse.status()!==200||hash(await reportResponse.body())!==hash(reportBytes))throw Error('report download differs');
   if(viewport==='desktop'){
    const manifest=JSON.parse(fs.readFileSync(path.join(base,'web/public/resultados/software/descargas-manifest.json')));
    for(const [name,sha] of Object.entries(manifest.files)){
     const url=origin+'/resultados/software/'+name;const response=await page.request.get(url);if(response.status()!==200)throw Error('download failed '+name);const actual=hash(await response.body());if(actual!==sha)throw Error('download hash mismatch '+name);downloads.push({name,http:200,sha256:actual});
    }
   }
   const bodyWidth=await page.locator('body').evaluate(el=>el.scrollWidth);if(bodyWidth>width+2)throw Error('body overflow at '+viewport);
   if(errors.length)throw Error('browser errors '+errors.join(';'));
   for(const detail of await section.locator('details[open]').all())await detail.locator('summary').click();
   const screenshot=path.join(base,'final-'+label+'-'+viewport+'.png');await section.screenshot({path:screenshot});checks.push({viewport,width,height,rows_checked_against_original_report:42,functional_valid_invalid_rows:42,global_comparisons:Object.keys(report.comparisons).length,strata_tables:5,H_not_applicable_for_N:true,full_package_matches:true,body_width:bodyWidth,page_errors:errors,screenshot_sha256:hash(fs.readFileSync(screenshot))});await context.close();
  }
 }finally{await browser.close()}
 const receipt={schema:1,scope:'actual final browser checks against immutable original report; no model or subject calls',at:new Date().toISOString(),origin,original_report_sha256:hash(reportBytes),checks,downloads};fs.writeFileSync(path.join(base,'final-'+label+'-view-checks.json'),JSON.stringify(receipt,null,2)+'\n');console.log(JSON.stringify(receipt));
})().catch(e=>{console.error(e.stack);process.exitCode=1});
