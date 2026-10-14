/** UXR-2 focused enrollment browser regression with synthetic Core fixtures.
 * No product server, credential store, Agent or real enrollment state is contacted.
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
 const source=`import React from 'react';import {createRoot} from 'react-dom/client';import {EnrollmentOnboarding} from './src/p0-enrollment';
 window.apiCalls=[];window.apiResponses=[];window.apiPending=new Map();window.refreshCalls=0;
 const api=async(path,init={})=>{window.apiCalls.push({path,method:init.method||'GET',body:init.body||null});const next=window.apiResponses.shift();if(!next)throw new Error('No synthetic API response for '+path);if(next.pending)return new Promise((resolve,reject)=>{window.apiPending.set(next.pending,{resolve,reject});init.signal?.addEventListener('abort',()=>{window.apiPending.delete(next.pending);reject(new DOMException('Request aborted','AbortError'))},{once:true});});if(next.reject)throw new Error(next.reject);return structuredClone(next.body);};
 window.resetApi=()=>{window.apiCalls=[];window.apiResponses=[];window.apiPending=new Map();window.refreshCalls=0};
 createRoot(document.getElementById('fixture')).render(<EnrollmentOnboarding api={api} data={{items:[],total:0}} refresh={()=>{window.refreshCalls++}} operator={{id:'fixture-admin',role:'Admin'}}/>);`;
 const bundle=(await build({stdin:{contents:source,resolveDir:root,loader:'tsx'},bundle:true,write:false,platform:'browser',format:'iife',jsx:'automatic',logLevel:'silent'})).outputFiles[0].contents;
 server=createServer((req,res)=>{
  if(req.url==='/bundle.js'){res.writeHead(200,{'Content-Type':'text/javascript'});res.end(bundle);return}
  if(req.url==='/styles.css'){res.writeHead(200,{'Content-Type':'text/css'});res.end(readFileSync(join(root,'dist/styles.css')));return}
  res.writeHead(200,{'Content-Type':'text/html'});res.end('<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/styles.css"><div id="fixture"></div><script src="/bundle.js"></script>');
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));url='http://127.0.0.1:'+server.address().port;
 browser=await chromium.launch({headless:true});
});
after(async()=>{await browser?.close();await new Promise(resolve=>server?.close(resolve));});

test('UXR-2.1 platform chooser is keyboard-operable and advanced options stay collapsed',async()=>{
 const page=await browser.newPage({viewport:{width:1280,height:800}});await page.goto(url);
 const group=page.getByRole('group',{name:'Agent platform'});await group.waitFor();
 const linux=group.getByRole('button',{name:/Linux/}),mac=group.getByRole('button',{name:/macOS/}),windows=group.getByRole('button',{name:/Windows/});
 assert.equal(await linux.getAttribute('aria-pressed'),'true');
 assert.equal(await page.locator('.dr-enrollment-advanced[open]').count(),0);
 await mac.focus();await page.keyboard.press('Enter');assert.equal(await mac.getAttribute('aria-pressed'),'true');assert.equal(await linux.getAttribute('aria-pressed'),'false');
 await windows.click();assert.equal(await windows.getAttribute('aria-pressed'),'true');
 await page.getByText('Advanced enrollment options',{exact:true}).click();
 await page.getByLabel('Enrollment mode').selectOption('manual');
 assert.equal(await windows.isDisabled(),true);assert.equal(await linux.getAttribute('aria-pressed'),'true','manual Windows falls back to Linux');
 assert.equal(await page.evaluate(()=>window.apiCalls.length),0);
 await page.close();
});

test('UXR-2.1 320px layout has one-column platform choices and no horizontal page overflow',async()=>{
 const page=await browser.newPage({viewport:{width:320,height:568}});await page.goto(url);await page.getByRole('group',{name:'Agent platform'}).waitFor();
 const metrics=await page.evaluate(()=>({client:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,columns:getComputedStyle(document.querySelector('.dr-enrollment-platforms')).gridTemplateColumns,overs:[...document.querySelectorAll('*')].filter(el=>el.getClientRects().length&&el.getBoundingClientRect().right>document.documentElement.clientWidth+1).slice(0,8).map(el=>({tag:el.tagName,cls:el.className,text:(el.textContent||'').trim().slice(0,60),right:el.getBoundingClientRect().right,width:el.getBoundingClientRect().width}))}));
 assert.ok(metrics.scroll<=metrics.client,JSON.stringify(metrics.overs));assert.ok(!metrics.columns.includes(' '),metrics.columns);
 await page.close();
});
