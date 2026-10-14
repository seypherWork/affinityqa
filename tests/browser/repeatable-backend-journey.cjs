// Built frontend + actual repeatable HTTP/storage/runtime; only providers are fake.
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const crypto = require('node:crypto');
const {spawn} = require('node:child_process');
const {createRequire} = require('node:module');
const {chromium} = createRequire(path.resolve(__dirname, '../../web/package.json'))('playwright');

async function main() {
  const args = ['-B', path.join(__dirname, 'serve_repeatable_cases.py'), '--exit-after-seconds', '60'];
  if (process.env.AFFINITYQA_TEST_WEB_ROOT) args.push('--web-root', process.env.AFFINITYQA_TEST_WEB_ROOT);
  const child = spawn(process.env.AFFINITYQA_TEST_PYTHON || 'python', args, {stdio: ['ignore', 'pipe', 'pipe']});
  let output = '', errors = '', origin, closed = false;
  const exit = new Promise(resolve => child.on('close', (code, signal) => {closed=true;resolve({code,signal});}));
  const ready = new Promise((resolve,reject) => {
    child.on('error',reject);
    child.stdout.on('data',data => {
      output += data;
      for (const line of output.split('\n')) {
        try {const value=JSON.parse(line);if(value.ready_origin){origin=value.ready_origin;resolve(origin);}} catch {}
      }
    });
    child.stderr.on('data',data => {errors += data;});
    child.on('close',() => {if(!origin)reject(Error('Repeatable fixture failed to start: '+errors));});
  });
  let browser, page;
  try {
    const url = await Promise.race([ready,new Promise((_,reject)=>setTimeout(()=>reject(Error('Host readiness timeout')),30000))]);
    browser = await chromium.launch({headless:true,
      ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? {executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
        args:['--no-sandbox','--disable-dev-shm-usage']} : {})});
    const context = await browser.newContext({viewport:{width:1280,height:900},acceptDownloads:true});
    page = await context.newPage();
    const pageErrors=[],posts=[];
    page.on('pageerror',error=>pageErrors.push(error.message));
    page.on('request',request=>{if(request.method()==='POST')posts.push(new URL(request.url()).pathname);});
    await page.route('**/*',route=>{
      assert.equal(new URL(route.request().url()).origin,url,'No external browser traffic');
      return route.continue();
    });
    await page.goto(url+'/demo#new');
    await page.getByRole('button',{name:'OPEN OR RESTORE MY SESSION',exact:true}).click();
    await page.getByRole('heading',{name:'YOUR MUSICAL INTERESTS',exact:true}).waitFor();
    const initial=await(await page.request.get(url+'/api/demo/cases/capabilities')).json();
    assert.equal(initial.admission_mode,'repeatable-v1');
    assert.equal(initial.simulation_only,true);
    assert.equal(initial.remaining_executions,null);
    for(const label of ['A','B']) {
      await page.locator('summary').filter({hasText:new RegExp('^PROFILE '+label)}).click();
      await page.getByLabel(`Profile ${label}: ${initial.catalog[0].name}`,{exact:true}).selectOption('favorite');
      await page.getByLabel(`Profile ${label}: ${initial.catalog[19].name}`,{exact:true}).selectOption('exclude');
    }
    const jobs=[],receipts=[],receiptHashes=[];
    const evidenceDir=process.env.AFFINITYQA_TEST_EVIDENCE_DIR;
    if(evidenceDir)fs.mkdirSync(evidenceDir,{recursive:false});
    for(let iteration=0;iteration<2;iteration+=1) {
      await page.getByRole('button',{name:'REVIEW A NEW PLAN',exact:true}).click();
      await page.getByRole('status').filter({hasText:/^PLANNED$/}).waitFor();
      await page.getByRole('button',{name:'FIND ARTISTS',exact:true}).click();
      await page.getByRole('heading',{name:'CONFIRM YOUR ARTISTS',exact:true}).waitFor({timeout:20000});
      const confirm=page.getByRole('button',{name:'CONFIRM ARTISTS & START REVIEW',exact:true});
      assert.equal(await confirm.isEnabled(),false,'Explicit identity choice required for every case');
      for(const label of ['A','B'])await page.getByRole('group',{name:'PROFILE '+label,exact:true}).getByRole('radio').check();
      await confirm.click();
      await page.getByRole('status').filter({hasText:/^COMPLETE$/}).waitFor({timeout:25000});
      const cap=await(await page.request.get(url+'/api/demo/cases/capabilities')).json();
      assert.equal(cap.remaining_executions,null);
      const row=cap.jobs.find(value=>!jobs.includes(value.job_id));
      assert.ok(row,'Each explicit plan creates one different owned job');
      jobs.push(row.job_id);
      const job=await(await page.request.get(url+'/api/demo/cases/jobs/'+row.job_id)).json();
      assert.equal(job.result.verification_status,'VERIFIED_COMPLETE');
      assert.equal(job.result.cultural_gate,'NOT_VALIDATED');
      assert.equal(job.result.provenance,'SIMULATION_ONLY');
      for(const label of ['A','B']) {
        assert.equal(job.result.cinema_results[label].delivered.length,5);
        assert.equal(job.result.cinema_results[label].delivered.includes(initial.catalog[0].entity_id),false);
        assert.equal(job.result.cinema_results[label].delivered.includes(initial.catalog[19].entity_id),false);
      }
      const response=await page.request.get(url+'/api/demo/cases/jobs/'+row.job_id+'/verification');
      assert.equal(response.status(),200);
      assert.match(response.headers()['content-disposition'],/^attachment;/);
      const bytes=await response.body();
      receiptHashes.push(crypto.createHash('sha256').update(bytes).digest('hex'));
      if(evidenceDir)fs.writeFileSync(path.join(evidenceDir,`selected-http-verification-${iteration+1}.json`),bytes,{flag:'wx'});
      const receipt=await response.json();receipts.push(receipt);
      assert.equal(receipt.receipt_sha256,job.receipt_sha256);
      assert.equal('artifact_sha256' in receipt,false);
      assert.equal('source_sha256' in receipt,false);
    }
    const beforePosts=posts.length;
    await page.reload();
    await page.getByRole('button',{name:'OPEN OR RESTORE MY SESSION',exact:true}).click();
    await page.getByRole('status').filter({hasText:/^COMPLETE$/}).waitFor();
    assert.deepEqual(posts.slice(beforePosts),['/api/demo/cases/session'],'Reload restoration only opens ownership, never executes work');
    const restored=await(await page.request.get(url+'/api/demo/cases/jobs/'+jobs[0]+'/verification')).json();
    assert.deepEqual(restored,receipts[0],'Earlier selected verification survives a later case and reload');
    assert.equal(posts.filter(p=>p.endsWith('/plans')).length,2);
    assert.equal(posts.filter(p=>p.endsWith('/execute')).length,2);
    assert.equal(posts.filter(p=>p.endsWith('/confirm-identities')).length,2);
    assert.deepEqual(pageErrors,[]);
    await browser.close();browser=undefined;
    const exitResult=await exit;
    assert.equal(exitResult.code,0,errors);
    const state=output.split('\n').flatMap(line=>{try{return[JSON.parse(line)];}catch{return[];}}).find(v=>'synthetic_model_calls' in v);
    assert.ok(state,'Graceful fixture shutdown must report its actual counters');
    assert.equal(state.real_provider_calls,0);
    assert.equal(state.synthetic_model_calls,4);
    console.log(JSON.stringify({result:'PASS',scenario:'actual repeatable backend and built browser, two same-owner cases',
      verified_owned_jobs:jobs.length,verification_http_attachments:receipts.length,
      selected_http_attachment_sha256:receiptHashes,native_download:'NOT_TESTED',...state}));
  } catch(error) {
    if(page) {
      try {console.error(JSON.stringify({synthetic_browser_body:(await page.locator('body').innerText()).slice(-5000)}));} catch {}
    }
    console.error(JSON.stringify({synthetic_host_output:output.slice(-1500),synthetic_host_errors:errors.slice(-1500)}));
    throw error;
  } finally {
    if(browser)await browser.close();
    if(!closed)child.kill('SIGTERM');
  }
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});
