const fs=require('fs'),path=require('path'),crypto=require('crypto');
const {chromium}=require('/home/stev/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const origin=process.argv[2];
if(!['http://127.0.0.1:4183','https://specorganon.stevenvallejo.com'].includes(origin))throw Error('Unexpected target');
const repository='https://github.com/stevenvo780/SpecOrganon/tree/main';
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
(async()=>{
 const browser=await chromium.launch({headless:true});const checks=[];
 try{
  for(const [name,width,height] of [['desktop',1440,1000],['mobile',390,844]]){
   const context=await browser.newContext({viewport:{width,height},reducedMotion:'reduce',acceptDownloads:true});
   const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(String(e)));
   await page.route('**/*',r=>r.request().url().startsWith(origin+'/')?r.continue():r.abort());
   const response=await page.goto(origin+'/#empezar',{waitUntil:'networkidle'});if(response.status()!==200)throw Error('Page not200');
   const repositoryLinks=page.locator('a[href="'+repository+'"]');if(await repositoryLinks.count()<4)throw Error('Main repository links missing');
   const commands=await page.locator('.command-code').innerText();
   if(!commands.includes('git clone --branch main https://github.com/stevenvo780/SpecOrganon.git')||!commands.includes('uv sync --frozen --extra dev'))throw Error('Main install commands missing');
   const downloading=page.waitForEvent('download');await page.getByRole('button',{name:'Descargar guía operativa',exact:true}).click();
   const download=await downloading;const guide=fs.readFileSync(await download.path(),'utf8');
   if(!guide.includes('git clone --branch main')||!guide.includes(repository)||!guide.includes('RangeAudit completó nueve fases'))throw Error('Downloaded guide stale');
   if(/corte inicial|objetivo inicial|no completaron las nueve fases/.test(guide))throw Error('Stale guide claims');
   const body=await page.locator('body').innerText();if(/conserva un corte inicial|contiene por ahora el objetivo inicial/.test(body))throw Error('Stale repository notice');
   const data=await (await page.request.get(origin+'/project.json')).json();if(data.repository!==repository)throw Error('Public metadata wrong branch');
   for(const source of data.sources)if(source.url&&source.url.startsWith('https://github.com/')){
    if(!source.url.startsWith('https://github.com/stevenvo780/SpecOrganon/blob/main/'))throw Error('Source link wrong branch');
   }
   const bodyWidth=await page.locator('body').evaluate(e=>e.scrollWidth);if(bodyWidth>width+2||errors.length)throw Error('Layout/runtime failure '+JSON.stringify({bodyWidth,errors}));
   await page.locator('#empezar').screenshot({path:path.join(__dirname,'main-'+(origin.startsWith('https')?'public':'local')+'-'+name+'.png')});
   checks.push({viewport:name,width,height,repository_links_to_main:await repositoryLinks.count(),guide_sha256:hash(Buffer.from(guide)),clone_branch:'main',metadata_branch:'main',body_width:bodyWidth,page_errors:errors});
   await context.close();
  }
 }finally{await browser.close()}
 const r={schema:1,at:new Date().toISOString(),origin,repository,checks};fs.writeFileSync(path.join(__dirname,'main-'+(origin.startsWith('https')?'public':'local')+'-checks.json'),JSON.stringify(r,null,2)+'\n');console.log(JSON.stringify(r));
})().catch(e=>{console.error(e.stack);process.exitCode=1});
