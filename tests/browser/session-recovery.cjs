// Browser regression over built assets with synthetic API responses only.
// Requires Playwright and its Chromium browser. No provider is contacted.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const {createRequire} = require('node:module');
const webRequire = createRequire(path.resolve(__dirname, '../../web/package.json'));
const {chromium} = webRequire('playwright');

const root = path.resolve(__dirname, '../../web/out');
const jobId = '20261013T000000Z-00000000';
const artists = {A: 'Synthetic artist A', B: 'Synthetic artist B'};
const job = {
  job_id: jobId, status: 'STARTED', artists, model: 'synthetic',
  operator_mode: 'groq', maximum_qloo_requests: 4, maximum_model_decisions: 39,
  saved_provider_samples: 0, saved_model_packets: 0, declared_faults: 3,
  plan_sha256: 'a'.repeat(64), catalog_sha256: 'b'.repeat(64),
  simulation_only: true, error_class: null, result: null,
};
const capabilities = {
  configured: true, execution_enabled: true, simulation_only: true,
  remaining_plans: 1, remaining_executions: 0, model: 'synthetic',
  operator_mode: 'groq', catalog: [], jobs: [{job_id: jobId, status: 'STARTED', artists}],
};

async function recoverThroughSavedHistory(browser, origin, mobile, openDifferentCase = false) {
  const page = await browser.newPage({viewport: mobile ? {width: 390, height: 844} : {width: 1280, height: 900}});
  const saved = {...job, job_id: 'synthetic-lost-execute-response', status: 'PLANNED'};
  const other = {...job, job_id: 'other-completed-case', status: 'COMPLETE', artists: {A: 'Other saved A', B: 'Other saved B'}};
  const posts = [], errors = [];
  let capabilitiesReads = 0, statusReads = 0;
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', route => {
    const request = route.request(), url = new URL(request.url());
    assert.equal(url.origin, origin, 'External browser request forbidden');
    const json = body => route.fulfill({json: body});
    if (request.method() === 'POST') posts.push(url.pathname);
    if (url.pathname === '/healthz') return json({new_cases_configured: true});
    if (url.pathname === '/api/demo/summary') return json({schema_version: 1, status: 'UNAVAILABLE', pairs: []});
    if (url.pathname === '/api/demo/cases/session') return json({schema_version: 1, csrf_token: 'c'.repeat(64), expires_utc: '2099-01-01T00:00:00Z'});
    if (url.pathname === '/api/demo/cases/capabilities') {
      capabilitiesReads += 1;
      return json({...capabilities, remaining_plans: null, remaining_executions: null, admission_mode: 'repeatable-v1', default_artists: artists, jobs: [saved, other].map(({job_id, status, artists}) => ({job_id, status, artists}))});
    }
    if (url.pathname === '/api/demo/cases/jobs/' + saved.job_id) {
      statusReads += 1;
      if (saved.status === 'STARTED') saved.status = 'COMPLETE';
      return json(saved);
    }
    if (url.pathname === '/api/demo/cases/jobs/' + other.job_id) return json(other);
    if (url.pathname === '/api/demo/cases/jobs/' + saved.job_id + '/execute') {
      assert.equal(saved.status, 'PLANNED', 'Execution must be admitted only once');
      saved.status = 'STARTED';
      return route.fulfill({status: 503, json: {error: 'Synthetic lost execution response'}});
    }
    if (url.pathname.startsWith('/api/')) throw Error('Unexpected API request: ' + url.pathname);
    return route.continue();
  });
  try {
    await page.goto(origin + '/demo#new');
    await page.getByRole('button', {name: 'OPEN OR RESTORE MY SESSION', exact: true}).click();
    await page.getByRole('button', {name: /Synthetic artist A \/ Synthetic artist B — PLANNED/}).click();
    await page.getByRole('button', {name: 'START THIS REVIEWED CLOUD PLAN', exact: true}).click();
    await page.getByText('Synthetic lost execution response', {exact: true}).waitFor();
    assert.equal(await page.getByRole('button', {name: 'REVIEW A NEW PLAN', exact: true}).isEnabled(), false);
    // Both reopening the original and inspecting another case must retain recovery.
    await page.getByRole('button', {name: openDifferentCase ? /Other saved A \/ Other saved B — COMPLETE/ : /Synthetic artist A \/ Synthetic artist B — PLANNED/}).click();
    await page.getByRole('status').filter({hasText: /^COMPLETE$/}).waitFor();
    assert.equal(await page.getByText('Synthetic lost execution response', {exact: true}).count(), 0);
    assert.equal(await page.getByRole('button', {name: 'REVIEW A NEW PLAN', exact: true}).isEnabled(), false, 'Reading history must not silently resolve mutation uncertainty');
    const statusControl = page.getByRole('button', {name: 'CHECK CURRENT STATUS', exact: true});
    assert.equal(await statusControl.count(), 1, 'Uncertain response must retain its recovery control after reading saved history');
    await page.getByText('The response is uncertain.', {exact: false}).waitFor();
    const before = {posts: posts.length, capabilitiesReads, statusReads};
    await statusControl.click();
    await page.waitForFunction(() => [...document.querySelectorAll('button')].some(button => button.textContent.trim().startsWith('REVIEW A NEW PLAN') && !button.disabled));
    assert.ok(capabilitiesReads > before.capabilitiesReads && statusReads > before.statusReads, 'Explicit recovery must refresh capabilities and the selected case');
    assert.equal(posts.length, before.posts, 'Status recovery must not repeat any mutation');
    assert.equal(posts.filter(value => value.endsWith('/execute')).length, 1);
    assert.equal(await page.locator('dd').filter({hasText: /^synthetic-lost-execute-response$/}).count(), 1, 'Recovery must restore the original uncertain case, even after selecting another');
    assert.equal(await statusControl.count(), 0, 'Recovered uncertainty should clear');
    assert.deepEqual(errors, []);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
    console.log(JSON.stringify({result: 'PASS', scenario: 'lost execution response recovered through saved history and explicit status', selected_different_case: openDifferentCase, viewport: mobile ? 'mobile' : 'desktop', execution_posts: 1, recovery_mutations: 0, provider_calls: 0}));
  } finally {
    await page.close();
  }
}

async function recoverPlanAndSwitchMode(browser, origin, mobile, deferRestoration = false) {
  const page = await browser.newPage({viewport: mobile ? {width: 390, height: 844} : {width: 1280, height: 900}});
  const completed = {...job, job_id: 'completed-discovery-case', status: 'COMPLETE', case_protocol: 'cinema-confirmed-discovery-v3', admission_mode: 'repeatable-v1', maximum_model_decisions: 2, declared_faults: 0};
  const other = {...job, job_id: 'completed-integrity-case', status: 'COMPLETE', artists: {A: 'Other integrity A', B: 'Other integrity B'}};
  const jobs = [completed, other], posts = [], errors = [];
  let statusReads = 0;
  let releaseRestore, restoreStarted;
  const delayedRestore = new Promise(resolve => { releaseRestore = resolve; });
  const restorationStarted = new Promise(resolve => { restoreStarted = resolve; });
  const catalog = Array.from({length: 20}, (_, index) => ({entity_id: 'movie-' + index, name: 'Synthetic film ' + index, release_year: 2000 + index}));
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', route => {
    const request = route.request(), url = new URL(request.url());
    assert.equal(url.origin, origin, 'External browser request forbidden');
    const json = body => route.fulfill({json: body});
    if (request.method() === 'POST') posts.push(url.pathname);
    if (url.pathname === '/healthz') return json({new_cases_configured: true});
    if (url.pathname === '/api/demo/summary') return json({schema_version: 1, status: 'UNAVAILABLE', pairs: []});
    if (url.pathname === '/api/demo/cases/session') return json({schema_version: 1, csrf_token: 'c'.repeat(64), expires_utc: '2099-01-01T00:00:00Z'});
    if (url.pathname === '/api/demo/cases/capabilities') return json({...capabilities, remaining_plans: null, remaining_executions: null, admission_mode: 'repeatable-v1', default_artists: artists, catalog, cinema_preferences_supported: true, cinema_identity_confirmation_supported: true, cinema_discoveries_supported: true, minimum_model_interval_seconds: 22, jobs: jobs.map(({job_id, status, artists}) => ({job_id, status, artists}))});
    if (url.pathname === '/api/demo/cases/plans') {
      jobs.unshift({...job, job_id: 'admitted-plan-with-lost-response', status: 'PLANNED'});
      return route.fulfill({status: 503, json: {error: 'Synthetic lost plan response'}});
    }
    const selected = jobs.find(value => url.pathname === '/api/demo/cases/jobs/' + value.job_id);
    if (selected) {
      statusReads += 1;
      if (deferRestoration && selected.job_id === completed.job_id) {
        restoreStarted();
        return delayedRestore.then(() => json(selected));
      }
      return json(selected);
    }
    if (url.pathname.startsWith('/api/')) throw Error('Unexpected API request: ' + url.pathname);
    return route.continue();
  });
  try {
    if (deferRestoration) await page.addInitScript(() => sessionStorage.setItem('affinityqa-public-selected-case-v1', 'completed-discovery-case'));
    await page.goto(origin + '/demo#new');
    await page.getByRole('button', {name: 'OPEN OR RESTORE MY SESSION', exact: true}).click();
    if (deferRestoration) {
      await restorationStarted;
    } else {
    await page.getByRole('button', {name: /Synthetic artist A \/ Synthetic artist B — COMPLETE/}).click();
    await page.getByRole('status').filter({hasText: /^COMPLETE$/}).waitFor();
    await page.locator('summary').filter({hasText: /^ADVANCED \/ PROFILE INTEGRITY EXPERIMENT/}).click();
    assert.equal(await page.getByRole('button', {name: /^PROFILE INTEGRITY/}).isEnabled(), false, 'The 39-decision mode must require explicit acknowledgement');
    await page.getByRole('checkbox', {name: 'I understand this selects the longer 39-decision experiment, not the film-pick flow.', exact: true}).check();
    await page.getByRole('button', {name: /^PROFILE INTEGRITY/}).click();
    const workflow = page.getByRole('list', {name: 'Individual case workflow', exact: true});
    assert.equal(await workflow.getByRole('listitem').count(), 3, 'The selected workflow has three explicit stages');
    assert.equal((await workflow.innerText()).includes('CONFIRM THE MATCHES'), false, 'A completed discovery must not override the next integrity workflow');
    assert.ok((await workflow.innerText()).includes('START THE REVIEW'));
    await page.getByText('NEXT NEW PLAN: up to 39 model attempts.', {exact: false}).waitFor();
    await page.getByRole('button', {name: /Other integrity A \/ Other integrity B — COMPLETE/}).click();
    await page.locator('dd').filter({hasText: /^completed-integrity-case$/}).waitFor({state: 'attached'});
    await page.getByRole('button', {name: /^FILM PREFERENCES/}).click();
    assert.ok((await workflow.innerText()).includes('CONFIRM THE MATCHES'), 'A completed integrity result must not override the next discovery workflow');
    assert.equal((await workflow.innerText()).includes('START THE REVIEW'), false);
    await page.getByText('NEXT NEW PLAN: up to 2 model attempts.', {exact: false}).waitFor();
    }
    await page.getByRole('button', {name: 'REVIEW A NEW PLAN', exact: true}).click();
    await page.getByText('Synthetic lost plan response', {exact: true}).waitFor();
    if (deferRestoration) {
      releaseRestore();
      await page.getByRole('status').filter({hasText: /^COMPLETE$/}).waitFor();
      assert.equal(await page.getByRole('button', {name: 'REVIEW A NEW PLAN', exact: true}).isEnabled(), false, 'A late restore response must not clear uncertainty from a later plan mutation');
      await page.getByText('The response is uncertain.', {exact: false}).waitFor();
    }
    const beforeReads = statusReads;
    await page.getByRole('button', {name: 'CHECK CURRENT STATUS', exact: true}).click();
    await page.getByText('Saved plans have been refreshed.', {exact: false}).waitFor();
    await page.locator('li').filter({has: page.getByText('admitted-plan-with-lost-response', {exact: true})}).getByRole('button').waitFor();
    assert.equal(statusReads, beforeReads, 'Unknown plan ID must not be guessed from a prior selection or the first history entry');
    assert.equal(await page.locator('dd').filter({hasText: deferRestoration ? /^completed-discovery-case$/ : /^completed-integrity-case$/}).count(), 1, 'A refreshed plan list must preserve the selected case');
    assert.equal(posts.filter(value => value.endsWith('/plans')).length, 1, 'Lost plan response must not repeat its POST');
    assert.equal(posts.filter(value => value.endsWith('/execute') || value.endsWith('/confirm-identities')).length, 0);
    assert.deepEqual(errors, []);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
    console.log(JSON.stringify({result: 'PASS', scenario: deferRestoration ? 'late restoration preserves newer mutation uncertainty' : 'completed-case mode switch and lost-plan status-only recovery', viewport: mobile ? 'mobile' : 'desktop', plan_posts: 1, execution_posts: 0, provider_calls: 0}));
  } finally {
    await page.close();
  }
}

async function preserveActiveCaseWhileReadingHistory(browser, origin, mobile) {
  const page=await browser.newPage({viewport:mobile?{width:390,height:844}:{width:1280,height:900}});
  const active={...job,job_id:'running-integrity-case',status:'STARTED'};
  const historical={...job,job_id:'historical-complete-case',status:'COMPLETE',artists:{A:'Historical artist A',B:'Historical artist B'}};
  const planned={...job,job_id:'saved-integrity-plan',status:'PLANNED',artists:{A:'Consent profile A',B:'Consent profile B'}};
  const catalog=Array.from({length:20},(_,index)=>({entity_id:'movie-'+index,name:'Synthetic film '+index,release_year:2000+index}));
  const posts=[],errors=[];let activeReads=0,completeActive=false;
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',route=>{
    const request=route.request(),url=new URL(request.url());assert.equal(url.origin,origin,'External browser request forbidden');
    const json=body=>route.fulfill({json:body});if(request.method()==='POST')posts.push(url.pathname);
    if(url.pathname==='/healthz')return json({new_cases_configured:true});
    if(url.pathname==='/api/demo/summary')return json({schema_version:1,status:'UNAVAILABLE',pairs:[]});
    if(url.pathname==='/api/demo/cases/session')return json({schema_version:1,csrf_token:'c'.repeat(64),expires_utc:'2099-01-01T00:00:00Z'});
    if(url.pathname==='/api/demo/cases/capabilities')return json({...capabilities,remaining_plans:null,remaining_executions:null,admission_mode:'repeatable-v1',default_artists:artists,catalog,cinema_preferences_supported:true,cinema_identity_confirmation_supported:true,cinema_discoveries_supported:true,jobs:[active,historical,planned].map(({job_id,status,artists})=>({job_id,status,artists}))});
    if(url.pathname==='/api/demo/cases/jobs/'+active.job_id){activeReads++;return json({...active,status:completeActive?'COMPLETE':'STARTED',saved_model_packets:completeActive?39:activeReads-1});}
    if(url.pathname==='/api/demo/cases/jobs/'+historical.job_id)return json(historical);
    if(url.pathname==='/api/demo/cases/jobs/'+planned.job_id)return json(planned);
    if(url.pathname.startsWith('/api/'))throw Error('Unexpected mutation or API read: '+url.pathname);
    return route.continue();
  });
  try{
    await page.goto(origin+'/demo#new');await page.getByRole('button',{name:'OPEN OR RESTORE MY SESSION',exact:true}).click();
    await page.getByRole('button',{name:/Consent profile A \/ Consent profile B — PLANNED/}).click();
    const start=page.getByRole('button',{name:'START THIS REVIEWED CLOUD PLAN',exact:true});
    assert.equal(await start.isEnabled(),false,'A saved 39-decision plan also requires acknowledgement when film mode is available');
    await page.locator('summary').filter({hasText:/^ADVANCED \/ PROFILE INTEGRITY EXPERIMENT/}).click();
    await page.getByRole('checkbox',{name:'I understand this selects the longer 39-decision experiment, not the film-pick flow.',exact:true}).check();
    assert.equal(await start.isEnabled(),true,'Consent permits reviewing the saved plan but does not execute it');
    await page.getByRole('button',{name:/Synthetic artist A \/ Synthetic artist B — STARTED/}).click();
    await page.getByRole('status').filter({hasText:/^STARTED$/}).waitFor();
    const beforeHistory=activeReads;
    await page.getByRole('button',{name:/Historical artist A \/ Historical artist B — COMPLETE/}).click();
    await page.locator('dd').filter({hasText:/^historical-complete-case$/}).waitFor({state:'attached'});
    const runningNotice=page.getByRole('complementary',{name:'Running case kept in progress',exact:true});
    await runningNotice.waitFor();
    assert.equal(await page.getByRole('button',{name:'REVIEW A NEW PLAN',exact:true}).isEnabled(),false,'Inspecting history must not admit overlapping work');
    const beforeBackgroundRead=activeReads;
    await page.waitForFunction(({minimum})=>{const text=document.querySelector('[aria-label="Running case kept in progress"]')?.textContent??'';const saved=text.match(/(\d+)\/39 model packets saved/);return !!saved&&Number(saved[1])>=minimum;},{minimum:beforeBackgroundRead},{timeout:8000});
    assert.ok(activeReads>beforeBackgroundRead&&activeReads>beforeHistory,'The original active ID must keep polling while historical evidence is selected');
    assert.equal(await page.locator('dd').filter({hasText:/^historical-complete-case$/}).count(),1,'Background polling must not steal the historical selection');
    assert.deepEqual(posts,['/api/demo/cases/session'],'Reading history and observing progress must not execute work');
    const postsBeforeReload=posts.length;
    await page.reload();
    await page.getByRole('button',{name:'OPEN OR RESTORE MY SESSION',exact:true}).click();
    await page.locator('dd').filter({hasText:/^historical-complete-case$/}).waitFor({state:'attached'});
    await runningNotice.waitFor();
    assert.equal(await page.getByRole('button',{name:'REVIEW A NEW PLAN',exact:true}).isEnabled(),false,'Reloading a selected historical case must restore the owned active companion and keep new work blocked');
    const beforeRestoredPoll=activeReads;
    await page.waitForFunction(({minimum})=>{const text=document.querySelector('[aria-label="Running case kept in progress"]')?.textContent??'';const saved=text.match(/(\d+)\/39 model packets saved/);return !!saved&&Number(saved[1])>=minimum;},{minimum:beforeRestoredPoll},{timeout:8000});
    assert.ok(activeReads>beforeRestoredPoll,'The owned active case must resume polling after reload while historical evidence stays selected');
    assert.equal(await page.locator('dd').filter({hasText:/^historical-complete-case$/}).count(),1);
    assert.deepEqual(posts.slice(postsBeforeReload),['/api/demo/cases/session'],'Reopening ownership may post the session once; companion restoration must use GETs and never execute or confirm work');
    await page.getByRole('button',{name:'RETURN TO RUNNING CASE',exact:true}).click();
    await page.locator('dd').filter({hasText:/^running-integrity-case$/}).waitFor({state:'attached'});
    await page.getByRole('status').filter({hasText:/^STARTED$/}).waitFor();
    await page.getByRole('button',{name:/Historical artist A \/ Historical artist B — COMPLETE/}).click();
    await page.locator('dd').filter({hasText:/^historical-complete-case$/}).waitFor({state:'attached'});
    completeActive=true;
    await runningNotice.waitFor({state:'hidden',timeout:8000});
    await page.waitForFunction(()=>[...document.querySelectorAll('button')].some(button=>button.textContent.trim().startsWith('REVIEW A NEW PLAN')&&!button.disabled));
    assert.equal(await page.locator('dd').filter({hasText:/^historical-complete-case$/}).count(),1,'Completing the background case must not open or replace the selected historical case');
    assert.deepEqual(posts,['/api/demo/cases/session','/api/demo/cases/session']);assert.deepEqual(errors,[]);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
    console.log(JSON.stringify({result:'PASS',scenario:'saved advanced consent and active polling preserved across historical inspection and reload; terminal background does not replace selection',viewport:mobile?'mobile':'desktop',active_reads:activeReads,session_posts:2,execution_posts:0,provider_calls:0}));
  }finally{await page.close();}
}

async function main() {
  const server = http.createServer((req, res) => {
    const pathname = new URL(req.url, 'http://localhost').pathname;
    const relative = pathname === '/demo' || pathname === '/demo/' ? 'demo.html' : pathname.slice(1);
    const file = path.resolve(root, relative);
    if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
      res.writeHead(404).end(); return;
    }
    const mime = {'.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml'};
    res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream');
    fs.createReadStream(file).pipe(res);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let browser;
  try {
    browser = await chromium.launch({headless: true,
      ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? {
        executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
        args: ['--no-sandbox', '--disable-dev-shm-usage'],
      } : {})});
    const mobile = process.argv.includes('--mobile');
    const repeatedInterruption = process.argv.includes('--repeat-interruption');
    const page = await browser.newPage({viewport: mobile ? {width: 390, height: 844} : {width: 1280, height: 900}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    let reads = 0, recoveryRead = false, mutations = 0;
    await page.route('**/*', async route => {
      const request = route.request();
      const url = new URL(request.url());
      assert.equal(url.hostname, '127.0.0.1', 'External browser request forbidden');
      const json = body => route.fulfill({json: body});
      if (url.pathname === '/healthz') return json({new_cases_configured: true});
      if (url.pathname === '/api/demo/summary') return json({schema_version: 1, status: 'UNAVAILABLE', pairs: []});
      if (url.pathname === '/api/demo/cases/session') {
        mutations += 1;
        return json({schema_version: 1, csrf_token: 'c'.repeat(64), expires_utc: '2099-01-01T00:00:00Z'});
      }
      if (url.pathname === '/api/demo/cases/capabilities') return json(capabilities);
      if (url.pathname === '/api/demo/cases/jobs/' + jobId) {
        reads += 1;
        if (reads === 1) return json(job); // Open a saved, running case.
        if (reads === 2) return route.fulfill({status: 503, json: {error: 'Synthetic interruption'}});
        if (repeatedInterruption && reads === 3) return route.fulfill({status: 503, json: {error: 'Synthetic interruption'}});
        if (reads === (repeatedInterruption ? 4 : 3)) { recoveryRead = true; return json(job); } // Same id/status after manual recovery.
        return json({...job, status: 'COMPLETE'});
      }
      if (url.pathname.startsWith('/api/')) throw Error('Unexpected API request: ' + url.pathname);
      return route.continue();
    });
    await page.goto(`http://127.0.0.1:${server.address().port}/demo#new`);
    await page.getByRole('button', {name: 'OPEN OR RESTORE MY SESSION'}).click();
    await page.getByRole('button', {name: /Synthetic artist A \/ Synthetic artist B/}).click();
    await page.getByText('Progress is unavailable.', {exact: false}).waitFor();
    await page.getByRole('button', {name: 'CHECK CURRENT STATUS'}).click();
    if (repeatedInterruption) {
      await page.getByText('Synthetic interruption', {exact: true}).waitFor();
      await page.getByRole('button', {name: 'CHECK CURRENT STATUS'}).click();
    }
    await page.getByRole('status').filter({hasText: /^COMPLETE$/}).waitFor({timeout: 8000});
    assert.equal(recoveryRead, true);
    assert.ok(reads >= 4, 'Automatic polling must resume after a same-status recovery');
    assert.equal(mutations, 1, 'Recovery must not create, execute or confirm another case');
    assert.deepEqual(errors, []);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true, 'Case view must fit the viewport');
    console.log(JSON.stringify({result: 'PASS', scenario: 'same-status polling recovery', viewport: mobile ? 'mobile' : 'desktop', repeated_interruption: repeatedInterruption, reads, session_posts: mutations, provider_calls: 0}));
    await recoverThroughSavedHistory(browser, `http://127.0.0.1:${server.address().port}`, mobile);
    await recoverThroughSavedHistory(browser, `http://127.0.0.1:${server.address().port}`, mobile, true);
    await recoverPlanAndSwitchMode(browser, `http://127.0.0.1:${server.address().port}`, mobile);
    await recoverPlanAndSwitchMode(browser, `http://127.0.0.1:${server.address().port}`, mobile, true);
    await preserveActiveCaseWhileReadingHistory(browser, `http://127.0.0.1:${server.address().port}`, mobile);
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
}
main().catch(error => {console.error(error.message); process.exitCode = 1;});
