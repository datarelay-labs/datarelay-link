// G-25: AI-specific Core-read-only destination and permission references in
// loaded Policy cards. No vendor code reuse, privilege, policy grant or E2E claim.
import assert from "node:assert/strict";
import {test} from "node:test";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const temp=mkdtempSync(join(root,"node_modules",".drlink-g25-policy-refs-"));
let card;
try{
 const path=join(temp,"card.mjs");
 await build({entryPoints:[join(root,"src","uxb-policy-cards.ts")],
   outfile:path,platform:"node",format:"esm",bundle:true,logLevel:"silent"});
 card=await import(pathToFileURL(path).href);
}finally{rmSync(temp,{recursive:true,force:true})}
const NOW=Date.parse("2026-10-12T00:00:00Z");
const ai={id:"p-ai",name:"Model staging",plane:"ai",source_identity_id:"bot-3",
 enabled:true,expires_at:null,destination_ref_kind:"provider",destination_ref_id:"provider-4",
 permission_ref_kind:"model",permission_ref_id:"model-7",credential:"PRIVATE_KEY"};

test("G-25 AI Policy card shows strict Core Source/Destination/Permission/Expiry without effect inference",()=>{
 const item=card.observedPolicyCardSummary(ai,NOW);
 assert.deepEqual(item?.facts,[
  {label:"Source identity",value:"bot-3"},
  {label:"Destination reference",value:"provider · provider-4"},
  {label:"Permission reference",value:"model · model-7"},
  {label:"Expires",value:"Never"}
 ]);
 assert.doesNotMatch(JSON.stringify(item),/PRIVATE_KEY|credential|effective access|approved/);
});

test("G-25 malformed/incomplete Core reference pair fails closed rather than making up association",()=>{
 const bad=[
  {...ai,destination_ref_kind:null},
  {...ai,destination_ref_id:{"token":"CREDENTIAL"}},
  {...ai,destination_ref_kind:"provider\u202e"},
  {...ai,destination_ref_id:"bad\nname"},
  {...ai,permission_ref_id:null},
  {...ai,permission_ref_kind:{private_key:"NEVER_RENDER"}},
  {...ai,permission_ref_id:"bad\u2069value"}
 ];
 for(const row of bad){
  const facts=card.observedPolicyCardSummary(row,NOW)?.facts;
  assert.ok(facts,"row must retain safe identity and UNKNOWN facts");
  assert.equal(facts.length,4);
  assert.equal(facts[1].value=== "UNKNOWN"||facts[2].value==="UNKNOWN",true);
  assert.doesNotMatch(JSON.stringify(facts),/CREDENTIAL|NEVER_RENDER|private_key|\u202e|\u2069/);
 }
});

test("G-25 Remote/Internet cards remain existing action + expiry facts, not NetBird mesh target model",()=>{
 for(const plane of ["remote","internet"]){
  const row={id:"policy-1",name:"Existing",plane,action:"ALLOW",enabled:1,expires_at:null,
   source_identity_id:"IGNORE",destination_ref_kind:"private",destination_ref_id:"DO_NOT_SHOW"};
  assert.deepEqual(card.observedPolicyCardSummary(row,NOW)?.facts,[
   {label:"Action",value:"ALLOW"},{label:"Expires",value:"Never"}
  ]);
 }
});

test("G-25 card facts use only existing fixed Core whitelist without new API, permissions or dashboard exposure",()=>{
 const source=readFileSync(join(root,"src","uxb-policy-cards.ts"),"utf8");
 assert.match(source,/get\("Destination kind"\)/);
 assert.match(source,/get\("Destination ID"\)/);
 assert.match(source,/get\("Permission kind"\)/);
 assert.match(source,/get\("Permission ID"\)/);
 assert.match(source,/label:"Destination reference"/);
 assert.match(source,/label:"Permission reference"/);
 assert.doesNotMatch(source,/\b(?:fetch|api|localStorage|sessionStorage|eval)\s*\(/);
 const main=readFileSync(join(root,"src","main.tsx"),"utf8");
 const policy=main.split("function PolicyWorkspace(",2)[1]?.split("function ServiceUseActions(",1)[0]||"";
 assert.match(policy,/observedPolicyCardSummary\(item,expiryObservedAt\)/);
 assert.match(policy,/info\.facts\.map\(field=>/);
 assert.match(policy,/Core policy list may be incomplete/);
 const css=readFileSync(join(root,"dist","styles.css"),"utf8");
 assert.match(css,/\.dr-resource-card-fact>strong\{[^}]*overflow-wrap:anywhere/);
});
