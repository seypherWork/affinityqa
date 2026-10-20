// Local contract fixture. Ranking/candidates are synthetic; five image URLs are
// exact metadata previously recorded from Qloo, never inferred from film names.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const http=require('node:http');
const path=require('node:path');
const {createHash}=require('node:crypto');
const hash=value=>createHash('sha256').update(JSON.stringify(value)).digest('hex');
const clone=value=>JSON.parse(JSON.stringify(value));
const stableHash=value=>createHash('sha256').update(JSON.stringify(value,(_key,member)=>member&&typeof member==='object'&&!Array.isArray(member)?Object.fromEntries(Object.keys(member).sort().map(key=>[key,member[key]])):member)).digest('hex');
const sourceFallback='Seleccionada por IA entre las películas obtenidas para esta búsqueda. No hay una descripción breve vinculada disponible.';
function makeDisplay(job){
  const result=job.result.wide_cinema_results;
  const reasons=result.delivered.map((entity_id,position)=>{
    const catalog_index=result.candidate_catalog.findIndex(row=>row.entity_id===entity_id),movie=result.candidate_catalog[catalog_index];
    const language=position===1?'en':'es',missing=position===2;
    const text=missing?sourceFallback:language==='en'?`A synthetic source description for ${movie.name} belongs only to this browser fixture, without any claim about taste.`:`Ficha sintética para ${movie.name}, vinculada sólo a este registro de prueba y sin afirmar preferencias personales.`;
    const pointer=`/response/results/entities/${position}/properties/short_descriptions/0`;
    return {catalog_index,entity_id,kind:missing?'RETRIEVAL_CONTEXT':'SOURCE_EXTRACT',verification:'SOURCE_BOUND_NOT_FACT_CHECKED',text,provider_cause_verified:false,evidence:{schema_version:1,renderer:'qloo-short-description-v1',source:missing?'RETRIEVAL_CONTEXT':'QLOO_OBSERVED',language:missing?null:language,catalog_index,entity_id,title:movie.name,release_year:movie.release_year,page:1,position,sample_sha256:'b'.repeat(64),response_sha256:'c'.repeat(64),value_pointer:missing?null:pointer+'/value',languages_pointer:missing?null:pointer+'/languages',value_sha256:missing?null:createHash('sha256').update(text).digest('hex'),fallback_reason:missing?'MISSING':null}};
  });
  const value={schema_version:1,renderer_version:'qloo-grounded-display-v1',receipt_sha256:job.receipt_sha256,protocol_version:'qloo-wide-cinema-discovery-v8',delivered:clone(result.delivered),reasons,legacy_original_archived:true,notice:'La explicación original de IA se conserva archivada. Esta ficha utiliza únicamente datos vinculados de Qloo o un aviso sin trama.',integrity:'SOURCE_BOUND'};
  return {...value,binding_sha256:stableHash(value)};
}
const observed=[
  {entity_id:'e53f4c11-65ac-453a-a579-6f97357154b6',name:'The Equalizer',release_year:2014,url:'https://images.qloo.com/i/E53F4C11-65AC-453A-A579-6F97357154B6-420x-auto.jpg'},
  {entity_id:'e3adc5f9-e598-4a6a-8062-a26ef0ce6c06',name:'John Wick: Chapter 2',release_year:2017,url:'https://images.qloo.com/i/E3ADC5F9-E598-4A6A-8062-A26EF0CE6C06-420x-auto.jpg'},
  {entity_id:'f197a609-1478-4336-8e40-c11a6c6893b4',name:'Furious 7',release_year:2015,url:'https://images.qloo.com/i/F197A609-1478-4336-8E40-C11A6C6893B4-420x-auto.jpg'},
  {entity_id:'5fbd6e83-5887-41cc-b9d4-c6a2c8931448',name:'John Wick: Chapter 3 - Parabellum',release_year:2019,url:'https://images.qloo.com/i/5FBD6E83-5887-41CC-B9D4-C6A2C8931448-420x-auto.jpg'},
  {entity_id:'45803025-c93a-443c-ab69-90dd1a19120d',name:'Taken 3',release_year:2014,url:'https://images.qloo.com/i/45803025-C93A-443C-AB69-90DD1A19120D-420x-auto.jpg'},
];
const catalog=[...observed.map(({url,...row})=>row),...Array.from({length:95},(_,i)=>({entity_id:`00000000-0000-4000-8000-${String(i).padStart(12,'0')}`,name:`Synthetic retrieved film ${i+1}`,release_year:1920+i}))].sort((a,b)=>a.entity_id.localeCompare(b.entity_id));
const seedChoices=[{entity_id:'10000000-0000-4000-8000-000000000001',name:'John Wick',release_year:2014,type:'urn:entity:movie'},{entity_id:'10000000-0000-4000-8000-000000000002',name:'John Wick',release_year:2024,type:'urn:entity:movie'},{entity_id:'10000000-0000-4000-8000-000000000003',name:'John Wick',release_year:null,type:'urn:entity:movie'}];
const artist={entity_id:'20000000-0000-4000-8000-000000000001',name:'Synthetic Massive Attack',type:'urn:entity:artist'};
const favorites=[{entity_id:'30000000-0000-4000-8000-000000000001',name:'Gladiator',release_year:1992,type:'urn:entity:movie'},{entity_id:'30000000-0000-4000-8000-000000000002',name:'Gladiator',release_year:2000,type:'urn:entity:movie'}];
function makeResult(job){
  const delivered=observed.map(row=>row.entity_id);
  return {verification_status:'VERIFIED_COMPLETE',provenance:'SYNTHETIC',qloo_attempts:job.maximum_qloo_requests,model_attempts:1,wide_cinema_results:{mode:job.discovery_mode,seed_identity:job.discovery_mode==='movie'?seedChoices.find(row=>row.entity_id===job.selected_seed_entity_id)||seedChoices[0]:artist,known_favorite_movie:job.favorite_movie_query?favorites.find(row=>row.entity_id===job.selected_favorite_movie_entity_id)||favorites[1]:null,candidate_catalog:catalog,candidate_count:100,raw_selection:delivered,delivered,baseline_delivered:delivered.slice().reverse(),reasons:delivered.map(entity_id=>({catalog_index:catalog.findIndex(row=>row.entity_id===entity_id),entity_id,text:'Synthetic model interpretation for this saved film; no quality or factual claim is established.',kind:'MODEL_INTERPRETATION',verification:'NOT_FACT_CHECKED',provider_cause_verified:false})),intent_text:job.intent_text,information_policy:{model_cinematic_knowledge_allowed:true,same_total_information_attested:false},boundaries:{synthetic_fixture:true,application_intent_sha256:'6'.repeat(64),seed_identity_sha256:'7'.repeat(64)},provider_rows_count:100,rejected_rows_count:0,deduplicated_rows_count:0,presentation_assets:observed.map(({url,...movie})=>({entity_id:movie.entity_id,identity_sha256:hash(movie),url,source:'QLOO_OBSERVED',sample_sha256:'b'.repeat(64)}))}};
}
function makeJob(id,body={mode:'movie',seed_query:'Saved fixture film',favorite_movie_query:null,intent_text:''}){return {job_id:id,status:'PLANNED',wide_cinema_discovery:true,discovery_mode:body.mode,seed_query:body.seed_query,favorite_movie_query:body.favorite_movie_query,intent_text:body.intent_text,maximum_qloo_requests:body.favorite_movie_query?4:3,maximum_model_decisions:1,saved_provider_samples:0,saved_model_packets:0,plan_sha256:'a'.repeat(64),simulation_only:true,result:null,admission_mode:'repeatable-v1'};}
async function createFixture({webRoot=path.resolve(__dirname,'../../web'),wideEnabled=true}={}){
  const legacy={job_id:'legacy-preserved-case',status:'PLANNED',artists:{A:'Preserved artist A',B:'Preserved artist B'},model:'synthetic',operator_mode:'groq',maximum_qloo_requests:4,maximum_model_decisions:2,saved_provider_samples:0,saved_model_packets:0,plan_sha256:'f'.repeat(64),catalog_sha256:'e'.repeat(64),simulation_only:true,model_load_requests:0,model_metadata_requests:0,result:null,error_class:null,read_only:true,legacy_case:true,admission_mode:'legacy-finite'};
  const jobs=new Map(),posts=[],reads=[];
  const state={wideEnabled,historyPageSize:3,dropNextConfirm:false,remainingExecutions:null,legacyHash:hash(legacy),legacy,posts,reads,jobs};
  const capabilities=()=>{const rows=[...jobs.values()].reverse(),page=rows.slice(0,state.historyPageSize);return {configured:true,execution_enabled:true,wide_cinema_discovery_supported:state.wideEnabled,open_movie_discovery_supported:true,simulation_only:true,remaining_plans:null,remaining_executions:state.remainingExecutions,admission_mode:'repeatable-v1',catalog:catalog.slice(0,20),default_artists:legacy.artists,cinema_preferences_supported:true,cinema_identity_confirmation_supported:true,cinema_discoveries_supported:true,jobs:[legacy],open_movie_jobs:[],wide_cinema_jobs:page,wide_cinema_jobs_truncated:rows.length>page.length,wide_cinema_next_cursor_job_id:rows.length>page.length?page.at(-1).job_id:null};};
  const server=http.createServer(async(req,res)=>{
    try{
      const url=new URL(req.url,'http://127.0.0.1');let body;
      if(url.pathname.startsWith('/api/demo/cases/')&&url.search){res.writeHead(400).end();return;}
      if(req.method==='POST'){const chunks=[];for await(const chunk of req)chunks.push(chunk);body=JSON.parse(Buffer.concat(chunks).toString());posts.push({path:url.pathname,body:clone(body)});if(url.pathname!=='/api/demo/cases/session')assert.equal(req.headers['x-affinityqa-csrf'],'c'.repeat(64));}
      else reads.push(url.pathname+url.search);
      const json=value=>{res.writeHead(200,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(value));};
      if(url.pathname==='/healthz')return json({new_cases_configured:true,open_movie_discovery_configured:true,wide_cinema_discovery_configured:state.wideEnabled});
      if(url.pathname==='/api/demo/summary')return json({schema_version:1,status:'UNAVAILABLE',notice:'Synthetic local browser fixture.',pairs:[]});
      if(url.pathname==='/api/demo/cases/session')return json({schema_version:1,csrf_token:'c'.repeat(64)});
      if(url.pathname==='/api/demo/cases/capabilities')return json(capabilities());
      const older=url.pathname.match(/^\/api\/demo\/cases\/wide-cinema\/jobs\/older-than\/([^/]+)$/);
      if(older){const rows=[...jobs.values()].reverse(),index=rows.findIndex(row=>row.job_id===decodeURIComponent(older[1])),page=rows.slice(index+1,index+1+state.historyPageSize);assert.ok(index>=0,'History cursor is an owned case');return json({wide_cinema_jobs:page,wide_cinema_jobs_truncated:rows.length>index+1+page.length,wide_cinema_next_cursor_job_id:rows.length>index+1+page.length?page.at(-1).job_id:null});}
      if(url.pathname==='/api/demo/cases/wide-cinema/plans'){
        assert.deepEqual(Object.keys(body).sort(),['excluded_entity_ids','favorite_movie_query','intent_text','mode','seed_query']);assert.ok(['movie','music'].includes(body.mode));assert.ok(body.intent_text.length<=600);assert.deepEqual(body.excluded_entity_ids,[]);if(body.mode==='movie')assert.equal(body.favorite_movie_query,null);
        const job=makeJob('wide-fixture-'+(jobs.size+1),body);jobs.set(job.job_id,job);return json(job);
      }
      const match=url.pathname.match(/^\/api\/demo\/cases\/jobs\/([^/]+)(?:\/(execute|confirm-wide|verification))?$/);
      if(match){const job=match[1]===legacy.job_id?legacy:jobs.get(match[1]);assert.ok(job,'Owned saved case exists');if(match[2])assert.notEqual(job.job_id,legacy.job_id,'Legacy may never execute');
        if(match[2]==='execute'){assert.equal(job.status,'PLANNED');assert.deepEqual(body,{plan_sha256:job.plan_sha256});Object.assign(job,{status:'AWAITING_IDENTITY_CONFIRMATION',identity_receipt_sha256:'d'.repeat(64),seed_candidates:job.discovery_mode==='movie'?seedChoices:[artist],favorite_movie_candidates:job.favorite_movie_query?favorites:[],saved_provider_samples:job.favorite_movie_query?2:1});return json(job);}
        if(match[2]==='confirm-wide'){assert.equal(job.status,'AWAITING_IDENTITY_CONFIRMATION');assert.deepEqual(Object.keys(body).sort(),['identity_receipt_sha256','plan_sha256','selected_favorite_movie_entity_id','selected_seed_entity_id']);assert.equal(body.identity_receipt_sha256,job.identity_receipt_sha256);assert.equal(body.plan_sha256,job.plan_sha256);assert.ok(job.seed_candidates.some(row=>row.entity_id===body.selected_seed_entity_id));if(job.favorite_movie_query)assert.ok(favorites.some(row=>row.entity_id===body.selected_favorite_movie_entity_id));else assert.equal(body.selected_favorite_movie_entity_id,null);Object.assign(job,body,{status:'COMPLETE',saved_provider_samples:job.maximum_qloo_requests,saved_model_packets:1,receipt_sha256:'9'.repeat(64)});job.result=makeResult(job);job.wide_cinema_display=makeDisplay(job);if(state.dropNextConfirm){state.dropNextConfirm=false;res.destroy();return;}return json(job);}
        if(match[2]==='verification'){res.setHeader('Content-Disposition',`attachment; filename="${job.job_id}-verification.json"`);return json({job_id:job.job_id,result:job.result});}return json(job);
      }
      if(url.pathname.startsWith('/api/'))throw Error('Unexpected API route '+url.pathname);
      const out=path.resolve(webRoot,'out'),file=path.resolve(out,url.pathname==='/demo'||url.pathname==='/demo/'?'demo.html':url.pathname.slice(1));
      if(!file.startsWith(out+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404).end();return;}
      res.setHeader('Content-Security-Policy',"img-src 'self' data:");res.setHeader('Content-Type',({'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml'})[path.extname(file)]||'application/octet-stream');fs.createReadStream(file).pipe(res);
    }catch(error){state.failure=error;res.writeHead(500,{'Content-Type':'application/json'}).end(JSON.stringify({error:error.message}));}
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  return {state,origin:`http://127.0.0.1:${server.address().port}`,close:()=>new Promise(resolve=>server.close(resolve)),addComplete(id,change){const job={...makeJob(id),status:'COMPLETE',receipt_sha256:'9'.repeat(64),saved_provider_samples:3,saved_model_packets:1};job.result=makeResult(job);job.wide_cinema_display=makeDisplay(job);if(change)change(job);jobs.set(id,job);return job;},assertPreserved(){assert.equal(hash(legacy),state.legacyHash);if(state.failure)throw state.failure;}};
}
module.exports={createFixture,observed,clone,stableHash};
if(require.main===module)createFixture({webRoot:process.env.AFFINITYQA_WEB_ROOT}).then(fixture=>{process.stdout.write(JSON.stringify({ready_origin:fixture.origin,synthetic_only:true})+'\n');const stop=()=>{fixture.close().then(()=>process.exit(0))};process.on('SIGTERM',stop);process.on('SIGINT',stop)}).catch(error=>{process.stderr.write(error.stack+'\n');process.exitCode=1});
