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
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
}
main().catch(error => {console.error(error.message); process.exitCode = 1;});
