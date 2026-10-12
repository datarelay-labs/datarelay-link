// M2/R6 Core Job Detail sanitization is deterministic source evidence,
// not a logged-in Browser or privileged Core/Agent E2E.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {mkdtempSync,rmSync,readFileSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {build} from 'esbuild';
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,'node_modules','.drlink-m2-job-display-'));
let view;
try{
 const outfile=join(scratch,'job-display.mjs');
 await build({entryPoints:[join(root,'src','uxb-jobs-display.ts')],outfile,
   platform:'node',format:'esm',bundle:true,logLevel:'silent'});
 view=await import(pathToFileURL(outfile).href);
}finally{rmSync(scratch,{recursive:true,force:true})}
const valid={id:'mjob_'+'a'.repeat(24),job_type:'doctor',status:'RUNNING',
  target_count:2,resource_type:'managed-host',resource_ref:'host-a',
  deadline_at:'2026-10-12T07:00:00Z',last_error:'',cancel_requested:0,
  requested_by:'web:admin',payload:{secret:'PRIVATE_PAYLOAD'},
  targets:[
   {target_id:'host-a',status:'RUNNING',attempt:2,
     updated_at:'2026-10-12T06:00:00Z',error:'',
     worker_id:'PRIVATE_WORKER',result:{api_key:'PRIVATE_RESULT'}},
   {target_id:'host-b',status:'FAILED',attempt:1,
     updated_at:'2026-10-12T06:01:00Z',error:'WORKER_LEASE_EXPIRED',
     result:{password:'PRIVATE_RESULT'}}
  ],
  security_tokens:{bearer:'PRIVATE_TOP'}
};
test('M2 R6 Job Detail displays only scoped Core progress facts, not Agent results, tokens or user payload',()=>{
 const data=view.observedCoreJobDisplay(valid);
 assert.deepEqual(data,{
  id:valid.id,job_type:'doctor',status:'RUNNING',target_count:2,
  resource_type:'managed-host',resource_ref:'host-a',
  deadline_at:'2026-10-12T07:00:00Z',last_error:'',
  targets:[
   {target_id:'host-a',status:'RUNNING',attempt:2,updated_at:'2026-10-12T06:00:00Z',error:''},
   {target_id:'host-b',status:'FAILED',attempt:1,updated_at:'2026-10-12T06:01:00Z',error:'WORKER_LEASE_EXPIRED'}
  ]});
 assert.doesNotMatch(JSON.stringify(data),/PRIVATE_|api_key|password|worker_id|requested_by|security_tokens/);
});
test('M2 R6 malformed Job evidence never enables a false cancel or a fabricated healthy target',()=>{
 for(const invalid of [null,{},[],{...valid,id:'mjob_wrong'},
  {...valid,job_type:'unknown'},{...valid,status:'COMPLETE'},
  {...valid,target_count:101},{...valid,target_count:0},
  {...valid,targets:[]},{...valid,targets:[valid.targets[0],valid.targets[0]]},
  {...valid,targets:[{...valid.targets[0],status:'SUCCESSED'},valid.targets[1]]}]){
  assert.equal(view.observedCoreJobDisplay(invalid),null,JSON.stringify(invalid)?.slice(0,110));
 }
 const untrusted=view.observedCoreJobDisplay({...valid,
  last_error:'Bearer PRIVATE_SECRET',
  resource_ref:'https://evil.example/private?api_key=PRIVATE_SECRET',
  targets:[{...valid.targets[0],attempt:{token:'PRIVATE'},
    error:'HTTP 401 token=PRIVATE_SECRET',updated_at:'yesterday'},valid.targets[1]]});
 assert.equal(untrusted.last_error,'UNKNOWN');
 assert.equal(untrusted.resource_ref,'UNKNOWN');
 assert.equal(untrusted.targets[0].attempt,'UNKNOWN');
 assert.equal(untrusted.targets[0].error,'UNKNOWN');
 assert.equal(untrusted.targets[0].updated_at,'UNKNOWN');
 assert.doesNotMatch(JSON.stringify(untrusted),/PRIVATE_SECRET|evil.example|Bearer|\[object Object\]/);
});
test('M2 R6 Job Operations renders sanitized display-only copy, no raw target.result/errors and no unsafe cancellation action',()=>{
 const source=readFileSync(join(root,'src','main.tsx'),'utf8');
 const panel=source.split('function JobOperations(',2)[1]?.split('function ObjectsWorkspace(',1)[0]||'';
 assert.match(source,/import \{observedCoreJobDisplay,observedJobCancelAvailable\} from "\.\/uxb-jobs-display"/);
 assert.match(panel,/const safeDetail=detail\?observedCoreJobDisplay\(detail\):null;/);
 assert.match(panel,/\{safeDetail&&<div className="card">/);
 assert.match(panel,/\{detail&&!safeDetail&&<p role="alert"/);
 assert.match(panel,/value=\{safeDetail.status\}/);
 assert.match(panel,/safeDetail.targets/);
 assert.doesNotMatch(panel,/result:x.result/);
 assert.doesNotMatch(panel,/error:x.error\|\|""/);
 assert.doesNotMatch(panel,/\{detail&&<div className="card">/);
});

test('R6 Operator cannot cancel Admin-only Agent rollout, while regular Jobs remain role-scoped',()=>{
 const doctor=view.observedCoreJobDisplay({...valid,status:'QUEUED'});
 const rollout=view.observedCoreJobDisplay({...valid,status:'QUEUED',job_type:'agent-update-rollout'});
 const terminal=view.observedCoreJobDisplay({...valid,status:'SUCCEEDED'});
 assert.equal(view.observedJobCancelAvailable(doctor,'Admin'),true);
 assert.equal(view.observedJobCancelAvailable(doctor,'Operator'),true);
 assert.equal(view.observedJobCancelAvailable(doctor,'Read Only'),false);
 assert.equal(view.observedJobCancelAvailable(doctor,'unknown'),false);
 assert.equal(view.observedJobCancelAvailable(rollout,'Admin'),true);
 assert.equal(view.observedJobCancelAvailable(rollout,'Operator'),false);
 assert.equal(view.observedJobCancelAvailable(rollout,'Read Only'),false);
 assert.equal(view.observedJobCancelAvailable(terminal,'Admin'),false);
 assert.equal(view.observedJobCancelAvailable(terminal,'Operator'),false);
 assert.equal(view.observedJobCancelAvailable(null,'Admin'),false);
 const source=readFileSync(join(root,'src','main.tsx'),'utf8');
 const panel=source.split('function JobOperations(',2)[1]?.split('function ObjectsWorkspace(',1)[0]||'';
 assert.match(panel,/observedJobCancelAvailable\(safeDetail,operator.role\)/);
 assert.match(panel,/!observedJobCancelAvailable\(observedCoreJobDisplay\(detail\),operator.role\)/);
});
