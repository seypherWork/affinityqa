// Real frontend + FastAPI + on-disk case manager; only providers are synthetic.
const assert = require('node:assert/strict');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {createRequire} = require('node:module');
const webRequire = createRequire(path.resolve(__dirname, '../../web/package.json'));
const {chromium} = webRequire('playwright');

async function bounded(promise, milliseconds, message) {
  let timer;
  try {
    return await Promise.race([promise, new Promise((_, reject) => {
      timer = setTimeout(() => reject(Error(message)), milliseconds);
    })]);
  } finally { clearTimeout(timer); }
}

async function main() {
  const child = spawn(process.env.AFFINITYQA_TEST_PYTHON || 'python',
    ['-B', path.join(__dirname, 'serve_synthetic_cases.py'), '--exit-after-seconds', '60'], {stdio: ['ignore', 'pipe', 'pipe']});
  let output = '', errors = '', origin, closed = false;
  const exit = new Promise(resolve => child.on('close', (code, signal) => {closed = true; resolve({code, signal});}));
  const ready = new Promise((resolve, reject) => {
    child.on('error', reject);
    child.stdout.on('data', data => {
      output += data;
      for (const line of output.split('\n')) {
        try {const value = JSON.parse(line); if (value.ready_origin) {origin = value.ready_origin; resolve(origin);}} catch {}
      }
    });
    child.stderr.on('data', data => {errors += data;});
    child.on('close', () => {if (!origin) reject(Error('Synthetic case host failed to start: ' + errors));});
  });
  let browser;
  try {
    const url = await bounded(ready, 20000, 'Synthetic case host readiness timed out');
    for (let attempt = 0; attempt < 100; attempt += 1) {
      try {if ((await fetch(url + '/healthz')).ok) break;} catch {}
      if (attempt === 99) throw Error('Synthetic case host did not become healthy');
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    browser = await chromium.launch({headless: true,
      ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? {
        executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
        args: ['--no-sandbox', '--disable-dev-shm-usage'],
      } : {})});
    const page = await browser.newPage({viewport: {width: 1280, height: 900}});
    const pageErrors = [], posts = [];
    page.on('pageerror', e => pageErrors.push(e.message));
    page.on('request', request => {if (request.method() === 'POST') posts.push(new URL(request.url()).pathname);});
    await page.route('**/*', route => {
      if (new URL(route.request().url()).origin !== url) throw Error('External browser request forbidden');
      return route.continue();
    });
    await page.goto(url + '/demo#new');
    await page.getByRole('button', {name: 'OPEN OR RESTORE MY SESSION', exact: true}).click();
    await page.getByRole('heading', {name: 'YOUR MUSICAL INTERESTS', exact: true}).waitFor();
    const capResponse = await page.request.get(url + '/api/demo/cases/capabilities');
    assert.equal(capResponse.status(), 200);
    const cap = await capResponse.json();
    assert.equal(cap.simulation_only, true);
    assert.equal(cap.jobs.length, 0);
    for (const label of ['A', 'B']) {
      await page.locator('summary').filter({hasText: new RegExp('^PROFILE ' + label)}).click();
      await page.getByLabel(`Profile ${label}: ${cap.catalog[0].name}`, {exact: true}).selectOption('favorite');
      await page.getByLabel(`Profile ${label}: ${cap.catalog[19].name}`, {exact: true}).selectOption('exclude');
    }
    await page.getByRole('button', {name: 'REVIEW A NEW PLAN', exact: true}).click();
    await page.getByRole('status').filter({hasText: /^PLANNED$/}).waitFor();
    await page.getByRole('button', {name: 'FIND ARTISTS', exact: true}).click();
    await page.getByRole('heading', {name: 'CONFIRM YOUR ARTISTS', exact: true}).waitFor();
    const confirm = page.getByRole('button', {name: 'CONFIRM ARTISTS & START REVIEW', exact: true});
    assert.equal(await confirm.isEnabled(), false, 'No artist may be selected automatically');
    const pendingCap = await (await page.request.get(url + '/api/demo/cases/capabilities')).json();
    assert.equal(pendingCap.remaining_executions, 0, 'Search consumed the single execution admission');
    for (const label of ['A', 'B']) await page.getByRole('group', {name: 'PROFILE ' + label, exact: true}).getByRole('radio').check();
    await confirm.click();
    await page.getByRole('status').filter({hasText: /^COMPLETE$/}).waitFor({timeout: 20000});
    const finalCap = await (await page.request.get(url + '/api/demo/cases/capabilities')).json();
    assert.equal(finalCap.jobs.length, 1);
    const jobId = finalCap.jobs[0].job_id;
    const job = await (await page.request.get(url + '/api/demo/cases/jobs/' + jobId)).json();
    assert.equal(job.case_protocol, 'cinema-confirmed-discovery-v3');
    assert.equal(job.saved_provider_samples, 4);
    assert.equal(job.saved_model_packets, 2);
    assert.equal(job.result.preference_gate, 'PASS');
    assert.equal(job.result.cultural_gate, 'NOT_VALIDATED');
    assert.equal(job.result.release_gate, 'BLOCKED');
    for (const label of ['A', 'B']) {
      const delivered = job.result.cinema_results[label].delivered;
      assert.equal(delivered.length, 5);
      assert.equal(delivered.includes(cap.catalog[0].entity_id), false, 'Known favorite must not be rediscovered');
      assert.equal(delivered.includes(cap.catalog[19].entity_id), false, 'Excluded film must not be delivered');
    }
    const receipt = await page.request.get(url + '/api/demo/cases/jobs/' + jobId + '/verification');
    assert.equal(receipt.status(), 200);
    assert.equal((await receipt.json()).result.verification_status, 'VERIFIED_COMPLETE');
    await page.reload();
    await page.getByRole('button', {name: 'OPEN OR RESTORE MY SESSION', exact: true}).click();
    await page.getByRole('button', {name: /— COMPLETE$/}).click();
    await page.getByRole('status').filter({hasText: /^COMPLETE$/}).waitFor();
    assert.equal(posts.filter(p => p.endsWith('/plans')).length, 1);
    assert.equal(posts.filter(p => p.endsWith('/execute')).length, 1);
    assert.equal(posts.filter(p => p.endsWith('/confirm-identities')).length, 1);
    assert.equal(posts.filter(p => p.endsWith('/session')).length, 2);
    assert.deepEqual(pageErrors, []);
    await browser.close(); browser = undefined;
    // Wait for the fixture's bounded graceful shutdown on Windows and Unix.
    const exitResult = await bounded(exit, 75000, 'Synthetic case host graceful shutdown timed out');
    assert.equal(exitResult.code, 0, errors);
    const state = output.split('\n').flatMap(line => {try {return [JSON.parse(line)];} catch {return [];}}).find(v => 'real_provider_calls' in v);
    assert.deepEqual(state, {synthetic_qloo_calls: 4, synthetic_model_calls: 2,
      session_records: 1, plan_records: 1, execution_admissions: 1, real_provider_calls: 0});
    console.log(JSON.stringify({result: 'PASS', scenario: 'full new-case browser journey and reload', ...state}));
  } finally {
    if (browser) await browser.close();
    if (!closed) child.kill('SIGKILL');
  }
}
main().catch(error => {console.error(error.message); process.exitCode = 1;});
