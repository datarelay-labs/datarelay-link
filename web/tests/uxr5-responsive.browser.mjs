/** UXR-5.4 responsive regression over actual production View components.
 * Synthetic same-origin GET fixtures only. Never contacts a product API or performs mutation.
 */
import assert from 'node:assert/strict';
import {after,before,test} from 'node:test';
import {build} from 'esbuild';
import {readFileSync} from 'node:fs';
import {createServer} from 'node:http';
import {dirname,join} from 'node:path';
import {fileURLToPath} from 'node:url';

const root=dirname(dirname(fileURLToPath(import.meta.url)));
const {chromium}=await import(process.env.DRLINK_PLAYWRIGHT_MODULE||'playwright');
let browser,server,url;

before(async()=>{
 const source=`import React from 'react';import {createRoot} from 'react-dom/client';import {View} from './src/main';
 const root=createRoot(document.getElementById('fixture'));
 const host={id:'host-a',name:'Server A',hostname:'server-a',connected:1,admission_state:'APPROVED',trust_status:'trusted',agent_platform:'Linux',agent_version:'3.0.0',agent_heartbeat_at:'2026-10-14T05:00:00Z'};
 const service={id:'svc-a',name:'SSH Admin',managed_host:'Server A',managed_host_id:'host-a',service_type:'ssh',public_port:6000,target_host:'127.0.0.1',target_port:22,enabled:1,released:0};
 const catalog={resources:{
  'network-object':{resource_type:'network-object',items:[{id:'net-src',name:'source-office'}],next_cursor:null},
  'network-group':{resource_type:'network-group',items:[],next_cursor:null},
  'service-object':{resource_type:'service-object',items:[{id:'so-ssh',name:'ssh-tcp22',type:'tcp',port:22}],next_cursor:null},
  'service-group':{resource_type:'service-group',items:[],next_cursor:null},
  'permission-object':{resource_type:'permission-object',items:[],next_cursor:null},
  'permission-group':{resource_type:'permission-group',items:[],next_cursor:null},
  'ai-identity':{resource_type:'ai-identity',items:[],next_cursor:null}
 }};
 const json=(body,status=200)=>new Response(JSON.stringify(body),{status,headers:{'content-type':'application/json'}});
 window.fixtureMode='ready';window.calls=[];
 window.fetch=async(path,init={})=>{
  const u=new URL(path,location.origin),method=init.method||'GET';window.calls.push({path:u.pathname+u.search,method});
  if(method!=='GET')throw new Error('UXR-5.4 fixture forbids mutations');
  if(window.fixtureMode==='error')return json({error:'Synthetic Core unavailable'},503);
  if(u.pathname==='/api/v1/overview')return json({schema_version:1,overview:{schema_version:1,state_class:'DERIVED',authoritative:false,rebuildable:true,generated_at:'2026-10-14T05:00:00Z',managed_hosts:{total:1,connected:1,pending_approval:0},remote_services:{total:1,enabled:1},management_jobs:{active_jobs:0,failed_jobs:0,queued_jobs:0,running_jobs:0,queued_targets:0,running_targets:0},policies:{remote:{total:1,enabled:1},internet:{total:0,enabled:0},ai:{total:0,enabled:0}}},attention:{count:0,authoritative:false,generated_at:'2026-10-14T05:00:00Z',items:[]}});
  if(u.pathname==='/api/v1/inventory'){
    const kind=u.searchParams.get('resource_type');
    return json({resource_type:kind,limit:Number(u.searchParams.get('limit')||100),next_cursor:null,items:kind==='managed-host'?[host]:kind==='remote-service'?[service]:[]});
  }
  if(u.pathname==='/api/v1/enrollments')return json({items:[],total:0,next_cursor:null});
  if(u.pathname==='/api/v1/objects-groups')return json(catalog);
  if(u.pathname==='/api/v1/policies'){
    const plane=u.searchParams.get('plane');return json({plane,limit:100,items:[],next_cursor:null});
  }
  if(u.pathname==='/api/v1/audit'){
    const limit=Number(u.searchParams.get('limit')||50);return json({resource_type:'audit-event',limit,items:[],next_cursor:null});
  }
  if(u.pathname==='/api/v1/audit/retention')return json({config:{control_days:365,access_days:90,max_events:500000},total_events:0,db_size_bytes:0,capacity_exceeded:false,capacity_policy:'Core separates control and access retention'});
  if(u.pathname==='/api/v1/revisions'){
    const limit=Number(u.searchParams.get('limit')||100);return json({resource_type:'revision',limit,items:[],next_cursor:null});
  }
  if(u.pathname==='/api/v1/saved-views')return json({items:[],next_cursor:null});
  if(u.pathname==='/api/v1/emergency-cutoffs'){
    const plane=u.searchParams.get('plane');return json({plane,items:[],count:0,returned:0,active:false,limit:200,truncated:false});
  }
  if(u.pathname==='/api/v1/live-access')return json({status:'UNKNOWN',items:[]});
  return json({error:'No synthetic fixture for '+u.pathname},503);
 };
 window.renderRoute=(active,theme='light',mode='ready')=>{window.calls=[];window.fixtureMode=mode;document.documentElement.setAttribute('data-dr-theme',theme);root.render(<View key={active+theme+mode} active={active} operator={{id:'admin-fixture',username:'fixture',role:'Admin'}} onNavigate={()=>{}}/>);};
 `;
 const bundle=(await build({stdin:{contents:source,resolveDir:root,loader:'tsx'},bundle:true,write:false,platform:'browser',format:'iife',jsx:'automatic',logLevel:'silent'})).outputFiles[0].contents;
 server=createServer((req,res)=>{
  if(req.url==='/bundle.js'){res.writeHead(200,{'Content-Type':'text/javascript'});res.end(bundle);return}
  if(req.url==='/styles.css'){res.writeHead(200,{'Content-Type':'text/css'});res.end(readFileSync(join(root,'dist/styles.css')));return}
  if(req.url==='/foundation.css'){res.writeHead(200,{'Content-Type':'text/css'});res.end(readFileSync(join(root,'dist/foundation.css')));return}
  res.writeHead(200,{'Content-Type':'text/html'});res.end('<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/styles.css"><link rel="stylesheet" href="/foundation.css"><main id="fixture" style="padding:16px"></main><script src="/bundle.js"></script>');
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));url='http://127.0.0.1:'+server.address().port;
 browser=await chromium.launch({headless:true});
});
after(async()=>{await browser?.close();await new Promise(resolve=>server?.close(resolve));});

const routes=[
 ['overview','.dr-command-center','ready'],
 ['hosts','.dr-workflow-servers','ready'],
 ['setup','.dr-uxb-setup','ready'],
 ['services','.dr-resource-workspace','ready'],
 ['policies','.dr-resource-workspace','ready'],
 ['access','.dr-access-workspace','ready'],
 ['audit','.dr-audit-card','ready'],
 ['services','.error','error'],
];

test('UXR-5.4 affected workflow screens remain usable across desktop/mobile and light/dark',async()=>{
 const failures=[];
 for(const [width,height] of [[1440,900],[1280,800],[375,812],[320,568]]){
  for(const theme of ['light','dark']){
   for(const [active,marker,mode] of routes){
    const page=await browser.newPage({viewport:{width,height}});page.setDefaultTimeout(5000);
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.goto(url);await page.evaluate(({active,theme,mode})=>window.renderRoute(active,theme,mode),{active,theme,mode});
    await page.locator(marker).first().waitFor();
    const metrics=await page.evaluate(()=>({
      client:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,
      critical:[...document.querySelectorAll('button.primary,button.secondary,button.danger,.dr-icon-button')]
        .filter(el=>el.getClientRects().length&&getComputedStyle(el).visibility!=='hidden')
        .filter(el=>el.getBoundingClientRect().height<43)
        .map(el=>({text:(el.textContent||el.getAttribute('aria-label')||'').trim().slice(0,60),height:el.getBoundingClientRect().height})),
      openWide:[...document.querySelectorAll('.dr-table-scroll,.dr-audit-readable-scroll')]
        .filter(el=>el.getClientRects().length&&el.scrollWidth>el.clientWidth)
        .map(el=>({cls:el.className,overflow:getComputedStyle(el).overflowX}))
    }));
    const writes=await page.evaluate(()=>window.calls.filter(x=>x.method!=='GET').length);
    if(metrics.scroll>metrics.client||metrics.critical.length||errors.length||writes)
      failures.push({active,mode,width,height,theme,metrics,errors,writes});
    for(const row of metrics.openWide)assert.match(row.overflow,/auto|scroll/);
    await page.close();
   }
  }
 }
 assert.deepEqual(failures,[]);
});
