// Browser contract and recovery using an isolated synthetic API.
// All third-party traffic is denied, including historical image URLs.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {createRequire}=require('node:module');
const {createFixture,observed,stableHash}=require('./serve_wide_cinema_synthetic.cjs');
const {createHash}=require('node:crypto');
const webRoot=path.resolve(process.env.AFFINITYQA_WEB_ROOT||path.join(__dirname,'../../web'));
const {chromium}=createRequire(path.join(webRoot,'package.json'))('playwright');
assert.ok(!process.argv.includes('--real-posters'),'External poster requests are no longer part of this test or presentation policy');
const mobile=process.argv.includes('--mobile');
async function main(){
  const fixture=await createFixture({webRoot}),errors=[],externalRequests=[];let browser,imageEvidence=[];
  try{
    browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,args:['--no-sandbox','--disable-dev-shm-usage']}:{})});
    const context=await browser.newContext({viewport:mobile?{width:360,height:844}:{width:1440,height:1000},acceptDownloads:true});
    const page=await context.newPage();page.on('pageerror',value=>errors.push(value.message));
    await context.route('**/*',async route=>{const request=route.request(),url=new URL(request.url());assert.notEqual(url.port,'60882','The real local service is forbidden in synthetic browser tests');if(url.origin===fixture.origin){if(fixture.state.dropNextConfirm&&request.method()==='POST'&&url.pathname.endsWith('/confirm-wide')){fixture.state.dropNextConfirm=false;await route.fetch();return route.abort('failed')}return route.continue()}externalRequests.push(url.href);return route.abort('blockedbyclient');});
    const root=()=>page.locator('section[aria-labelledby="wide-cinema-title"]');
    const noInternalIdentifiers=async()=>{
      const text=await root().textContent();
      assert.doesNotMatch(text,/INSPECT CASE IDENTIFIERS|PLAN SHA-256|urn:entity:|\b[a-f0-9]{64}\b|\b[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}\b/i,'Discovery text must stay readable, including closed details and saved history');
      for(const id of fixture.state.jobs.keys())assert.ok(!text.includes(id),'Saved case identifiers stay in transport and verification, not page text');
    };
    const openSession=async()=>{const button=root().getByRole('button',{name:'OPEN OR RESTORE MY SESSION'});await button.click();await button.waitFor({state:'hidden'});};
    const openDraft=async()=>{if(!await root().getByLabel('FILM TITLE',{exact:true}).isVisible()&&!await root().getByLabel('ARTIST NAME',{exact:true}).isVisible()){await root().getByRole('button',{name:/^(NEW DISCOVERY|EDIT DRAFT)$/}).first().click();}};
    const openSaved=async()=>{if(!await root().locator('#wide-cinema-history').isVisible())await page.getByRole('navigation',{name:'Main navigation'}).getByRole('link',{name:'SAVED',exact:true}).click();await root().locator('#wide-cinema-history').waitFor({state:'visible'});};
    const prepare=async()=>{await root().getByRole('button',{name:'REVIEW MY DISCOVERY PLAN'}).click();await root().locator('[data-state="PLANNED"]').waitFor();await noInternalIdentifiers();};
    const noMutation=()=>fixture.state.posts.filter(row=>row.path!=='/api/demo/cases/session').length;
    const capture=async name=>{if(!process.env.AFFINITYQA_TEST_SCREENSHOT_DIR)return;const directory=path.resolve(process.env.AFFINITYQA_TEST_SCREENSHOT_DIR);fs.mkdirSync(directory,{recursive:true});await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));fs.writeFileSync(path.join(directory,name+'.png'),await page.screenshot({fullPage:true}),{flag:'wx'});};
    async function auditFixesRegression(which='all'){
      const before=noMutation();
      if(which!=='history'){
        const movies=[
          {entity_id:'50000000-0000-4000-8000-000000000001',name:'Scary Movie',release_year:2026,type:'urn:entity:movie'},
          {entity_id:'50000000-0000-4000-8000-000000000002',name:'Scary Movie',release_year:2026,type:'urn:entity:movie'},
          {entity_id:'50000000-0000-4000-8000-000000000003',name:'Scary Movie',release_year:2000,type:'urn:entity:movie'},
        ];
        const savedArtist={entity_id:'60000000-0000-4000-8000-000000000001',name:'Synthetic Björk',type:'urn:entity:artist'};
        const restore=async(mode,favorite)=>{
          const id=mode==='movie'?'ambiguous-seed-regression':'ambiguous-favorite-regression';
          const saved=fixture.addComplete(id,job=>Object.assign(job,{status:'AWAITING_IDENTITY_CONFIRMATION',discovery_mode:mode,seed_query:mode==='movie'?'Scary Movie':'Synthetic Björk',favorite_movie_query:favorite?'Scary Movie':null,intent_text:'',result:null,identity_receipt_sha256:'d'.repeat(64),seed_candidates:mode==='movie'?movies:[savedArtist],favorite_movie_candidates:favorite?movies:[],saved_provider_samples:favorite?2:1,saved_model_packets:0,receipt_sha256:undefined}));
          await page.evaluate(({id,music,movie,artist})=>{sessionStorage.setItem('affinityqa-wide-cinema-selected-case-v1',id);sessionStorage.setItem('affinityqa-wide-cinema-choice-v1',JSON.stringify({job_id:id,identity_receipt_sha256:'d'.repeat(64),selected_seed_entity_id:music?artist:movie,selected_favorite_movie_entity_id:music?movie:null}))},{id:saved.job_id,music:mode==='music',movie:movies[0].entity_id,artist:savedArtist.entity_id});
          await page.reload();await openSession();
          const group=root().getByRole('group',{name:favorite?'SELECT YOUR KNOWN FAVORITE FILM':'SELECT ONE FILM',exact:true});await group.waitFor();
          return group;
        };
        for(const mode of ['movie','music']){
          const group=await restore(mode,mode==='music'),radios=group.getByRole('radio');
          assert.ok(await radios.nth(0).isDisabled(),'Same-title/year movie record1 must not offer an indistinguishable choice');
          assert.ok(await radios.nth(1).isDisabled(),'Same-title/year movie record2 must not offer an indistinguishable choice');
          assert.ok(await radios.nth(2).isEnabled(),'The unambiguous2000 film remains available');
          assert.match(await group.innerText(),/cannot be distinguished with the supplied title and year/i);
          assert.ok(await root().getByRole('button',{name:'CONFIRM & DISCOVER FIVE',exact:true}).isDisabled(),'Restored ambiguous seed/favorite must not enable confirmation');
          await radios.nth(2).check();
          assert.ok(await root().getByRole('button',{name:'CONFIRM & DISCOVER FIVE',exact:true}).isEnabled(),'An explicitly chosen unique film can continue');
          await noInternalIdentifiers();
          await capture('ambiguous-'+(mode==='music'?'favorite':'seed')+(mobile?'-mobile':'-desktop'));
        }
      }
      if(which!=='identity'){
        fixture.state.historyPageSize=200;
        const pageId='older-page-regression',detailId='older-detail-regression';
        const planned=(id,title)=>fixture.addComplete(id,job=>Object.assign(job,{status:'PLANNED',seed_query:title,result:null,receipt_sha256:undefined,saved_provider_samples:0,saved_model_packets:0}));
        planned(pageId,'Older page transition');planned(detailId,'Older detail transition');
        for(let i=0;i<205;i++)planned('recent-history-'+i,'Recent history '+String(i).padStart(3,'0'));
        await openSaved();await root().getByRole('button',{name:'REFRESH',exact:true}).click();
        await root().getByRole('button',{name:'FILM · Recent history 204 PLANNED',exact:true}).waitFor();
        const earlier=root().getByRole('button',{name:'LOAD EARLIER DISCOVERIES',exact:true});
        await earlier.click();await earlier.waitFor({state:'hidden'});
        await root().getByRole('button',{name:'FILM · Older page transition PLANNED',exact:true}).waitFor();
        const names=()=>root().locator('#wide-cinema-history li>button strong').allTextContents();
        const originalOrder=await names();assert.ok(originalOrder.length>200);
        fixture.addComplete(pageId,job=>{job.seed_query='Older page transition'});
        await root().getByRole('button',{name:'REFRESH',exact:true}).click();await earlier.waitFor();
        await earlier.click();await earlier.waitFor({state:'hidden'});
        assert.equal(await root().getByRole('button',{name:'FILM · Older page transition COMPLETE',exact:true}).count(),1,'Fresh older-page status replaces the cached PLANNED row');
        assert.deepEqual(await names(),originalOrder,'Fresh statuses do not reorder history or drop earlier rows');
        fixture.addComplete(detailId,job=>{job.seed_query='Older detail transition'});
        await root().getByRole('button',{name:'FILM · Older detail transition PLANNED',exact:true}).click();
        await root().getByRole('heading',{name:'INSPIRED BY John Wick',exact:true}).waitFor();
        await openSaved();
        assert.equal(await root().getByRole('button',{name:'FILM · Older detail transition COMPLETE',exact:true}).count(),1,'Opening a fresh historical job updates its cached row even outside newest200');
        assert.deepEqual(await names(),originalOrder,'Remember updates the historical row in place');
        const downloadBefore=await (await page.request.get(fixture.origin+'/api/demo/cases/jobs/'+detailId+'/verification')).body();
        await page.reload();await openSession();await root().getByRole('heading',{name:'INSPIRED BY John Wick',exact:true}).waitFor();
        assert.deepEqual(await (await page.request.get(fixture.origin+'/api/demo/cases/jobs/'+detailId+'/verification')).body(),downloadBefore,'Restoring a historical result preserves its original verification bytes');
        await noInternalIdentifiers();
      }
      assert.equal(noMutation(),before,'History reads, local choices and restoration must not resubmit provider work');
      fixture.assertPreserved();
    }
    if(process.argv.includes('--audit-history-only')||process.argv.includes('--audit-identity-only')){
      await page.goto(fixture.origin+'/demo');await root().waitFor();await openSession();
      await auditFixesRegression(process.argv.includes('--audit-history-only')?'history':'identity');
      assert.deepEqual(errors,[]);
      process.stdout.write(JSON.stringify({status:'PASS',focused_audit_regression:process.argv.includes('--audit-history-only')?'history':'identity',viewport:mobile?'mobile':'desktop',provider_api_calls:0,model_calls:0,legacy_preserved:true})+'\n');return;
    }
    await page.goto(fixture.origin+'/demo');await root().waitFor({state:'visible'});
    await page.locator('.cinema-footer').getByText('Card artwork is original and decorative.',{exact:false}).waitFor();
    assert.doesNotMatch(await page.locator('.cinema-footer').innerText(),/images.*supplied by Qloo/,'Shared footer must agree with the original-art presentation');
    assert.equal(fixture.state.posts.length,0,'Mode discovery does not open a session');
    await openSession();await root().getByLabel('FILM TITLE',{exact:true}).fill('John Wick');await root().getByLabel('Your direction (optional)',{exact:true}).fill('Fast action, tense pace, no claim of guaranteed satisfaction.');
    await prepare();assert.equal(fixture.state.posts.at(-1).body.mode,'movie');
    await openDraft();await root().getByRole('button',{name:'START WITH AN ARTIST',exact:true}).click();assert.equal(await root().locator('[data-state="PLANNED"]').count(),0,'Mode change invalidates an unexecuted plan');
    await root().getByRole('button',{name:'START WITH A FILM',exact:true}).click();await root().getByLabel('FILM TITLE',{exact:true}).fill('John Wick');await prepare();
    await root().getByRole('button',{name:'FIND MY FILM',exact:true}).click();await root().getByRole('heading',{name:'CONFIRM YOUR STARTING POINT'}).waitFor();
    await noInternalIdentifiers();
    assert.ok(await root().getByRole('button',{name:'CONFIRM & DISCOVER FIVE',exact:true}).isDisabled());assert.equal(await root().getByRole('radio',{checked:true}).count(),0);assert.ok(await root().getByRole('radio').last().isDisabled(),'A missing release year cannot be confirmed');
    await root().getByRole('group',{name:'SELECT ONE FILM',exact:true}).getByRole('radio').first().check();
    const beforeReload=noMutation();await page.reload();await openSession();await root().getByText('Your previous selection was restored.',{exact:false}).waitFor();assert.equal(noMutation(),beforeReload,'Restoring manual choice makes no repeated POST');
    fixture.state.remainingExecutions=0;await root().getByRole('button',{name:'REFRESH SAVED STATUS',exact:true}).click();await page.waitForFunction(element=>!element.disabled,await root().getByRole('button',{name:'CONFIRM & DISCOVER FIVE',exact:true}).elementHandle());assert.ok(await root().getByRole('button',{name:'CONFIRM & DISCOVER FIVE',exact:true}).isEnabled(),'Confirmation reuses the admitted execution');
    await root().getByRole('button',{name:'CONFIRM & DISCOVER FIVE',exact:true}).click();await root().getByRole('heading',{name:'INSPIRED BY John Wick',exact:true}).waitFor();
    await noInternalIdentifiers();
    const completedJob=[...fixture.state.jobs.values()].find(job=>job.status==='COMPLETE');assert.ok(completedJob);
    const physicalDownload=page.waitForEvent('download');await root().getByRole('link',{name:'DOWNLOAD DISCOVERY VERIFICATION',exact:true}).click();
    const downloaded=await physicalDownload;assert.equal(await downloaded.failure(),null);const verificationBytes=fs.readFileSync(await downloaded.path());const verification=JSON.parse(verificationBytes);
    assert.equal(verification.job_id,completedJob.job_id);assert.deepEqual(verification.result,completedJob.result,'The original IDs and evidence remain in the downloaded verification');
    assert.equal(fixture.state.posts.find(row=>row.path.endsWith('/execute')).body.plan_sha256,completedJob.plan_sha256,'Hidden hashes still bind the reviewed execution request');
    if(process.env.AFFINITYQA_TEST_NATIVE_RECEIPT)fs.writeFileSync(process.env.AFFINITYQA_TEST_NATIVE_RECEIPT,verificationBytes,{flag:'wx'});
    const cards=root().locator('[data-result-movie-id]');
    const assertOriginalArtwork=async()=>{
      assert.equal(await cards.count(),5);
      assert.equal(await cards.locator('img,image,svg use').count(),0,'No external image element may render, even with archived URLs');
      for(let i=0;i<5;i++){
        const card=cards.nth(i);await card.scrollIntoViewIfNeeded();
        const art=card.locator('svg.film-abstract-art');await art.waitFor();
        assert.equal(await art.getAttribute('aria-hidden'),'true','Decorative art does not describe a film');
        await card.getByText('ORIGINAL ILLUSTRATION',{exact:true}).waitFor();
        const bounds=await art.boundingBox();assert.ok(bounds&&bounds.width>50&&bounds.height>50,'Original vector art is visibly rendered');
      }
      assert.deepEqual(externalRequests,[],'Neither safe nor unsafe historical artwork may trigger external traffic');
    };
    await assertOriginalArtwork();
    for(let i=0;i<5;i++){assert.equal(await cards.nth(i).getAttribute('data-result-movie-id'),observed[i].entity_id);assert.equal(await cards.nth(i).locator('h3').textContent(),observed[i].name);}
    assert.deepEqual(verification.result.wide_cinema_results.presentation_assets,completedJob.result.wide_cinema_results.presentation_assets,'Archived image metadata stays byte-bound in verification despite the presentation change');
    imageEvidence=await cards.evaluateAll(rows=>rows.map(row=>{const image=row.querySelector('svg.film-abstract-art');return {entity_id:row.getAttribute('data-result-movie-id'),kind:'original-decorative-svg',rendered_width:image.getBoundingClientRect().width,rendered_height:image.getBoundingClientRect().height}}));
    await root().locator('summary').filter({hasText:'HOW THESE WERE CHOSEN'}).click();await root().locator('summary').filter({hasText:'INSPECT THE RETRIEVED FILM POOL'}).click();assert.equal(await root().locator('summary').filter({hasText:'INSPECT THE RETRIEVED FILM POOL'}).locator('..').locator('ul>li').count(),100);await root().locator('summary').filter({hasText:'INSPECT THE RETRIEVED FILM POOL'}).click();await root().locator('summary').filter({hasText:'HOW THESE WERE CHOSEN'}).click();await capture('wide-five-'+'original-art'+(mobile?'-mobile':'-desktop'));
    await openDraft();await root().getByRole('button',{name:'START WITH AN ARTIST',exact:true}).click();assert.equal(await root().getByRole('heading',{name:'INSPIRED BY John Wick',exact:true}).count(),1,'Saved result is not relabelled by draft mode');await root().getByText('This saved case keeps the starting point and direction shown here. Editing a draft does not change it.',{exact:true}).waitFor();
    const beforeSavedNotice=noMutation();
    await openSaved();await root().getByRole('button',{name:'FILM · John Wick COMPLETE',exact:true}).click();
    assert.equal(await root().getByLabel('ARTIST NAME',{exact:true}).isVisible(),false,'Saved-only view has no artist draft form');
    assert.equal(await root().getByLabel('FILM TITLE',{exact:true}).isVisible(),false,'Saved-only view has no film draft form');
    await root().getByText('This saved case keeps the starting point and direction shown here. Editing a draft does not change it.',{exact:true}).waitFor();
    assert.doesNotMatch(await root().innerText(),/The form above is a new draft\./,'Saved notice must not refer to a hidden form');
    assert.equal(await root().getByRole('heading',{name:'INSPIRED BY John Wick',exact:true}).count(),1,'Saved identity stays bound to the original film');
    assert.equal(await cards.count(),5,'Saved results stay visible');
    assert.equal(noMutation(),beforeSavedNotice,'Opening Saved must not submit a new search or model request');
    await capture('saved-notice'+(mobile?'-mobile':'-desktop'));
    await openDraft();
    fixture.state.remainingExecutions=null;await root().getByRole('button',{name:'REFRESH SAVED STATUS',exact:true}).click();await root().getByLabel('ARTIST NAME',{exact:true}).fill('Massive Attack');await root().getByLabel('ONE FILM YOU ALREADY LIKE',{exact:false}).fill('Gladiator');await prepare();await root().getByRole('button',{name:'FIND MY ARTIST & FAVORITE FILM',exact:true}).click();
    await root().getByRole('group',{name:'SELECT YOUR KNOWN FAVORITE FILM',exact:true}).getByRole('radio').last().check();assert.ok(await root().getByRole('button',{name:'CONFIRM & DISCOVER FIVE',exact:true}).isDisabled());await root().getByRole('group',{name:'SELECT ONE ARTIST',exact:true}).getByRole('radio').check();
    fixture.state.dropNextConfirm=true;const beforeLost=noMutation();await root().getByRole('button',{name:'CONFIRM & DISCOVER FIVE',exact:true}).click();await root().getByText('The response is uncertain.',{exact:false}).waitFor();assert.equal(noMutation(),beforeLost+1);await root().getByRole('button',{name:'CHECK CURRENT STATUS',exact:true}).click();await root().getByRole('heading',{name:'INSPIRED BY Synthetic Massive Attack',exact:true}).waitFor();assert.equal(noMutation(),beforeLost+1,'Lost confirmation is recovered through reads only');
    const last=fixture.state.posts.filter(row=>row.path.endsWith('/confirm-wide')).at(-1).body;assert.equal(last.selected_favorite_movie_entity_id,'30000000-0000-4000-8000-000000000002');
    const counts=noMutation();await page.getByRole('navigation',{name:'Main navigation'}).getByRole('link',{name:'PREVIOUS COMPARISONS',exact:true}).click();const legacyRoot=page.locator('section[aria-labelledby="individual-title"]');await legacyRoot.getByRole('button',{name:'OPEN OR RESTORE MY SESSION'}).click();await page.locator('#saved-cases').getByRole('button',{name:/Preserved artist A/}).click();await legacyRoot.getByRole('heading',{name:'PRESERVED CASE · READ ONLY'}).waitFor();fixture.assertPreserved();assert.equal(noMutation(),counts,'Opening the historical case makes no mutation');
    await page.getByRole('navigation',{name:'Main navigation'}).getByRole('link',{name:'FILM DISCOVERY',exact:true}).click();assert.equal(await root().getByRole('heading',{name:'INSPIRED BY Synthetic Massive Attack',exact:true}).count(),1,'The new component stays mounted across mode navigation');
    fixture.addComplete('unsafe-images',job=>{const assets=job.result.wide_cinema_results.presentation_assets;assets[0].url='https://untrusted.invalid/poster.jpg';assets[1].url=observed[0].url;assets[2].identity_sha256='0'.repeat(64);assets[3].url=observed[3].url+'?tracking=bad';});await root().getByRole('button',{name:'REFRESH SAVED STATUS',exact:true}).click();await openSaved();await root().getByRole('button',{name:/FILM · Saved fixture film/}).click();await root().getByRole('heading',{name:'INSPIRED BY John Wick',exact:true}).waitFor();await page.reload();await openSession();await root().getByRole('heading',{name:'INSPIRED BY John Wick',exact:true}).waitFor();assert.equal(await cards.count(),5);await assertOriginalArtwork();assert.equal(await cards.locator('h3').count(),5);await capture('wide-archived-art'+(mobile?'-mobile':'-desktop'));
    await openSaved();await root().getByRole('button',{name:'LOAD EARLIER DISCOVERIES',exact:true}).click();await root().getByRole('button',{name:'FILM · John Wick PLANNED',exact:true}).waitFor();await noInternalIdentifiers();assert.ok(fixture.state.reads.some(value=>value==='/api/demo/cases/wide-cinema/jobs/older-than/wide-fixture-2'),'History pagination keeps its transport cursor while displaying readable case names');
    fixture.addComplete('unknown-result',job=>{job.status='UNKNOWN';job.result=null;job.seed_query='Unknown fixture outcome';});await root().getByRole('button',{name:'REFRESH',exact:true}).click();await root().getByRole('button',{name:/FILM · Unknown fixture outcome/}).click();await root().getByRole('heading',{name:'PROVIDER RESULT UNKNOWN'}).waitFor();assert.equal(await cards.count(),0);assert.equal(await root().getByRole('button',{name:'CONFIRM & DISCOVER FIVE',exact:true}).count(),0);
    fixture.addComplete('truncated-reason',job=>{job.seed_query='Truncated reason fixture';job.result.wide_cinema_results.reasons[0].text='Too short.';});await root().getByRole('button',{name:'REFRESH SAVED STATUS',exact:true}).click();await openSaved();await root().getByRole('button',{name:/FILM · Truncated reason fixture/}).click();await cards.first().getByText('Fuente: Qloo · Español',{exact:true}).waitFor();assert.equal(await cards.count(),5,'Historical prose is ignored while the bound display is checked independently');assert.doesNotMatch(await cards.allTextContents().then(rows=>rows.join(' ')),/Too short/);
    const legacyCanary='LEGACY_BOXER_CLAIM_MUST_NOT_RENDER: an invented historical champion remains in the archived receipt only.';
    const literal='<script>window.syntheticPwned=true</script> Esta ficha sintética se muestra literalmente como texto, sin ejecutar HTML.';
    const archived=fixture.addComplete('source-bound-archive',job=>{job.seed_query='Source-bound archived fixture';job.result.wide_cinema_results.reasons[0].text=legacyCanary;const display=job.wide_cinema_display;display.reasons[0].text=literal;display.reasons[0].evidence.value_sha256=createHash('sha256').update(literal).digest('hex');const {binding_sha256,...body}=display;display.binding_sha256=stableHash(body);});
    const beforeArchive=noMutation();await root().getByRole('button',{name:'REFRESH SAVED STATUS',exact:true}).click();await openSaved();await root().getByRole('button',{name:/FILM · Source-bound archived fixture/}).click();await cards.first().getByText('Fuente: Qloo · Español',{exact:true}).waitFor();assert.equal(await cards.first().locator('p').textContent(),literal);assert.equal(await cards.first().locator('script').count(),0);assert.equal(await page.evaluate(()=>window.syntheticPwned),undefined);assert.doesNotMatch((await cards.allTextContents()).join(' '),/LEGACY_BOXER_CLAIM_MUST_NOT_RENDER/);assert.equal(await root().getByText('Fuente: Qloo · English',{exact:true}).count(),1);assert.equal(await root().getByText('Ficha breve no disponible · Sin detalles de trama',{exact:true}).count(),1);await root().getByText('La explicación original de IA se conserva archivada.',{exact:false}).waitFor();
    const downloadUrl=fixture.origin+'/api/demo/cases/jobs/'+archived.job_id+'/verification';const originalDownload=await (await page.request.get(downloadUrl)).body();assert.equal(JSON.parse(originalDownload).result.wide_cinema_results.reasons[0].text,legacyCanary);assert.ok(!originalDownload.includes(Buffer.from('wide_cinema_display')));await page.reload();await openSession();await cards.first().getByText('Fuente: Qloo · Español',{exact:true}).waitFor();assert.deepEqual(await (await page.request.get(downloadUrl)).body(),originalDownload);assert.equal(noMutation(),beforeArchive,'Saved source display and download restore use reads only');await capture('grounded-archive'+(mobile?'-mobile':'-desktop'));
    fixture.addComplete('current-v10',job=>{job.seed_query='Current v10 index-only fixture';job.wide_cinema_display.protocol_version='qloo-wide-cinema-discovery-v10';job.wide_cinema_display.legacy_original_archived=false;job.wide_cinema_display.notice='La IA selecciona; Qloo aporta la ficha. La fidelidad a la fuente no acredita su verdad ni la afinidad cultural.';const {binding_sha256,...body}=job.wide_cinema_display;job.wide_cinema_display.binding_sha256=stableHash(body);});
    await root().getByRole('button',{name:'REFRESH SAVED STATUS',exact:true}).click();await openSaved();await root().getByRole('button',{name:/FILM · Current v10 index-only fixture/}).click();await cards.first().getByText('Fuente: Qloo · Español',{exact:true}).waitFor();assert.equal(await cards.count(),5);await root().getByText('La IA selecciona; Qloo aporta la ficha.',{exact:false}).waitFor();assert.equal(await root().getByText('La explicación original de IA se conserva archivada.',{exact:false}).count(),0);
    fixture.addComplete('forged-source-display',job=>{job.seed_query='Tampered source fixture';job.result.wide_cinema_results.reasons[0].text=legacyCanary;job.wide_cinema_display.reasons[0].text='An unbound invented plot must fail the source display digest and remain invisible.';});await root().getByRole('button',{name:'REFRESH SAVED STATUS',exact:true}).click();await openSaved();await root().getByRole('button',{name:/FILM · Tampered source fixture/}).click();await root().getByText('La ficha vinculada no está disponible.',{exact:false}).waitFor();assert.equal(await cards.count(),5);assert.equal(await root().getByText('Fuente: Qloo · Español',{exact:true}).count(),0);assert.doesNotMatch((await cards.allTextContents()).join(' '),/unbound invented|LEGACY_BOXER_CLAIM_MUST_NOT_RENDER/);
    // Artist-choice regression: exact full-name ARTIST stays primary; all five
    // original rows remain selectable, and restoring a choice never submits it.
    const artistRows=[
      {entity_id:'40000000-0000-4000-8000-000000000001',name:'Eminem & Jay-Z',type:'urn:entity:artist'},
      {entity_id:'40000000-0000-4000-8000-000000000002',name:'Eminem',type:'urn:entity:person'},
      {entity_id:'40000000-0000-4000-8000-000000000003',name:'Eminem',type:'urn:entity:artist'},
      {entity_id:'40000000-0000-4000-8000-000000000004',name:'Eminem & Dr. Dre',type:'urn:entity:artist'},
      {entity_id:'40000000-0000-4000-8000-000000000005',name:'Eminem, 50 Cent & Nate Dogg',type:'urn:entity:artist'},
    ];
    const artistJob=fixture.addComplete('artist-choice-regression',job=>Object.assign(job,{status:'AWAITING_IDENTITY_CONFIRMATION',discovery_mode:'music',seed_query:'  eMiNeM  ',favorite_movie_query:null,intent_text:'',result:null,identity_receipt_sha256:'d'.repeat(64),seed_candidates:artistRows,favorite_movie_candidates:[],saved_provider_samples:1,saved_model_packets:0,receipt_sha256:undefined}));
    await page.evaluate(id=>{sessionStorage.setItem('affinityqa-wide-cinema-selected-case-v1',id);sessionStorage.removeItem('affinityqa-wide-cinema-choice-v1')},artistJob.job_id);
    const beforeArtistChoices=noMutation();await page.reload();await openSession();
    const artistGroup=root().getByRole('group',{name:'SELECT ONE ARTIST',exact:true});await artistGroup.waitFor();
    await noInternalIdentifiers();
    const alternativeDetails=artistGroup.locator('details');
    assert.equal(await artistGroup.locator(':scope > label').count(),1);
    assert.equal(await artistGroup.locator(':scope > label input').inputValue(),artistRows[2].entity_id);
    assert.equal(await artistGroup.getByRole('radio',{checked:true}).count(),0);
    assert.ok(await root().getByRole('button',{name:'CONFIRM & DISCOVER FIVE',exact:true}).isDisabled());
    assert.equal(await artistGroup.locator('label code,label [title]').count(),0);
    assert.doesNotMatch(await artistGroup.locator(':scope > label').innerText(),/urn:entity:|[a-f0-9]{8}-[a-f0-9]{4}-/i);
    assert.match(await artistGroup.locator('summary').innerText(),/Other matches & collaborations \(4\)/);
    assert.equal(await alternativeDetails.getAttribute('open'),null);
    await capture('artist-choice'+(mobile?'-mobile':'-desktop'));
    await artistGroup.locator('summary').focus();await page.keyboard.press('Enter');
    await alternativeDetails.locator('input').last().check();
    assert.match(await alternativeDetails.innerText(),/PERSON PROFILE/);
    const selectedArtist=await artistGroup.getByRole('radio',{checked:true}).inputValue();
    assert.equal(selectedArtist,artistRows[4].entity_id);assert.equal(noMutation(),beforeArtistChoices);
    await page.reload();await openSession();await root().getByText('Your previous selection was restored.',{exact:false}).waitFor();
    assert.equal(await artistGroup.getByRole('radio',{checked:true}).inputValue(),selectedArtist);
    assert.notEqual(await alternativeDetails.getAttribute('open'),null);
    assert.equal(noMutation(),beforeArtistChoices,'Artist grouping, keyboard choice and restoration make no provider POST');
    await auditFixesRegression();
    fixture.assertPreserved();assert.deepEqual(errors,[]);assert.deepEqual(externalRequests,[]);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth),false,'No horizontal overflow');
    process.stdout.write(JSON.stringify({status:'PASS',viewport:mobile?'mobile':'desktop',candidate_count:100,delivered_count:5,image_evidence:'five-visible-original-illustrations',external_image_requests:externalRequests.length,images:imageEvidence,provider_api_calls:0,model_calls:0,posts:fixture.state.posts.length,recovery_without_repeat:true,legacy_preserved:true,history_pagination:true,history_status_refresh_in_place:true,saved_notice_without_visible_draft:true,ambiguous_seed_and_favorite_blocked:true,technical_identifiers_hidden:true,verification_identifiers_preserved:true,physical_download_bytes:verificationBytes.length})+'\n');
  }finally{if(browser)await browser.close();await fixture.close();}
}
main().catch(error=>{process.stderr.write(error.stack+'\n');process.exitCode=1});
