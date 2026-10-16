// Real built frontend; API responses are explicit synthetic fixtures.
// This checks the browser contract, not provider access or recommendation quality.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const http=require('node:http');
const path=require('node:path');
const {createHash}=require('node:crypto');
const {createRequire}=require('node:module');
const {chromium}=createRequire(path.resolve(__dirname,'../../web/package.json'))('playwright');
const root=path.resolve(__dirname,'../../web/out');
const artists={A:'Synthetic artist A',B:'Synthetic artist B'};
const catalog=Array.from({length:20},(_,i)=>({entity_id:`catalog-film-${i}`,name:`Synthetic catalog film ${i}`,release_year:1980+i}));
const artistIds={A:{entity_id:'artist-A',name:artists.A,type:'urn:entity:artist'},B:{entity_id:'artist-B',name:artists.B,type:'urn:entity:artist'}};
const films={
  gladiator1992:{entity_id:'film-gladiator-1992',name:'Gladiator',release_year:1992,type:'urn:entity:movie'},
  gladiator2000:{entity_id:'film-gladiator-2000',name:'Gladiator',release_year:2000,type:'urn:entity:movie'},
  thing1951:{entity_id:'film-thing-1951',name:'The Thing',release_year:1951,type:'urn:entity:movie'},
  thing1982:{entity_id:'film-thing-1982',name:'The Thing',release_year:1982,type:'urn:entity:movie'},
  invalidYear:{entity_id:'film-year-unverified',name:'Gladiator',release_year:null,type:'urn:entity:movie'},
};
const emptyPreferences=()=>({schema_version:1,favorite_entity_ids:[],excluded_entity_ids:[]});
const preferenceRows=()=>Object.fromEntries(['A','B'].map(profile=>[profile,{preferences_sha256:'f'.repeat(64),intent_sha256:'e'.repeat(64),raw_ranking:catalog.map(movie=>movie.entity_id),delivered:catalog.slice(0,5).map(movie=>movie.entity_id),baseline_delivered:catalog.slice(0,5).map(movie=>movie.entity_id),raw_ranking_sha256:'d'.repeat(64),delivery_sha256:'c'.repeat(64),eligible_count:20,selection_changed:false,excluded_removed:[],preference_gate:'PASS',known_favorite_count:0,discovery_count:5}]));
const verifiedResult=()=>({verification_status:'VERIFIED_COMPLETE',provenance:'SYNTHETIC',causal_gate:'NOT_EVALUATED',behavioral_gate:'NOT_EVALUATED',cultural_gate:'NOT_VALIDATED',release_gate:'BLOCKED',qloo_attempts:6,model_attempts:2,external_service_attested:false,preference_gate:'PASS',cinema_results:preferenceRows()});
const makeJob=(id)=>({job_id:id,status:'PLANNED',artists,preferences:{A:emptyPreferences(),B:emptyPreferences()},model:'synthetic',operator_mode:'groq',maximum_qloo_requests:4,maximum_model_decisions:2,saved_provider_samples:0,saved_model_packets:0,declared_faults:0,model_load_requests:0,model_metadata_requests:0,plan_sha256:'a'.repeat(64),catalog_sha256:'b'.repeat(64),simulation_only:true,error_class:null,result:null,case_protocol:'cinema-confirmed-discovery-v3',identity_queries:artists,admission_mode:'repeatable-v1'});
const clone=value=>JSON.parse(JSON.stringify(value));

async function main(){
  const historical={...makeJob('historical-complete'),status:'COMPLETE',saved_provider_samples:4,saved_model_packets:2,result:verifiedResult()};
  const historicalHash=createHash('sha256').update(JSON.stringify(historical)).digest('hex');
  const jobs=new Map([[historical.job_id,historical]]),posts=[],errors=[];
  let capabilityEnabled=false,confirmations=0;
  const server=http.createServer((req,res)=>{
    const url=new URL(req.url,'http://127.0.0.1');
    const receipt=url.pathname.match(/^\/api\/demo\/cases\/jobs\/([^/]+)\/verification$/);
    if(receipt){const job=jobs.get(receipt[1]);if(!job?.result){res.writeHead(404).end();return;}const bytes=JSON.stringify({schema_version:1,job_id:job.job_id,result:job.result,chosen_movie_inputs:job.chosen_movie_inputs});res.writeHead(200,{'Content-Type':'application/json','Content-Disposition':`attachment; filename="${job.job_id}-verification.json"`,'Content-Length':Buffer.byteLength(bytes)});res.end(bytes);return;}
    const file=path.resolve(root,url.pathname==='/demo'||url.pathname==='/demo/'?'demo.html':url.pathname.slice(1));
    if(!file.startsWith(root+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404).end();return;}
    res.setHeader('Content-Type',({'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml'})[path.extname(file)]||'application/octet-stream');fs.createReadStream(file).pipe(res);
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const origin=`http://127.0.0.1:${server.address().port}`;
  let browser;
  try{
    browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,args:['--no-sandbox','--disable-dev-shm-usage']}:{})});
    const context=await browser.newContext({acceptDownloads:true,viewport:process.argv.includes('--mobile')?{width:390,height:844}:{width:1280,height:900}});
    const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
    const capture=async name=>{if(!process.env.AFFINITYQA_TEST_SCREENSHOT_DIR)return;const directory=path.resolve(process.env.AFFINITYQA_TEST_SCREENSHOT_DIR);fs.mkdirSync(directory,{recursive:true});fs.writeFileSync(path.join(directory,name+'.png'),await page.screenshot({fullPage:true}),{flag:'wx'});};
    const capabilities=()=>({configured:true,execution_enabled:true,simulation_only:true,admission_mode:'repeatable-v1',remaining_plans:null,remaining_executions:null,operator_mode:'groq',model:'synthetic',catalog,default_artists:artists,cinema_preferences_supported:true,cinema_identity_confirmation_supported:true,cinema_discoveries_supported:true,...(capabilityEnabled?{movie_input_search_supported:true,maximum_movie_queries_per_case:2}:{}),jobs:[...jobs.values()].map(({job_id,status,artists})=>({job_id,status,artists}))});
    await context.route(url=>!/^\/api\/demo\/cases\/jobs\/[^/]+\/verification$/.test(url.pathname),async route=>{
      const req=route.request(),url=new URL(req.url());assert.equal(url.origin,origin,'External browser requests forbidden');
      const json=body=>route.fulfill({json:clone(body)});
      if(req.method()==='POST')posts.push({path:url.pathname,body:req.postDataJSON()});
      if(url.pathname==='/healthz')return json({new_cases_configured:true});
      if(url.pathname==='/api/demo/summary')return json({schema_version:1,status:'UNAVAILABLE',pairs:[]});
      if(url.pathname==='/api/demo/cases/session')return json({schema_version:1,csrf_token:'c'.repeat(64),expires_utc:'2099-01-01T00:00:00Z'});
      if(url.pathname==='/api/demo/cases/capabilities')return json(capabilities());
      if(url.pathname==='/api/demo/cases/plans'){
        const body=req.postDataJSON();const count=(body.movie_queries?.A.length??0)+(body.movie_queries?.B.length??0);assert.ok(count<=2);
        const job={...makeJob(`movie-case-${jobs.size}`),preferences:body.preferences};
        if(count)Object.assign(job,{case_protocol:'cinema-confirmed-discovery-v4',movie_queries:body.movie_queries,maximum_qloo_requests:4+count});
        jobs.set(job.job_id,job);return json(job);
      }
      const match=url.pathname.match(/^\/api\/demo\/cases\/jobs\/([^/]+)(?:\/(execute|confirm-identities))?$/);
      if(match){const job=jobs.get(match[1]);assert.ok(job,'Owned case exists');
        if(match[2]==='execute'){
          assert.equal(job.status,'PLANNED');Object.assign(job,{status:'AWAITING_IDENTITY_CONFIRMATION',identity_receipt_sha256:'d'.repeat(64),identity_candidates:{A:[artistIds.A],B:[artistIds.B]},saved_provider_samples:job.maximum_qloo_requests-2});
          if(job.movie_queries)job.movie_candidates=Object.fromEntries(['A','B'].map(profile=>[profile,job.movie_queries[profile].map(query=>query==='No matching film'?[]:query.includes('Thing')?[films.thing1951,films.thing1982]:[films.gladiator1992,films.gladiator2000,films.invalidYear])]));return json(job);
        }
        if(match[2]==='confirm-identities'){
          const body=req.postDataJSON();assert.equal(job.status,'AWAITING_IDENTITY_CONFIRMATION');assert.deepEqual(body.selected_entity_ids,{A:'artist-A',B:'artist-B'});
          if(job.movie_queries){assert.deepEqual(Object.keys(body.selected_movie_entity_ids).sort(),['A','B']);
            job.chosen_movie_inputs=Object.fromEntries(['A','B'].map(profile=>{const selected=body.selected_movie_entity_ids[profile];assert.equal(selected.length,job.movie_queries[profile].length);assert.equal(new Set(selected).size,selected.length);return [profile,selected.map((id,slot)=>{const movie=job.movie_candidates[profile][slot].find(value=>value.entity_id===id);assert.ok(movie&&Number.isInteger(movie.release_year));return movie;})];}));
          }else assert.equal(Object.hasOwn(body,'selected_movie_entity_ids'),false);
          confirmations++;Object.assign(job,{status:'COMPLETE',chosen_identities:artistIds,saved_provider_samples:job.maximum_qloo_requests,saved_model_packets:2,result:verifiedResult()});return json(job);
        }return json(job);
      }
      if(url.pathname.startsWith('/api/'))throw Error('Unexpected API request '+url.pathname);return route.continue();
    });
    const openSession=async()=>{await page.getByRole('button',{name:'OPEN OR RESTORE MY SESSION',exact:true}).click();await page.getByRole('heading',{name:'YOUR MUSICAL INTERESTS',exact:true}).waitFor();};
    const plan=async()=>{await page.getByRole('button',{name:'REVIEW A NEW PLAN',exact:true}).click();await page.getByRole('status').filter({hasText:/^PLANNED$/}).waitFor();};
    const chooseArtists=async()=>{for(const profile of ['A','B'])await page.getByRole('group',{name:'PROFILE '+profile,exact:true}).getByRole('radio').check();};
    await page.goto(origin+'/demo#new');await openSession();
    assert.equal(await page.getByRole('heading',{name:'ADD A FILM YOU ALREADY LIKE',exact:true}).count(),0,'Older servers hide the feature');
    await plan();assert.equal(Object.hasOwn(posts.at(-1).body,'movie_queries'),false,'Zero-query legacy payload stays unchanged');
    assert.equal(await page.getByRole('button',{name:'FIND ARTISTS',exact:true}).count(),1);
    capabilityEnabled=true;await page.reload();await openSession();
    await page.getByRole('heading',{name:'ADD A FILM YOU ALREADY LIKE',exact:true}).waitFor();
    const beforeTyping=posts.length;
    await page.getByRole('button',{name:'ADD FILM TO PROFILE A',exact:true}).click();
    assert.equal(await page.getByRole('button',{name:'REVIEW A NEW PLAN',exact:true}).isEnabled(),false,'An empty added slot cannot enter a plan');
    await page.getByLabel('Profile A film title 1',{exact:true}).fill('  Ｇｌａｄｉａｔｏｒ   ');
    await page.getByRole('button',{name:'ADD FILM TO PROFILE B',exact:true}).click();await page.getByLabel('Profile B film title 1',{exact:true}).fill('The Thing');
    for(const profile of ['A','B'])assert.equal(await page.getByRole('button',{name:'ADD FILM TO PROFILE '+profile,exact:true}).isEnabled(),false,'Two total slots cap applies across profiles');
    assert.equal(posts.length,beforeTyping,'Typing and editing must make no API mutations');
    await plan();assert.deepEqual(posts.at(-1).body.movie_queries,{A:['Gladiator'],B:['The Thing']});
    await page.getByLabel('Profile A film title 1',{exact:true}).fill('Gladiator 2000');
    assert.equal(await page.getByRole('heading',{name:'YOUR EXECUTION PLAN',exact:true}).count(),0,'Editing a query invalidates the visible plan');
    assert.equal(await page.getByLabel('Profile B film title 1',{exact:true}).inputValue(),'The Thing','Editing one query preserves the other');
    await plan();await page.getByRole('button',{name:'FIND ARTISTS & FILMS',exact:true}).click();
    await page.getByRole('heading',{name:'CONFIRM YOUR FILMS',exact:true}).waitFor();
    const confirm=page.getByRole('button',{name:'CONFIRM IDENTITIES & START REVIEW',exact:true});
    assert.equal(await confirm.isEnabled(),false);assert.equal(await page.getByRole('radio',{checked:true}).count(),0,'No artist or film identity may be selected automatically');
    assert.equal(await page.getByRole('radio',{name:/Year unverified/}).isEnabled(),false,'A film without a verified year is not confirmable');
    await chooseArtists();assert.equal(await confirm.isEnabled(),false,'Artists alone do not confirm films');
    await page.getByRole('group',{name:'MOVIE PROFILE A · QUERY 1',exact:true}).getByRole('radio',{name:/Gladiator \(2000\)/}).check();
    assert.equal(await confirm.isEnabled(),false,'Every query requires its own choice');
    await page.getByRole('group',{name:'MOVIE PROFILE B · QUERY 1',exact:true}).getByRole('radio',{name:/The Thing \(1982\)/}).check();
    assert.equal(await confirm.isEnabled(),true);await capture('01-film-title-year-confirmation');
    await confirm.click();await page.getByRole('status').filter({hasText:/^COMPLETE$/}).waitFor();
    const completed=[...jobs.values()].find(job=>job.chosen_movie_inputs);assert.ok(completed);
    assert.deepEqual(posts.at(-1).body.selected_movie_entity_ids,{A:['film-gladiator-2000'],B:['film-thing-1982']});
    await page.getByRole('heading',{name:'CONFIRMED FILM INPUTS',exact:true}).waitFor();await page.getByText('Gladiator (2000)',{exact:true}).waitFor();await capture('02-confirmed-films-and-results');
    const downloadPromise=page.waitForEvent('download');await page.getByRole('link',{name:'DOWNLOAD SELECTED VERIFICATION',exact:true}).click();
    const download=await downloadPromise;assert.equal(new URL(download.url()).origin,origin);const stream=await download.createReadStream(),chunks=[];for await(const chunk of stream)chunks.push(chunk);const receiptBytes=Buffer.concat(chunks),receipt=JSON.parse(receiptBytes.toString('utf8'));assert.equal(receipt.job_id,completed.job_id);assert.deepEqual(receipt.chosen_movie_inputs,completed.chosen_movie_inputs);
    const beforeRestore=posts.filter(post=>!post.path.endsWith('/session')).length;await page.reload();await openSession();await page.getByRole('heading',{name:'CONFIRMED FILM INPUTS',exact:true}).waitFor();assert.equal(posts.filter(post=>!post.path.endsWith('/session')).length,beforeRestore,'Restoring a selected movie case uses reads only');
    // A same-profile duplicate is blocked even if two different queries returned it.
    await page.getByRole('button',{name:'ADD FILM TO PROFILE A',exact:true}).click();await page.getByLabel('Profile A film title 1',{exact:true}).fill('Gladiator');
    await page.getByRole('button',{name:'ADD FILM TO PROFILE A',exact:true}).click();await page.getByLabel('Profile A film title 2',{exact:true}).fill('Gladiator 2000');await plan();await page.getByRole('button',{name:'FIND ARTISTS & FILMS',exact:true}).click();await chooseArtists();
    for(const slot of [1,2])await page.getByRole('group',{name:'MOVIE PROFILE A · QUERY '+slot,exact:true}).getByRole('radio',{name:/Gladiator \(2000\)/}).check();
    await page.getByText('Choose distinct films within this profile.',{exact:false}).first().waitFor();assert.equal(await confirm.isEnabled(),false,'Duplicate selected identities are blocked within a profile');
    await page.getByRole('group',{name:'MOVIE PROFILE A · QUERY 2',exact:true}).getByRole('radio',{name:/Gladiator \(1992\)/}).check();assert.equal(await confirm.isEnabled(),true);
    // Editing after a search removes its identity choices without erasing saved cases.
    const savedCount=jobs.size;await page.getByLabel('Profile A film title 1',{exact:true}).fill('No matching film');assert.equal(await page.getByRole('heading',{name:'CONFIRM YOUR FILMS',exact:true}).count(),0);assert.equal(jobs.size,savedCount);await page.getByRole('button',{name:'Remove profile A film query 2',exact:true}).click();await plan();await page.getByRole('button',{name:'FIND ARTISTS & FILMS',exact:true}).click();await chooseArtists();await page.getByText('No film matches were saved for this query.',{exact:false}).waitFor();assert.equal(await confirm.isEnabled(),false);await capture('03-no-film-match');
    assert.equal(createHash('sha256').update(JSON.stringify(jobs.get(historical.job_id))).digest('hex'),historicalHash,'Historical case bytes stay unchanged');assert.equal(confirmations,1);assert.deepEqual(errors,[]);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
    console.log(JSON.stringify({result:'PASS',scenario:'movie query cap, legacy payload, normalized plan, edit invalidation, explicit title/year confirmation, duplicate and unknown-year rejection, native receipt, restoration, no-match and historical preservation',viewport:process.argv.includes('--mobile')?'mobile':'desktop',completed_synthetic_cases:1,synthetic_confirmations:confirmations,real_provider_calls:0,historical_case_sha256:historicalHash,downloaded_receipt_sha256:createHash('sha256').update(receiptBytes).digest('hex'),scope:'FRONTEND_WITH_SYNTHETIC_API_ONLY'}));
  }finally{if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
}
main().catch(error=>{console.error(error.stack||error.message);process.exitCode=1;});
