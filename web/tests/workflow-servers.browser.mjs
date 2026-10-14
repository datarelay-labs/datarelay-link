/** Real Chromium-mounted production View route, with explicitly synthetic API fixtures.
 * This is browser regression, not live Core/Agent or owner acceptance.
 * Run: DRLINK_PLAYWRIGHT_MODULE=/absolute/path/to/playwright/index.mjs node --test tests/workflow-servers.browser.mjs
 */
import assert from 'node:assert/strict';
import {before,after,test} from 'node:test';
import {mkdtempSync,rmSync,readFileSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createServer} from 'node:http';
import {build} from 'esbuild';
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const {chromium}=await import(process.env.DRLINK_PLAYWRIGHT_MODULE||'playwright');
const admin={id:'operator-admin',username:'admin',role:'Admin'};
const inventory=(items=[],next_cursor=null)=>({resource_type:'managed-host',limit:100,items,next_cursor});
const host=(id='host-a',extra={})=>({id,name:'Server '+id,hostname:id,admission_state:'APPROVED',connected:1,trust_status:'trusted',agent_platform:'linux',agent_version:'3.0.0',...extra});
let browser,server,url,scratch,bundle;
const failures=[];
before(async()=>{
  scratch=mkdtempSync(join(root,'node_modules','.servers-browser-'));
  const entry=`import React from 'react';import {createRoot} from 'react-dom/client';import {View,App} from './src/main';
  const root=createRoot(document.getElementById('fixture'));
  window.calls=[];window.responses=[];window.pending=new Map();window.navigations=[];window.serverReturnState=null;
  window.fetch=(path,init={})=>{window.calls.push({path,method:init.method||'GET',body:init.body||null});
    const response=window.responses.shift();if(!response)return Promise.reject(new Error('No fixture for '+path));
    if(response.reject)return Promise.reject(new Error(response.reject));
    if(response.pending)return new Promise((resolve,reject)=>{window.pending.set(response.pending,{resolve:result=>resolve(new Response(JSON.stringify(result.body),{status:result.status||200,headers:{'Content-Type':'application/json'}})),reject});if(!response.ignoreAbort)init.signal?.addEventListener('abort',()=>reject(new DOMException('Request aborted','AbortError')),{once:true});});
    return Promise.resolve(new Response(JSON.stringify(response.body),{status:response.status||200,headers:{'Content-Type':'application/json'}}));};
  window.mount=(props)=>{window.props={active:'hosts',operator:${JSON.stringify(admin)},onNavigate:(...args)=>window.navigations.push(args),onServerReturnStateChange:state=>window.serverReturnState=state,...props};root.render(<View {...window.props}/>);};
  window.remount=(props)=>{window.props={...window.props,...props};root.render(<View {...window.props}/>);};
  window.mountApp=()=>root.render(<App/>);
  window.settle=(key,body,status=200)=>{const pending=window.pending.get(key);if(!pending)throw new Error('Missing pending fixture '+key);pending.resolve({body,status});window.pending.delete(key);};
  window.rejectPending=(key,message)=>{window.pending.get(key).reject(new Error(message));window.pending.delete(key);};`;
  const result=await build({stdin:{contents:entry,resolveDir:root,loader:'tsx'},bundle:true,write:false,platform:'browser',format:'iife',jsx:'automatic',logLevel:'silent'});
  bundle=result.outputFiles[0].contents;
  server=createServer((req,res)=>{
    if(req.url==='/bundle.js'){res.writeHead(200,{'Content-Type':'text/javascript'});res.end(bundle);return;}
    if(req.url==='/styles.css'){res.writeHead(200,{'Content-Type':'text/css; charset=utf-8'});res.end(readFileSync(join(root,'dist/styles.css')));return;}
    res.writeHead(200,{'Content-Type':'text/html'});res.end('<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/styles.css"></head><body><div id="fixture"></div><script src="/bundle.js"></script></body></html>');
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));url='http://127.0.0.1:'+server.address().port;
  browser=await chromium.launch({headless:true});
});
after(async()=>{await browser?.close();await new Promise(resolve=>server?server.close(resolve):resolve());if(scratch)rmSync(scratch,{recursive:true,force:true});});
async function scenario(fn){const page=await browser.newPage({viewport:{width:1280,height:800}});page.setDefaultTimeout(2500);page.on('pageerror',e=>failures.push(e.message));await page.goto(url);try{await fn(page);assert.deepEqual(failures,[]);}finally{await page.close();failures.length=0;}}
async function mount(page,responses,props={}){await page.evaluate(({responses,props})=>{window.responses=responses;window.mount(props);},{responses,props});}
async function visible(page,text){await page.getByText(text,{exact:true}).first().waitFor({state:'visible'});}
async function absent(page,text){assert.equal(await page.getByText(text,{exact:false}).count(),0,text);}
async function finishRead(page){await page.waitForFunction(()=>window.calls.length>0);await page.waitForTimeout(80);}

test('UXR-1.1 mounted hosts route: complete zero is onboarding, never targetless management forms',()=>scenario(async page=>{
  await mount(page,[{body:inventory()}]);await visible(page,'Connect your first server');
  assert.equal(await page.getByRole('button',{name:'Add server',exact:true}).count(),1);
  await absent(page,'Guided Managed Host Metadata');await absent(page,'Managed Host Approval / Quarantine');await absent(page,'Managed Host Lifecycle');
  assert.equal(await page.getByRole('table').count(),0);
  await page.getByRole('button',{name:'Add server',exact:true}).click();
  assert.equal((await page.evaluate(()=>window.navigations))[0][0],'enrollments');
}));
test('UXR-1.1 mounted loading is announced and cannot display empty onboarding',()=>scenario(async page=>{
  await mount(page,[{pending:'slow'}]);await page.getByRole('status').filter({hasText:'Reading servers'}).waitFor({state:'visible'});await absent(page,'Connect your first server');
  await page.evaluate(body=>window.settle('slow',body),inventory());await visible(page,'Connect your first server');
}));
for(const status of [401,403,500,503])test('UXR-1.1 HTTP '+status+' remains unavailable, retry can recover',()=>scenario(async page=>{
  await mount(page,[{status,body:{error:'Fixture denied '+status}}]);await page.getByRole('alert').waitFor({state:'visible'});await absent(page,'Connect your first server');
  await page.evaluate(body=>window.responses.push({body}),inventory());await page.getByRole('button',{name:/Retry/}).click();await visible(page,'Connect your first server');
}));
test('UXR-1.1 timeout does not become an empty inventory',()=>scenario(async page=>{
  await mount(page,[{reject:'Request timed out'}]);await page.getByRole('alert').waitFor();await absent(page,'Connect your first server');
}));
test('UXR-1.1 partial and malformed pages cannot claim first-server onboarding',()=>scenario(async page=>{
  await mount(page,[{body:inventory([],'next-page')}]);await page.getByRole('alert').waitFor();await absent(page,'Connect your first server');
}));
test('UXR-1.1 filtered zero preserves controls and is not first use',()=>scenario(async page=>{
  await mount(page,[{body:inventory([host()])}],{context:{savedFilter:'name:missing'}});await visible(page,'No matching servers');await absent(page,'Connect your first server');
  await page.getByRole('button',{name:'Clear filters',exact:true}).first().click();await page.getByRole('button',{name:/Server host-a/}).first().waitFor();
}));
test('UXR-1.1 actor change discards previous inventory and late response',()=>scenario(async page=>{
  await mount(page,[{pending:'previous'}]);await page.waitForFunction(()=>window.pending.has('previous'));
  await page.evaluate(({body})=>{window.responses.push({body});window.remount({operator:{id:'read-only-new',role:'Read Only',username:'reader'}});},{body:inventory([host('new')])});
  await page.getByRole('button',{name:/Server new/}).first().waitFor();
  await page.evaluate(body=>window.settle('previous',body),inventory([host('private-old')]));await page.waitForTimeout(80);
  await absent(page,'private-old');assert.equal(await page.getByRole('button',{name:'Add server',exact:true}).count(),0);
}));
test('UXR-1.1 loaded actor state disappears synchronously on session change',()=>scenario(async page=>{
  await mount(page,[{body:inventory([host('previous-private')])}]);await page.getByRole('button',{name:/Server previous-private/}).first().waitFor();
  await page.evaluate(()=>{window.responses.push({pending:'new-actor'});window.remount({operator:{id:'operator-new',role:'Read Only'}});});
  await page.getByRole('status').filter({hasText:'Reading servers'}).waitFor();await absent(page,'previous-private');await absent(page,'Connect your first server');
}));
test('UXR-1.1 route change invalidates an in-flight host response',()=>scenario(async page=>{
  await mount(page,[{pending:'hosts'}]);await page.waitForFunction(()=>window.pending.has('hosts'));
  await page.evaluate(()=>{window.responses.push({body:{resource_type:'remote-service',items:[],limit:100,next_cursor:null}});window.remount({active:'services'});});await finishRead(page);
  await page.evaluate(body=>window.settle('hosts',body),inventory([host('late-private')]));await page.waitForTimeout(80);await absent(page,'late-private');await absent(page,'Connect your first server');
}));
for(const role of ['Admin','Operator','Read Only'])test('UXR-1.2 '+role+' empty route has only authorized enrollment',()=>scenario(async page=>{
  await mount(page,[{body:inventory()}],{operator:{...admin,role}});await visible(page,'Connect your first server');
  assert.equal(await page.getByRole('button',{name:'Add server',exact:true}).count(),role==='Admin'?1:0);
  assert.equal(await page.getByRole('textbox').count(),0);
}));
test('UXR-1.3 six contract columns, unknown service count is not zero',()=>scenario(async page=>{
  await mount(page,[{body:inventory([host()])}]);await page.getByRole('columnheader').first().waitFor({state:'visible'});
  assert.deepEqual(await page.getByRole('columnheader').allTextContents(),['Server','Agent connection','Approval','Services','Last observed','Action']);
  assert.equal(await page.locator('td[data-label="Services"]').innerText(),'Not reported');
}));
test('UXR-1.5 detail tabs, selected metadata target and focus return',()=>scenario(async page=>{
  await mount(page,[{body:inventory([host()])}]);const trigger=page.getByRole('button',{name:/Server host-a/}).first();await trigger.click();
  await page.getByRole('dialog',{name:'Server details'}).waitFor();
  assert.deepEqual(await page.getByRole('tab').allTextContents(),['Overview','Services','Activity','Settings']);
  await page.getByRole('tab',{name:'Settings',exact:true}).click();await page.getByRole('button',{name:/Edit name, description and tags/}).click();
  assert.equal(await page.getByPlaceholder('Managed Host ID/name').count(),0);
  await page.getByLabel('Display name',{exact:true}).fill('Renamed server');
  await page.evaluate(()=>window.responses.push({body:{no_change:true}}));await page.getByRole('button',{name:'Preview',exact:true}).click();
  await page.getByRole('status').filter({hasText:'NO_CHANGE'}).waitFor();
  const posted=await page.evaluate(()=>window.calls.filter(x=>x.method==='POST').map(x=>JSON.parse(x.body)));
  assert.equal(posted[0].payload.host,'host-a');assert.equal(posted[0].payload.label,'Renamed server');
  await page.keyboard.press('Escape');assert.equal(await page.getByRole('dialog').count(),0);assert.equal(await trigger.evaluate(el=>el===document.activeElement),true);
}));
test('UXR-1.4 100/101 load-more preserves first page and rejects stale page after actor change',()=>scenario(async page=>{
  await mount(page,[{body:inventory(Array.from({length:100},(_,n)=>host('host-'+n)),'page-2')}]);await page.getByRole('button',{name:'Load more',exact:true}).waitFor();
  await page.evaluate(()=>window.responses.push({body:{resource_type:'managed-host',limit:100,items:[{id:'host-100',name:'Last server'}],next_cursor:null}}));
  await page.getByRole('button',{name:'Load more',exact:true}).click();await visible(page,'101 shown · 101 loaded · 2 pages');
}));

test('UXR-1.1 failed refresh retains explicitly stale read-only rows and no success badge',()=>scenario(async page=>{
  await mount(page,[{body:inventory([host('current')])}]);await page.getByRole('button',{name:/Server current/}).first().waitFor();
  await page.evaluate(()=>window.responses.push({status:503,body:{error:'Fixture unavailable'}}));await page.getByRole('button',{name:'Refresh',exact:true}).click();
  await visible(page,'Previous server observations · not current');await page.getByRole('button',{name:/Server current/}).first().click();
  await page.getByRole('tab',{name:'Settings',exact:true}).click();assert.equal(await page.getByRole('button',{name:/Edit name/}).count(),0);
  await page.keyboard.press('Escape');assert.equal(await page.getByRole('button',{name:'Add server',exact:true}).count(),0);
}));
test('UXR-1.5 new navigation selection replaces old detail only when observed in current rows',()=>scenario(async page=>{
  await mount(page,[{body:inventory([host('one'),host('two')])}],{context:{inspectResourceId:'one'}});
  await page.getByRole('dialog').getByRole('heading',{name:'Server one',exact:true}).waitFor();
  await page.evaluate(()=>window.remount({context:{inspectResourceId:'two'}}));
  await page.getByRole('dialog').getByRole('heading',{name:'Server two',exact:true}).waitFor();
  assert.equal((await page.evaluate(()=>window.calls)).length,1,'No unbounded by-ID request');
}));
test('UXR-1.8 closing a contextual detail stays closed after refreshing inventory',()=>scenario(async page=>{
  const body=inventory([host('one')]);await mount(page,[{body}],{context:{inspectResourceId:'one'}});
  await page.getByRole('dialog').waitFor();await page.getByRole('button',{name:'Done',exact:true}).click();
  await page.evaluate(body=>window.responses.push({body}),body);await page.getByRole('button',{name:'Refresh',exact:true}).click();
  await page.waitForFunction(()=>window.calls.length===2);await page.waitForTimeout(80);assert.equal(await page.getByRole('dialog').count(),0);
}));
test('UXR-1.4 actor change invalidates pending load-more without exposing prior account rows',()=>scenario(async page=>{
  await mount(page,[{body:inventory([host('old')],'next-page')}]);await page.getByRole('button',{name:'Load more',exact:true}).waitFor();
  await page.evaluate(()=>window.responses.push({pending:'more'}));await page.getByRole('button',{name:'Load more',exact:true}).click();
  await page.evaluate(body=>{window.responses.push({body});window.remount({operator:{id:'new-account',role:'Read Only'}});},inventory([host('new')]));
  await page.getByRole('button',{name:/Server new/}).first().waitFor();
  await page.evaluate(body=>window.settle('more',body),inventory([host('old-late')]));await page.waitForTimeout(80);await absent(page,'old-late');await absent(page,'Server old');
}));

test('UXR-1.8 Activity return restores filters and selected tab from actor-scoped UI state only',()=>scenario(async page=>{
  const body=inventory([host('one'),host('two')]);await mount(page,[{body}]);await page.getByRole('textbox',{name:'Search servers'}).fill('name:Server one');
  await page.locator('.dr-server-filter-menu summary').click();await page.getByLabel('Agent connection filter').selectOption('connected');await page.getByLabel('Server sort').selectOption('name_desc');
  await page.getByRole('button',{name:/Server one/}).first().click();await page.getByRole('tab',{name:'Activity',exact:true}).click();await page.getByRole('button',{name:'Open activity log',exact:true}).click();
  const saved=await page.evaluate(()=>window.serverReturnState);assert.equal(saved.filter,'name:Server one');assert.equal(saved.detailTab,'activity');
  assert.deepEqual(Object.keys(saved).sort(),['actor','admission','cards','connection','detailTab','filter','inspectResourceId','reviewOnly','scrollTop','sort']);
  await page.evaluate(()=>{window.responses.push({body:{resource_type:'remote-service',limit:100,items:[],next_cursor:null}});window.remount({active:'services'});});await finishRead(page);
  await page.evaluate(({body,saved})=>{window.responses.push({body});window.remount({active:'hosts',serverReturnState:saved,context:{savedFilter:'id:one',inspectResourceId:'one'}});},{body,saved});
  await page.getByRole('dialog').waitFor();assert.equal(await page.getByRole('textbox',{name:'Search servers'}).inputValue(),'name:Server one');
  assert.equal(await page.getByRole('tab',{name:'Activity',exact:true}).getAttribute('aria-selected'),'true');
  assert.equal(await page.getByLabel('Agent connection filter').inputValue(),'connected');assert.equal(await page.getByLabel('Server sort').inputValue(),'name_desc');
}));
test('UXR-1.8 foreign-actor UI snapshot is ignored rather than leaking search context',()=>scenario(async page=>{
  const serverReturnState={actor:'private-old:Admin',filter:'private-needle',admission:'all',connection:'connected',sort:'name_desc',cards:true,reviewOnly:true,inspectResourceId:'one',detailTab:'settings',scrollTop:100};
  await mount(page,[{body:inventory([host('one')])}],{serverReturnState});await page.getByRole('textbox',{name:'Search servers'}).waitFor();
  assert.equal(await page.getByRole('textbox',{name:'Search servers'}).inputValue(),'');assert.equal(await page.getByRole('dialog').count(),0);
}));

// UXR-1.1: prove actual timeout and refresh-epoch handling, not a pre-rejected fixture.
test('UXR-1.1 real request timeout is distinct from empty and retry is bounded',()=>scenario(async page=>{
  await page.clock.install();await mount(page,[{pending:'timeout'}]);
  await page.getByRole('status').filter({hasText:'Reading servers'}).waitFor();
  await page.clock.fastForward(15001);await page.getByRole('alert').filter({hasText:'timed out'}).waitFor();
  await absent(page,'Connect your first server');
  await page.evaluate(body=>window.responses.push({body}),inventory());
  await page.getByRole('button',{name:'Retry',exact:true}).click();await visible(page,'Connect your first server');
  assert.equal(await page.evaluate(()=>window.calls.length),2);
}));
test('UXR-1.1 superseded refresh response cannot replace latest inventory',()=>scenario(async page=>{
  await mount(page,[{body:inventory([host('initial')])}]);await page.getByRole('button',{name:/Server initial/}).first().waitFor();
  await page.evaluate(()=>window.responses.push({pending:'old-refresh',ignoreAbort:true}));await page.getByRole('button',{name:'Refresh',exact:true}).click();
  await page.evaluate(body=>window.responses.push({body}),inventory([host('latest')]));await page.getByRole('button',{name:'Refresh',exact:true}).click();
  await page.getByRole('button',{name:/Server latest/}).first().waitFor();
  await page.evaluate(body=>window.settle('old-refresh',body),inventory([host('superseded')]));await page.waitForTimeout(80);
  await absent(page,'Server superseded');await page.getByRole('button',{name:/Server latest/}).first().waitFor();
}));
for(const flag of [{partial:true},{truncated:true},{complete:false},{stale:true}])test('UXR-1.1 explicit incomplete marker '+JSON.stringify(flag)+' cannot imply first use',()=>scenario(async page=>{
  await mount(page,[{body:{...inventory(),...flag}}]);await page.getByRole('alert').waitFor();await absent(page,'Connect your first server');
}));
test('UXR-1.5 related-service navigation preserves exact selected identity',()=>scenario(async page=>{
  await mount(page,[{body:inventory([host()])}]);await page.getByRole('button',{name:/Server host-a/}).first().click();
  await page.evaluate(()=>window.responses.push({body:{resource_type:'remote-service',limit:100,items:[{id:'svc-a',name:'SSH',managed_host_id:'host-a',enabled:true}],next_cursor:null}}));
  await page.getByRole('tab',{name:'Services',exact:true}).click();await page.getByRole('button',{name:/SSH.*Open service details/}).click();
  const navigation=await page.evaluate(()=>window.navigations.at(-1));assert.equal(navigation[0],'services');assert.equal(navigation[2].inspectResourceId,'svc-a');
}));

test('UXR-1.9 stale connection observations do not retain a current-success presentation',()=>scenario(async page=>{
  await mount(page,[{body:inventory([host('observed')])}]);await page.getByRole('button',{name:/Server observed/}).first().waitFor();
  await page.evaluate(()=>window.responses.push({status:503,body:{error:'Unavailable'}}));await page.getByRole('button',{name:'Refresh',exact:true}).click();
  await visible(page,'Previous server observations · not current');
  assert.equal(await page.locator('.dr-wf-state.success').count(),0,'Historical Agent state must not look current');
  await page.getByRole('button',{name:/Server observed/}).first().click();
  assert.equal(await page.getByRole('dialog').locator('.dr-wf-state.success').count(),0);
}));
test('UXR-1.5 incomplete related-service inventory cannot certify no services',()=>scenario(async page=>{
  await mount(page,[{body:inventory([host()])}]);await page.getByRole('button',{name:/Server host-a/}).first().click();
  await page.evaluate(()=>window.responses.push({body:{resource_type:'remote-service',limit:100,items:[],next_cursor:null,partial:true}}));
  await page.getByRole('tab',{name:'Services',exact:true}).click();
  await page.getByRole('dialog').getByRole('alert').waitFor();
  await absent(page,'No services reference this server in the returned inventory.');
}));
