// Synthetic local browser acceptance. No provider calls or personal profile.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {spawn}=require('node:child_process');
const {createRequire}=require('node:module');
const webRoot=path.resolve(process.env.AFFINITYQA_WEB_ROOT||path.join(__dirname,'../../web'));
const {chromium}=createRequire(path.join(webRoot,'package.json'))('playwright');
const mobile=process.argv.includes('--mobile');
async function main(){
  const python=process.env.AFFINITYQA_TEST_PYTHON||'python';
  const child=spawn(python,['-B',path.join(__dirname,'serve_diagnostic_synthetic.py'),'--exit-after-seconds','150'],{stdio:['pipe','pipe','pipe'],env:process.env});
  let stdout='',stderr='',browser;
  child.stdout.on('data',chunk=>stdout+=chunk);child.stderr.on('data',chunk=>stderr+=chunk);
  try{
    const origin=await new Promise((resolve,reject)=>{
      const deadline=setTimeout(()=>reject(Error('Synthetic host did not start: '+stderr)),30000);
      const inspect=()=>{const line=stdout.split('\n').find(line=>line.includes('ready_origin'));if(line){clearTimeout(deadline);resolve(JSON.parse(line).ready_origin)}};
      child.stdout.on('data',inspect);child.once('exit',code=>{clearTimeout(deadline);reject(Error('Synthetic host exited '+code+': '+stderr))});inspect();
    });
    browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,args:['--no-sandbox','--disable-dev-shm-usage']}:{})});
    const context=await browser.newContext({viewport:mobile?{width:360,height:844}:{width:1440,height:1000}});
    const page=await context.newPage(),errors=[];
    page.on('pageerror',value=>errors.push(value.message));
    let faultMode='',replays=0;
    await context.route('**/*',async route=>{
      const url=new URL(route.request().url());
      assert.equal(url.origin,origin,'All browser traffic stays on the owned synthetic host');
      if(url.pathname==='/api/demo/replay'){
        replays++;
        if(faultMode==='busy')return route.fulfill({status:429,contentType:'application/json',body:'{"error":"Synthetic busy"}'});
        if(faultMode==='unavailable')return route.fulfill({status:503,contentType:'application/json',body:'{"error":"Synthetic unavailable"}'});
        if(faultMode){
          const response=await route.fetch(),value=await response.json();
          if(faultMode==='missing')delete value.diagnostic_evidence;
          if(faultMode==='truthy')value.diagnostic_evidence.checks.model_payload_bound=1;
          if(faultMode==='mismatch')value.diagnostic_evidence.diagnosis='STALE_PROFILE';
          if(faultMode==='downgrade'){value.schema_version=1;delete value.diagnostic_evidence}
          if(faultMode==='extra')value.diagnostic_evidence.private_packet='PRIVATE_CANARY_MUST_NOT_RENDER';
          return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(value)});
        }
      }
      return route.continue();
    });
    await page.goto(origin+'/demo#recorded');
    const root=page.locator('section[aria-labelledby="public-demo-title"]');
    await root.getByRole('button',{name:'Replay this incident',exact:true}).waitFor();
    await page.getByText('SYNTHETIC LOCAL VALIDATION · NO REAL PROVIDER CALLS',{exact:true}).waitFor();
    const proof=()=>page.getByRole('region',{name:'Verified Qloo diagnosis and repair',exact:true});
    const clickReplay=async()=>{await root.getByRole('button',{name:'Replay this incident',exact:true}).click()};
    const faultNames=['cache-omits-profile','stale-profile','wrong-tool-profile'];
    for(const fault of faultNames){
      await root.getByLabel('Demo fault',{exact:true}).selectOption(fault);
      for(const repeat of [1,2,3]){
        await root.getByLabel('Demo repeat',{exact:true}).selectOption(String(repeat));await clickReplay();
        await proof().getByText('EVIDENCE CHECKED',{exact:true}).waitFor();
        assert.match(await root.innerText(),/Replay PASS/);
        assert.equal(await proof().getByRole('heading',{name:'WHAT FAILED. WHAT CHANGED.',exact:true}).count(),1);
        assert.equal(await proof().locator('code').count(),0,'Ordinary proof cards contain no technical codes');
        assert.doesNotMatch(await proof().innerText(),/[a-f0-9]{64}|urn:entity:|PRIVATE_CANARY/);
        assert.equal(await root.locator('ol').count(),3); // before / after / healthy
        const beforeFilms=await root.locator('ol').nth(1).innerText();
        assert.equal(await root.locator('ol').nth(2).innerText(),beforeFilms,'Repair reaches recorded healthy movies');
        const summary=proof().locator('summary');await summary.focus();await page.keyboard.press('Enter');
        assert.equal(await proof().locator('li strong').filter({hasText:'PASS'}).count(),8);
        await page.keyboard.press('Enter');
        for(const name of ['Detect','Diagnose','Repair','Verify'])await root.getByRole('navigation',{name:'Demo investigation stages'}).getByRole('button',{name:new RegExp(name)}).click();
        const size=await page.evaluate(()=>({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth}));
        assert.ok(size.scroll<=size.width+1,'No horizontal overflow');
      }
    }
    if(process.env.AFFINITYQA_TEST_SCREENSHOT){fs.writeFileSync(process.env.AFFINITYQA_TEST_SCREENSHOT,await page.screenshot({fullPage:true}),{flag:'wx'})}
    for(const mode of ['missing','truthy','mismatch','downgrade','extra','busy','unavailable']){
      faultMode=mode;await clickReplay();
      const alert=root.getByRole('alert');await alert.waitFor();
      assert.equal(await proof().count(),0,'Invalid proof cannot retain a prior successful repair');
      assert.doesNotMatch(await root.innerText(),/PRIVATE_CANARY_MUST_NOT_RENDER/);
      assert.match(await alert.innerText(),mode==='busy'?/busy/:/verified|approved/);
    }
    faultMode='';await clickReplay();await proof().getByText('EVIDENCE CHECKED',{exact:true}).waitFor();
    assert.equal(errors.length,0,errors.join('\n'));
    const receipt={status:'PASS',provenance:'synthetic local backend and browser; not real Qloo or model evidence',mobile,
      controls:{three_faults_three_repeats:true,eight_semantic_checks:true,healthy_recovery:true,keyboard:true,
        no_overflow:true,malformed_proofs_blocked:true,downgrade_blocked:true,busy_and_failure:true,zero_provider_calls:true},
      replays_requested:replays,real_qloo_calls:0,real_model_calls:0};
    if(process.env.AFFINITYQA_TEST_NATIVE_RECEIPT)fs.writeFileSync(process.env.AFFINITYQA_TEST_NATIVE_RECEIPT,JSON.stringify(receipt,null,2),{flag:'wx'});
    console.log(JSON.stringify(receipt));
  }finally{
    if(browser)await browser.close();
    if(child.exitCode===null){child.stdin.write('stop\n');await new Promise(resolve=>{child.once('exit',resolve);setTimeout(resolve,5000)})}
    if(child.exitCode===null)child.kill();
  }
}
main().catch(error=>{console.error(error);process.exitCode=1});
