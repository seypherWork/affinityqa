// Built UI + actual owned API/storage/runtime; only provider responses are synthetic.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const {spawn}=require('node:child_process');
const {createRequire}=require('node:module');
const {chromium}=createRequire(path.resolve(__dirname,'../../web/package.json'))('playwright');

async function main(){
  const mobile=process.argv.includes('--mobile');
  const args=['-B',path.join(__dirname,'serve_open_movie_cases.py'),'--exit-after-seconds','60'];
  if(process.env.AFFINITYQA_TEST_WEB_ROOT)args.push('--web-root',process.env.AFFINITYQA_TEST_WEB_ROOT);
  const child=spawn(process.env.AFFINITYQA_TEST_PYTHON||'python',args,{stdio:['ignore','pipe','pipe']});
  let output='',errors='',origin,closed=false,browser,page;
  const exit=new Promise(resolve=>child.on('close',(code,signal)=>{closed=true;resolve({code,signal})}));
  const ready=new Promise((resolve,reject)=>{
    child.on('error',reject);child.stdout.on('data',data=>{output+=data;for(const line of output.split('\n')){try{const value=JSON.parse(line);if(value.ready_origin){origin=value.ready_origin;resolve(origin)}}catch{}}});
    child.stderr.on('data',data=>errors+=data);child.on('close',()=>{if(!origin)reject(Error('Local fixture failed: '+errors))});
  });
  try{
    const url=await Promise.race([ready,new Promise((_,reject)=>setTimeout(()=>reject(Error('Readiness timeout')),30000))]);
    browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,args:['--no-sandbox','--disable-dev-shm-usage']}: {})});
    const context=await browser.newContext({viewport:mobile?{width:390,height:844}:{width:1440,height:1000},acceptDownloads:true});
    page=await context.newPage();const pageErrors=[],posts=[];let dropPlanResponse=false;
    page.on('pageerror',error=>pageErrors.push(error.message));
    page.on('request',request=>{if(request.method()==='POST')posts.push(new URL(request.url()).pathname)});
    await page.route('**/*',async route=>{
      assert.equal(new URL(route.request().url()).origin,url,'No external traffic');
      if(dropPlanResponse&&route.request().method()==='POST'&&new URL(route.request().url()).pathname==='/api/demo/cases/open-movies/plans'){
        dropPlanResponse=false;await route.fetch();return route.abort('failed');
      }
      return route.continue();
    });
    await page.goto(url+'/demo#open');
    const discovery=page.locator('section[aria-labelledby="open-movie-title"]');
    await discovery.getByRole('heading',{name:'FIND YOUR NEXT FIVE',exact:true}).waitFor();
    await discovery.getByRole('button',{name:/^OPEN OR RESTORE MY SESSION/}).click();
    await page.getByLabel('FILM TITLE',{exact:true}).fill('John Wick');
    await page.getByLabel('Your direction (optional)',{exact:true}).fill('A fast action film with a tense pace.');
    await page.getByRole('button',{name:'REVIEW MY DISCOVERY PLAN',exact:true}).click();
    await page.getByRole('button',{name:'FIND MY FILM',exact:true}).waitFor();
    assert.equal(posts.filter(p=>p.endsWith('/execute')).length,0);
    await page.getByRole('button',{name:'FIND MY FILM',exact:true}).click();
    await page.getByRole('heading',{name:'WHICH FILM DID YOU MEAN?',exact:true}).waitFor({timeout:20000});
    const confirm=page.getByRole('button',{name:'CONFIRM FILM & DISCOVER FIVE',exact:true});
    assert.equal(await confirm.isEnabled(),false,'No automatic title/year selection');
    await page.getByRole('group',{name:'SELECT ONE FILM',exact:true}).getByRole('radio').first().check();
    // Preserve the manually selected identity across a reload; never auto-confirm.
    const beforeReload=posts.length;await page.reload();
    await discovery.getByRole('button',{name:/^OPEN OR RESTORE MY SESSION/}).click();
    await confirm.waitFor();assert.equal(await confirm.isEnabled(),true);
    assert.deepEqual(posts.slice(beforeReload),['/api/demo/cases/session']);
    await confirm.click();
    await page.getByRole('heading',{name:/^BEYOND /}).waitFor({timeout:25000});
    assert.equal(await page.locator('ol').filter({has:page.locator('li h3')}).first().locator('li h3').count(),5);
    const cap=await(await page.request.get(url+'/api/demo/cases/capabilities')).json();
    assert.equal(cap.jobs.length,0);assert.equal(cap.open_movie_jobs.length,1);
    const job=await(await page.request.get(url+'/api/demo/cases/jobs/'+cap.open_movie_jobs[0].job_id)).json();
    assert.equal(job.status,'COMPLETE');assert.equal(job.result.provenance,'SIMULATION_ONLY');
    assert.equal(job.result.open_movie_results.delivered.length,5);assert.equal(job.saved_model_packets,1);
    const link=page.getByRole('link',{name:'DOWNLOAD DISCOVERY VERIFICATION',exact:true});
    await page.locator('summary').filter({hasText:/^INSPECT VERIFICATION & EVIDENCE LIMITS$/}).click();
    const downloadEvent=page.waitForEvent('download');await link.click();const download=await downloadEvent;
    assert.equal(await download.failure(),null);const bytes=fs.readFileSync(await download.path());const receipt=JSON.parse(bytes);
    if(process.env.AFFINITYQA_TEST_NATIVE_RECEIPT)fs.writeFileSync(process.env.AFFINITYQA_TEST_NATIVE_RECEIPT,bytes,{flag:'wx'});
    assert.equal(receipt.job_id,job.job_id);assert.deepEqual(receipt.result.open_movie_results,job.result.open_movie_results);
    const readOnlyStart=posts.length;await page.reload();
    await discovery.getByRole('button',{name:/^OPEN OR RESTORE MY SESSION/}).click();
    await page.getByRole('heading',{name:/^BEYOND /}).waitFor();
    assert.deepEqual(posts.slice(readOnlyStart),['/api/demo/cases/session']);
    const restored=await(await page.request.get(url+'/api/demo/cases/jobs/'+job.job_id+'/verification')).json();
    assert.deepEqual(restored,receipt);
    const switchStart=posts.length;
    await page.getByRole('button',{name:/^02 \/ MUSIC & FILMS/}).click();
    await page.getByRole('heading',{name:'BUILD YOUR NEXT WATCH',exact:true}).waitFor();
    await page.getByRole('button',{name:/^01 \/ START WITH A FILM/}).click();
    await page.getByRole('heading',{name:/^BEYOND /}).waitFor();
    assert.equal(posts.length,switchStart,'Switching modes retains discovery without another POST');
    assert.equal(posts.filter(p=>p.endsWith('/plans')).length,1);
    assert.equal(posts.filter(p=>p.endsWith('/execute')).length,1);
    assert.equal(posts.filter(p=>p.endsWith('/confirm-movie')).length,1);
    // The server commits a plan, but the browser loses its response. Recovery
    // must read owned history rather than issuing that mutation again.
    await page.getByLabel('FILM TITLE',{exact:true}).fill('Second synthetic film');dropPlanResponse=true;
    await page.getByRole('button',{name:'REVIEW MY DISCOVERY PLAN',exact:true}).click();
    await page.getByRole('button',{name:'CHECK CURRENT STATUS',exact:true}).waitFor();
    await page.getByRole('button',{name:'CHECK CURRENT STATUS',exact:true}).click();
    await page.getByRole('button',{name:'Second synthetic film PLANNED',exact:true}).click();
    await page.getByRole('button',{name:'FIND MY FILM',exact:true}).waitFor();
    assert.equal(posts.filter(p=>p.endsWith('/plans')).length,2,'Lost response does not repeat plan admission');
    assert.equal(posts.filter(p=>p.endsWith('/execute')).length,1,'Recovered plan does not execute automatically');
    await page.getByRole('button',{name:'John Wick COMPLETE',exact:true}).click();
    await page.getByRole('heading',{name:/^BEYOND /}).waitFor();
    assert.deepEqual(pageErrors,[]);
    if(process.env.AFFINITYQA_TEST_SCREENSHOT)await page.screenshot({path:process.env.AFFINITYQA_TEST_SCREENSHOT,fullPage:true});
    await browser.close();browser=undefined;
    const ended=await exit;assert.equal(ended.code,0,errors);
    const audit=output.split('\n').flatMap(line=>{try{return[JSON.parse(line)]}catch{return[]}}).find(v=>'synthetic_model_calls' in v);
    assert.ok(audit);assert.equal(audit.synthetic_qloo_calls,2);assert.equal(audit.synthetic_model_calls,1);
    console.log(JSON.stringify({result:'PASS',viewport:mobile?'mobile':'desktop',native_download_bytes:bytes.length,
      native_download_sha256:crypto.createHash('sha256').update(bytes).digest('hex'),reloads_without_execution:2,
      modes_retained:true,lost_plan_response_recovered_without_repost:true,...audit}));
  }catch(error){
    if(page)try{console.error(JSON.stringify({synthetic_body:(await page.locator('body').innerText()).slice(-5500)}))}catch{}
    console.error(JSON.stringify({synthetic_host_output:output.slice(-1500),synthetic_host_errors:errors.slice(-1500)}));throw error;
  }finally{if(browser)await browser.close();if(!closed)child.kill('SIGTERM')}
}
main().catch(error=>{console.error(error.message);process.exitCode=1});
