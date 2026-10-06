const fs=require('fs'),path=require('path'),crypto=require('crypto');
const {chromium}=require('/home/stev/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const origin=process.argv[2],base=__dirname,label=origin.startsWith('https')?'public':'local';
if(!['http://127.0.0.1:4191','https://specorganon.stevenvallejo.com'].includes(origin))throw Error('Unexpected target');
const pub=path.resolve(base,'../../../website/public/resultados/software');
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
(async()=>{const browser=await chromium.launch({headless:true}),checks=[],downloads=[];try{
for(const [viewport,width,height] of [['desktop',1440,1000],['mobile',390,844]]){
const ctx=await browser.newContext({viewport:{width,height},reducedMotion:'reduce',acceptDownloads:true}),page=await ctx.newPage(),errors=[];
page.on('pageerror',e=>errors.push(String(e)));await page.route('**/*',r=>r.request().url().startsWith(origin+'/')?r.continue():r.abort());
let response;try{response=await page.goto(origin+'/#piloto-dev8',{waitUntil:'networkidle'});}catch(e){if(!String(e).includes('ERR_NETWORK_CHANGED'))throw e;fs.appendFileSync(path.join(base,'browser-navigation-transient-errors.jsonl'),JSON.stringify({at:new Date().toISOString(),viewport,error:String(e),scope:'Browser navigation only; not an experiment retry'})+'\n');await page.waitForTimeout(1500);response=await page.goto(origin+'/#piloto-dev8',{waitUntil:'networkidle'});}if(response.status()!==200)throw Error('HTTP page');
const section=page.locator('section[aria-labelledby="avance-dev8"]');await section.waitFor();const text=await section.innerText();
for(const value of ['0.2.0rc3.dev8','156 pruebas seleccionadas aprobadas','41 módulos byte iguales','MCP real de 24 herramientas','380 entradas SHA-256','58663–84841','78620 / 83870 / 105480','95429 / 100553 / 122863','Nunca enviadas','Cero nuevos intentos nativos','sin admisión, freeze completo, calificación, competencia ni superioridad','seis gates FAILED de seis','94 descargas históricas'])if(!text.includes(value))throw Error('Missing '+value);
const repo='https://github.com/stevenvo780/SpecOrganon/tree/main',links=await page.locator('a[href*="github.com/stevenvo780/SpecOrganon"]').evaluateAll(ns=>ns.map(n=>n.href));if(links.some(x=>!x.startsWith(repo)&&!x.startsWith('https://github.com/stevenvo780/SpecOrganon/blob/main/')))throw Error('Wrong repo branch');
const main=await page.locator('a[href="'+repo+'"]').count();if(main<4)throw Error('Main missing');
if(!(await page.locator('.command-code').innerText()).includes('git clone --branch main'))throw Error('Guidebranch');
const waiting=page.waitForEvent('download');await page.getByRole('button',{name:'Descargar guía operativa',exact:true}).click();const guide=fs.readFileSync(await(await waiting).path(),'utf8');if(!guide.includes('ingeniería parcial dev8'))throw Error('Stale guide');
if(viewport==='desktop')for(const dir of ['', 'cohorte-nativa-01/','cohorte-nativa-02/','avance-dev3/','avance-dev4/','avance-dev5/','avance-dev6/','cohorte-dev4-terminal/','controles-dev6/']){
const name=dir?'descargas-sha256.json':'descargas-manifest.json',manifest=fs.readFileSync(path.join(pub,dir,name));if(origin.startsWith('https')){const r=await page.request.get(origin+'/resultados/software/'+dir+name);if(r.status()!==200||hash(await r.body())!==hash(manifest))throw Error('Manifest '+dir);}
for(const [name,expected]of Object.entries(JSON.parse(manifest).files)){const r=await page.request.get(origin+'/resultados/software/'+dir+name),digest=hash(await r.body());if(r.status()!==200||digest!==expected)throw Error('Download '+dir+name);downloads.push({file:dir+name,http:200,sha256:digest});}}
const pilot=page.locator('section[aria-labelledby="piloto-dev7"]');const ptext=await pilot.innerText();
for(const v of ['6 cierres de 6 posiciones fijadas','6 gates fallidos y 0/6 gates completos','648/648 comprobaciones públicas descriptivas','Los seis carecen de auditoría D/G final','common_complete y F externo siguen sin evidencia (null)','19 lanzamientos nativos de roles: 13 autores y 6 revisores','1830,455 segundos','corte parcial report-01 de 2/6 permanece inmutable','1080 nuevos','1087 entradas','No ampliar el presupuesto','sin superioridad demostrada'])if(!ptext.includes(v))throw Error('Missing terminal '+v);
if(await pilot.locator('tbody tr').count()!==6||await pilot.getByText('FAILED: exact canonical request exceeds budget',{exact:true}).count()!==6)throw Error('Wrong terminal rows');
await pilot.screenshot({path:path.join(base,label+'-pilot-'+viewport+'.png')});
const custody=page.locator('section[aria-labelledby="avance-dev9"]');const ctext=await custody.innerText();
for(const v of ['0.2.0rc3.dev9','194 pruebas seleccionadas y 46 subtests','18 controles sintéticos','42 módulos idénticos','MCP real de 24 herramientas','Sin','sin admisión T'])if(v!=='Sin'&&!ctext.includes(v))throw Error('Missing dev9 '+v);
const livecut=page.locator('section[aria-labelledby="piloto-dev8"]');const ltext=await livecut.innerText();
for(const v of ['Seis posiciones originales cerradas de seis','648/648','131246 bytes frente al límite128000','common_complete y F externo son null en los seis','propuesta offline no implementada','1171 archivos RAW','1180 entradas','BATTERY_ADDITION.md'])if(!ltext.includes(v))throw Error('Missing dev8cut '+v);
if(await livecut.locator('tbody tr').count()!==6)throw Error('Wrong partial row count');
const states=await livecut.locator('tbody tr td:nth-child(4)').allTextContents();if(JSON.stringify(states)!==JSON.stringify(['failed','failed','review_ready','failed','review_ready','failed']))throw Error('Wrong partial states');
await custody.screenshot({path:path.join(base,label+'-dev9-'+viewport+'.png')});await livecut.screenshot({path:path.join(base,label+'-dev8-cut-'+viewport+'.png')});
const bodyWidth=await page.locator('body').evaluate(e=>e.scrollWidth);if(bodyWidth>width+2||errors.length)throw Error('Runtime/layout '+JSON.stringify({bodyWidth,errors}));
await section.screenshot({path:path.join(base,label+'-dev8-'+viewport+'.png')});checks.push({viewport,width,height,bodyWidth,main_links:main,repository_links_checked:links.length,page_errors:errors,guide_sha256:hash(Buffer.from(guide))});await ctx.close();}
if(downloads.length!==94)throw Error('Downloadcount '+downloads.length);fs.writeFileSync(path.join(base,label+'-web-checks.json'),JSON.stringify({origin,checks,downloads,downloads_verified:94,manifest_count:9},null,2)+'\n');process.stdout.write(JSON.stringify({origin,viewports:2,downloads_verified:94,main_links:checks.map(c=>c.main_links),errors:0})+'\n');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
