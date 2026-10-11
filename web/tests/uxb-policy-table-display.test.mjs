// M1-B G-29: original, fixed-field Policy Table visual projection.
// No NetBird AGPL reuse, no Core mutation, no protected drawer edit.
import assert from "node:assert/strict";
import {test} from "node:test";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,"node_modules",".drlink-g29-policy-table-"));
let projector;
try{
 const path=join(scratch,"display.mjs");
 await build({entryPoints:[join(root,"src","uxb-policy-table-display.ts")],
  outfile:path,platform:"node",format:"esm",bundle:true,logLevel:"silent"});
 projector=await import(pathToFileURL(path).href);
}finally{rmSync(scratch,{recursive:true,force:true})}

test("G-29 safe table identity uses only already verified public Core text",()=>{
 const row={id:"pol-5",name:"Staging access",description:"Engineering review",
  plane:"remote",action:"ALLOW",metadata:{secret:"UNTOUCHED"}};
 assert.deepEqual(projector.observedPolicyTableDisplayCells(row),{
  id:"pol-5",name:"Staging access",action:"ALLOW",description:"Engineering review"
 });
 assert.deepEqual(projector.observedPolicyTableDisplayCells({...row,name:null}),{
  id:"pol-5",name:"pol-5",action:"ALLOW",description:"Engineering review"
 });
});

test("G-29 malformed, unknown or hidden Core shapes do not stringify into Table",()=>{
 for(const row of [undefined,null,"x",[],{}, {id:"bad\nunsafe",name:"Public"}]){
  assert.deepEqual(projector.observedPolicyTableDisplayCells(row),{
   id:"UNKNOWN",name:"UNKNOWN",action:"UNKNOWN",description:"UNKNOWN"
  });
 }
 const observed={id:"pol-6",name:{password:"PRIVATE_PASSWORD"},
  action:{api_key:"HIDDEN_TOKEN"},description:"A\u202eprivate",
  credential:"PRIVATE_CREDENTIAL",nested:{secret:"HIDDEN_SECRET"}};
 const facts=projector.observedPolicyTableDisplayCells(observed);
 assert.deepEqual(facts,{id:"pol-6",name:"pol-6",action:"UNKNOWN",description:"UNKNOWN"});
 assert.doesNotMatch(JSON.stringify(facts),/PRIVATE_|HIDDEN_|\[object Object\]/);
});

test("G-29 oversize, controls and bidi fields are UNKNOWN, not dropped Core rows",()=>{
 const row={id:"public-id",name:"Visible",action:"ALLOW",description:"Normal"};
 assert.equal(projector.observedPolicyTableDisplayCells({...row,name:"x".repeat(161)}).name,"public-id");
 assert.equal(projector.observedPolicyTableDisplayCells({...row,action:"\u202eALLOW"}).action,"UNKNOWN");
 assert.equal(projector.observedPolicyTableDisplayCells({...row,description:"x".repeat(241)}).description,"UNKNOWN");
 assert.equal(projector.observedPolicyTableDisplayCells({...row,description:"\nsecret"}).description,"UNKNOWN");
 assert.deepEqual(projector.observedPolicyTableDisplayCells(row).id,"public-id");
});

test("G-29 default Table uses safe Core projection, retaining Card/Audit/filters/drawer as they were",()=>{
 const main=readFileSync(join(root,"src","main.tsx"),"utf8");
 const policy=main.split("function PolicyWorkspace(",2)[1]?.split("function ServiceSshConnectHint(",1)[0]||"";
 assert.match(main,/import \{observedPolicyTableDisplayCells\} from "\.\/uxb-policy-table-display"/);
 assert.match(policy,/<strong>\{observedPolicyTableDisplayCells\(item\)\.name\}<\/strong>/);
 assert.match(policy,/<small>\{observedPolicyTableDisplayCells\(item\)\.id\}<\/small>/);
 assert.match(policy,/<td>\{observedPolicyTableDisplayCells\(item\)\.action\}<\/td>/);
 assert.match(policy,/<td>\{observedPolicyTableDisplayCells\(item\)\.description\}<\/td>/);
 assert.doesNotMatch(policy,/<td>\{item\.description\|\|"—"\}<\/td>/);
 assert.match(policy,/policyView==="cards"\?<div className="dr-resource-cards"/);
 assert.match(policy,/AiPolicyMappingCell row=\{item\}/);
 assert.match(policy,/Review related Audit/);
 assert.match(policy,/Recent activity/);
 assert.match(policy,/Core policy list may be incomplete/);
 const source=readFileSync(join(root,"src","uxb-policy-table-display.ts"),"utf8");
 assert.match(source,/observedPolicyDetailFields/);
 assert.doesNotMatch(source,/\b(?:fetch|api|localStorage|sessionStorage|eval|onNavigate)\s*\(/);
});
