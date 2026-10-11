// Read-only, fail-closed Web integration inventory presentation; no credentials or live calls.
import assert from "node:assert/strict";
import {test} from "node:test";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";

const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,"node_modules",".pfci-integration-state-"));
let projection;
try{
 const output=join(scratch,"state.mjs");
 await build({entryPoints:[join(root,"src","uxb-integrations-state.ts")],
   outfile:output,platform:"node",format:"esm",bundle:true,logLevel:"silent"});
 projection=await import(pathToFileURL(output).href);
}finally{rmSync(scratch,{recursive:true,force:true})}

test("Account and webhook state must be Core-observed, never guessed from truthiness",()=>{
 for(const [raw,account,hook] of [
  [true,"Active","Enabled"],[false,"Revoked","Disabled"],
  [1,"Active","Enabled"],[0,"Revoked","Disabled"],
  [undefined,"UNKNOWN","UNKNOWN"],[null,"UNKNOWN","UNKNOWN"],
  ["false","UNKNOWN","UNKNOWN"],[2,"UNKNOWN","UNKNOWN"]
 ]){
  assert.equal(projection.serviceAccountStatus({enabled:raw}),account);
  assert.equal(projection.webhookStatus({enabled:raw}),hook);
 }
 assert.equal(projection.serviceAccountStatus(null),"UNKNOWN");
 assert.equal(projection.webhookStatus({}),"UNKNOWN");
});

test("Expiry: explicit no-expiry is distinct from missing or invalid Core facts",()=>{
 assert.equal(projection.serviceAccountExpiry({expires_at:null}),"No expiry");
 assert.equal(projection.serviceAccountExpiry({expires_at:""}),"No expiry");
 assert.equal(projection.serviceAccountExpiry({}),"UNKNOWN");
 assert.equal(projection.serviceAccountExpiry({expires_at:undefined}),"UNKNOWN");
 assert.equal(projection.serviceAccountExpiry({expires_at:"not-a-date"}),"UNKNOWN");
 assert.equal(projection.serviceAccountExpiry({expires_at:"2026-11-01T12:30:00Z"}),"2026-11-01T12:30:00Z");
});

test("Only allowlisted Service Account permissions are displayed",()=>{
 assert.equal(projection.serviceAccountPermissions({permissions:["management-read","management-job-observe"]}),
  "management-read, management-job-observe");
 assert.equal(projection.serviceAccountPermissions({permissions:[]}),"none reported");
 for(const raw of [undefined,null,"management-read",["management-read","secret-access"],
  ["management-read",null]]){
  assert.equal(projection.serviceAccountPermissions({permissions:raw}),"UNKNOWN");
 }
});

test("Webhook delivery counts show only bounded known statuses; absent isn't zero",()=>{
 assert.equal(projection.webhookDeliverySummary({delivery_counts:{}}),"none reported");
 assert.equal(projection.webhookDeliverySummary({}),"UNKNOWN");
 assert.equal(projection.webhookDeliverySummary({delivery_counts:{PENDING:0,DELIVERED:2,FAILED:1}}),
  "PENDING:0 · DELIVERED:2 · FAILED:1");
 for(const bad of [{PENDING:-1},{DELIVERED:"2"},{SENDING:1,SOME_SECRET:23},null]){
  assert.equal(projection.webhookDeliverySummary({delivery_counts:bad}),"UNKNOWN");
 }
});

test("IntegrationsPanel renders qualified statuses and guards actions against unknown Core flags",()=>{
 const main=readFileSync(join(root,"src","main.tsx"),"utf8");
 const source=main.split("function IntegrationsPanel(",2)[1]?.split("function CommandCenter(",1)[0]||"";
 for(const f of ["serviceAccountStatus(a)","serviceAccountExpiry(a)","serviceAccountPermissions(a)",
    "webhookStatus(h)","webhookDeliverySummary(h)"]){
   assert.ok(source.includes(f),f);
 }
 assert.match(source,/serviceAccountStatus\(a\)==="Active"&&/);
 assert.match(source,/webhookStatus\(h\)==="Enabled"&&/);
 assert.doesNotMatch(source,/a.enabled\?"Active":"Revoked"/);
 assert.doesNotMatch(source,/h.enabled\?"Enabled":"Disabled"/);
 assert.doesNotMatch(source,/h.delivery_counts\|\|\{\}/);
 assert.match(source,/requireObservedMenuPayload\("service-accounts",a\)/);
 assert.match(source,/requireObservedMenuPayload\("webhooks",w\)/);
});

test("Service Account expiry requires a real timezone-bound calendar instant, never Date.parse rollover",()=>{
 for(const good of [
  "2028-02-29T23:59:59Z",
  "2028-02-29T23:59:59.123456+00:00",
  "2026-11-01T12:30:00+09:00",
  "2026-12-31T23:59:59-04:00"
 ]){
  assert.equal(projection.serviceAccountExpiry({expires_at:good}),good);
 }
 for(const bad of [
  "2026-02-29T12:30:00Z",
  "2026-02-31T12:30:00Z",
  "2026-04-31T12:30:00Z",
  "2026-00-15T12:30:00Z",
  "2026-11-01T12:30:00",
  "2026-11-01T12:30:00+24:00",
  "2026-11-01T12:30:00+09:61",
  "2026-11-01T12:30:60Z",
  "2026-11-01T12:30:00Z trailing",
  "0000-01-01T00:00:00Z"
 ]){
  assert.equal(projection.serviceAccountExpiry({expires_at:bad}),"UNKNOWN",bad);
 }
});

test("Core absolute-time evidence rejects impossible civil timezone offsets",()=>{
 for(const raw of [
  "2026-10-11T10:30:00+14:01",
  "2026-10-11T10:30:00+15:00",
  "2026-10-11T10:30:00-16:00",
  "2026-10-11T10:30:00+23:59"
 ]){
  assert.equal(projection.isObservedAbsoluteTime(raw),false,raw);
  assert.equal(projection.serviceAccountExpiry({expires_at:raw}),"UNKNOWN",raw);
 }
 for(const valid of ["2026-10-11T10:30:00+14:00","2026-10-11T10:30:00-12:00"])
  assert.equal(projection.isObservedAbsoluteTime(valid),true,valid);
});
