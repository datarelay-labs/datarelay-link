// M2 native Link Core integration contract: explicit Admin write receipts only.
// No external HTTP, real credentials, production/host effects or E2E.
import assert from "node:assert/strict";
import {test} from "node:test";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const temp=mkdtempSync(join(root,"node_modules",".drlink-m2-integrations-receipts-"));
let helper;
try{
 const outfile=join(temp,"receipt.mjs");
 await build({entryPoints:[join(root,"src","uxb-integration-write-receipts.ts")],
  outfile,platform:"node",format:"esm",bundle:true,logLevel:"silent"});
 helper=await import(pathToFileURL(outfile).href);
}finally{rmSync(temp,{recursive:true,force:true})}
const msa="msa_"+"a".repeat(24),cred="msc_"+"b".repeat(24),wh="wh_"+"c".repeat(24);
const saToken="drlink_sa_"+"A".repeat(43),hookSecret="drlink_wh_"+"B".repeat(43);
const receipt=(path,request,response)=>helper.observedIntegrationWriteReceipt(path,request,response);

test("M2 admin Core Service Account create/rotate returns only structurally verified one-time token",()=>{
 assert.deepEqual(receipt("/api/v1/service-accounts",{name:"robot",permissions:["management-read"]},{
  id:msa,name:"robot",permissions:["management-read"],expires_at:"",credential:saToken,credential_id:cred
 }),{status:"secret",kind:"Service Account token",id:msa,secret:saToken});
 assert.deepEqual(receipt("/api/v1/service-accounts/rotate",{account_id:msa},
  {credential:saToken,credential_id:cred}),
  {status:"secret",kind:"Service Account token",id:msa,secret:saToken});
});

test("M2 admin Core Webhook create/rotate binds one-time secret to exactly requested Webhook identity",()=>{
 assert.deepEqual(receipt("/api/v1/webhooks",{name:"Event hook",url:"https://hooks.example.test/",
  event_classes:["attention"]},{id:wh,url:"https://hooks.example.test/",event_classes:["attention"],
  secret:hookSecret}),{status:"secret",kind:"Webhook signing secret",id:wh,secret:hookSecret});
 assert.deepEqual(receipt("/api/v1/webhooks/rotate",{webhook_id:wh},{id:wh,secret:hookSecret}),
  {status:"secret",kind:"Webhook signing secret",id:wh,secret:hookSecret});
 assert.equal(receipt("/api/v1/webhooks/rotate",{webhook_id:wh},
  {id:"wh_"+"d".repeat(24),secret:hookSecret}),null,"other webhook response never counts");
});

test("M2 disable/revoke response must confirm exact Core entity and explicit disabled flag",()=>{
 assert.deepEqual(receipt("/api/v1/webhooks/disable",{webhook_id:wh},{id:wh,enabled:false}),
  {status:"disabled",id:wh});
 assert.deepEqual(receipt("/api/v1/service-accounts/revoke",{account_id:msa},{id:msa,enabled:false}),
  {status:"disabled",id:msa});
 for(const flag of [undefined,null,0,"false",true]){
  assert.equal(receipt("/api/v1/webhooks/disable",{webhook_id:wh},{id:wh,enabled:flag}),null);
 }
 assert.equal(receipt("/api/v1/service-accounts/revoke",{account_id:msa},
  {id:"msa_"+"d".repeat(24),enabled:false}),null);
});

test("M2 malformed HTTP 200 is never proof a minted secret was safely delivered",()=>{
 const valid={credential:saToken,credential_id:cred};
 for(const data of [null,{},[],{credential_id:cred}, {credential:saToken},
  {credential:"drlink_sa_not_real",credential_id:cred},
  {credential:saToken+"\nPRIVATE",credential_id:cred},
  {credential:{nested:"PRIVATE"},credential_id:cred},
  {credential:saToken,credential_id:{"secret":"PRIVATE"}},
  {credential:"drlink_wh_"+"B".repeat(43),credential_id:cred}
 ]){
  assert.equal(receipt("/api/v1/service-accounts/rotate",{account_id:msa},data),null);
 }
 for(const path of ["/api/v1/webhooks/anything","/api/v1/service-accounts/delete","/api/v1/operators"]){
  assert.equal(receipt(path,{webhook_id:wh},{id:wh,secret:hookSecret}),null);
 }
 for(const wrong of [null,undefined,{},[],{account_id:"bad\u202e"},
    {account_id:wh}, {webhook_id:msa}]){
  assert.equal(receipt("/api/v1/service-accounts/rotate",wrong,valid),null);
 }
 assert.equal(receipt("/api/v1/webhooks", {name:"Hook"}, {id:wh,secret:hookSecret}),null);
 assert.equal(receipt("/api/v1/service-accounts",{name:"Robot"},{
  id:msa,credential:saToken,credential_id:cred,name:"Wrong"
 }),null);
});

test("M2 optional datetime-local expiry validates real local calendar before UTC projection",()=>{
 assert.equal(helper.integrationLocalExpiryToUtc(""),"");
 for(const text of ["2030-02-28T14:30","2032-02-29T00:00","2030-12-31T23:59"]){
  assert.equal(helper.integrationLocalExpiryToUtc(text),new Date(text).toISOString());
 }
 for(const bad of [undefined,null,2,{},[],"2030-02-29T14:30","2030-04-31T10:10",
  "2030-02-28T25:00","2030-02-28T15:61","2030-02-28T14:30Z",
  "2030-02-28\nT14:30","2030-02-28T14:30\u202e"]){
  assert.equal(helper.integrationLocalExpiryToUtc(bad),null,String(bad));
 }
});

test("M2 Web integrations show ONLY a verified secret and preserve input on UNKNOWN postwrite response",()=>{
 const main=readFileSync(join(root,"src","main.tsx"),"utf8");
 const panel=main.split("function IntegrationsPanel(",2)[1]?.split("function CommandCenter(",1)[0]||"";
 assert.match(main,/import \{observedIntegrationWriteReceipt,integrationLocalExpiryToUtc\} from "\.\/uxb-integration-write-receipts"/);
 assert.match(panel,/const receipt=observedIntegrationWriteReceipt\(path,body,result\)/);
 assert.match(panel,/if\(!receipt\)throw new Error\(/);
 assert.match(panel,/if\(receipt.status==="secret"\)setOnce\(\{kind:receipt.kind,secret:receipt.secret,id:receipt.id\}\)/);
 assert.match(panel,/Core integration outcome UNKNOWN/);
 assert.match(panel,/Inspect the current Core inventory and Audit before retrying/);
 assert.match(panel,/return true/);
 assert.match(panel,/return false/);
 assert.match(panel,/const expiry=integrationLocalExpiryToUtc\(accountExpiry\)/);
 assert.match(panel,/if\(expiry===null\)/);
 assert.match(panel,/if\(!ok\)return/);
 assert.doesNotMatch(panel,/result\.credential\|\|result\.secret/);
 assert.doesNotMatch(panel,/await mutate\("\/api\/v1\/webhooks"[^;]+;\s*setHookName/);
 assert.match(panel,/onClick=\{\(\)=>setOnce\(null\)\}/);
 assert.doesNotMatch(panel,/localStorage|sessionStorage/);
});


test("M2 non-idempotent Core integration changes refuse overlapping writes and preserve prior one-time secret until Done",()=>{
 const main=readFileSync(join(root,"src","main.tsx"),"utf8");
 const panel=main.split("function IntegrationsPanel(",2)[1]?.split("function CommandCenter(",1)[0]||"";
 assert.match(panel,/const integrationMutationInFlight=useRef\(false\)/);
 assert.match(panel,/if\(integrationMutationInFlight\.current\|\|once\)/);
 assert.match(panel,/integrationMutationInFlight\.current=true/);
 assert.match(panel,/integrationMutationInFlight\.current=false/);
 assert.doesNotMatch(panel,/setBusy\(true\);setError\("".*?\);setOnce\(null\)/);
 assert.match(panel,/Store or dismiss the visible one-time secret before any further integration operation/);
 assert.match(panel,/disabled=\{busy\|\|!!once\|\|!accountName/);
 assert.match(panel,/disabled=\{busy\|\|!!once\|\|!hookName/);
 assert.match(panel,/disabled=\{busy\|\|!!once\} onClick/);
 assert.match(panel,/if\(!ok\)return;\s*setAccountName\("".*?\);setAccountExpiry\("".*?\)/);
 assert.match(panel,/if\(!ok\)return;\s*setHookName\("".*?\);setHookUrl\("".*?\)/);
 assert.doesNotMatch(panel,/\.then\(\(\)=>mutate\(/);
 assert.doesNotMatch(panel,/setTimeout\(/);
});
