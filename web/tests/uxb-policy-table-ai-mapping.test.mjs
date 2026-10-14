// G-26: configured AI Source→Destination→Permission references in default Policy Table.
// Tests are source/SSR qualification, NOT authenticated browser or policy approval.
import assert from "node:assert/strict";
import {test} from "node:test";
import {build} from "esbuild";
import {createElement} from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const temp=mkdtempSync(join(root,"node_modules",".drlink-g26-ai-table-"));
let mapping;
try{
 const path=join(temp,"ai.mjs");
 await build({entryPoints:[join(root,"src","uxb-policy-table-ai-mapping.tsx")],
  outfile:path,platform:"node",format:"esm",bundle:true,external:["react","react-dom"],logLevel:"silent"});
 mapping=await import(pathToFileURL(path).href);
}finally{rmSync(temp,{recursive:true,force:true})}
const AS_OF=Date.parse("2026-10-12T00:00:00Z");
const ai={id:"policy-ai-2",plane:"ai",name:"AI staging",enabled:true,
 source_identity_id:"robot-3",destination_ref_kind:"provider",destination_ref_id:"provider-4",
 permission_ref_kind:"model",permission_ref_id:"model-7",
 expires_at:null,secret_key:"SHOULD_NEVER_SHOW",metadata:{token:"HIDDEN"}};
const html=(item)=>renderToStaticMarkup(createElement(mapping.AiPolicyMappingCell,{row:item,asOf:AS_OF}));

test("G-26 verified Core AI policy table mapping is exactly Source, Destination, Permission from G25 projector",()=>{
 assert.deepEqual(mapping.observedAiPolicyTableMapping(ai,AS_OF),{
  source:"robot-3",destination:"provider · provider-4",permission:"model · model-7"
 });
 const rendered=html(ai);
 assert.match(rendered,/AI policy Core references/);
 for(const text of ["Source identity","robot-3","Destination reference","provider · provider-4",
  "Permission reference","model · model-7"]) assert.ok(rendered.includes(text),text);
 assert.doesNotMatch(rendered,/SHOULD_NEVER_SHOW|HIDDEN|secret_key|metadata|approved|allowed/);
});

test("G-26 malformed/missing Core target parts are UNKNOWN, never raw nested data or an invented grant",()=>{
 for(const changes of [
  {destination_ref_kind:undefined},{destination_ref_id:"bad\u202e"},
  {destination_ref_id:{credential:"SECRET"}},{permission_ref_kind:null},
  {permission_ref_id:"bad\nvalue"},{source_identity_id:{secret:"TOKEN"}}
 ]){
  const projection=mapping.observedAiPolicyTableMapping({...ai,...changes},AS_OF);
  assert.ok(projection);
  assert.ok(Object.values(projection).includes("UNKNOWN"),JSON.stringify(changes));
  assert.doesNotMatch(JSON.stringify(projection),/SECRET|TOKEN|credential|\u202e/);
  assert.doesNotMatch(html({...ai,...changes}),/SECRET|TOKEN|credential/);
 }
 for(const row of [{...ai,id:"bad\nunsafe"}, {...ai,plane:"ai",id:null}]){
  assert.equal(mapping.observedAiPolicyTableMapping(row,AS_OF),null);
  assert.match(html(row),/UNKNOWN/);
 }
});

test("G-26 Remote and Internet never inherit AI mappings or imply no actual policy",()=>{
 for(const plane of ["remote","internet"]){
  const row={...ai,plane,action:"ALLOW"};
  assert.equal(mapping.observedAiPolicyTableMapping(row,AS_OF),null);
  assert.match(html(row),/Not provided by Core/);
  assert.doesNotMatch(html(row),/provider-4|robot-3|model-7/);
 }
 assert.match(html(null),/Not provided by Core/);
 assert.match(html("unsafe"),/Not provided by Core/);
});

test("G-26 source wiring adds exactly one read-only Table column; Card, Audit, Core and drawer remain intact",()=>{
 const src=readFileSync(join(root,"src","main.tsx"),"utf8");
 const policy=src.split("function PolicyWorkspace(",2)[1]?.split("function ServiceUseActions(",1)[0]||"";
 assert.match(src,/import \{AiPolicyMappingCell\} from "\.\/uxb-policy-table-ai-mapping"/);
 assert.match(policy,/<th>AI mapping<\/th>/);
 assert.match(policy,/<AiPolicyMappingCell row=\{item\} asOf=\{expiryObservedAt\}\/>/);
 assert.match(policy,/policyView==="cards"\?<div className="dr-resource-cards"/);
 assert.match(policy,/observedPolicyCardSummary\(item,expiryObservedAt\)/);
 assert.match(policy,/Review related Audit/);
 assert.match(policy,/Core policy list may be incomplete/);
 assert.match(policy,/Load more/);
 assert.match(policy,/Recent activity/);
 const helper=readFileSync(join(root,"src","uxb-policy-table-ai-mapping.tsx"),"utf8");
 assert.match(helper,/import \{observedPolicyCardSummary\} from "\.\/uxb-policy-cards"/);
 assert.doesNotMatch(helper,/\b(?:fetch|api|localStorage|sessionStorage|eval|onNavigate)\s*\(/);
 const css=readFileSync(join(root,"dist","styles.css"),"utf8");
 assert.match(css,/\.dr-table-scroll\{overflow:auto\}/);
 assert.match(css,/\.dr-policy-ai-mapping\{[^}]*overflow-wrap:anywhere/);
});
