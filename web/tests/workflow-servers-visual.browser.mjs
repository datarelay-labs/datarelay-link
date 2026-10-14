/** Mounted production View read-only browser/viewport evidence.
 * Synthetic fixture data is labeled. Never sends product POSTs or qualifies live E2E.
 */
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {readFileSync,mkdirSync,writeFileSync} from 'node:fs';
import {createServer} from 'node:http';
import {dirname,join} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const {chromium}=await import(process.env.DRLINK_PLAYWRIGHT_MODULE||'playwright');
const output=process.env.DRLINK_UI_EVIDENCE_DIR;
if(!output||!output.startsWith('/'))throw new Error('An absolute private evidence directory is required.');
mkdirSync(output,{recursive:true,mode:0o700});
const source=`import React from 'react';import {createRoot} from 'react-dom/client';import {View} from './src/main';
 const root=createRoot(document.getElementById('fixture'));window.calls=[];window.errors=[];
 window.load=({rows,role='Admin',mode='ready'})=>{window.calls=[];
 window.fetch=async(path,init={})=>{window.calls.push({path,method:init.method||'GET'});
 if(init.method&&init.method!=='GET')throw new Error('Read-only browser fixture forbids mutations');
 if(mode==='unavailable')return new Response(JSON.stringify({error:'Fixture unavailable'}),{status:503});
 return new Response(JSON.stringify({resource_type:path.includes('remote-service')?'remote-service':'managed-host',items:path.includes('remote-service')?[]:rows,limit:100,next_cursor:null}),{status:200});};
 root.render(<View key={role+':'+mode} active='hosts' operator={{id:'fixture-operator',username:'fixture',role}}/>);};`;
const bundle=(await build({stdin:{contents:source,resolveDir:root,loader:'tsx'},bundle:true,write:false,platform:'browser',format:'iife',jsx:'automatic',logLevel:'silent'})).outputFiles[0].contents;
const server=createServer((req,res)=>{
 if(req.url==='/bundle.js'){res.writeHead(200,{'Content-Type':'text/javascript'});res.end(bundle);return;}
 if(req.url==='/styles.css'){res.writeHead(200,{'Content-Type':'text/css; charset=utf-8'});res.end(readFileSync(join(root,'dist/styles.css')));return;}
 res.writeHead(200,{'Content-Type':'text/html'});res.end('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/styles.css"></head><body><main style="padding:16px" id="fixture"></main><script src="/bundle.js"></script></body></html>');
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
let browser;const observations=[];
try{
 browser=await chromium.launch({headless:true});
 const host=(n)=>({id:'host-'+n,name:'Server '+String(n).padStart(3,'0'),hostname:'node-'+n+'.example.test',connected:n%4===0?false:n%4===1?null:true,admission_state:n%5===0?'PENDING_APPROVAL':n%5===1?'QUARANTINED':'APPROVED',trust_status:'trusted',agent_platform:'Linux',agent_version:'3.0.0',agent_heartbeat_at:'2026-10-14T02:00:00Z'});
 for(const [width,height] of [[1440,900],[1280,800],[375,812],[320,568]])for(const theme of ['light','dark'])for(const count of [0,1,10,50]){
  const page=await browser.newPage({viewport:{width,height}});const pageErrors=[];page.on('pageerror',e=>pageErrors.push(e.message));
  await page.goto('http://127.0.0.1:'+server.address().port);await page.evaluate(({rows,theme})=>{document.documentElement.setAttribute('data-dr-theme',theme);window.load({rows});},{rows:Array.from({length:count},(_,n)=>host(n)),theme});
  await page.locator(count?'.dr-server-table':'.dr-server-welcome').waitFor();
  const name=`servers-${count}-${theme}-${width}x${height}`;
  const headersByRole=await page.getByRole('columnheader').allTextContents();
  if(count)assert.deepEqual(headersByRole,['Server','Agent connection','Approval','Services','Last observed','Action']);
  const metrics=await page.evaluate(()=>({pageWidth:document.documentElement.clientWidth,scrollWidth:document.documentElement.scrollWidth,
   headers:[...document.querySelectorAll('th')].map(el=>({text:el.textContent,role:el.getAttribute('role'),scope:el.getAttribute('scope'),display:getComputedStyle(el).display})),
   smallTargets:[...document.querySelectorAll('button,summary,input,select')].filter(el=>el.getClientRects().length&&getComputedStyle(el).visibility!=='hidden').filter(el=>el.getBoundingClientRect().height<43).map(el=>({text:el.textContent||el.getAttribute('aria-label'),height:el.getBoundingClientRect().height})),
   firstActionBottom:document.querySelector('.dr-server-welcome .primary')?.getBoundingClientRect().bottom||null,
   posts:window.calls.filter(call=>call.method!=='GET').length}));
  await page.screenshot({path:join(output,name+'.png'),fullPage:true});
  observations.push({name,scope:'production View with synthetic GET fixture, not live login',...metrics,pageErrors});
  if(count){
   const trigger=page.getByRole('button',{name:count===1?/Server 000/:/Server 002/}).first();await trigger.click();await page.getByRole('dialog',{name:'Server details'}).waitFor();
   await page.screenshot({path:join(output,name+'-detail.png'),fullPage:false});
   await page.getByRole('tab',{name:'Overview',exact:true}).focus();await page.keyboard.press('ArrowRight');
   const selected=await page.getByRole('tab',{name:'Services',exact:true}).getAttribute('aria-selected');assert.equal(selected,'true');
   await page.getByRole('button',{name:'Done',exact:true}).focus();await page.keyboard.press('Tab');
   assert.equal(await page.getByRole('button',{name:'Close server details'}).evaluate(el=>el===document.activeElement),true);
   await page.keyboard.press('Escape');assert.equal(await trigger.evaluate(el=>el===document.activeElement),true);
  }
  await page.close();
 }
 writeFileSync(join(output,'visual-observations.json'),JSON.stringify(observations,null,2)+'\n');
 console.log(JSON.stringify({runs:observations.length,layoutOverflow:observations.filter(x=>x.scrollWidth>x.pageWidth).map(x=>x.name),smallTargets:observations.filter(x=>x.smallTargets.length).map(x=>({name:x.name,targets:x.smallTargets})),pageErrors:observations.flatMap(x=>x.pageErrors),writes:observations.reduce((total,x)=>total+x.posts,0)},null,2));
 assert.ok(observations.every(x=>x.scrollWidth<=x.pageWidth),'Unexpected page-wide overflow');
 assert.ok(observations.every(x=>!x.pageErrors.length),'Browser runtime error');
 assert.ok(observations.every(x=>!x.posts),'Browser test attempted mutation');
 assert.ok(observations.every(x=>!x.smallTargets.length),'Control smaller than 44px');
}finally{await browser?.close();await new Promise(resolve=>server.close(resolve));}
