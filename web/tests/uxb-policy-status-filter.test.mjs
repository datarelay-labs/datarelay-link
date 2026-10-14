// G-09: an original, local-only policy status filter inspired by public NetBird UI evidence.
// This is source qualification, not logged-in tenant/three-role Browser E2E.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {build} from 'esbuild';
import {mkdtempSync,rmSync,readFileSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,'node_modules','.drl3-policy-status-'));
let module;
try{
 const outfile=join(scratch,'status.mjs');
 await build({entryPoints:[join(root,'src','uxb-policy-status-filter.ts')],
   outfile,bundle:true,platform:'node',format:'esm',logLevel:'silent'});
 module=await import(pathToFileURL(outfile).href);
}finally{rmSync(scratch,{recursive:true,force:true})}

test('G-09 filters only already loaded Core policies with canonical Enabled/Disabled/UNKNOWN semantics',()=>{
 const observed=[
   {id:'yes',enabled:true},{id:'one',enabled:1},
   {id:'no',enabled:false},{id:'zero',enabled:0},
   {id:'missing'},{id:'null',enabled:null},{id:'text',enabled:'false'},
   {id:'object',enabled:{secret:'SHOULD_NOT_USE'}}
 ];
 const ids=(status)=>module.filterObservedPoliciesByStatus(observed,status).map(x=>x.id);
 assert.deepEqual(ids('all'),observed.map(x=>x.id));
 assert.deepEqual(ids('enabled'),['yes','one']);
 assert.deepEqual(ids('disabled'),['no','zero']);
 assert.deepEqual(ids('unknown'),['missing','null','text','object']);
 assert.equal(module.filterObservedPoliciesByStatus(observed,'unknown')[0],observed[4],
   'display filtering must not mutate or clone Core rows');
});
test('G-09 rejects invalid filter selectors and non-array inputs without broadening access',()=>{
 const observed=[{enabled:true},{enabled:false},{enabled:undefined}];
 for(const selector of [null,undefined,{},0,true,'', 'Disabled','active','unapproved',[], 'unknown '])
   assert.deepEqual(module.filterObservedPoliciesByStatus(observed,selector),[],String(selector));
 for(const items of [null,{},undefined,{items:observed},'foo'])
   assert.deepEqual(module.filterObservedPoliciesByStatus(items,'all'),[]);
});
test('G-09 Web status buttons are native, pressed-state accessible and loaded-only, retaining existing Core page contracts',()=>{
 const main=readFileSync(join(root,'src','main.tsx'),'utf8');
 const policy=main.split('function PolicyWorkspace(',2)[1]?.split('function ResourceWorkspace(',1)[0]||'';
 assert.match(policy,/const \[statusFilter,setStatusFilter\]=useState/);
 assert.match(policy,/filterObservedPoliciesByStatus(?:<any>)?\([\s\S]*?,statusFilter\)/);
 assert.match(policy,/role="group" aria-label="Filter loaded policy state"/);
 assert.match(policy,/type="button"/);
 assert.match(policy,/aria-pressed=\{statusFilter===status\}/);
 assert.match(policy,/onClick=\{\(\)=>setStatusFilter\(status\)\}/);
 assert.match(policy,/All states/);
 assert.match(policy,/UNKNOWN/);
 assert.match(policy,/Filters inspect only loaded rules/);
 assert.match(policy,/\bLoad more\b/);
 assert.match(policy,/policyStateLabel\(item.enabled\)/);
 assert.match(policy,/policyExpiryLabel\(item\)/);
 const css=readFileSync(join(root,'dist','styles.css'),'utf8');
 assert.match(css,/\.dr-form-actions\{[^}]*flex-wrap:wrap/);
});
