// M2/R6: existing Core support-bundle create response may include extra
// operational/worker state; never reflect it or confuse with download.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {mkdtempSync,rmSync,readFileSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {build} from 'esbuild';
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,'node_modules','.drlink-m2-support-bundle-'));
let mod;
try{
 const outfile=join(scratch,'bundle.mjs');
 await build({entryPoints:[join(root,'src','uxb-support-bundle.ts')],outfile,
  platform:'node',format:'esm',bundle:true,logLevel:'silent'});
 mod=await import(pathToFileURL(outfile).href);
}finally{rmSync(scratch,{recursive:true,force:true})}
const receipt={status:'CREATED',path:'/var/lib/drlink/support-bundles/drlink-support-20261012T043050Z-a1b2c3d4.tar.gz',
 size_bytes:512,sha256:'a'.repeat(64),
 protected_artifact:false,sanitized:true,download_exposed:false,
 authoritative_mutation:false,
 stdout:'token PRIVATE_SECRET',payload:{credential:'PRIVATE_SECRET'}};
test('R6 support bundle displays canonical Core-owned sanitized artifact proof, not raw secret output',()=>{
 const observed=mod.observedCoreSupportBundleReceipt(receipt);
 assert.deepEqual(observed,{
  status:'CREATED',path:receipt.path,size_bytes:512,sha256:'a'.repeat(64),
  sanitized:true,download_exposed:false,authoritative_mutation:false
 });
 assert.doesNotMatch(JSON.stringify(observed),/PRIVATE_SECRET|stdout|payload|credential/);
});
test('R6 fabricated CREATED, path escape, download exposure, mutation and malformed hash are UNKNOWN',()=>{
 for(const bad of [null,undefined,{},[],
  {...receipt,status:'QUEUED'}, {...receipt,status:'COMPLETE'},
  {...receipt,protected_artifact:true},{...receipt,sanitized:false},
  {...receipt,download_exposed:true},{...receipt,authoritative_mutation:true},
  {...receipt,size_bytes:0},{...receipt,size_bytes:-1},{...receipt,size_bytes:'512'},
  {...receipt,sha256:'hash'},{...receipt,sha256:'A'.repeat(64)},
  {...receipt,path:'/tmp/drlink-support-20261012T043050Z-a1b2c3d4.tar.gz'},
  {...receipt,path:'/var/lib/drlink/support-bundles/../secrets'},
  {...receipt,path:'https://external.example.com?token=SECRET'},
  {...receipt,path:'/var/lib/drlink/support-bundles/drlink-support-20261012T043050Z-a1b2c3d4.tar.gz/../secret'},
  {...receipt,path:'/var/lib/drlink/support-bundles/drlink-support-too-long.tar.gz'},
 ])assert.equal(mod.observedCoreSupportBundleReceipt(bad),null,JSON.stringify(bad)?.slice(0,145));
});
test('R6 Support Bundle POST is locked immediately and only source-verified CREATED allows display',()=>{
 const src=readFileSync(join(root,'src','main.tsx'),'utf8');
 const panel=src.split('function SystemPanel(',2)[1]?.split('function AccessOperations(',1)[0]||'';
 assert.match(src,/import \{observedCoreSupportBundleReceipt\} from "\.\/uxb-support-bundle"/);
 assert.match(panel,/const supportBundleInFlight=useRef\(false\)/);
 assert.match(panel,/if\(supportBundleInFlight\.current/);
 assert.match(panel,/supportBundleInFlight\.current=true;/);
 assert.match(panel,/const observed=observedCoreSupportBundleReceipt\(raw\);/);
 assert.match(panel,/if\(!observed\)throw new Error/);
 assert.match(panel,/setSupportArtifact\(observed\)/);
 assert.match(panel,/supportBundleInFlight\.current=false;/);
 assert.match(panel,/Core Support Bundle outcome UNKNOWN/);
 assert.doesNotMatch(panel,/setSupportArtifact\(await api/);
 assert.match(panel,/disabled=\{supportBundleBusy\|\|!support.create_available\}/);
});
