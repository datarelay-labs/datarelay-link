// M1-B G-24: independently implemented Policy display chips and local reset only.
// Source unit evidence, NOT authenticated browser/real Core or agent E2E.
import assert from "node:assert/strict";
import {test} from "node:test";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,"node_modules",".drlink-g24-policy-chips-"));
let chip;
try{
 const output=join(scratch,"chips.mjs");
 await build({entryPoints:[join(root,"src","uxb-policy-filter-chips.ts")],
   outfile:output,bundle:true,platform:"node",format:"esm",logLevel:"silent"});
 chip=await import(pathToFileURL(output).href);
}finally{rmSync(scratch,{recursive:true,force:true})}
const active=(plane="all",search="",state="all",expiry="all",sort="core")=>
 chip.activePolicyFilterChips(plane,search,state,expiry,sort);

test("G-24 active Policy UI choices have five fixed facet IDs with finite labels",()=>{
 assert.deepEqual(active(),[]);
 assert.deepEqual(active("remote","policy-6","enabled","due24h","name_asc"),[
  {id:"plane",label:"Plane",value:"Remote"},
  {id:"search",label:"Search",value:"Active"},
  {id:"status",label:"State",value:"Enabled"},
  {id:"expiry",label:"Expiry",value:"Due within 24h"},
  {id:"sort",label:"Sort",value:"Policy name A–Z"}
 ]);
 assert.deepEqual(active("ai","  ","unknown","never","name_desc"),[
  {id:"plane",label:"Plane",value:"AI"},
  {id:"status",label:"State",value:"UNKNOWN"},
  {id:"expiry",label:"Expiry",value:"Never"},
  {id:"sort",label:"Sort",value:"Policy name Z–A"}
 ]);
 assert.deepEqual(active("internet","","disabled","expired","core"),[
  {id:"plane",label:"Plane",value:"Internet"},
  {id:"status",label:"State",value:"Disabled"},
  {id:"expiry",label:"Expiry",value:"Expired"}
 ]);
});

test("G-24 typed search and malformed/secret-bearing selector values are never shown in chip text",()=>{
 const out=active("admin:TOP_SECRET","token:SECRET_VALUE\u202e","__proto__","../private","user:APIKEY");
 assert.deepEqual(out,[
  {id:"plane",label:"Plane",value:"UNKNOWN"},
  {id:"search",label:"Search",value:"Active"},
  {id:"status",label:"State",value:"UNKNOWN"},
  {id:"expiry",label:"Expiry",value:"UNKNOWN"},
  {id:"sort",label:"Sort",value:"UNKNOWN"}
 ]);
 assert.doesNotMatch(JSON.stringify(out),/TOP_SECRET|SECRET_VALUE|__proto__|private|APIKEY/);
 assert.deepEqual(active(null,null,null,null,null).map(x=>x.id),
 ["plane","search","status","expiry","sort"]);
 assert.equal(active("remote","search","enabled","later","name_asc").length,5);
});

test("G-24 Policy filter chips wiring removes exactly one local selector per native action",()=>{
 const src=readFileSync(join(root,"src","main.tsx"),"utf8");
 const policy=src.split("function PolicyWorkspace(",2)[1]?.split("function ServiceSshConnectHint(",1)[0]||"";
 assert.match(src,/import \{activePolicyFilterChips,type PolicyFilterChipId\} from "\.\/uxb-policy-filter-chips"/);
 assert.match(policy,/const policyFilterChips=activePolicyFilterChips\(plane,filter,statusFilter,expiryFilter,policySort\)/);
 const handler=policy.match(/function removePolicyFilterChip\(id:PolicyFilterChipId\)\{([\s\S]*?)\n  \}/)?.[1]||"";
 for(const [id,setter,val] of [
  ["plane","setPlane",'"all"'],["search","setFilter",'""'],
  ["status","setStatusFilter",'"all"'],["expiry","setExpiryFilter",'"all"'],
  ["sort","setPolicySort",'"core"']
 ]){
  assert.ok(handler.includes('id==="'+id+'"'),"removes "+id);
  assert.ok(handler.includes(setter+"("+val+")"),"only setter "+setter);
 }
 assert.doesNotMatch(handler,/\b(?:api|fetch|loadMore|setAdditional|setSelected|onNavigate|setNextByPlane)\s*\(/);
 assert.match(policy,/role="group" aria-label="Active Policy display filters"/);
 assert.match(policy,/policyFilterChips\.map\(entry=><button/);
 assert.match(policy,/aria-label=\{"Remove "\+entry\.label\+" filter"\}/);
 assert.match(policy,/onClick=\{\(\)=>removePolicyFilterChip\(entry\.id\)\}/);
 assert.match(policy,/type="button"/);
 assert.match(policy,/Search text is never displayed in these chips/);
});

test("G-24 one-click Clear affects exactly five local selectors, not view/selection/authority",()=>{
 const src=readFileSync(join(root,"src","main.tsx"),"utf8");
 const policy=src.split("function PolicyWorkspace(",2)[1]?.split("function ServiceSshConnectHint(",1)[0]||"";
 const handler=policy.match(/function clearPolicyDisplayFilters\(\)\{([\s\S]*?)\n  \}/)?.[1]||"";
 assert.ok(handler);
 for(const state of ['setPlane("all")','setFilter("")','setStatusFilter("all")','setExpiryFilter("all")','setPolicySort("core")'])
  assert.ok(handler.includes(state),state);
 assert.doesNotMatch(handler,/\b(?:api|fetch|loadMore|setAdditional|setSelected|onNavigate|setNextByPlane|setPolicyView|setExpiryObservedAt|setPageError)\s*\(/);
 assert.match(policy,/onClick=\{clearPolicyDisplayFilters\}>Clear Policy display filters/);
 assert.match(policy,/Core rule evaluation\/precedence and Saved Views remain unchanged/);
 assert.match(policy,/Core policy list may be incomplete/);
 assert.match(policy,/Load more/);
 const helper=readFileSync(join(root,"src","uxb-policy-filter-chips.ts"),"utf8");
 assert.doesNotMatch(helper,/\b(?:fetch|api|localStorage|sessionStorage|eval)\s*\(/);
 const css=readFileSync(join(root,"dist","styles.css"),"utf8");
 assert.match(css,/\.dr-form-actions\{[^}]*flex-wrap:wrap/);
});
