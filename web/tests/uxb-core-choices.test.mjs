// DRL3-7B source/SSR UX contract only; never a browser or real Agent E2E.
import assert from "node:assert/strict";
import {before,after,test} from "node:test";
import {mkdtempSync,rmSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
import {build} from "esbuild";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";

const root=dirname(dirname(fileURLToPath(import.meta.url)));
let scratch,choices;
before(async()=>{
  scratch=mkdtempSync(join(root,"node_modules",".uxb-choices-"));
  const outfile=join(scratch,"choices.mjs");
  await build({entryPoints:[join(root,"src","uxb-core-choices.tsx")],outfile,
    bundle:true,platform:"node",format:"esm",jsx:"automatic",
    external:["react","react/jsx-runtime"],logLevel:"silent"});
  choices=await import(pathToFileURL(outfile).href);
});
after(()=>{if(scratch)rmSync(scratch,{recursive:true,force:true})});

const fixture={resources:{
  "network-object":{items:[{id:"net1",name:"office"},{id:"net2",name:"private-target"}]},
  "network-group":{items:[{id:"ng1",name:"staff-networks"}]},
  "service-object":{items:[{id:"svc1",name:"ssh-tcp22"}]},
  "service-group":{items:[]},
  "permission-object":{items:[{name:"read-status"}]},
  "permission-group":{items:[{name:"audit-readers"}]},
  "ai-identity":{items:[{id:"actor",name:"ci-reader"}]},
}};

test("Core suggestions keep Remote/Internet/AI public nouns distinct",()=>{
 const get=(plane,field)=>choices.coreSelectorOptions(fixture,plane,field).names;
 assert.deepEqual(get("remote","source"),["office","private-target","staff-networks"]);
 assert.deepEqual(get("internet","destination"),["office","private-target","staff-networks"]);
 assert.deepEqual(get("remote","selector"),["ssh-tcp22"]);
 assert.deepEqual(get("ai","source"),["ci-reader"]);
 assert.deepEqual(get("ai","selector"),["audit-readers","read-status"]);
 assert.ok(!get("ai","selector").includes("ssh-tcp22"));
 assert.ok(!get("remote","selector").includes("read-status"));
});
test("Unknown, empty and paginated Core choices never invent availability",()=>{
 assert.deepEqual(choices.coreSelectorOptions(null,"remote","source"),
   {status:"unknown",names:[],truncated:false});
 assert.equal(choices.coreSelectorOptions({resources:{}},"ai","source").status,"unknown");
 assert.equal(choices.coreSelectorOptions({resources:{"ai-identity":{items:[]}}},"ai","source").status,"empty");
 const limited={resources:{...fixture.resources,"service-object":{items:[{name:"ssh-tcp22"}],next_cursor:"opaque-cursor"}}};
 const got=choices.coreSelectorOptions(limited,"remote","selector");
 assert.equal(got.status,"available");
 assert.equal(got.truncated,true);
 assert.deepEqual(got.names,["ssh-tcp22"]);
});
test("Operator chooses a Core selector deliberately, never an implicit allow",()=>{
 const render=(catalog,plane,field,value)=>renderToStaticMarkup(React.createElement(
   choices.CoreChoiceField,{catalog,plane,field,value,onChoose:()=>{}}
 ));
 const empty=render(null,"remote","source","");
 assert.match(empty,/Core inventory UNKNOWN/);
 assert.match(empty,/disabled=""/);
 assert.match(empty,/not an approval|may still be entered manually/);
 const ai=render(fixture,"ai","selector","");
 assert.match(ai,/Permission Object \/ Group/);
 assert.match(ai,/Choose existing/);
 assert.match(ai,/read-status/);
 assert.doesNotMatch(ai,/ssh-tcp22/);
 assert.match(ai,/<option value="" selected="">Select an existing name/);
 const selected=render(fixture,"remote","selector","ssh-tcp22");
 assert.match(selected,/<option value="ssh-tcp22" selected=""/);
 const locked=renderToStaticMarkup(React.createElement(choices.CoreChoiceField,{
  catalog:fixture,plane:"remote",field:"selector",value:"ssh-tcp22",disabled:true,onChoose:()=>{}
 }));
 assert.match(locked,/<select[^>]*disabled=""/);
});
