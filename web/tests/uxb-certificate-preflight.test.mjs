// M2 R4: evidence-only Core certificate preflight projection.
// Offline contract checks: no live DNS/ACME, TLS mutation or Browser E2E.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {mkdtempSync,rmSync,readFileSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {build} from 'esbuild';
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,'node_modules','.drlink-r4-cert-preflight-'));
let cert;
try {
 const outfile=join(scratch,'preflight.mjs');
 await build({entryPoints:[join(root,'src','uxb-certificate-preflight.ts')],outfile,
   platform:'node',format:'esm',bundle:true,logLevel:'silent'});
 cert=await import(pathToFileURL(outfile).href);
} finally {rmSync(scratch,{recursive:true,force:true})}
const expected={hostname:'mcp.example.com',mode:'AUTO_ACME'};
const core={hostname:'mcp.example.com',mode:'AUTO_ACME',
  authoritative_mutation:false,ok:true,resolves:true,private_only:false,
  challenge_port_80_open:true,addresses:['203.0.113.5'],
  warnings:[],errors:[],extra:{token:'SECRET_TOKEN'}};

test('R4 Core certificate preflight displays only bounded confirmed public diagnostic facts',()=>{
 const result=cert.observedCoreCertificatePreflight(core,expected);
 assert.deepEqual(result,{
  hostname:'mcp.example.com',mode:'AUTO_ACME',read_only:true,
  conclusion:'CORE_PREFLIGHT_PASS',dns:'RESOLVED',
  private_only:false,local_port_80:'REACHABLE',
  address_count:1,warnings_count:0,errors_count:0
 });
 assert.doesNotMatch(JSON.stringify(result),/SECRET_TOKEN|203\.0\.113|extra|addresses/);
 const failure=cert.observedCoreCertificatePreflight({
  ...core,ok:false,resolves:false,addresses:[],
  challenge_port_80_open:null,errors:['hostname does not resolve'],
  warnings:['TLS API key=PRIVATE_SECRET']},expected);
 assert.deepEqual(failure,{...result,conclusion:'CORE_PREFLIGHT_ATTENTION',
  dns:'NOT_RESOLVED',local_port_80:'NOT_CHECKED',address_count:0,
  errors_count:1,warnings_count:1});
 assert.doesNotMatch(JSON.stringify(failure),/PRIVATE_SECRET|hostname does not resolve/);
});
test('R4 cross-host, forged mutation, malformed/contradictory status and unbounded evidence stay UNKNOWN',()=>{
 for(const bad of [
  null,{},[],{...core,hostname:'other.example.com'},
  {...core,mode:'PRIVATE_CA'}, {...core,authoritative_mutation:true},
  {...core,authoritative_mutation:undefined},
  {...core,ok:'true'}, {...core,resolves:'true'},
  {...core,private_only:'false'},
  {...core,challenge_port_80_open:'true'},
  {...core,addresses:'203.0.113.5'}, {...core,addresses:[{token:'X'}]},
  {...core,addresses:Array.from({length:101},(_,i)=>'203.0.113.'+i)},
  {...core,warnings:{secret:'CREDENTIAL'}}, {...core,errors:'no'},
  {...core,ok:true,errors:['invalid']},
  {...core,resolves:false,addresses:['203.0.113.5']},
  {...core,challenge_port_80_open:true,resolves:false,addresses:[]},
  {...core,ok:false,errors:[]},
 ]) {
  assert.equal(cert.observedCoreCertificatePreflight(bad,expected),null,
    JSON.stringify(bad)?.slice(0,140));
 }
 assert.equal(cert.observedCoreCertificatePreflight(core,
   {hostname:'mcp.example.net',mode:'AUTO_ACME'}),null);
 assert.equal(cert.observedCoreCertificatePreflight(core,
   {hostname:'mcp.example.com',mode:'UNKNOWN'}),null);
});
test('R4 SystemPanel binds Core certificate preflight to same verified configured hostname and redacts raw JSON',()=>{
 const src=readFileSync(join(root,'src','main.tsx'),'utf8');
 const system=src.split('function SystemPanel(',2)[1]?.split('function AccessOperations(',1)[0]||'';
 assert.match(src,/import \{observedCoreCertificatePreflight\} from "\.\/uxb-certificate-preflight"/);
 assert.match(system,/const projected=observedCoreCertificatePreflight\(result,data\.certificate\);/);
 assert.match(system,/if\(!projected\)throw new Error\("Core certificate preflight/);
 assert.match(system,/setPreflight\(projected\)/);
 assert.doesNotMatch(system,/setPreflight\(await api/);
 assert.match(system,/JSON\.stringify\(preflight,null,2\)/);
 assert.match(system,/Preflight is advisory/);
});
