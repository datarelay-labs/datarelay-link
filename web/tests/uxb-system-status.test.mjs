// M2/R4 — Core System source-owned status is not arbitrary Web JSX.
// Source-only, not browser/host or privileged lifecycle qualification.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {mkdtempSync,rmSync,readFileSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {build} from 'esbuild';
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,'node_modules','.drlink-r4-system-'));
let sys;
try{
 const outfile=join(scratch,'system.mjs');
 await build({entryPoints:[join(root,'src','uxb-system-status.ts')],outfile,
  platform:'node',format:'esm',bundle:true,logLevel:'silent'});
 sys=await import(pathToFileURL(outfile).href);
}finally{rmSync(scratch,{recursive:true,force:true})}
const status={
 read_only:true,side_effect_free:true,
 identity:{display_identity:'3.0.0-dev',project_version:'3.0.0',
  relay_engine_version:'0.65.0',source_head:'a'.repeat(40),source_ref:'abc123',
  bundle_sha256:'a'.repeat(64),channel:'development',private_token:'NO_LEAK'},
 certificate:{mode:'AUTO_ACME',hostname:'mcp.example.com',
  issuer:'Cert Authority',certificate:'valid',expires:'2027-03-01T00:00:00Z',
  days_remaining:121,auto_renewal:true,private_key:'NO_LEAK'},
 backup:{directory:'/var/lib/drlink/backups',directory_present:true,
  create_available:true,validate_available:true,restore_available:true,
  archive_private_key:'NO_LEAK'},
 support_bundle:{directory:'/var/lib/drlink/support-bundles',directory_present:true,
  create_available:true,sanitized:true,secret:'NO_LEAK'},
 update:{product_check_available:true,product_apply_via_web:true,
  product_apply_mode:'QUEUED_EXACT_BUILD',engine_check_available:true,
  engine_apply_via_web:true,token:'NO_LEAK'},
 unknown:{password:'NO_LEAK'}
};
test('M2 R4 Web displays only verified Core System public status, never nested credential fields',()=>{
 const view=sys.observedCoreSystemStatus(status);
 assert.equal(view.read_only,true);
 assert.equal(view.identity.display_identity,'3.0.0-dev');
 assert.equal(view.backup.create_available,true);
 assert.equal(view.certificate.mode,'AUTO_ACME');
 assert.equal(view.update.product_apply_via_web,true);
 assert.equal(view.support_bundle.sanitized,true);
 assert.doesNotMatch(JSON.stringify(view),/NO_LEAK|unknown|private_token|archive_private_key/);
 assert.deepEqual(Object.keys(view),['read_only','side_effect_free','identity','certificate','backup','support_bundle','update']);
});
test('M2 R4 invalid origin or action availability is UNKNOWN / disabled, not manufactured Admin capabilities',()=>{
 for(const bad of [null,undefined,[],{},{...status,read_only:false},
  {...status,side_effect_free:false},{...status,identity:null},
  {...status,certificate:null},{...status,backup:null},
  {...status,update:null},{...status,support_bundle:null}]){
  assert.equal(sys.observedCoreSystemStatus(bad),null,JSON.stringify(bad)?.slice(0,90));
 }
 const wrong=sys.observedCoreSystemStatus({...status,
  identity:{...status.identity,display_identity:{token:'NO_LEAK'}},
  certificate:{...status.certificate,hostname:{credential:'NO_LEAK'},
   mode:'SUPERUSER',days_remaining:{token:'NO_LEAK'}},
  backup:{...status.backup,create_available:'true',validate_available:'true'},
  update:{...status.update,product_apply_mode:'UNVERIFIED',product_apply_via_web:'true',
   engine_apply_via_web:'true'},
  support_bundle:{...status.support_bundle,create_available:{credential:'NO_LEAK'}}});
 assert.equal(wrong.identity.display_identity,'UNKNOWN');
 assert.equal(wrong.certificate.mode,'UNKNOWN');
 assert.equal(wrong.certificate.hostname,'');
 assert.equal(wrong.certificate.days_remaining,'UNKNOWN');
 assert.equal(wrong.backup.create_available,undefined);
 assert.equal(wrong.backup.validate_available,undefined);
 assert.equal(wrong.update.product_apply_via_web,undefined);
 assert.equal(wrong.update.engine_apply_via_web,undefined);
 assert.equal(wrong.support_bundle.create_available,undefined);
 assert.doesNotMatch(JSON.stringify(wrong),/NO_LEAK|\[object Object\]|SUPERUSER|UNVERIFIED/);
});
test('System route must project source Core response before rendering Foundation administration and sensitive controls',()=>{
 const source=readFileSync(join(root,'src','main.tsx'),'utf8');
 assert.match(source,/import \{observedCoreSystemStatus\} from "\.\/uxb-system-status"/);
 assert.match(source,/active==="system"\?observedCoreSystemStatus\(payload\)/);
 assert.match(source,/if\(!projected\)throw new Error\("Core System status/);
 assert.match(source,/setData\(projected\)/);
 assert.doesNotMatch(source,/setData\(requireObservedMenuPayload\("system",payload\)\)/);
});
