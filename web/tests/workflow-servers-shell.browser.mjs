/** Actual App -> Shell -> View routing against a loopback GET-only fixture.
 * Synthetic sessions are never forwarded to a product server. Not live/user E2E.
 */
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {readFileSync} from 'node:fs';
import {createServer} from 'node:http';
import {dirname,join} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const {chromium}=await import(process.env.DRLINK_PLAYWRIGHT_MODULE||'playwright');
const bundle=(await build({stdin:{contents:"import React from 'react';import {createRoot} from 'react-dom/client';import {App} from './src/main';createRoot(document.getElementById('fixture')).render(<App/>);",resolveDir:root,loader:'tsx'},bundle:true,write:false,platform:'browser',format:'iife',jsx:'automatic',logLevel:'silent'})).outputFiles[0].contents;
const server=createServer((req,res)=>{
 if(req.url==='/bundle.js'){res.writeHead(200,{'Content-Type':'text/javascript; charset=utf-8'});res.end(bundle);return;}
 if(req.url==='/styles.css'){res.writeHead(200,{'Content-Type':'text/css; charset=utf-8'});res.end(readFileSync(join(root,'dist/styles.css')));return;}
 if(req.url.startsWith('/api/')){res.writeHead(503,{'Content-Type':'application/json'});res.end('{"error":"No product API exists on this fixture"}');return;}
 res.writeHead(200,{'Content-Type':'text/html; charset=utf-8'});res.end('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/styles.css"></head><body><div id="fixture"></div><script src="/bundle.js"></script></body></html>');
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));let browser;
const results=[];
try{
 browser=await chromium.launch({headless:true});
 for(const role of ['Admin','Operator','Read Only']){
  const page=await browser.newPage({viewport:{width:1280,height:800}});page.setDefaultTimeout(5000);
  const calls=[],errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/**',async route=>{
   const request=route.request(),url=new URL(request.url());calls.push({method:request.method(),path:url.pathname+url.search});
   if(request.method()!=='GET'){await route.abort();return;}
   let body,status=200;
   if(url.pathname==='/api/v1/session')body={session_id:'ws_'+'1'.repeat(24),csrf_token:'0'.repeat(64),operator:{id:'wop_'+'1'.repeat(24),username:'fixture',role}};
   else if(url.pathname==='/api/v1/inventory'){
    const kind=url.searchParams.get('resource_type');body={resource_type:kind,limit:100,next_cursor:null,items:kind==='managed-host'?Array.from({length:10},(_,n)=>({id:'host-'+n,name:'Server '+String(n).padStart(3,'0'),hostname:'node-'+n,connected:1,admission_state:'APPROVED',trust_status:'trusted',agent_platform:'Linux',agent_version:'3.0.0'})):[]};
   }else{status=503;body={error:'Only fixture inventory is available'};}
   await route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
  });
  await page.goto('http://127.0.0.1:'+server.address().port);
  const servers=page.getByRole('button',{name:'Servers & Agents',exact:true});
  if(!await servers.isVisible())await page.locator('.nav-group-toggle').filter({hasText:'Connections'}).click();
  await servers.click();await page.getByRole('textbox',{name:'Search servers'}).fill('name:Server');
  await page.locator('.dr-server-filter-menu summary').click();await page.getByLabel('Agent connection filter').selectOption('connected');await page.getByLabel('Server sort').selectOption('name_desc');
  await page.getByRole('button',{name:/Server 002/}).first().click();await page.getByRole('tab',{name:'Activity',exact:true}).click();await page.getByRole('button',{name:'Open activity log',exact:true}).click();
  await servers.click();await page.getByRole('dialog',{name:'Server details'}).waitFor();
  assert.equal(await page.getByRole('textbox',{name:'Search servers'}).inputValue(),'name:Server');
  assert.equal(await page.getByRole('tab',{name:'Activity',exact:true}).getAttribute('aria-selected'),'true');
  assert.equal(await page.getByLabel('Agent connection filter').inputValue(),'connected');assert.equal(await page.getByLabel('Server sort').inputValue(),'name_desc');
  await page.getByRole('button',{name:'Done',exact:true}).click();
  // Sidebar-origin navigation must preserve display choices but not reopen a closed dialog.
  await page.getByRole('button',{name:'Published services',exact:true}).click();await servers.click();await page.getByRole('textbox',{name:'Search servers'}).waitFor();
  assert.equal(await page.getByRole('textbox',{name:'Search servers'}).inputValue(),'name:Server');assert.equal(await page.getByRole('dialog').count(),0);
  assert.equal(await page.getByRole('button',{name:'Add server',exact:true}).count(),role==='Admin'?1:0);
  const reads=calls.filter(c=>c.path.includes('resource_type=managed-host')).length;assert.ok(reads>=3,'Return must fetch current inventory, not trust cached records');
  assert.deepEqual(errors,[]);assert.equal(calls.filter(c=>c.method!=='GET').length,0);
  results.push({role,result:'PASS',hostInventoryReads:reads,posts:0,scope:'actual App/Shell/View; synthetic GET/session fixtures'});await page.close();
 }
 console.log(JSON.stringify(results,null,2));
}finally{await browser?.close();await new Promise(resolve=>server.close(resolve));}
