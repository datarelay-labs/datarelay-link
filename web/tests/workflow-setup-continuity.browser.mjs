/** UXR-2.5 read-only browser continuity: observed Host -> Service -> Rule.
 * Synthetic GET fixtures only; no product mutation or credential is contacted.
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
 const source=`import React from 'react';import {createRoot} from 'react-dom/client';import {FirstConnectionSetup} from './src/uxb-setup';
 window.calls=[];
 const host=(id,name)=>({id,name,admission_state:'APPROVED',trust_status:'trusted',connected:true,agent_heartbeat_at:'2030-01-01T00:00:00Z'});
 const catalog={resources:{
  'network-object':{items:[{name:'source-office'},{name:'destination-app'}],next_cursor:null},
  'network-group':{items:[],next_cursor:null},'service-object':{items:[{name:'ssh-tcp22'}],next_cursor:null},
  'service-group':{items:[],next_cursor:null},'permission-object':{items:[],next_cursor:null},
  'permission-group':{items:[],next_cursor:null},'ai-identity':{items:[],next_cursor:null}
 }};
 const api=async(path,init={})=>{window.calls.push({path,method:init.method||'GET'});if(init.method&&init.method!=='GET')throw new Error('Fixture forbids mutation');
  if(path.includes('resource_type=managed-host'))return {resource_type:'managed-host',limit:100,items:[host('host-a','Server A'),host('host-b','Server B')],next_cursor:null};
  if(path.includes('resource_type=remote-service'))return {resource_type:'remote-service',limit:100,items:[],next_cursor:null};
  if(path==='/api/v1/enrollments?limit=50')return {items:[],total:0};
  if(path==='/api/v1/objects-groups?limit=50')return catalog;
  throw new Error('Unexpected GET '+path);
 };
 createRoot(document.getElementById('fixture')).render(<FirstConnectionSetup api={api} operator={{id:'admin-a',role:'Admin'}}/>);`;
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

test('UXR-2.5 selected Host flows into service and rule without copying an ID',async()=>{
 const page=await browser.newPage({viewport:{width:1280,height:800}});page.setDefaultTimeout(4000);await page.goto(url);
 const hostSelect=page.locator('.dr-uxb-choice').getByLabel('Managed Host');
 await hostSelect.waitFor();await hostSelect.selectOption('host-a');
 await page.getByRole('button',{name:/Next: Publish one Remote Service/}).click();
 const owner=page.getByLabel('Owning Agent / Managed Host');
 assert.equal(await owner.inputValue(),'host-a');assert.equal(await owner.isEditable(),false);
 await page.getByLabel('Remote Service name',{exact:true}).fill('ssh-admin');
 await page.getByLabel('Choose existing Service Object / Group',{exact:true}).selectOption('ssh-tcp22');
 await page.getByRole('button',{name:/Next: Define a narrow access rule/}).click();
 await page.getByText(/Service: ssh-tcp22/).waitFor();
 assert.equal(await page.getByText('host-a',{exact:true}).count(),0,'Host ID is not a policy field to retype');
 await page.getByRole('button',{name:/Publish one Remote Service/}).click();
 assert.equal(await page.getByLabel('Owning Agent / Managed Host').inputValue(),'host-a');
 assert.equal(await page.getByLabel('Remote Service name',{exact:true}).inputValue(),'ssh-admin');
 assert.equal(await page.evaluate(()=>window.calls.filter(x=>x.method!=='GET').length),0);
 await page.close();
});

test('UXR-2.5 changing the observed Host clears prior service/rule target state',async()=>{
 const page=await browser.newPage({viewport:{width:1280,height:800}});await page.goto(url);
 const hostSelect=page.locator('.dr-uxb-choice').getByLabel('Managed Host');await hostSelect.waitFor();await hostSelect.selectOption('host-a');
 await page.getByRole('button',{name:/Next: Publish one Remote Service/}).click();
 await page.getByLabel('Remote Service name',{exact:true}).fill('ssh-admin');await page.getByLabel('Choose existing Service Object / Group',{exact:true}).selectOption('ssh-tcp22');
 await page.getByRole('button',{name:/Add & approve Agent/}).click();
 await page.locator('.dr-uxb-choice').getByLabel('Managed Host').selectOption('host-b');
 await page.getByRole('button',{name:/Next: Publish one Remote Service/}).click();
 assert.equal(await page.getByLabel('Owning Agent / Managed Host').inputValue(),'host-b');
 assert.equal(await page.getByLabel('Remote Service name',{exact:true}).inputValue(),'');
 assert.equal(await page.locator('.dr-uxb-service label.dr-field').filter({hasText:'Service Object'}).locator('input').first().inputValue(),'');
 assert.equal(await page.evaluate(()=>window.calls.filter(x=>x.method!=='GET').length),0);
 await page.close();
});
