// Built UI + actual API/store/dispatcher. Provider replies are synthetic.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {spawn}=require('node:child_process');
const {createRequire}=require('node:module');
const {chromium}=createRequire(path.resolve(__dirname,'../../web/package.json'))('playwright');
async function main(){
  const mobile=process.argv.includes('--mobile'),args=['-B',path.join(__dirname,'serve_wide_name_cases.py'),'--exit-after-seconds','90'];
  if(process.env.AFFINITYQA_TEST_WEB_ROOT)args.push('--web-root',process.env.AFFINITYQA_TEST_WEB_ROOT);
  const child=spawn(process.env.AFFINITYQA_TEST_PYTHON||'python',args,{stdio:['ignore','pipe','pipe']});
  let output='',errors='',origin,closed=false,browser,page;
  const exited=new Promise(resolve=>child.on('close',(code,signal)=>{closed=true;resolve({code,signal})}));
  const ready=new Promise((resolve,reject)=>{
    child.on('error',reject);child.stdout.on('data',data=>{output+=data;for(const line of output.split('\n')){try{const value=JSON.parse(line);if(value.ready_origin){origin=value.ready_origin;resolve(origin)}}catch{}}});
    child.stderr.on('data',data=>errors+=data);child.on('close',()=>{if(!origin)reject(Error('Synthetic fixture did not start: '+errors))});
  });
  try{
    const url=await Promise.race([ready,new Promise((_,reject)=>setTimeout(()=>reject(Error('Readiness timeout')),30000))]);
    browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,args:['--no-sandbox','--disable-dev-shm-usage']}:{})});
    const context=await browser.newContext({viewport:mobile?{width:390,height:844}:{width:1440,height:1000},acceptDownloads:true});
    page=await context.newPage();const faults=[],posts=[];
    page.on('pageerror',error=>faults.push(error.message));
    page.on('request',request=>{if(request.method()==='POST')posts.push(new URL(request.url()).pathname)});
    await page.route('**/*',route=>{assert.equal(new URL(route.request().url()).origin,url,'No external traffic');return route.continue()});
    const root=()=>page.locator('section[aria-labelledby="wide-cinema-title"]');
    const openSession=async()=>{const button=root().getByRole('button',{name:/^OPEN OR RESTORE MY SESSION/});await button.click();await button.waitFor({state:'hidden'});await root().getByRole('button',{name:/^(START WITH A FILM|NEW DISCOVERY)$/}).first().waitFor({state:'visible'});};
    const newPlan=async name=>{
      if(!await root().getByLabel('ARTIST NAME',{exact:true}).isVisible()&&!await root().getByLabel('FILM TITLE',{exact:true}).isVisible())await root().getByRole('button',{name:'NEW DISCOVERY',exact:true}).first().click();
      await root().getByRole('button',{name:'START WITH AN ARTIST',exact:true}).click();
      await root().getByLabel('ARTIST NAME',{exact:true}).fill(name);
      await root().getByRole('button',{name:'REVIEW MY DISCOVERY PLAN',exact:true}).click();
      await root().getByRole('button',{name:'FIND MY ARTIST',exact:true}).click();
    };
    const download=async()=>{
      const details=root().locator('summary').filter({hasText:/^INSPECT VERIFICATION & EVIDENCE LIMITS$/});
      if(await details.isVisible()&&!await details.evaluate(el=>el.parentElement.open))await details.click();
      const promise=page.waitForEvent('download');await root().getByRole('link',{name:'DOWNLOAD DISCOVERY VERIFICATION',exact:true}).click();
      const item=await promise;assert.equal(await item.failure(),null);const file=await item.path();assert.ok(file);
      return fs.readFileSync(file);
    };
    await page.goto(url+'/demo#wide');await openSession();await newPlan('Synthetic artist');
    await root().getByRole('heading',{name:'CONFIRM YOUR STARTING POINT',exact:true}).waitFor({timeout:20000});
    const radios=root().getByRole('group',{name:'SELECT ONE ARTIST',exact:true}).getByRole('radio');
    assert.equal(await radios.count(),1,'Unusable alternative must not block or become selectable');
    const confirm=root().getByRole('button',{name:'CONFIRM & DISCOVER FIVE',exact:true});
    assert.equal(await confirm.isEnabled(),false,'Explicit identity selection is required');
    await radios.first().check();await confirm.click();
    await root().getByRole('heading',{name:'INSPIRED BY Synthetic artist',exact:true}).waitFor({timeout:25000});
    assert.equal(await root().locator('li h3').count(),5);
    assert.equal(await root().getByText('ORIGINAL ILLUSTRATION',{exact:true}).count(),5);
    const completeDownload=JSON.parse((await download()).toString());
    assert.equal(completeDownload.result.verification_status,'VERIFIED_COMPLETE');
    assert.equal(completeDownload.result.provenance,'SIMULATION_ONLY');
    const beforeRestore=posts.length;await page.reload();await openSession();
    await root().getByRole('heading',{name:'INSPIRED BY Synthetic artist',exact:true}).waitFor();
    assert.deepEqual(posts.slice(beforeRestore),['/api/demo/cases/session']);
    await newPlan('Only malformed');
    await root().getByRole('heading',{name:'NO COMPLETE DISCOVERY CLAIM',exact:true}).waitFor({timeout:20000});
    assert.equal(await root().getByRole('heading',{name:'EVIDENCE CHANGED',exact:true}).count(),0);
    const partialBytes=await download(),partial=JSON.parse(partialBytes.toString());
    assert.equal(partial.result.verification_status,'VERIFIED_PARTIAL');
    assert.equal(partial.result.status,'INCOMPLETE');assert.equal(partial.result.error_class,'SchemaError');
    const beforePartialRestore=posts.length;await page.reload();await openSession();
    await root().getByRole('heading',{name:'NO COMPLETE DISCOVERY CLAIM',exact:true}).waitFor();
    assert.deepEqual(posts.slice(beforePartialRestore),['/api/demo/cases/session']);
    assert.deepEqual(await download(),partialBytes,'Partial receipt stays byte-identical after reload');
    const cap=await(await page.request.get(url+'/api/demo/cases/capabilities')).json();
    assert.equal(cap.wide_cinema_jobs.length,2);
    assert.equal(cap.wide_cinema_jobs.filter(v=>v.status==='COMPLETE').length,1);
    assert.equal(cap.wide_cinema_jobs.filter(v=>v.status==='PARTIAL').length,1);
    assert.equal(posts.filter(p=>p.endsWith('/execute')).length,2);
    assert.equal(posts.filter(p=>p.endsWith('/confirm-wide')).length,1);
    assert.deepEqual(faults,[]);
    assert.doesNotMatch(await root().textContent(),/INSPECT CASE IDENTIFIERS|PLAN SHA-256|urn:entity:|\b[a-f0-9]{64}\b/i);
    if(process.env.AFFINITYQA_TEST_SCREENSHOT)await page.screenshot({path:process.env.AFFINITYQA_TEST_SCREENSHOT,fullPage:true});
    const receipt={status:'PASS',provenance:'local actual app with synthetic provider replies',mobile,real_provider_calls:0,completed_cases:1,preserved_partial_cases:1,source_bound_films:5,original_illustrations:5,physical_downloads:3,restore_without_redispatch:true,prior_case_preserved:true,unusable_name_excluded:true,explicit_selection_required:true,page_errors:faults};
    if(process.env.AFFINITYQA_TEST_NATIVE_RECEIPT)fs.writeFileSync(process.env.AFFINITYQA_TEST_NATIVE_RECEIPT,JSON.stringify(receipt,null,2),{flag:'wx'});
    console.log(JSON.stringify(receipt));
  }finally{
    if(browser)await browser.close();
    if(!closed)child.kill('SIGTERM');
    await exited;
  }
}
main().catch(error=>{console.error(error.stack||error);process.exitCode=1});
