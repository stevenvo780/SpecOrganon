const fs=require('fs'),path=require('path'),crypto=require('crypto');
const {chromium}=require('/home/stev/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const origin=process.argv[2],base=__dirname,label=origin.startsWith('https')?'public':'local';
if(!['http://127.0.0.1:4183','https://specorganon.stevenvallejo.com'].includes(origin))throw Error('Unexpected target');
const repo='https://github.com/stevenvo780/SpecOrganon/tree/main';
const publicRoot=path.resolve(base,'../../../website/public/resultados/software');
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
(async()=>{
 const browser=await chromium.launch({headless:true});const checks=[],downloads=[];
 try{
  for(const [viewport,width,height] of [['desktop',1440,1000],['mobile',390,844]]){
   const context=await browser.newContext({viewport:{width,height},reducedMotion:'reduce',acceptDownloads:true});
   const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(String(e)));
   await page.route('**/*',r=>r.request().url().startsWith(origin+'/')?r.continue():r.abort());
   const response=await page.goto(origin+'/#cohorte-nativa',{waitUntil:'networkidle'});if(response.status()!==200)throw Error('Page not 200');
   const section=page.locator('section[aria-labelledby="cohorte-nativa"]');
   await section.locator('tbody tr').first().waitFor({state:'attached'});
   if(await section.locator('tbody tr').count()!==10)throw Error('Fixed cohort rows missing');
   const text=await section.innerText();
   const dev6=page.locator('section[aria-labelledby="avance-dev6"]');const dev6text=await dev6.innerText();
   for(const value of ['389 pruebas acotadas pasaron y 3 quedaron omitidas','El wheel dev6 es local y no se libera; el último wheel público es dev5.','No hay smoke MCP nuevo','aceptación posterior se limita a los helpers','infraestructura no concede un ganador','Cero sujetos reservados'])if(!dev6text.includes(value))throw Error('Missing dev6 limit '+value);
   const dev5=page.locator('section[aria-labelledby="avance-dev5"]');const dev5text=await dev5.innerText();
   for(const value of ['328 controles en el host y 328 en el wheel instalado','Tres controles Docker reales con pérdida de respuesta inyectada','No reproducen el timeout natural de 15 segundos','6 intentos cerrados, 2 entregas completas, 10 intentos fijados','104/104','105/105','Dev5 todavía no tiene cohorte nativa.','propuesta pendiente de implementación','tests_executed=false'])if(!dev5text.includes(value))throw Error('Missing dev5 evidence '+value);
   if(await dev5.locator('tbody tr').count()!==10)throw Error('Dev4 snapshot rows absent');
   const dev4=page.locator('section[aria-labelledby="avance-dev4"]');const dev4text=await dev4.innerText();
   for(const value of ['296 controles en el host y 296 en el wheel instalado','nueve llamadas: seis fallos y tres respuestas válidas','No son generaciones de software ni demuestran eficacia de dev4.','45 fuentes vinculadas','no puede reanudar ni migrar esos runs'])if(!dev4text.includes(value))throw Error('Missing dev4 evidence '+value);
   const dev3=page.locator('section[aria-labelledby="avance-dev3"]');const dev3text=await dev3.innerText();
   for(const value of ['193 controles en el host y 193 en el wheel instalado','dev3 no tiene todavía eficacia nativa medida','admission_repair=True','tests_executed=false','schema11'])if(!dev3text.includes(value))throw Error('Missing dev3 limits '+value);
   if(await section.getByText('Entrega completa',{exact:true}).count()!==3)throw Error('Complete attempt missing');
   for(const value of ['10 intentos cerrados, 3 entregas completas, 10 intentos fijados','115/115 queda fuera del denominador','El criterio de fiabilidad del 90% se incumplió: 3/10, un 30%.','104/104','La meta permanece activa'])if(!text.includes(value))throw Error('Missing cohort evidence: '+value);
   if(await page.locator('a[href="'+repo+'"]').count()<4)throw Error('Main entry links absent');
   if(!(await page.locator('.command-code').innerText()).includes('git clone --branch main'))throw Error('Guide wrong branch');
   const downloading=page.waitForEvent('download');await page.getByRole('button',{name:'Descargar guía operativa',exact:true}).click();
   const guide=fs.readFileSync(await (await downloading).path(),'utf8');if(!guide.includes(repo)||!guide.includes('git clone --branch main'))throw Error('Downloaded guide wrong branch');
   const links=await page.locator('a[href*="github.com/stevenvo780/SpecOrganon"]').evaluateAll(nodes=>nodes.map(n=>n.getAttribute('href')));
   if(links.some(h=>!h.startsWith(repo)&&!h.startsWith('https://github.com/stevenvo780/SpecOrganon/blob/main/')))throw Error('Relevant repository link is not main');
   if(viewport==='desktop'){
    for(const [prefix,manifestPath] of [['',path.join(publicRoot,'descargas-manifest.json')],['cohorte-nativa-01/',path.join(publicRoot,'cohorte-nativa-01/descargas-sha256.json')],['cohorte-nativa-02/',path.join(publicRoot,'cohorte-nativa-02/descargas-sha256.json')],['avance-dev3/',path.join(publicRoot,'avance-dev3/descargas-sha256.json')],['avance-dev4/',path.join(publicRoot,'avance-dev4/descargas-sha256.json')],['avance-dev5/',path.join(publicRoot,'avance-dev5/descargas-sha256.json')],['avance-dev6/',path.join(publicRoot,'avance-dev6/descargas-sha256.json')]]){
     const manifest=JSON.parse(fs.readFileSync(manifestPath));
     if(prefix==='avance-dev6/'&&Object.keys(manifest.files).some(n=>n.endsWith('.whl')))throw Error('Local dev6 wheel must not be released');
     if(!prefix&&Object.keys(manifest.files).length!==32)throw Error('Historical download count altered');
     for(const [name,expected] of Object.entries(manifest.files)){
      const r=await page.request.get(origin+'/resultados/software/'+prefix+name);const actual=hash(await r.body());
      if(r.status()!==200||actual!==expected)throw Error('Public download differs '+prefix+name);
      downloads.push({file:prefix+name,http:200,sha256:actual,historical:prefix===''});
     }
    }
   }
   const bodyWidth=await page.locator('body').evaluate(el=>el.scrollWidth);if(bodyWidth>width+2||errors.length)throw Error('Layout/runtime failure '+JSON.stringify({bodyWidth,errors}));
   await section.screenshot({path:path.join(base,label+'-'+viewport+'.png')});
   await dev6.screenshot({path:path.join(base,label+'-dev6-'+viewport+'.png')});
   checks.push({viewport,width,height,bodyWidth,cohort_rows:10,closed:10,completed:3,dev4_snapshot_closed:6,dev4_snapshot_complete:2,dev5_targeted_tests:328,main_links:await page.locator('a[href="'+repo+'"]').count(),repository_links_checked:links.length,guide_sha256:hash(Buffer.from(guide)),page_errors:errors});
   await context.close();
  }
 }finally{await browser.close()}
 const result={schema:1,at:new Date().toISOString(),origin,snapshot_at:'2026-10-06T02:53:19.482908+00:00',dev4_snapshot_at:'2026-10-06T03:43:23.682090+00:00',scope:'actual browser/HTTP checks of published snapshot, no experimental calls',checks,downloads};
 fs.writeFileSync(path.join(base,label+'-web-checks.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
})().catch(e=>{console.error(e.stack);process.exitCode=1});
