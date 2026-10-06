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
   if(await section.locator('tbody tr').count()!==10)throw Error('Fixed cohort rows missing');
   const text=await section.innerText();
   for(const value of ['1 intento cerrado, 0 generaciones completas, 10 intentos fijados','115/115 queda fuera del denominador','phase item resource admission exceeded: compare','Sin iniciar en esta foto','La meta permanece activa'])if(!text.includes(value))throw Error('Missing cohort evidence: '+value);
   if(await page.locator('a[href="'+repo+'"]').count()<4)throw Error('Main entry links absent');
   if(!(await page.locator('.command-code').innerText()).includes('git clone --branch main'))throw Error('Guide wrong branch');
   const downloading=page.waitForEvent('download');await page.getByRole('button',{name:'Descargar guía operativa',exact:true}).click();
   const guide=fs.readFileSync(await (await downloading).path(),'utf8');if(!guide.includes(repo)||!guide.includes('git clone --branch main'))throw Error('Downloaded guide wrong branch');
   const links=await page.locator('a[href*="github.com/stevenvo780/SpecOrganon"]').evaluateAll(nodes=>nodes.map(n=>n.getAttribute('href')));
   if(links.some(h=>!h.startsWith(repo)&&!h.startsWith('https://github.com/stevenvo780/SpecOrganon/blob/main/')))throw Error('Relevant repository link is not main');
   if(viewport==='desktop'){
    for(const [prefix,manifestPath] of [['',path.join(publicRoot,'descargas-manifest.json')],['cohorte-nativa-01/',path.join(publicRoot,'cohorte-nativa-01/descargas-sha256.json')]]){
     const manifest=JSON.parse(fs.readFileSync(manifestPath));
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
   checks.push({viewport,width,height,bodyWidth,cohort_rows:10,closed:1,completed:0,main_links:await page.locator('a[href="'+repo+'"]').count(),repository_links_checked:links.length,guide_sha256:hash(Buffer.from(guide)),page_errors:errors});
   await context.close();
  }
 }finally{await browser.close()}
 const result={schema:1,at:new Date().toISOString(),origin,snapshot_at:'2026-10-06T01:55:11.147329+00:00',scope:'actual browser/HTTP checks of published snapshot, no experimental calls',checks,downloads};
 fs.writeFileSync(path.join(base,label+'-web-checks.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
})().catch(e=>{console.error(e.stack);process.exitCode=1});
