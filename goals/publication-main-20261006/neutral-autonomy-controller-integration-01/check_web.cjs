const fs=require('fs'),path=require('path'),crypto=require('crypto');
const {chromium}=require('/home/stev/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const origin=process.argv[2],base=__dirname,label=origin.startsWith('https')?'public':'local';
if(!['http://127.0.0.1:4183','https://specorganon.stevenvallejo.com'].includes(origin))throw Error('Unexpected target');
const pub=path.resolve(base,'../../../website/public/resultados/software');
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
(async()=>{const browser=await chromium.launch({headless:true}),checks=[],downloads=[];try{
for(const [viewport,width,height] of [['desktop',1440,1000],['mobile',390,844]]){
const ctx=await browser.newContext({viewport:{width,height},reducedMotion:'reduce',acceptDownloads:true}),page=await ctx.newPage(),errors=[];
page.on('pageerror',e=>errors.push(String(e)));await page.route('**/*',r=>r.request().url().startsWith(origin+'/')?r.continue():r.abort());
const response=await page.goto(origin+'/#avance-dev7',{waitUntil:'networkidle'});if(response.status()!==200)throw Error('HTTP page');
const section=page.locator('section[aria-labelledby="avance-dev7"]');await section.waitFor();const text=await section.innerText();
for(const value of ['0.2.0rc3.dev7','186 pruebas seleccionadas aprobadas','3 controles Docker reales corregidos','40 módulos byte iguales','Codex CLI 0.160.0 y MCP real de 24 herramientas','no hay release pública dev7','Cero nuevas generaciones nativas','competencia no establecida','no hay superioridad demostrada','5/10 entregas y 543/543'])if(!text.includes(value))throw Error('Missing '+value);
const repo='https://github.com/stevenvo780/SpecOrganon/tree/main',links=await page.locator('a[href*="github.com/stevenvo780/SpecOrganon"]').evaluateAll(ns=>ns.map(n=>n.href));if(links.some(x=>!x.startsWith(repo)&&!x.startsWith('https://github.com/stevenvo780/SpecOrganon/blob/main/')))throw Error('Wrong repo branch');
const main=await page.locator('a[href="'+repo+'"]').count();if(main<4)throw Error('Main missing');
if(!(await page.locator('.command-code').innerText()).includes('git clone --branch main'))throw Error('Guidebranch');
const waiting=page.waitForEvent('download');await page.getByRole('button',{name:'Descargar guía operativa',exact:true}).click();const guide=fs.readFileSync(await(await waiting).path(),'utf8');if(!guide.includes('0.2.0rc3.dev7')&&!guide.includes('Main contiene dev7'))throw Error('Stale guide');
if(viewport==='desktop')for(const dir of ['', 'cohorte-nativa-01/','cohorte-nativa-02/','avance-dev3/','avance-dev4/','avance-dev5/','avance-dev6/','cohorte-dev4-terminal/','controles-dev6/']){
const name=dir?'descargas-sha256.json':'descargas-manifest.json',manifest=fs.readFileSync(path.join(pub,dir,name));if(origin.startsWith('https')){const r=await page.request.get(origin+'/resultados/software/'+dir+name);if(r.status()!==200||hash(await r.body())!==hash(manifest))throw Error('Manifest '+dir);}
for(const [name,expected]of Object.entries(JSON.parse(manifest).files)){const r=await page.request.get(origin+'/resultados/software/'+dir+name),digest=hash(await r.body());if(r.status()!==200||digest!==expected)throw Error('Download '+dir+name);downloads.push({file:dir+name,http:200,sha256:digest});}}
const bodyWidth=await page.locator('body').evaluate(e=>e.scrollWidth);if(bodyWidth>width+2||errors.length)throw Error('Runtime/layout '+JSON.stringify({bodyWidth,errors}));
await section.screenshot({path:path.join(base,label+'-dev7-'+viewport+'.png')});checks.push({viewport,width,height,bodyWidth,main_links:main,repository_links_checked:links.length,page_errors:errors,guide_sha256:hash(Buffer.from(guide))});await ctx.close();}
if(downloads.length!==94)throw Error('Downloadcount '+downloads.length);fs.writeFileSync(path.join(base,label+'-web-checks.json'),JSON.stringify({origin,checks,downloads,downloads_verified:94,manifest_count:9},null,2)+'\n');process.stdout.write(JSON.stringify({origin,viewports:2,downloads_verified:94,main_links:checks.map(c=>c.main_links),errors:0})+'\n');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
