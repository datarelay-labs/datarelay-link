// R4: certificate actions are Core-authorized, one-shot, and contain no raw
// key PEM, DNS or arbitrary nested Core state in Web output. Source-only.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {mkdtempSync,rmSync,readFileSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {build} from 'esbuild';
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,'node_modules','.drlink-cert-actions-'));
let actions;
try{
 const outfile=join(scratch,'certificate.mjs');
 await build({entryPoints:[join(root,'src','uxb-certificate-actions.ts')],outfile,
   platform:'node',format:'esm',bundle:true,logLevel:'silent'});
 actions=await import(pathToFileURL(outfile).href);
}finally{rmSync(scratch,{recursive:true,force:true})}
const expected={hostname:'mcp.example.com',mode:'AUTO_ACME'};
const receipt={authoritative_mutation:true,status:'CONFIGURED',
 certificate:{hostname:'mcp.example.com',mode:'AUTO_ACME',certificate:'VALID',
 active_key_path:'/etc/private/SECRET',raw:{private_key:'SECRET'}}};

test('R4 Core certificate Configure, Issue and Import receipts are exact, redacted and not TLS reachability proof',()=>{
 const configured=actions.observedCoreCertificateActionReceipt(receipt,'configure',expected);
 assert.deepEqual(configured,{status:'CONFIGURED',hostname:expected.hostname,mode:'AUTO_ACME',
  authoritative_mutation:true,certificate_state:'CORE_REPORTS_VALID'});
 assert.doesNotMatch(JSON.stringify(configured),/SECRET|private_key|active_key_path|raw/);
 assert.deepEqual(actions.observedCoreCertificateActionReceipt({...receipt,status:'ISSUED'},'issue',expected),
  {...configured,status:'ISSUED'});
 const imported=actions.observedCoreCertificateActionReceipt({...receipt,status:'IMPORTED',
  certificate:{...receipt.certificate,mode:'USER_CERTIFICATE'}},'import',
  {...expected,mode:'USER_CERTIFICATE'});
 assert.equal(imported?.status,'IMPORTED');
 assert.equal(imported?.mode,'USER_CERTIFICATE');
});
test('R4 reject malformed status, authority, host or mode and do not echo arbitrary Core values',()=>{
 for(const bad of [null,{},[],
  {...receipt,status:'APPLIED'},
  {...receipt,authoritative_mutation:false},
  {...receipt,authoritative_mutation:'true'},
  {...receipt,certificate:null},
  {...receipt,certificate:{...receipt.certificate,hostname:'other.example.com'}},
  {...receipt,certificate:{...receipt.certificate,mode:'PRIVATE_CA'}},
  {...receipt,certificate:{...receipt.certificate,certificate:{secret:'SECRET'}}},
 ])assert.equal(actions.observedCoreCertificateActionReceipt(bad,'configure',expected),null);
 for(const invalid of ['danger','renew',null,0]){
  assert.equal(actions.observedCoreCertificateActionReceipt(receipt,invalid,expected),null);
 }
 assert.equal(actions.observedCoreCertificateActionReceipt(receipt,'configure',
  {hostname:'other.example.com',mode:'AUTO_ACME'}),null);
 assert.equal(actions.observedCoreCertificateActionReceipt(receipt,'configure',
  {hostname:'mcp.example.com',mode:'UNKNOWN'}),null);
});
test('R4 renewal does not claim issue success from not_due/backoff/failed receipts',()=>{
 const cert={hostname:expected.hostname,mode:expected.mode,certificate:'VALID',secret:'DONT_SHOW'};
 const renewed={renewed:true,reason:'renewed',failure_class:'',
   authoritative_mutation:true,certificate:cert,private_key:'DONT_SHOW'};
 assert.deepEqual(actions.observedCoreCertificateRenewalReceipt(renewed,expected),{
  outcome:'RENEWED',hostname:expected.hostname,mode:expected.mode,
  authoritative_mutation:true,certificate_state:'CORE_REPORTS_VALID',failure_class:''
 });
 const skipped=actions.observedCoreCertificateRenewalReceipt({...renewed,
  renewed:false,reason:'not_due',authoritative_mutation:false},expected);
 assert.equal(skipped?.outcome,'NOT_DUE');
 assert.equal(skipped?.authoritative_mutation,false);
 const failed=actions.observedCoreCertificateRenewalReceipt({...renewed,
  renewed:false,reason:'failed',failure_class:'ACME_UNAVAILABLE'},expected);
 assert.equal(failed?.outcome,'FAILED');
 assert.equal(failed?.failure_class,'ACME_UNAVAILABLE');
 assert.doesNotMatch(JSON.stringify(failed),/DONT_SHOW|secret/);
 for(const bad of [null,{},[],
  {...renewed,renewed:false,reason:'renewed',authoritative_mutation:false},
  {...renewed,renewed:true,reason:'backoff'},
  {...renewed,renewed:false,reason:'not_due',authoritative_mutation:true},
  {...renewed,renewed:false,reason:'made-up',authoritative_mutation:false},
  {...renewed,certificate:{...cert,hostname:'other.example.com'}},
 ]){
  assert.equal(actions.observedCoreCertificateRenewalReceipt(bad,expected),null);
 }
});
test('R4 SystemPanel verifies Core certificate action receipt, blocks double POST and clears sent key PEM',()=>{
 const source=readFileSync(join(root,'src','main.tsx'),'utf8');
 const part=source.split('function SystemPanel(',2)[1]?.split('function AccessOperations(',1)[0]||'';
 assert.match(source,/import \{observedCoreCertificateActionReceipt,observedCoreCertificateRenewalReceipt\} from "\.\/uxb-certificate-actions"/);
 assert.match(part,/const certMutationInFlight=useRef\(false\)/);
 assert.match(part,/if\(certMutationInFlight\.current\)return;/);
 assert.match(part,/certMutationInFlight\.current=true;/);
 assert.match(part,/observedCoreCertificateActionReceipt\(raw,operation,expected\)/);
 assert.match(part,/observedCoreCertificateRenewalReceipt\(raw,data\.certificate\)/);
 assert.match(part,/setCertAction\(confirmed\)/);
 assert.match(part,/setRenewal\(confirmed\)/);
 assert.match(part,/certMutationInFlight\.current=false;/);
 assert.match(part,/finally\{setCertPem\(""\);setKeyPem\(""\);setChainPem\(""\);setImportConfirmation\(""\)\}/);
 assert.doesNotMatch(part,/setCertAction\(await api/);
 assert.doesNotMatch(part,/setRenewal\(await api/);
 assert.match(part,/Core mutation outcome UNKNOWN/);
});
