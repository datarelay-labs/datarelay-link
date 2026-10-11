// M1-B G-20: original loaded-only Policy expiry and safe visible search contract.
// Source+helper tests are not an authenticated user/browser/Agent E2E.
import assert from "node:assert/strict";
import {test} from "node:test";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const temp=mkdtempSync(join(root,"node_modules",".drl3-policy-expiry-"));
let helper;
try{
 const path=join(temp,"expiry.mjs");
 await build({entryPoints:[join(root,"src","uxb-policy-expiry.ts")],
  outfile:path,bundle:true,platform:"node",format:"esm",logLevel:"silent"});
 helper=await import(pathToFileURL(path).href);
}finally{rmSync(temp,{recursive:true,force:true})}

const NOW=Date.parse("2026-10-12T00:00:00Z");
const rows=[
 {id:"expired",name:"Legacy support",plane:"remote",enabled:1,expires_at:"2026-10-11T23:59:59Z"},
 {id:"exact",name:"At boundary",plane:"internet",enabled:1,expires_at:"2026-10-12T00:00:00Z"},
 {id:"due",name:"Temporary access",plane:"ai",enabled:1,expires_at:"2026-10-12T08:00:00Z"},
 {id:"edge",name:"Exactly 24h",plane:"remote",enabled:0,expires_at:"2026-10-13T00:00:00Z"},
 {id:"later",name:"Planned expiry",plane:"ai",enabled:1,expires_at:"2026-10-13T00:00:01Z"},
 {id:"never",name:"Permanent config",plane:"remote",enabled:1,expires_at:null},
 {id:"missing",name:"Unobserved",plane:"internet",enabled:1},
 {id:"bad",name:"Bad date",plane:"ai",enabled:1,expires_at:"2026-02-30T00:00:00Z"},
 {id:"str",name:"Wrong input",plane:"remote",expires_at:"No expiry"}
];

test("G-20 exact captured-time expiry bucket boundaries and independent Core enabled state",()=>{
 const kind=helper.observedPolicyExpiryState;
 assert.deepEqual(rows.map(row=>kind(row,NOW)),
  ["expired","expired","due24h","due24h","later","never","unknown","unknown","unknown"]);
 const ids=choice=>helper.filterObservedPoliciesByExpiry(rows,choice,NOW).map(row=>row.id);
 assert.deepEqual(ids("all"),rows.map(row=>row.id));
 assert.deepEqual(ids("expired"),["expired","exact"]);
 assert.deepEqual(ids("due24h"),["due","edge"]);
 assert.deepEqual(ids("later"),["later"]);
 assert.deepEqual(ids("never"),["never"]);
 assert.deepEqual(ids("unknown"),["missing","bad","str"]);
 const counts=helper.observedPolicyExpiryCounts(rows,NOW);
 assert.deepEqual(counts,{loadedCount:9,expired:2,due24h:2,later:1,never:1,unknown:3,asOf:NOW});
 assert.equal(ids("due24h")[1],"edge","disabled-but-due Core policy is a config fact, not an access grant");
 assert.equal(helper.filterObservedPoliciesByExpiry(rows,"expired",NOW)[0],rows[0],
  "return original authorized Core row without mutation");
});
test("G-20 malformed timestamps, unsafe selectors and missing Core snapshot fail closed",()=>{
 for(const invalid of [null,undefined,NaN,Infinity,-1,{},[],true,"2026-10-12"]){
  assert.equal(helper.observedPolicyExpiryState(rows[0],invalid),"unknown");
  assert.deepEqual(helper.filterObservedPoliciesByExpiry(rows,"expired",invalid),[]);
 }
 for(const status of [null,undefined,"",{},[],"EXPIRED","past","tomorrow","due24h "]){
  assert.deepEqual(helper.filterObservedPoliciesByExpiry(rows,status,NOW),[]);
 }
 for(const source of [undefined,null,{},[], "not a list"]){
  assert.deepEqual(helper.filterObservedPoliciesByExpiry(source,"expired",NOW),[]);
 }
 for(const date of ["2026-10-12T00:00:00","2025-02-29T00:00:00Z",
  "2026-10-12T10:00:00+14:30","2026-10-12T00:00:00Z\u202e",
  {token:"PRIVATE_KEY"}]){
  assert.equal(helper.observedPolicyExpiryState({expires_at:date},NOW),"unknown");
 }
 assert.equal(helper.observedPolicyExpiryState({expires_at:"2028-02-29T00:00:00+09:00"},NOW),"later");
});
test("G-20 safe visible-field Policy text search excludes nested or invisible credential metadata",()=>{
 const selection=[
  {...rows[0],credentials:{password:"NEVER_SEARCH"},internal_token:"INVISIBLE-QUERY"},
  {...rows[2],description:"temporary DB maintenance",api_key:"HIDDEN_API"},
  {...rows[5],description:"explicit no expiry"}
 ];
 const find=q=>helper.filterObservedPolicySearch(selection,q);
 assert.deepEqual(find("").items.map(row=>row.id),["expired","due","never"]);
 assert.deepEqual(find("legacy").items.map(row=>row.id),["expired"]);
 assert.deepEqual(find("db maintenance").items.map(row=>row.id),["due"]);
 assert.deepEqual(find("never").items.map(row=>row.id),["never"]);
 assert.deepEqual(find("remote").items.map(row=>row.id),["expired","never"]);
 assert.deepEqual(find("2026-10-11").items.map(row=>row.id),["expired"]);
 for(const hidden of ["NEVER_SEARCH","INVISIBLE-QUERY","HIDDEN_API","[object Object]"]){
  const value=find(hidden);
  assert.deepEqual(value.items,[],hidden);
  assert.equal(value.scope,"loaded-only");
  assert.equal(value.error,null);
 }
 const selected=find("legacy");
 assert.equal(selected.items[0],selection[0]);
 assert.equal(selected.loadedCount,3);
});
test("G-20 unsafe/unbounded typed Policy filter is explicit error, no broadening to hidden fields",()=>{
 for(const bad of [null,undefined,{},[],1,"x".repeat(121),"Name\u202ePrivate","keyword\nsecret"]){
  const result=helper.filterObservedPolicySearch(rows,bad);
  assert.deepEqual(result.items,[],String(bad));
  assert.match(result.error,/invalid|search/i);
 }
 for(const source of [undefined,null,{},{"items":rows}, "wrong"]){
  const r=helper.filterObservedPolicySearch(source,"");
  assert.deepEqual(r.items,[]);
  assert.ok(r.error);
 }
 const valid=helper.filterObservedPolicySearch(rows,"EXPIRE");
 assert.deepEqual(valid.items.map(x=>x.id),["expired"]);
 assert.deepEqual(helper.filterObservedPolicySearch(rows,"expir").items.map(x=>x.id),["expired","later"]);
});
test("G-20 Web policy UX preserves scope/plane/state, displays as-of and native expiry filters without Core modification",()=>{
 const src=readFileSync(join(root,"src","main.tsx"),"utf8");
 const policy=src.split("function PolicyWorkspace(",2)[1]?.split("function ServiceSshConnectHint(",1)[0]||"";
 assert.match(src,/import \{observedPolicyExpiryState,filterObservedPoliciesByExpiry,observedPolicyExpiryCounts,filterObservedPolicySearch/);
 assert.match(policy,/const \[expiryFilter,setExpiryFilter\]=useState/);
 assert.match(policy,/const \[expiryObservedAt,setExpiryObservedAt\]=useState\(\(\)=>Date\.now\(\)\)/);
 assert.match(policy,/filterObservedPolicySearch\(/);
 assert.match(policy,/filterObservedPoliciesByStatus/);
 assert.match(policy,/filterObservedPoliciesByExpiry/);
 assert.match(policy,/observedPolicyExpiryCounts/);
 assert.match(policy,/role="group" aria-label="Filter loaded policy expiry"/);
 assert.match(policy,/aria-pressed=\{expiryFilter===choice\}/);
 assert.match(policy,/onClick=\{\(\)=>setExpiryFilter\(choice\)\}/);
 assert.match(policy,/Re-evaluate local time/);
 assert.match(policy,/Expired/);
 assert.match(policy,/Due within 24h/);
 assert.match(policy,/Never/);
 assert.match(policy,/UNKNOWN/);
 assert.match(policy,/Loaded policy expiry only.*not.*live access/s);
 assert.match(policy,/Policy search not applied/);
 assert.match(policy,/policyExpiryLabel\(item\)/);
 assert.match(policy,/Partial|incomplete|Core policy list may be incomplete/);
 assert.doesNotMatch(policy,/Object\.values\(item\)\.some/);
 const helperSrc=readFileSync(join(root,"src","uxb-policy-expiry.ts"),"utf8");
 assert.doesNotMatch(helperSrc,/\b(?:fetch|api|sessionStorage|localStorage|eval)\s*\(/);
});

test("G-20 policy detail uses only explicit canonical Core selectors and never dumps arbitrary attributes",()=>{
 const actual=helper.observedPolicyDetailFields({
  id:"p-1",name:"Temporary policy",plane:"remote",position:1,
  action:"ALLOW",enabled:1,expires_at:"2026-10-13T00:00:00Z",
  row_version:4,description:"Approved configuration",
  api_key:"SECRET_KEY",password:"SECRET_PW",_internal:"SECRET_HIDDEN",
  metadata:{jwt:"SECRET_JWT"}
 });
 assert.deepEqual(actual,[
  {label:"Policy ID",value:"p-1"},
  {label:"Name",value:"Temporary policy"},
  {label:"Plane",value:"remote"},
  {label:"Action",value:"ALLOW"},
  {label:"Position",value:"1"},
  {label:"State",value:"Enabled"},
  {label:"Expires",value:"2026-10-13T00:00:00Z"},
  {label:"Description",value:"Approved configuration"},
  {label:"Revision",value:"4"}
 ]);
 assert.doesNotMatch(JSON.stringify(actual),/SECRET_|metadata|password|api_key/);
 assert.equal(helper.observedPolicyDetailFields({id:"invalid\nkey",token:"SECRET"}).length,0);
 const ai=helper.observedPolicyDetailFields({id:"a-1",plane:"ai",name:"AI config",
  enabled:null,expires_at:null,source_identity_id:"bot-a",
  destination_ref_kind:"permission-object",destination_ref_id:"repo-1",
  permission_ref_kind:"permission-group",permission_ref_id:"read",
  internal_token:"PRIVATE"});
 assert.deepEqual(ai.slice(-5),[
  {label:"Source identity",value:"bot-a"},
  {label:"Destination kind",value:"permission-object"},
  {label:"Destination ID",value:"repo-1"},
  {label:"Permission kind",value:"permission-group"},
  {label:"Permission ID",value:"read"}
 ]);
 assert.ok(ai.some(field=>field.label==="State"&&field.value==="UNKNOWN"));
 assert.ok(ai.some(field=>field.label==="Expires"&&field.value==="Never"));
 const src=readFileSync(join(root,"src","main.tsx"),"utf8");
 const policy=src.split("function PolicyWorkspace(",2)[1]?.split("function ServiceSshConnectHint(",1)[0]||"";
 assert.match(policy,/observedPolicyDetailFields\(selected\)\.map/);
 assert.doesNotMatch(policy,/Object\.entries\(selected\)/);
});
