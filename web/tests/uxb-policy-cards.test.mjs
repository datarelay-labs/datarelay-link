// G-21 PolicyWorkspace optional Table/Cards, independent Core-loaded projection.
// Source-only UI contract; authenticated browser/role/device E2E remains separate.
import assert from "node:assert/strict";
import {test} from "node:test";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const temp=mkdtempSync(join(root,"node_modules",".drlink-g21-policy-card-"));
let view;
try{
 const path=join(temp,"card.mjs");
 await build({entryPoints:[join(root,"src","uxb-policy-cards.ts")],
   outfile:path,platform:"node",format:"esm",bundle:true,logLevel:"silent"});
 view=await import(pathToFileURL(path).href);
}finally{rmSync(temp,{recursive:true,force:true})}
const NOW=Date.parse("2026-10-12T00:00:00Z");
test("G-21 Remote/Internet policy card is one safe Core rule with canonical state and expiration",()=>{
 const remote={id:"policy-7",name:"SSH operations",plane:"remote",action:"ALLOW",
   enabled:1,expires_at:"2026-10-12T04:00:00Z",row_version:7,
   description:"Ops",password:"SECRET",metadata:{key:"HIDDEN"}};
 assert.deepEqual(view.observedPolicyCardSummary(remote,NOW),{
  id:"policy-7",title:"SSH operations",plane:"Remote",
  status:"Enabled",expiryStatus:"Due within 24h",expiryAt:"2026-10-12T04:00:00Z",
  facts:[{label:"Action",value:"ALLOW"},{label:"Expires",value:"2026-10-12T04:00:00Z"}]
 });
 assert.doesNotMatch(JSON.stringify(view.observedPolicyCardSummary(remote,NOW)),/SECRET|HIDDEN|metadata/);
 const internet={...remote,id:"policy-int",plane:"internet",enabled:0,expires_at:null};
 assert.deepEqual(view.observedPolicyCardSummary(internet,NOW),{
   id:"policy-int",title:"SSH operations",plane:"Internet",
   status:"Disabled",expiryStatus:"Never",expiryAt:"Never",
   facts:[{label:"Action",value:"ALLOW"},{label:"Expires",value:"Never"}]
 });
});
test("G-21 AI policy card uses exact public Core AI identity, never guesses allow/deny",()=>{
 const ai={id:"policy-ai",name:"AI staging",plane:"ai",
  source_identity_id:"bot-3",enabled:true,expires_at:null,
  destination_ref_kind:"permission-group",destination_ref_id:"repo-1",
  api_key:"PRIVATE_KEY",authentication:"SECRET"};
 const info=view.observedPolicyCardSummary(ai,NOW);
 assert.deepEqual(info,{
  id:"policy-ai",title:"AI staging",plane:"AI",
  status:"Enabled",expiryStatus:"Never",expiryAt:"Never",
  facts:[{label:"Source identity",value:"bot-3"},{label:"Expires",value:"Never"}]
 });
 assert.doesNotMatch(JSON.stringify(info),/PRIVATE_KEY|SECRET|authentication/);
});
test("G-21 malformed/missing time/type/secret identity stays UNKNOWN or no card, never grants",()=>{
 for(const bad of [null,undefined,{},[],true,"policy",{id:"bad\nunsafe",plane:"remote"},
   {id:"policy-2",plane:"NETWORK"},{id:"policy-3",plane:{"secret":"SECRET"}}]){
  assert.equal(view.observedPolicyCardSummary(bad,NOW),null);
 }
 const result=view.observedPolicyCardSummary({id:"policy-4",plane:"remote",
   name:{secret:"DONT_SHOW"},action:{hidden:"DONT_SHOW"},enabled:"true",
   expires_at:"bad",private_key:"DO_NOT_COPY"},NOW);
 assert.deepEqual(result,{
   id:"policy-4",title:"policy-4",plane:"Remote",status:"UNKNOWN",
   expiryStatus:"UNKNOWN",expiryAt:"UNKNOWN",
   facts:[{label:"Action",value:"UNKNOWN"},{label:"Expires",value:"UNKNOWN"}]
 });
 assert.doesNotMatch(JSON.stringify(result),/DO_NOT_COPY|DONT_SHOW/);
});
test("G-21 native Policy Table/Cards control preserves loaded-only Core rules and exact existing detail drawer",()=>{
 const src=readFileSync(join(root,"src","main.tsx"),"utf8");
 const block=src.split("function PolicyWorkspace(",2)[1]?.split("function ServiceSshConnectHint(",1)[0]||"";
 assert.match(src,/import \{observedPolicyCardSummary\} from "\.\/uxb-policy-cards"/);
 assert.match(block,/const \[policyView,setPolicyView\]=useState<"table"\|"cards">\("table"\)/);
 assert.match(block,/role="group" aria-label="Policy inventory view"/);
 assert.match(block,/aria-pressed=\{policyView==="table"\}/);
 assert.match(block,/aria-pressed=\{policyView==="cards"\}/);
 assert.match(block,/onClick=\{\(\)=>setPolicyView\("table"\)\}/);
 assert.match(block,/onClick=\{\(\)=>setPolicyView\("cards"\)\}/);
 assert.match(block,/policyView==="cards"\?<div className="dr-resource-cards"/);
 assert.match(block,/observedPolicyCardSummary\(item,expiryObservedAt\)/);
 assert.match(block,/className="dr-resource-card"/);
 assert.match(block,/onClick=\{\(\)=>setSelected\(item\)\}/);
 assert.match(block,/role="list"/);
 assert.match(block,/role="listitem"/);
 assert.match(block,/policyExpiryLabel\(item\)/);
 assert.match(block,/dr-table-scroll/);
 assert.match(block,/filterObservedPoliciesByExpiry/);
 assert.match(block,/Core policy list may be incomplete/);
 assert.match(block,/Load more/);
 assert.match(block,/Policy detail/);
 const helper=readFileSync(join(root,"src","uxb-policy-cards.ts"),"utf8");
 assert.doesNotMatch(helper,/\b(?:api|fetch|localStorage|sessionStorage|eval)\s*\(/);
 const css=readFileSync(join(root,"dist","styles.css"),"utf8");
 assert.match(css,/\.dr-resource-cards\{[^}]*grid-template-columns/);
 assert.match(css,/@media\(max-width:560px\)\{\.dr-resource-cards\{/);
 assert.match(css,/\.dr-resource-card:focus-visible\{[^}]*outline:/);
});
