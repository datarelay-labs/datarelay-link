// G-27: original loaded-only AI Core reference search. No NetBird AGPL code.
import assert from "node:assert/strict";
import {test} from "node:test";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const temp=mkdtempSync(join(root,"node_modules",".drlink-g27-ai-reference-search-"));
let project;
try{
 const output=join(temp,"search.mjs");
 await build({entryPoints:[join(root,"src","uxb-policy-expiry.ts")],
  outfile:output,bundle:true,platform:"node",format:"esm",logLevel:"silent"});
 project=await import(pathToFileURL(output).href);
}finally{rmSync(temp,{recursive:true,force:true})}
const ai={id:"ai-policy-1",name:"Staging AI rule",plane:"ai",enabled:1,expires_at:null,
 source_identity_id:"robot-3",destination_ref_kind:"provider",destination_ref_id:"provider-4",
 permission_ref_kind:"model",permission_ref_id:"model-7",row_version:1,
 api_key:"PRIVATE_APIKEY",metadata:{token:"NESTED_SECRET"}};
const ai2={...ai,id:"ai-policy-2",name:"Other AI rule",source_identity_id:"bot-9",
 destination_ref_kind:"gateway",destination_ref_id:"gateway-2",permission_ref_id:"model-9"};
const remote={id:"r-1",plane:"remote",name:"Remote SSH",enabled:1,
 source_identity_id:"robot-3",destination_ref_id:"provider-4",permission_ref_id:"model-7"};
const corrupt={...ai,id:"unsafe\nID",name:"Unverified",source_identity_id:"robot-3",destination_ref_id:"provider-4"};
const rows=[ai,ai2,remote,corrupt];
const ids=q=>project.filterObservedPolicySearch(rows,q).items.map(r=>r.id);

test("G-27 AI policy search can find an exact observed Source/Target/Permission reference only from loaded rows",()=>{
 assert.deepEqual(ids("robot-3"),["ai-policy-1"]);
 assert.deepEqual(ids("provider-4"),["ai-policy-1"]);
 assert.deepEqual(ids("model-7"),["ai-policy-1"]);
 assert.deepEqual(ids("PROVIDER"),["ai-policy-1"]);
 assert.deepEqual(ids("gateway-2"),["ai-policy-2"]);
 assert.deepEqual(ids("bot-9"),["ai-policy-2"]);
 assert.deepEqual(ids("Staging"),["ai-policy-1"],"existing visible-field name search remains");
 const single=project.filterObservedPolicySearch([ai2],"provider-4");
 assert.deepEqual(single.items,[],"never search unloaded Core policy rows");
 assert.equal(single.scope,"loaded-only");
 assert.equal(single.loadedCount,1);
 assert.equal(project.filterObservedPolicySearch(rows,"provider-4").items[0],ai);
});

test("G-27 search never matches hidden credentials, nested data or foreign-plane AI-shaped fields",()=>{
 for(const forbidden of ["PRIVATE_APIKEY","NESTED_SECRET","[object Object]","random-password"])
  assert.deepEqual(ids(forbidden),[],forbidden);
 const foreign=[{id:"rem-1",plane:"internet",name:"web-only",
  destination_ref_id:"provider-4",source_identity_id:"robot-3",password:"PRIVATE_APIKEY"}];
 assert.deepEqual(project.filterObservedPolicySearch(foreign,"robot-3").items,[]);
 assert.deepEqual(project.filterObservedPolicySearch(foreign,"provider-4").items,[]);
 const withHidden={...ai,id:"hidden-ai",destination_ref_id:{secret:"NESTED_SECRET"},
  permission_ref_id:"SECRET\u202e",source_identity_id:"SECRET\nVALUE"};
 for(const secret of ["NESTED_SECRET","SECRET\u202e","SECRET\nVALUE"])
  assert.deepEqual(project.filterObservedPolicySearch([withHidden],secret).items,[]);
});

test("G-27 original 120-char typed input and G20 state/expiry failures still fail closed",()=>{
 for(const bad of [null,undefined,{},[],1,"x".repeat(121),"model\u202e-7","bad\nword"]){
  const result=project.filterObservedPolicySearch(rows,bad);
  assert.deepEqual(result.items,[]);
  assert.match(result.error,/invalid/i);
 }
 assert.deepEqual(ids("remote"),["r-1"]);
 assert.deepEqual(ids("never"),["ai-policy-1","ai-policy-2","unsafe\nID"],
  "existing G20 expiry search still includes loaded policy rows regardless of reference ID validation");
});

test("G-27 Web label advertises verified AI IDs, no Core query or security semantics changed",()=>{
 const main=readFileSync(join(root,"src","main.tsx"),"utf8");
 const policy=main.split("function PolicyWorkspace(",2)[1]?.split("function ServiceUseActions(",1)[0]||"";
 assert.match(policy,/aria-label="Search visible policy fields"/);
 assert.match(policy,/Filter policies \(name, ID, AI refs\)/);
 assert.match(policy,/maxLength=\{120\}/);
 assert.match(policy,/filterObservedPolicySearch\(loadedPlanePolicies,filter\)/);
 assert.match(policy,/Core policy list may be incomplete/);
 assert.match(policy,/Load more/);
 assert.match(policy,/Review related Audit/);
 const source=readFileSync(join(root,"src","uxb-policy-expiry.ts"),"utf8");
 assert.match(source,/observedPolicyDetailFields\(row\)/);
 assert.match(source,/AI_SEARCH_FIELDS/);
 assert.doesNotMatch(source,/\b(?:fetch|api|localStorage|sessionStorage|eval)\s*\(/);
});
