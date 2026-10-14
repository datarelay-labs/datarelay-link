// M2/R6: bounded read-only rollout Preview render projection, no Agent apply.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {mkdtempSync,rmSync,readFileSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {build} from 'esbuild';
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,'node_modules','.drlink-r6-rollout-display-'));
let view;
try{
 const outfile=join(scratch,'rollout.mjs');
 await build({entryPoints:[join(root,'src','uxb-rollout-display.ts')],outfile,
   platform:'node',format:'esm',bundle:true,logLevel:'silent'});
 view=await import(pathToFileURL(outfile).href);
}finally{rmSync(scratch,{recursive:true,force:true})}
const request={
  targets:['host-a','host-b'],canary_targets:['host-a'],
  artifact:{version:'3.0.0-rc.1',source_ref:'a'.repeat(40),sha256:'b'.repeat(64)},
  wave_size:1,failure_threshold_percent:20
};
const observation=(target_id,current_version='3.0.0',platform='linux-amd64')=>({
  target_id,current_version,target_version:'3.0.0-rc.1',platform,
  version_relation:current_version==='unknown'?'UNKNOWN':current_version==='3.0.0-rc.1'?'SAME_VERSION':'DIFFERENT',
  provenance:'NOT_VERIFIED',update_available:'UNKNOWN',last_heartbeat:null,
  worker_token:'DO_NOT_COPY'
});
const proof={read_only:true,eligible:true,ready_to_apply:false,creates_job:false,
  requires_fresh_validation_on_apply:true,artifact_qualification:'NOT_VERIFIED',
  qualification_note:'Core note with arbitrary private attributes',
  targets:request.targets,target_count:2,blocked_targets:[],canary_targets:['host-a'],
  wave_size:1,failure_threshold_percent:20,artifact:request.artifact,
  target_observations:[observation('host-a'),observation('host-b','unknown','unknown')],
  internal_key:'DO_NOT_COPY',update_package:{token:'DO_NOT_COPY'}
};
test('M2 R6 Preview keeps bounded public evidence only, never raw nested Agent metadata',()=>{
 const result=view.observedRolloutPreviewDisplay(proof,request);
 assert.equal(result.read_only,true);
 assert.equal(result.ready_to_apply,false);
 assert.equal(result.artifact_qualification,'NOT_VERIFIED');
 assert.deepEqual(result.targets,['host-a','host-b']);
 assert.equal(result.target_observations.length,2);
 assert.deepEqual(result.target_observations[0],{
  target_id:'host-a',current_version:'3.0.0',target_version:'3.0.0-rc.1',
  platform:'linux-amd64',version_relation:'DIFFERENT',
  provenance:'NOT_VERIFIED',update_available:'UNKNOWN'
 });
 assert.match(result.qualification_note,/not verified|NOT VERIFIED/i);
 assert.doesNotMatch(JSON.stringify(result),/DO_NOT_COPY|private attributes|worker_token|internal_key|update_package/);
});
test('Malformed or secret-shaped Core Agent labels are UNKNOWN, never a trusted version or leaked data',()=>{
 const altered={...proof,target_observations:[
  observation('host-a','key=SECRET_TOKEN','Bearer SECRET_TOKEN'),
  observation('host-b','unknown','unknown')
 ]};
 const result=view.observedRolloutPreviewDisplay(altered,request);
 assert.equal(result.target_observations[0].current_version,'UNKNOWN');
 assert.equal(result.target_observations[0].platform,'UNKNOWN');
 assert.equal(result.target_observations[0].version_relation,'UNKNOWN');
 assert.doesNotMatch(JSON.stringify(result),/SECRET_TOKEN|Bearer/);
 for(const bad of [
  {...proof,ready_to_apply:true},
  {...proof,artifact_qualification:'VERIFIED'},
  {...proof,targets:['host-b','host-a']},
  {...proof,target_observations:[observation('host-a')]},
 ]){
  assert.equal(view.observedRolloutPreviewDisplay(bad,request),null);
 }
 const badRequest={...request,artifact:{...request.artifact,version:'key=SECRET_TOKEN'}};
 const badResponse={...proof,artifact:badRequest.artifact,
   target_observations:[observation('host-a','unknown'),observation('host-b','unknown')].map(row=>({...row,target_version:badRequest.artifact.version}))};
 assert.equal(view.observedRolloutPreviewDisplay(badResponse,badRequest),null);
});
test('R6 rollout Web calls a redacted Preview projector before React, never posts an Apply',()=>{
 const source=readFileSync(join(root,'src','main.tsx'),'utf8');
 const panel=source.split('function AgentRolloutPreviewPanel()',2)[1]?.split('function JobOperations(',1)[0]||'';
 assert.match(source,/import \{observedRolloutPreviewDisplay\} from "\.\/uxb-rollout-display"/);
 assert.match(panel,/const verified=requireObservedRolloutPreview\(await api\("/);
 assert.match(panel,/const projected=observedRolloutPreviewDisplay\(verified,body\);/);
 assert.match(panel,/if\(!projected\)throw new Error\(/);
 assert.match(panel,/setPreview\(projected\);/);
 assert.doesNotMatch(panel,/setPreview\(result\);/);
 assert.doesNotMatch(panel,/\/api\/v1\/jobs\/agent-update-rollout"\s*,\s*\{method:"POST"/);
});
