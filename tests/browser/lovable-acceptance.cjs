// Offline acceptance of the integrated presentation against a local contract fixture.
// Every preference, identity receipt and result below is synthetic. No Qloo API,
// Groq, account, deployment, real-case store or provider ledger is accessed.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {createHash} = require('node:crypto');
const {createRequire} = require('node:module');
const {createFixture, observed} = require('./serve_wide_cinema_synthetic.cjs');
const webRoot = path.resolve(process.env.AFFINITYQA_WEB_ROOT || path.join(__dirname, '../../web'));
const {chromium} = createRequire(path.join(webRoot, 'package.json'))('playwright');
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
const imageBytes = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64');

async function runViewport(browser, width) {
  const fixture = await createFixture({webRoot});
  const context = await browser.newContext({viewport: {width, height: 1000}, acceptDownloads: true, reducedMotion: 'reduce'});
  const page = await context.newPage();
  const errors = [], requests = [], evidence = [], imageRequests = [];
  let capabilityPatch = {}, sessionMissing = false, queueExecute = false, loseConfirm = false;
  let executeSeen, releaseExecute;
  let executeGate = null;
  page.on('pageerror', error => errors.push(error.message));
  // A native attachment must not be synthesized through Playwright's response
  // interceptor. Only this exact loopback download route bypasses interception.
  await context.route(url => !(url.origin === fixture.origin && /^\/api\/demo\/cases\/jobs\/[^/]+\/verification$/.test(url.pathname)), async route => {
    const request = route.request(), url = new URL(request.url());
    requests.push({method: request.method(), path: url.pathname});
    if (url.origin !== fixture.origin) {
      assert.ok(observed.some(row => row.url === url.href), 'Only the five observed poster URLs may leave loopback');
      assert.equal(request.headers().referer, undefined, 'Poster request must not disclose the page referrer');
      imageRequests.push(url.href);
      return route.fulfill({contentType: 'image/png', body: imageBytes});
    }
    if (url.pathname === '/api/demo/cases/capabilities') {
      if (sessionMissing) return route.fulfill({status: 404, json: {error: 'Synthetic session unavailable'}});
      const response = await route.fetch();
      return route.fulfill({response, json: {...await response.json(), ...capabilityPatch}});
    }
    if (queueExecute && request.method() === 'POST' && url.pathname.endsWith('/execute')) {
      const response = await route.fetch(), job = await response.json();
      Object.assign(fixture.state.jobs.get(job.job_id), {status: 'QUEUED', queue_status: 'QUEUED', queue_position: 2, not_before: '2099-01-01T00:00:00Z'});
      if (executeSeen) executeSeen();
      if (executeGate) await executeGate;
      return route.fulfill({response, json: fixture.state.jobs.get(job.job_id)});
    }
    if (loseConfirm && request.method() === 'POST' && url.pathname.endsWith('/confirm-wide')) {
      loseConfirm = false;
      await route.fetch(); // The server committed the case before the response was lost.
      return route.abort('failed');
    }
    return route.continue();
  });
  const root = () => page.locator('section[aria-labelledby="wide-cinema-title"]');
  const mutationCount = () => requests.filter(row => row.method === 'POST' && row.path !== '/api/demo/cases/session').length;
  const postsTo = suffix => requests.filter(row => row.method === 'POST' && row.path.endsWith(suffix)).length;
  const saved = async () => {
    await page.getByRole('navigation', {name: 'Main navigation', exact: true}).getByRole('link', {name: 'SAVED', exact: true}).click();
    await root().locator('#wide-cinema-history').waitFor({state: 'visible'});
  };
  const discover = () => page.getByRole('navigation', {name: 'Main navigation', exact: true}).getByRole('link', {name: 'FILM DISCOVERY', exact: true}).click();
  const refresh = async () => {
    await saved();
    await root().getByRole('button', {name: 'REFRESH', exact: true}).click();
    // checkStatus may read the selected job and then refresh capabilities. Wait
    // for that complete read chain before changing a fixture admission/session.
    await page.waitForLoadState('networkidle');
  };
  const capture = async name => {
    if (!process.env.AFFINITYQA_TEST_SCREENSHOT_DIR) return;
    const directory = path.resolve(process.env.AFFINITYQA_TEST_SCREENSHOT_DIR);
    fs.mkdirSync(directory, {recursive: true});
    fs.writeFileSync(path.join(directory, `lovable-${width}-${name}.png`), await page.screenshot({fullPage: true}), {flag: 'wx'});
  };
  const noOverflow = async label => {
    const dimensions = await page.evaluate(() => ({viewport: innerWidth, document: document.documentElement.scrollWidth}));
    assert.ok(dimensions.document <= dimensions.viewport, `${label}: no horizontal overflow at ${width}px`);
    evidence.push({check: 'no-horizontal-overflow', state: label, ...dimensions});
  };
  try {
    await page.goto(fixture.origin + '/demo#wide');
    await root().waitFor({state: 'visible'});
    assert.equal(mutationCount(), 0, 'Opening the page cannot create a plan or call providers');
    assert.equal(await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches), true);
    const session = root().getByRole('button', {name: 'OPEN OR RESTORE MY SESSION'});
    for (let step = 0; step < 50 && !await session.evaluate(element => element === document.activeElement); step += 1) await page.keyboard.press('Tab');
    assert.equal(await session.evaluate(element => element === document.activeElement), true, 'Session is reachable through sequential keyboard navigation');
    const actionContrast = await session.evaluate(el=>{
      const rgb=text=>text.match(/[\d.]+/g).slice(0,3).map(Number);
      const lum=v=>v.map(n=>{n/=255;return n<=.04045?n/12.92:((n+.055)/1.055)**2.4}).reduce((n,v,i)=>n+v*[.2126,.7152,.0722][i],0);
      const ratio=(a,b)=>(Math.max(a,b)+.05)/(Math.min(a,b)+.05);
      const s=getComputedStyle(el),bg=lum(rgb(s.backgroundColor));
      return {text:ratio(lum(rgb(s.color)),bg),focus:ratio(lum(rgb(s.outlineColor)),lum(rgb(getComputedStyle(el.parentElement).backgroundColor))),outline:s.outlineStyle,width:parseFloat(s.outlineWidth)};
    });
    assert.ok(actionContrast.text>=4.5,'Primary action text remains legible');
    assert.ok(actionContrast.focus>=3&&actionContrast.outline!=='none'&&actionContrast.width>=2,'Primary action keyboard focus remains distinct');
    evidence.push({check:'primary-action-contrast',...actionContrast});
    await page.keyboard.press('Enter');
    await root().getByLabel('FILM TITLE', {exact: true}).waitFor();
    assert.ok(await root().getByRole('button', {name: 'REVIEW MY DISCOVERY PLAN'}).isDisabled(), 'Empty starting point cannot submit');
    await root().getByLabel('FILM TITLE', {exact: true}).fill('   ');
    assert.ok(await root().getByRole('button', {name: 'REVIEW MY DISCOVERY PLAN'}).isDisabled(), 'Whitespace cannot submit');
    assert.equal(mutationCount(), 0);
    await noOverflow('empty-form');
    const controlContrast = await root().locator('input:not([type="radio"]):not([type="checkbox"]), textarea, select').evaluateAll(elements => {
      const rgb=text=>text.match(/[\d.]+/g).slice(0,3).map(Number);
      const lum=values=>values.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}).reduce((n,v,i)=>n+v*[.2126,.7152,.0722][i],0);
      const ratio=(a,b)=>(Math.max(a,b)+.05)/(Math.min(a,b)+.05);
      return elements.filter(el=>el.getBoundingClientRect().width>0).map(el=>{const s=getComputedStyle(el),bg=lum(rgb(s.backgroundColor));return {tag:el.tagName,text:ratio(lum(rgb(s.color)),bg),border:ratio(lum(rgb(s.borderTopColor)),bg)}});
    });
    assert.ok(controlContrast.length>=2);
    for(const sample of controlContrast){assert.ok(sample.text>=4.5,'Control text contrast: '+JSON.stringify(sample));assert.ok(sample.border>=3,'Control border contrast: '+JSON.stringify(sample));}
    evidence.push({check:'visible-control-contrast',samples:controlContrast});

    capabilityPatch = {admissions_blocked: true};
    await refresh(); await discover();
    await root().getByRole('heading', {name: 'NEW ADMISSIONS PAUSED', exact: true}).waitFor();
    await root().getByLabel('FILM TITLE', {exact: true}).fill('John Wick');
    assert.ok(await root().getByRole('button', {name: 'REVIEW MY DISCOVERY PLAN'}).isDisabled());
    assert.equal(mutationCount(), 0, 'Unavailable capacity must not send a speculative plan');
    capabilityPatch = {};
    await refresh(); await discover();
    await root().getByRole('button', {name: 'REVIEW MY DISCOVERY PLAN'}).click();
    await root().locator('[data-state="PLANNED"]').waitFor();
    assert.equal(await root().getByLabel('FILM TITLE', {exact: true}).isVisible(), false, 'The reviewed plan replaces the input form');
    await root().getByRole('button', {name: 'EDIT DRAFT', exact: true}).click();
    await page.waitForFunction(() => document.activeElement?.id === 'wide-cinema-seed');
    await root().getByRole('button', {name: 'START WITH AN ARTIST', exact: true}).click();
    assert.equal(await root().locator('[data-state="PLANNED"]').count(), 0, 'Changing mode invalidates an unexecuted draft');
    await root().getByRole('button', {name: 'START WITH A FILM', exact: true}).click();
    await root().getByLabel('FILM TITLE', {exact: true}).fill('John Wick');
    await root().getByLabel('Your direction (optional)', {exact: true}).fill('Synthetic preference: fast action and cars.');
    await root().getByRole('button', {name: 'REVIEW MY DISCOVERY PLAN'}).click();
    await root().locator('[data-state="PLANNED"]').waitFor();
    evidence.push({check: 'keyboard-and-draft', keyboard_session: true, seed_focus_after_edit: true, empty_and_whitespace_blocked: true, mode_change_invalidates_plan: true});

    queueExecute = true;
    executeGate = new Promise(resolve => {releaseExecute = resolve;});
    const reachedExecute = new Promise(resolve => {executeSeen = resolve;});
    const start = root().getByRole('button', {name: 'FIND MY FILM', exact: true});
    await start.scrollIntoViewIfNeeded();
    const box = await start.boundingBox();
    assert.ok(box);
    const doubled = page.mouse.dblclick(box.x + box.width / 2, box.y + box.height / 2);
    await reachedExecute;
    assert.ok(await start.isDisabled(), 'An admitted request disables repeated clicks');
    assert.equal(postsTo('/execute'), 1, 'A real double-click dispatches one execution');
    releaseExecute(); await doubled;
    await root().locator('[data-state="QUEUED"]').waitFor();
    await root().getByText('This admitted case is waiting for provider capacity.', {exact: false}).waitFor();
    assert.ok(await root().getByRole('button', {name: 'NEW DISCOVERY', exact: true}).isDisabled(), 'A queued case cannot silently start another case');
    await noOverflow('queue'); await capture('queue');
    const queuedMutations = mutationCount();
    await saved();
    await root().getByRole('button', {name: /FILM · John Wick/}).filter({has: page.locator('span', {hasText: 'QUEUED'})}).click();
    await root().locator('[data-state="QUEUED"]').waitFor();
    assert.equal(await root().getByRole('heading', {name: 'NO COMPLETE DISCOVERY CLAIM', exact: true}).count(), 0, 'A queued case is still waiting, not falsely terminal');
    assert.equal(mutationCount(), queuedMutations, 'Reopening the queued case only reads');
    await discover();

    const activeJob = [...fixture.state.jobs.values()].at(-1);
    Object.assign(activeJob, {status: 'AWAITING_IDENTITY_CONFIRMATION', queue_status: null, queue_position: null, not_before: null});
    queueExecute = false;
    await root().getByRole('button', {name: 'REFRESH SAVED STATUS', exact: true}).click();
    await root().getByRole('heading', {name: 'CONFIRM YOUR STARTING POINT', exact: true}).waitFor();
    const choices = root().getByRole('group', {name: 'SELECT ONE FILM', exact: true}).getByRole('radio');
    assert.equal(await root().getByRole('radio', {checked: true}).count(), 0, 'No identity is chosen automatically');
    assert.ok(await choices.last().isDisabled(), 'Missing release year has no confirmable identity');
    assert.ok(await root().getByRole('button', {name: 'CONFIRM & DISCOVER FIVE', exact: true}).isDisabled());
    await choices.first().focus(); await page.keyboard.press('Space');
    assert.ok(await choices.first().isChecked(), 'Explicit identity is selectable by keyboard');
    assert.ok(await root().getByRole('button', {name: 'CONFIRM & DISCOVER FIVE', exact: true}).isEnabled());
    await noOverflow('identity');

    loseConfirm = true;
    await root().getByRole('button', {name: 'CONFIRM & DISCOVER FIVE', exact: true}).click();
    await root().getByText('The response is uncertain.', {exact: false}).waitFor();
    assert.equal(postsTo('/confirm-wide'), 1);
    const beforeRecovery = mutationCount();
    await root().getByRole('button', {name: 'CHECK CURRENT STATUS', exact: true}).click();
    await root().getByRole('heading', {name: 'INSPIRED BY John Wick', exact: true}).waitFor();
    assert.equal(mutationCount(), beforeRecovery, 'Uncertain confirmation recovers through GET, not another POST');
    assert.equal(postsTo('/execute'), 1); assert.equal(postsTo('/confirm-wide'), 1);
    const cards = root().locator('[data-result-movie-id]');
    assert.equal(await cards.count(), 5);
    const originalArtwork = await cards.locator('svg.film-abstract-art').evaluateAll(nodes => nodes.map(node => node.outerHTML));
    assert.equal(originalArtwork.length, 5, 'The existing five original illustrations are retained');
    assert.equal(await cards.locator('img').count(), 0, 'No unlicensed external poster is introduced');
    assert.equal(imageRequests.length, 0, 'The presentation makes no external image request');
    await discover();
    await root().getByRole('heading', {name: 'INSPIRED BY John Wick', exact: true}).waitFor();
    assert.equal(await cards.count(), 5, 'DISCOVER keeps a complete case instead of the prototype Finishing dead end');
    assert.deepEqual(await cards.locator('svg.film-abstract-art').evaluateAll(nodes => nodes.map(node => node.outerHTML)), originalArtwork);
    assert.equal(mutationCount(), beforeRecovery, 'Returning to the completed case makes no provider mutation');
    await noOverflow('five-results'); await capture('results');
    const animations = await root().evaluate(element => [...element.querySelectorAll('*')].flatMap(node => {
      const style = getComputedStyle(node);
      return style.animationName !== 'none' && style.animationDuration.split(',').some(value => parseFloat(value) > 0.01) ? [style.animationName] : [];
    }));
    assert.deepEqual(animations, [], 'Reduced motion removes sustained decorative animation');
    evidence.push({check: 'queue-and-uncertain-post', queued: true, repeated_click_dispatched_once: true, missing_year_blocked: true, lost_confirm_recovered_by_get: true, five_original_illustrations_preserved: true, complete_discover_navigation: true, reduced_motion: true});

    const expected = Buffer.from(JSON.stringify({job_id: activeJob.job_id, result: activeJob.result}));
    const downloadEvent = page.waitForEvent('download');
    await root().getByRole('link', {name: 'DOWNLOAD DISCOVERY VERIFICATION', exact: true}).click();
    const download = await downloadEvent;
    assert.equal(await download.failure(), null);
    const browserPath = await download.path();
    assert.ok(browserPath && fs.statSync(browserPath).isFile(), 'The browser created a physical download');
    const directory = process.env.AFFINITYQA_TEST_DOWNLOAD_DIR ? path.resolve(process.env.AFFINITYQA_TEST_DOWNLOAD_DIR) : fs.mkdtempSync(path.join(os.tmpdir(), 'affinityqa-lovable-download-'));
    fs.mkdirSync(directory, {recursive: true});
    const destination = path.join(directory, `lovable-${width}-${download.suggestedFilename()}`);
    assert.ok(!fs.existsSync(destination), 'Acceptance never overwrites an earlier downloaded file');
    await download.saveAs(destination);
    const physical = fs.readFileSync(destination);
    assert.deepEqual(physical, expected, 'The physical download is exactly the selected saved receipt');
    assert.equal(sha256(physical), sha256(expected));
    evidence.push({check: 'physical-download', path: destination, bytes: physical.length, sha256: sha256(physical)});
    const beforeReload = mutationCount();
    await page.reload();
    const reopen = root().getByRole('button', {name: 'OPEN OR RESTORE MY SESSION'});
    await reopen.click(); await reopen.waitFor({state: 'hidden'});
    await root().getByRole('heading', {name: 'INSPIRED BY John Wick', exact: true}).waitFor();
    assert.equal(mutationCount(), beforeReload, 'Reload and restored ownership do not repeat execution');
    await root().getByRole('button', {name: 'NEW DISCOVERY', exact: true}).click();
    await page.waitForFunction(() => document.activeElement?.id === 'wide-cinema-seed');
    await root().getByLabel('FILM TITLE', {exact: true}).fill('A different synthetic draft');
    assert.equal(await root().getByRole('heading', {name: 'INSPIRED BY John Wick', exact: true}).count(), 1, 'Editing a new draft never relabels saved results');
    assert.equal(mutationCount(), beforeReload);

    for (const status of ['PARTIAL', 'FAILED', 'UNKNOWN']) {
      const id = `lovable-${width}-${status.toLowerCase()}`;
      fixture.addComplete(id, job => {
        job.seed_query = `Synthetic ${status} case`; job.status = status; job.error_class = 'SyntheticFailure';
        job.result = status === 'PARTIAL' ? {verification_status: 'VERIFIED_PARTIAL', provenance: 'SYNTHETIC', qloo_attempts: 1, model_attempts: 0} : null;
      });
      const before = mutationCount();
      await refresh();
      await root().getByRole('button', {name: new RegExp(`FILM · Synthetic ${status} case`)}).click();
      await root().locator(`[data-state="${status}"]`).waitFor();
      assert.equal(await root().locator('[data-result-movie-id]').count(), 0, `${status} never displays successful recommendations`);
      assert.equal(await root().getByRole('button', {name: 'CONFIRM & DISCOVER FIVE', exact: true}).count(), 0, `${status} never silently retries selection`);
      if (status === 'UNKNOWN') await root().getByRole('heading', {name: 'PROVIDER RESULT UNKNOWN', exact: true}).waitFor();
      else await root().getByRole('heading', {name: 'NO COMPLETE DISCOVERY CLAIM', exact: true}).waitFor();
      assert.equal(mutationCount(), before, `${status} reads existing evidence without POST`);
      await noOverflow(status); await capture(status.toLowerCase());
    }
    evidence.push({check: 'terminal-states', partial: true, failed: true, unknown: true, no_fabricated_success: true, no_repeated_post: true});

    capabilityPatch = {remaining_executions: 0};
    await refresh();
    const beforeUnavailable = mutationCount();
    // The first complete case is still owned even when new execution capacity is zero.
    await root().getByRole('button', {name: 'LOAD EARLIER DISCOVERIES', exact: true}).click();
    await root().getByRole('button', {name: /FILM · John Wick/}).filter({has: page.locator('span', {hasText: 'COMPLETE'})}).click();
    await root().getByRole('heading', {name: 'INSPIRED BY John Wick', exact: true}).waitFor();
    assert.ok(await root().getByRole('link', {name: 'DOWNLOAD DISCOVERY VERIFICATION', exact: true}).isVisible());
    assert.equal(mutationCount(), beforeUnavailable);
    await root().getByRole('button', {name: 'NEW DISCOVERY', exact: true}).click();
    await root().getByLabel('FILM TITLE', {exact: true}).fill('Synthetic zero-capacity draft');
    await root().getByRole('button', {name: 'REVIEW MY DISCOVERY PLAN'}).click();
    await root().locator('[data-state="PLANNED"]').waitFor();
    assert.ok(await root().getByRole('button', {name: 'FIND MY FILM', exact: true}).isDisabled(), 'Zero remaining execution capacity blocks the provider action');
    assert.equal(postsTo('/execute'), 1, 'Reviewing a zero-capacity plan does not send another execution');
    capabilityPatch = {remaining_executions: 5, admissions_blocked: true};
    await root().getByRole('button', {name: 'REFRESH SAVED STATUS', exact: true}).click();
    await root().getByText('NEW ADMISSIONS PAUSED', {exact: true}).waitFor();
    assert.ok(await root().getByRole('button', {name: 'FIND MY FILM', exact: true}).isDisabled(), 'Updated paused admissions block an existing plan');
    assert.equal(mutationCount(), beforeUnavailable + 1, 'Refreshing paused capacity does not execute another case');
    capabilityPatch = {remaining_executions: 0};

    await refresh();
    const restoredCapabilities = page.waitForResponse(response => new URL(response.url()).pathname === '/api/demo/cases/capabilities' && response.request().method() === 'GET');
    await root().getByRole('button', {name: /FILM · John Wick/}).filter({has: page.locator('span', {hasText: 'COMPLETE'})}).click();
    await root().getByRole('heading', {name: 'INSPIRED BY John Wick', exact: true}).waitFor();
    await restoredCapabilities;
    await page.waitForFunction(element => !element.disabled, await root().getByRole('button', {name: 'REFRESH SAVED STATUS', exact: true}).elementHandle());
    const beforeMissingSession = mutationCount();
    sessionMissing = true;
    await root().getByRole('button', {name: 'REFRESH SAVED STATUS', exact: true}).click();
    await root().getByText('Your session is unavailable.', {exact: false}).waitFor();
    assert.ok(await root().getByRole('button', {name: 'OPEN OR RESTORE MY SESSION'}).isVisible());
    assert.equal(await root().getByRole('link', {name: 'DOWNLOAD DISCOVERY VERIFICATION', exact: true}).count(), 0, 'Wrong or expired session cannot download another ownership view');
    assert.equal(mutationCount(), beforeMissingSession, 'A missing session does not repeat any provider POST');
    await noOverflow('missing-session');
    evidence.push({check: 'session-and-capacity', completed_case_readable_at_zero_new_capacity: true, zero_capacity_blocks_execution: true, paused_capacity_refresh_blocks_existing_plan: true, queued_reopen_not_terminal: true, missing_session_blocks_download: true, no_repeated_post: true});
    fixture.assertPreserved();
    assert.deepEqual(errors, [], 'No uncaught browser exception');
    return {status: 'PASS', viewport: {width, height: 1000}, preferences: 'SYNTHETIC', provider_api_calls: 0, model_calls: 0, uncaught_page_errors: errors.length, preserved_legacy_case: true, evidence};
  } finally {if (releaseExecute) releaseExecute(); await context.close(); await fixture.close();}
}

async function checkLanding(browser, width) {
  const fixture = await createFixture({webRoot});
  const context = await browser.newContext({viewport: {width, height: 1000}, reducedMotion: 'reduce'});
  try {
    const page = await context.newPage();
    const external = [];
    await context.route('**/*', route => {
      if (new URL(route.request().url()).origin !== fixture.origin) {external.push(route.request().url()); return route.abort();}
      return route.continue();
    });
    await page.goto(fixture.origin + '/demo');
    await page.getByRole('heading', {name: 'Find the wrong context. Verify the repair.', exact: true}).waitFor();
    const sequence = page.getByRole('group', {name: 'Diagnostic sequence', exact: true});
    assert.equal(await sequence.locator('strong').count(), 4);
    await page.getByText('No verified capture installed.', {exact: true}).waitFor();
    const geometry = await page.evaluate(() => ({width: innerWidth, full: document.documentElement.scrollWidth, color: getComputedStyle(document.querySelector('.public-cinema')).color, scheme: getComputedStyle(document.querySelector('.public-cinema')).colorScheme}));
    assert.ok(geometry.full <= width + 1, 'Diagnosis has no horizontal overflow');
    assert.equal(geometry.scheme, 'dark');
    assert.equal(geometry.color, 'rgb(241, 240, 250)');
    const guide = page.getByRole('figure', {name:'Illustrative context-binding diagram, not a case result',exact:true});
    assert.ok(await guide.isVisible(), 'The visual guide is explicitly illustrative, never a verified case');
    assert.equal(await guide.getByText('ILLUSTRATIVE EXAMPLE',{exact:true}).count(),1);
    const contrast = await page.evaluate(() => {
      const rgb = text => {const parts=text.match(/[\d.]+/g).map(Number);return [...parts.slice(0,3),parts.length===4?parts[3]:1]};
      const luminance = values => values.slice(0,3).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}).reduce((n,v,i)=>n+v*[.2126,.7152,.0722][i],0);
      const background = element => {const layers=[];for(let node=element;node;node=node.parentElement){const color=rgb(getComputedStyle(node).backgroundColor);layers.push(color);if(color[3]===1)break;}let result=[0,0,0];for(const color of layers.reverse())result=result.map((v,i)=>color[i]*color[3]+v*(1-color[3]));return result};
      const selectors=['.violet-hero h1','.violet-hero h1 > span','.violet-hero-copy > p','.violet-eyebrow','.context-guide figcaption','.context-guide figcaption > span','.context-guide-node small','.cinema-primary-navigation a[aria-current="page"]'];
      return selectors.flatMap(selector=>Array.from(document.querySelectorAll(selector)).filter(el=>el.getBoundingClientRect().width>0).map(element=>{const a=luminance(rgb(getComputedStyle(element).color)),b=luminance(background(element));return {selector,ratio:(Math.max(a,b)+.05)/(Math.min(a,b)+.05)}}));
    });
    assert.ok(contrast.length>=6);
    for(const sample of contrast) assert.ok(sample.ratio>=4.5, sample.selector+' retains readable contrast: '+sample.ratio);
    const nav = page.getByRole('navigation', {name: 'Main navigation', exact: true});
    for (const name of ['DIAGNOSIS & EVIDENCE', 'FILM DISCOVERY', 'SAVED']) {
      const link = nav.getByRole('link', {name, exact: true});
      assert.ok(await link.isVisible());
      const box = await link.boundingBox();
      assert.ok(box && box.height >= 44, 'Primary navigation is touch accessible');
    }
    const diagnosis = nav.getByRole('link', {name: 'DIAGNOSIS & EVIDENCE', exact: true});
    await diagnosis.focus();
    const focus = await diagnosis.evaluate(element => ({outline:getComputedStyle(element).outlineStyle,width:parseFloat(getComputedStyle(element).outlineWidth)}));
    assert.ok(focus.outline !== 'none' && focus.width >= 2, 'Keyboard focus remains visible');
    if(process.env.AFFINITYQA_TEST_SCREENSHOT_DIR){
      const directory=path.resolve(process.env.AFFINITYQA_TEST_SCREENSHOT_DIR);fs.mkdirSync(directory,{recursive:true});
      fs.writeFileSync(path.join(directory,'jury-diagnosis-'+width+'.png'),await page.screenshot({fullPage:true}),{flag:'wx'});
    }
    await nav.getByRole('link', {name: 'FILM DISCOVERY', exact: true}).click();
    await page.locator('section[aria-labelledby="wide-cinema-title"]').waitFor({state:'visible'});
    assert.equal(await page.locator('[data-jury="recorded"]').isVisible(),false,'The inactive diagnosis is hidden by the real React mode');
    assert.equal(await guide.isVisible(),false,'The illustrative hero cannot leak into discovery');
    await diagnosis.click();
    assert.equal(await page.locator('[data-jury="wide"]').isVisible(),false,'The inactive discovery is hidden after returning to diagnosis');
    await page.getByRole('heading', {name: 'Find the wrong context. Verify the repair.', exact: true}).waitFor();
    assert.deepEqual(external, []);
    assert.equal(fixture.state.posts.length, 0, 'Navigation does not create provider work or open a session');
    fixture.assertPreserved();
    return {width, diagnosis_first:true, navigation_without_mutation:true, no_capture_honestly_unavailable:true, focus_visible:true, illustrative_guide:true, contrast, geometry};
  } finally {await context.close();await fixture.close();}
}

async function main() {
  // Keep physical browser artifacts in an explicit writable test directory.
  const downloadsPath = process.env.AFFINITYQA_TEST_DOWNLOAD_DIR ? path.resolve(process.env.AFFINITYQA_TEST_DOWNLOAD_DIR) : fs.mkdtempSync(path.join(os.tmpdir(), 'affinityqa-lovable-native-'));
  fs.mkdirSync(downloadsPath, {recursive: true});
  const browser = await chromium.launch({headless: true, downloadsPath, ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? {executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH, args: ['--no-sandbox', '--disable-dev-shm-usage']} : {})});
  try {
    const landing = [];
    for(const width of [360,768,1440]) landing.push(await checkLanding(browser,width));
    const results = [];
    for (const width of [360, 1440]) results.push(await runViewport(browser, width));
    process.stdout.write(JSON.stringify({status: 'PASS', scope: 'local synthetic presentation acceptance', landing, results, public_ci: 'NOT_RUN', live_provider_acceptance: 'NOT_RUN'}) + '\n');
  } finally {await browser.close();}
}
main().catch(error => {process.stderr.write(error.stack + '\n'); process.exitCode = 1;});
