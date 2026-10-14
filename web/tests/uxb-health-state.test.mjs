// R2.2/M2: Core Health is a bounded read-only diagnostic projection.
// Offline source proof; not installed/privileged Browser or traffic E2E.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {mkdtempSync,rmSync,readFileSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {build} from 'esbuild';
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,'node_modules','.drlink-r22-health-'));
let view;
try{
 const outfile=join(scratch,'health.mjs');
 await build({entryPoints:[join(root,'src','uxb-health-state.ts')],outfile,
    format:'esm',platform:'node',bundle:true,logLevel:'silent'});
 view=await import(pathToFileURL(outfile).href);
}finally{rmSync(scratch,{recursive:true,force:true})}
const raw={
 resource:'data-relay-link',read_only:true,db_healthy:true,mismatch:false,
 schema:35,revision:7,clients:7,services:4,
 internal_secret:'NOT_DISPLAYED',
 generations:{
  remote:{status:'active',generation:7,db_revision:7,error:'',
    activated_at:'2026-10-12T01:00:00Z',private_key:'NO_LEAK'},
  internet:{status:'not_configured',generation:0,db_revision:7,error:''},
  ai:{status:'failed',generation:3,db_revision:7,error:'Compile warning'},
  unrelated:{credential:'NOT_DISPLAYED'}
 },
 management_jobs:{active_jobs:1,queued_jobs:1,running_jobs:0,failed_jobs:2,
  queued_targets:2,running_targets:0,max_active_jobs:4,saturated:false,
  secret_token:'SECRET_JOB'}
};
test('R2.2 health only projects Core-owned public diagnostics, never raw data or unknown fields',()=>{
 const projected=view.observedCoreHealthSnapshot(raw);
 assert.equal(projected.resource,'data-relay-link');
 assert.equal(projected.read_only,true);
 assert.equal(projected.db_healthy,true);
 assert.equal(projected.revision,7);
 assert.equal(projected.generations.remote.status,'active');
 assert.equal(projected.generations.ai.status,'failed');
 assert.equal(projected.management_jobs.active_jobs,1);
 assert.equal(projected.management_jobs.saturated,false);
 assert.equal(view.observedHealthPlaneCount(projected),1);
 assert.deepEqual(Object.keys(projected.generations),['remote','internet','ai']);
 assert.doesNotMatch(JSON.stringify(projected),/NOT_DISPLAYED|NO_LEAK|SECRET_JOB|credential|private_key|secret_token|unrelated/);
});
test('R2.2 malformed Core health or contradictory capacity must remain UNKNOWN, never healthy',()=>{
 for(const invalid of [null,undefined,[],{},
  {...raw,resource:'private-unknown'}, {...raw,read_only:false},
  {...raw,db_healthy:'true'},{...raw,mismatch:'false'},
  {...raw,management_jobs:null}, {...raw,generations:null}]){
   assert.equal(view.observedCoreHealthSnapshot(invalid),null,JSON.stringify(invalid)?.slice(0,90));
 }
 const bad=view.observedCoreHealthSnapshot({...raw,
   generations:{...raw.generations,remote:{...raw.generations.remote,status:{private:'NOT_SAFE'},
     generation:{token:'TOKEN'},error:{secret:'SECRET'}}},
   management_jobs:{...raw.management_jobs,active_jobs:{token:'PRIVATE'},saturated:'false'}});
 assert.equal(bad.generations.remote.status,'UNKNOWN');
 assert.equal(bad.generations.remote.generation,null);
 assert.equal(bad.generations.remote.error,'UNKNOWN');
 assert.equal(bad.management_jobs.active_jobs,null);
 assert.equal(bad.management_jobs.saturated,null);
 assert.equal(view.observedHealthPlaneCount(bad),null);
 assert.doesNotMatch(JSON.stringify(bad),/NOT_SAFE|TOKEN|SECRET|PRIVATE|\[object Object\]/);
 const conflicting=view.observedCoreHealthSnapshot({...raw,
   management_jobs:{...raw.management_jobs,active_jobs:10,saturated:false}});
 assert.equal(conflicting.management_jobs.saturated,null);
 assert.equal(conflicting.management_jobs.active_jobs,null);
});
test('R2.2 HealthWorkspace renders ONLY redacted bounded Core snapshot, not the raw API object',()=>{
 const source=readFileSync(join(root,'src','main.tsx'),'utf8');
 const section=source.split('function HealthWorkspace(',2)[1]?.split('function AccessHygienePanel(',1)[0]||'';
 assert.match(source,/import \{observedCoreHealthSnapshot,observedHealthPlaneCount\} from "\.\/uxb-health-state"/);
 assert.match(section,/const observed=observedCoreHealthSnapshot\(raw\);/);
 assert.match(section,/if\(!observed\)return <section/);
 assert.match(section,/const data=observed;/);
 assert.match(section,/const configuredPlanes=observedHealthPlaneCount\(data\);/);
 assert.match(section,/JSON\.stringify\(observed,null,2\)/);
 assert.doesNotMatch(section,/JSON\.stringify\(raw,null,2\)/);
 assert.doesNotMatch(section,/Advanced · raw health payload/);
});
