// Built frontend with synthetic API receipts only. No provider or external origin is used.
// Default verifies browser-downloaded files. --http-receipts-only is an explicit
// narrower check and reports native downloads as unverified in its result.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const {createHash} = require('node:crypto');
const {createRequire} = require('node:module');
const webRequire = createRequire(path.resolve(__dirname, '../../web/package.json'));
const {chromium} = webRequire('playwright');
const root = path.resolve(__dirname, '../../web/out');
const artists = {A:'Synthetic artist A',B:'Synthetic artist B'};
const catalog = Array.from({length:8},(_,i)=>({entity_id:`movie-${i}`,name:`Synthetic film ${i}`,release_year:2000+i}));
const identities = {A:{entity_id:'artist-A',name:artists.A,type:'urn:entity:artist'},B:{entity_id:'artist-B',name:artists.B,type:'urn:entity:artist'}};
const usage=(http_attempts,cache_hits=0,reconstructed_steps=0,unknown_attempts=0)=>({http_attempts,cache_hits,reconstructed_steps,unknown_attempts});
const result=()=>({verification_status:'VERIFIED_COMPLETE',provenance:'SYNTHETIC',causal_gate:'INCONCLUSIVE',behavioral_gate:'NOT_EVALUATED',cultural_gate:'NOT_VALIDATED',release_gate:'BLOCKED',qloo_attempts:4,model_attempts:2,external_service_attested:false});
const makeJob=(id)=>({job_id:id,status:'PLANNED',artists,model:'synthetic',operator_mode:'groq',maximum_qloo_requests:4,maximum_model_decisions:2,saved_provider_samples:0,saved_model_packets:0,declared_faults:0,model_load_requests:0,model_metadata_requests:0,plan_sha256:'a'.repeat(64),catalog_sha256:'b'.repeat(64),simulation_only:true,error_class:null,result:null,case_protocol:'cinema-confirmed-discovery-v3',identity_queries:artists,admission_mode:'repeatable-v1',queue_status:null,queue_position:null,not_before:null,provider_stats:{qloo:usage(0),groq:usage(0)}});

async function main(){
  const jobs=new Map();
  const server=http.createServer((req,res)=>{
    const pathname=new URL(req.url,'http://localhost').pathname;
    const verification=pathname.match(/^\/api\/demo\/cases\/jobs\/([^/]+)\/verification$/);
    if(verification){const job=jobs.get(verification[1]);if(!job||!job.result){res.writeHead(404).end();return;}const body=JSON.stringify({job_id:job.job_id,result:job.result});res.writeHead(200,{'Content-Type':'application/json','Content-Length':Buffer.byteLength(body),'Content-Disposition':`attachment; filename="${job.job_id}-verification.json"`});res.end(body);return;}
    const file=path.resolve(root,pathname==='/demo'||pathname==='/demo/'?'demo.html':pathname.slice(1));
    if(!file.startsWith(root+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404).end();return;}
    res.setHeader('Content-Type',({'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml'})[path.extname(file)]||'application/octet-stream');
    fs.createReadStream(file).pipe(res);
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  let browser;
  try{
    const downloadsPath=process.env.AFFINITYQA_TEST_DOWNLOAD_DIR?path.resolve(process.env.AFFINITYQA_TEST_DOWNLOAD_DIR):undefined;
    if(downloadsPath)fs.mkdirSync(downloadsPath,{recursive:true});
    browser=await chromium.launch({headless:true,downloadsPath,...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,args:['--no-sandbox','--disable-dev-shm-usage']}:{})});
    const context=await browser.newContext({acceptDownloads:true,viewport:process.argv.includes('--mobile')?{width:390,height:844}:{width:1280,height:900}});
    const page=await context.newPage(),errors=[],posts=[],reads=new Map(),receiptHashes=[];
    const httpReceiptsOnly=process.argv.includes('--http-receipts-only');
    const capture=async name=>{if(!process.env.AFFINITYQA_TEST_SCREENSHOT_DIR)return;const directory=path.resolve(process.env.AFFINITYQA_TEST_SCREENSHOT_DIR);fs.mkdirSync(directory,{recursive:true});fs.writeFileSync(path.join(directory,name+'.png'),await page.screenshot({fullPage:true}),{flag:'wx'});};
    let finite=false,admissionsBlocked=false,paginationActive=false,paginationReads=0;
    const entry=({job_id,status,artists,legacy_case,read_only})=>({job_id,status,artists,legacy_case,read_only});
    const cap=()=>({configured:true,execution_enabled:true,simulation_only:true,admissions_blocked:admissionsBlocked,operator_mode:'groq',model:'synthetic',catalog,default_artists:artists,cinema_preferences_supported:true,cinema_identity_confirmation_supported:true,cinema_discoveries_supported:true,...(finite?{}:{admission_mode:'repeatable-v1'}),remaining_plans:finite?0:null,remaining_executions:finite?0:null,jobs_truncated:paginationActive,next_cursor_job_id:paginationActive?'repeatable-3':null,jobs:[...jobs.values()].filter(job=>!paginationActive||job.job_id!=='older-owned-case').map(entry)});
    page.on('pageerror',e=>errors.push(e.message));
    await context.route(url=>!(url.hostname==='127.0.0.1'&&/^\/api\/demo\/cases\/jobs\/[^/]+\/verification$/.test(url.pathname)),async route=>{
      const req=route.request(),url=new URL(req.url());
      assert.equal(url.hostname,'127.0.0.1','External browser request forbidden');
      const json=body=>route.fulfill({json:body});
      if(req.method()==='POST')posts.push(url.pathname);
      if(url.pathname==='/healthz')return json({new_cases_configured:true});
      if(url.pathname==='/api/demo/summary')return json({schema_version:1,status:'UNAVAILABLE',pairs:[]});
      if(url.pathname==='/api/demo/cases/session')return json({schema_version:1,csrf_token:'c'.repeat(64),expires_utc:'2099-01-01T00:00:00Z',admission_mode:'repeatable-v1'});
      if(url.pathname==='/api/demo/cases/capabilities')return json(cap());
      if(url.pathname==='/api/demo/cases/jobs/older-than/repeatable-3'){assert.equal(req.method(),'GET');paginationReads+=1;return json({schema_version:1,jobs:[entry(jobs.get('older-owned-case'))],jobs_truncated:false,next_cursor_job_id:null});}
      if(url.pathname==='/api/demo/cases/plans'){
        assert.equal(finite,false,'A finite exhausted session must not request a plan');
        const request=req.postDataJSON();assert.equal(request.confirm_identities,true);assert.equal(request.discover_new_movies,true);
        const job={...makeJob(`repeatable-${jobs.size+1}`),preferences:request.preferences,provider_stats:{}};jobs.set(job.job_id,job);return json(job);
      }
      const match=url.pathname.match(/^\/api\/demo\/cases\/jobs\/([^/]+)(?:\/(execute|confirm-identities|verification))?$/);
      if(match){
        const job=jobs.get(match[1]);assert.ok(job,'Owned case must exist');
        if(match[2]==='execute'){
          assert.equal(job.status,'PLANNED');assert.notEqual(job.read_only,true);
          Object.assign(job,{status:'QUEUED',queue_status:'QUEUED',queue_position:2,not_before:new Date(Date.now()+250).toISOString()});reads.set(job.job_id,0);return json(job);
        }
        if(match[2]==='confirm-identities'){
          assert.equal(job.status,'AWAITING_IDENTITY_CONFIRMATION');assert.deepEqual(req.postDataJSON().selected_entity_ids,{A:'artist-A',B:'artist-B'});
          Object.assign(job,{status:'RUNNING',queue_status:null,queue_position:null,not_before:null,chosen_identities:identities});
          if(job.job_id==='repeatable-2')Object.assign(job,{status:'WAITING_PROVIDER_CAPACITY',queue_status:'WAITING_PROVIDER_CAPACITY',queue_position:1,not_before:new Date(Date.now()+250).toISOString(),saved_provider_samples:4,saved_model_packets:1,provider_stats:{qloo:usage(0,4),groq:usage(1)},progress:{verification_status:'PENDING',successful_profiles:['A'],provenance:'SIMULATION_ONLY',cultural_gate:'NOT_VALIDATED'}});
          return json(job);
        }
        if(match[2]==='verification')return route.continue(); // Chrome downloads a real loopback attachment.
        reads.set(job.job_id,(reads.get(job.job_id)||0)+1);
        if(job.status==='QUEUED')Object.assign(job,{status:'WAITING_PROVIDER_CAPACITY',queue_status:'WAITING_PROVIDER_CAPACITY',queue_position:1});
        else if(job.status==='WAITING_PROVIDER_CAPACITY'&&!job.chosen_identities)Object.assign(job,{status:'AWAITING_IDENTITY_CONFIRMATION',queue_status:null,queue_position:null,not_before:null,identity_receipt_sha256:'d'.repeat(64),identity_candidates:{A:[identities.A],B:[identities.B]},saved_provider_samples:2,provider_stats:{qloo:job.job_id==='repeatable-1'?usage(2):usage(0,2),groq:usage(0)}});
        else if(job.status==='RUNNING'||job.status==='WAITING_PROVIDER_CAPACITY'&&job.chosen_identities)Object.assign(job,{status:'COMPLETE',queue_status:null,queue_position:null,not_before:null,saved_provider_samples:4,saved_model_packets:2,result:result(),provider_stats:{qloo:job.job_id==='repeatable-1'?usage(4):usage(0,4),groq:usage(2)}});
        return json(job);
      }
      if(url.pathname.startsWith('/api/'))throw Error('Unexpected API request '+url.pathname);
      return route.continue();
    });
    const origin=`http://127.0.0.1:${server.address().port}`;
    await page.goto(origin+'/demo#new');
    await page.getByRole('button',{name:'OPEN OR RESTORE MY SESSION',exact:true}).click();
    await page.getByRole('heading',{name:'YOUR MUSICAL INTERESTS',exact:true}).waitFor();
    assert.equal(await page.getByRole('heading',{name:'NEW REVIEW LIMIT REACHED',exact:true}).count(),0);
    for(let n=1;n<=3;n++){
      await page.getByRole('button',{name:'REVIEW A NEW PLAN',exact:true}).click();
      await page.getByRole('status').filter({hasText:/^PLANNED$/}).waitFor();
      await page.getByText('Provider work counters are unavailable for this saved state.',{exact:true}).waitFor();assert.equal(await page.locator('summary').filter({hasText:'INSPECT FRESH, CACHED AND RESTORED PROVIDER WORK'}).count(),0,'Empty counters must not be replaced with fabricated zeros');
      await page.getByRole('button',{name:'FIND ARTISTS',exact:true}).click();
      await page.getByRole('heading',{name:'QUEUED FOR PROVIDER CAPACITY',exact:true}).waitFor();
      assert.equal(await page.getByRole('button',{name:'REVIEW A NEW PLAN',exact:true}).isEnabled(),false,'Queued work must not allow overlapping case creation');
      await page.getByRole('heading',{name:'WAITING FOR PROVIDER CAPACITY',exact:true}).waitFor({timeout:6000});
      if(n===1){
        await page.getByText('Next eligibility estimate:',{exact:false}).waitFor();
        await capture('01-waiting-before-reload');
        const before=posts.filter(p=>!p.endsWith('/session')).length;
        await page.reload();
        await page.getByRole('button',{name:'OPEN OR RESTORE MY SESSION',exact:true}).click();
        await page.getByRole('heading',{name:'CONFIRM YOUR ARTISTS',exact:true}).waitFor();
        assert.equal(posts.filter(p=>!p.endsWith('/session')).length,before,'Restoration must read the selected case without executing it');
      }
      await page.getByRole('heading',{name:'CONFIRM YOUR ARTISTS',exact:true}).waitFor({timeout:6000});
      const confirm=page.getByRole('button',{name:'CONFIRM ARTISTS & START REVIEW',exact:true});
      assert.equal(await confirm.isEnabled(),false,'Identity must never be selected automatically');
      for(const profile of ['A','B'])await page.getByRole('group',{name:'PROFILE '+profile,exact:true}).getByRole('radio').check();
      if(n===1)await capture('02-explicit-artist-selection');
      await confirm.click();
      if(n===2){await page.getByText('Profile A saved · verification pending.',{exact:true}).waitFor();assert.equal(await page.getByRole('heading',{name:'NEW FILM DISCOVERIES',exact:true}).count(),0);await capture('03a-waiting-saved-profile-pending');}
      await page.getByRole('status').filter({hasText:/^COMPLETE$/}).waitFor({timeout:6000});
      await page.getByRole('button',{name:'REVIEW A NEW PLAN',exact:true}).waitFor({state:'visible'});
      const providerSummary=page.locator('summary').filter({hasText:'INSPECT FRESH, CACHED AND RESTORED PROVIDER WORK'});if(!await providerSummary.evaluate(node=>node.parentElement.open))await providerSummary.click();
      await page.getByText(n===1?'QLOO: 4 fresh HTTP attempts · 0 cached responses · 0 restored saved steps · 0 attempts with unknown outcome.':'QLOO: 0 fresh HTTP attempts · 4 cached responses · 0 restored saved steps · 0 attempts with unknown outcome.',{exact:true}).waitFor();
      if(n===2)await capture('03-complete-cached-context');
      const receiptLink=page.getByRole('link',{name:'DOWNLOAD SELECTED VERIFICATION',exact:true});
      assert.equal(await receiptLink.getAttribute('href'),`/api/demo/cases/jobs/repeatable-${n}/verification`);
      let receiptBytes;
      if(httpReceiptsOnly){const response=await page.request.get(origin+await receiptLink.getAttribute('href'));assert.equal(response.status(),200);assert.equal(response.headers()['content-disposition'],`attachment; filename="repeatable-${n}-verification.json"`);receiptBytes=await response.body();}
      else{const downloadPromise=page.waitForEvent('download');await receiptLink.click();const download=await downloadPromise;assert.equal(new URL(download.url()).origin,origin,'Receipt download must stay on the local fixture');const stream=await download.createReadStream(),chunks=[];for await(const chunk of stream)chunks.push(chunk);receiptBytes=Buffer.concat(chunks);}
      const receipt=JSON.parse(receiptBytes.toString('utf8'));assert.equal(receipt.job_id,'repeatable-'+n);assert.equal(receipt.result.verification_status,'VERIFIED_COMPLETE');receiptHashes.push({job_id:receipt.job_id,sha256:createHash('sha256').update(receiptBytes).digest('hex')});
      if(process.env.AFFINITYQA_TEST_SCREENSHOT_DIR)fs.writeFileSync(path.join(path.resolve(process.env.AFFINITYQA_TEST_SCREENSHOT_DIR),receipt.job_id+'-verification.json'),receiptBytes,{flag:'wx'});
      assert.equal(await page.getByRole('heading',{name:'NEW REVIEW LIMIT REACHED',exact:true}).count(),0);
    }
    assert.equal(jobs.size,3,'Three independent cases must survive in one session');
    assert.equal(posts.filter(p=>p.endsWith('/plans')).length,3);assert.equal(posts.filter(p=>p.endsWith('/execute')).length,3);assert.equal(posts.filter(p=>p.endsWith('/confirm-identities')).length,3);
    const older={...makeJob('older-owned-case'),status:'COMPLETE',saved_provider_samples:4,saved_model_packets:2,provider_stats:{qloo:usage(4),groq:usage(2)},result:result()};jobs.set(older.job_id,older);paginationActive=true;
    await page.reload();await page.getByRole('button',{name:'OPEN OR RESTORE MY SESSION',exact:true}).click();await page.getByRole('button',{name:'LOAD EARLIER CASES',exact:true}).click();await page.locator('li').filter({has:page.getByText(older.job_id,{exact:true})}).getByRole('button').click();assert.equal(paginationReads,1);assert.equal(await page.locator('li').filter({has:page.getByText(older.job_id,{exact:true})}).count(),1,'Earlier-case pages must deduplicate by job ID');
    const olderReceiptHref='/api/demo/cases/jobs/older-owned-case/verification';
    const selectedOlderReceipt=page.locator(`a[download][href="${olderReceiptHref}"]`);
    // The click starts an asynchronous owned GET. Wait for that exact case to
    // commit before reloading; another completed case has the same status text.
    await selectedOlderReceipt.waitFor({state:'visible'});
    const beforeOlderRestore=posts.filter(p=>!p.endsWith('/session')).length;await page.reload();await page.getByRole('button',{name:'OPEN OR RESTORE MY SESSION',exact:true}).click();await selectedOlderReceipt.waitFor({state:'visible'});await page.getByRole('status').filter({hasText:/^COMPLETE$/}).waitFor();assert.equal(await page.getByRole('link',{name:'DOWNLOAD SELECTED VERIFICATION',exact:true}).getAttribute('href'),olderReceiptHref);assert.equal(await page.locator('li').filter({has:page.getByText(older.job_id,{exact:true})}).count(),0,'Restored selection must be outside the first page');assert.equal(posts.filter(p=>!p.endsWith('/session')).length,beforeOlderRestore,'Older selected-case restoration must use reads only');await capture('03b-restored-older-owned-case');paginationActive=false;
    const partial={...makeJob('partial-case'),status:'PARTIAL',saved_provider_samples:4,saved_model_packets:1,error_class:'DiscoveryRateLimitError',result:{...result(),verification_status:'VERIFIED_PARTIAL',model_attempts:2},provider_stats:{qloo:usage(0,4),groq:usage(2)}};
    const unknown={...makeJob('unknown-case'),status:'UNKNOWN',provider_stats:{qloo:usage(0,0,2),groq:usage(1,0,0,1)}};
    const legacy={...makeJob('historical-plan'),legacy_case:true,read_only:true};
    const oversize={...makeJob('oversize-case'),status:'FAILED',error_class:'ProviderRequestTooLarge',request_diagnostic:{provider:'groq',window:'tpm',required:10000,capacity:8000,dispatch_started:false,automatic_retry:false}};
    const recordedFailure={...partial,job_id:'recorded-failure-case',error_class:'ProviderRecordedFailure'};
    for(const item of [partial,unknown,legacy,oversize,recordedFailure])jobs.set(item.job_id,item);
    await page.reload();await page.getByRole('button',{name:'OPEN OR RESTORE MY SESSION',exact:true}).click();
    await page.getByRole('heading',{name:'YOUR SAVED CASES',exact:true}).waitFor();
    const history=page.locator('section').filter({has:page.getByRole('heading',{name:'YOUR SAVED CASES',exact:true})}).last();
    const savedCase=id=>history.locator('li').filter({has:page.getByText(id,{exact:true})}).getByRole('button');
    await savedCase(partial.job_id).click();await page.getByText('The model provider reached a rate limit.',{exact:false}).waitFor();
    await capture('04-known-rate-limit-partial');
    await history.getByRole('button',{name:/— UNKNOWN$/}).click();await page.getByRole('heading',{name:'PROVIDER OUTCOME UNKNOWN',exact:true}).waitFor();
    await capture('05-unknown-provider-outcome');
    const beforeUnknown=posts.length;await page.waitForTimeout(3200);assert.equal(posts.length,beforeUnknown,'Unknown sent work must not be retried');
    await history.getByRole('button',{name:/— PLANNED$/}).click();await page.getByRole('heading',{name:'PRESERVED CASE · READ ONLY',exact:true}).waitFor();assert.equal(await page.getByRole('button',{name:'FIND ARTISTS',exact:true}).count(),0);
    await savedCase(oversize.job_id).click();await page.getByRole('heading',{name:'REQUEST EXCEEDS CONFIGURED PROVIDER CAPACITY',exact:true}).waitFor();await page.getByText('GROQ: request requires 10000; configured TPM window capacity is 8000.',{exact:true}).waitFor();await page.getByText('No provider request was sent for this rejected step.',{exact:false}).waitFor();assert.equal(await page.getByRole('heading',{name:'WAITING FOR PROVIDER CAPACITY',exact:true}).count(),0);await capture('06a-rejected-before-dispatch');
    await savedCase(recordedFailure.job_id).click();await page.getByText('A recorded provider attempt failed.',{exact:false}).waitFor();
    const paused={...makeJob('paused-case'),status:'FAILED',error_class:'ProviderAdmissionPaused'},pausedPlan=makeJob('paused-plan');jobs.set(paused.job_id,paused);jobs.set(pausedPlan.job_id,pausedPlan);admissionsBlocked=true;
    await page.reload();await page.getByRole('button',{name:'OPEN OR RESTORE MY SESSION',exact:true}).click();await page.getByRole('heading',{name:'NEW ADMISSIONS PAUSED',exact:true}).waitFor();await page.getByText("The server has paused new work for the owner's review.",{exact:false}).waitFor();assert.equal(await page.getByText("Storage requires the owner's inspection.",{exact:false}).count(),0);assert.equal(await page.getByRole('button',{name:'REVIEW A NEW PLAN',exact:true}).isEnabled(),false);await savedCase(paused.job_id).click();await page.getByText('Provider admissions are paused for owner review.',{exact:false}).waitFor();await savedCase(pausedPlan.job_id).click();assert.equal(await page.getByRole('button',{name:'FIND ARTISTS',exact:true}).isEnabled(),false);await capture('06b-durable-admission-pause');
    finite=true;admissionsBlocked=false;await page.reload();await page.getByRole('button',{name:'OPEN OR RESTORE MY SESSION',exact:true}).click();await page.getByRole('heading',{name:'NEW REVIEW LIMIT REACHED',exact:true}).waitFor();assert.equal(await page.getByRole('button',{name:'REVIEW A NEW PLAN',exact:true}).isEnabled(),false,'Finite legacy exhaustion must remain enforced');
    await capture('06-finite-legacy-exhaustion');
    assert.deepEqual(errors,[]);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
    console.log(JSON.stringify({result:'PASS',scenario:'three repeatable cases, queued reload, explicit identities, cache labels, owned earlier-case pagination, receipts, partial/unknown, pre-dispatch rejection, durable pause and legacy preservation',viewport:process.argv.includes('--mobile')?'mobile':'desktop',independent_completed_cases:3,plan_posts:3,execution_posts:3,confirmation_posts:3,pagination_reads:paginationReads,older_selected_case_restored_by_get:true,pre_dispatch_rejection_verified:true,receipt_verification:httpReceiptsOnly?'HTTP_ATTACHMENT_ONLY_NATIVE_DOWNLOAD_UNVERIFIED':'BROWSER_DOWNLOADED_FILE',receipt_hashes:receiptHashes,provider_calls:0}));
  }finally{if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
}
main().catch(error=>{console.error(error.stack||error.message);process.exitCode=1;});
