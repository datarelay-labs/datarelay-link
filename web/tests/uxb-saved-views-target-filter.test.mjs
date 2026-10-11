// G-32: original loaded-only private Saved Views resource-type facet.
// Static/SSR tests only; not authenticated browser or real actor E2E.
import assert from "node:assert/strict";
import {test} from "node:test";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const tmp=mkdtempSync(join(root,"node_modules",".drlink-g32-saved-facet-"));
let view;
try{
 const outfile=join(tmp,"views.mjs");
 await build({entryPoints:[join(root,"src","uxb-saved-views.tsx")],outfile,
  bundle:true,platform:"node",format:"esm",jsx:"automatic",
  external:["react","react/jsx-runtime"],logLevel:"silent"});
 view=await import(pathToFileURL(outfile).href);
}finally{rmSync(tmp,{recursive:true,force:true})}
const rows=[
 {id:"host-1",name:"Host",payload:{resource_type:"managed-host",filter:"offline"}},
 {id:"svc-1",name:"Service",payload:{resource_type:"remote-service",filter:"ssh"}},
 {id:"policy-1",name:"Policy",payload:{resource_type:"access-rule",filter:"provider-4",plane:"ai"}},
 {id:"old-1",name:"Legacy",payload:{filter:"offline"}},
 {id:"other-1",name:"Opaque",payload:{resource_type:"access-rule",filter:"provider-4",plane:"ai",api_key:"HIDDEN"}},
];
const ids=(choice,input=rows)=>view.filterLoadedSavedViewsByType(input,choice).map(x=>x.id);
const html=(items)=>renderToStaticMarkup(React.createElement(view.SavedViewsWorkspace,{
 data:{items},api:()=>{throw Error("SSR must not call API")},
 refresh:()=>{},onNavigate:()=>{}
}));

test("G-32 filters only currently loaded private saved view resource types through strict existing projector",()=>{
 assert.deepEqual(ids("all"),rows.map(x=>x.id));
 assert.deepEqual(ids("hosts"),["host-1"]);
 assert.deepEqual(ids("services"),["svc-1"]);
 assert.deepEqual(ids("policies"),["policy-1"]);
 assert.deepEqual(ids("unsupported"),["old-1","other-1"],"unknown legacy remains discoverable");
 const subset=[rows[1],rows[2]];
 assert.deepEqual(ids("policies",subset),["policy-1"],"never fetches or infers other Core rows");
 assert.equal(view.filterLoadedSavedViewsByType(rows,"hosts")[0],rows[0]);
 assert.notEqual(view.filterLoadedSavedViewsByType(rows,"all"),rows);
 assert.deepEqual(rows.map(x=>x.id),["host-1","svc-1","policy-1","old-1","other-1"]);
});

test("G-32 unsupported/legacy never leaks payloads or promotes unknown to a trusted Policy",()=>{
 const input=[...rows,{id:"bad",name:"Bad",payload:{resource_type:"access-rule",plane:"ai",
  filter:"secret\u202e",private_key:"DONT_READ"}}];
 const out=view.filterLoadedSavedViewsByType(input,"unsupported");
 assert.deepEqual(out.map(x=>x.id),["old-1","other-1","bad"]);
 assert.deepEqual(view.filterLoadedSavedViewsByType(input,"policies").map(x=>x.id),["policy-1"]);
 assert.doesNotMatch(out.map(x=>x.name).join(" "),/DONT_READ|HIDDEN/);
});

test("G-32 invalid selector/shape and >100 unverified list fail closed",()=>{
 for(const mode of ["","policy","Hosts","__proto__",null,2,{},[],true]){
  assert.equal(view.isSavedViewTargetFilter(mode),false);
  assert.deepEqual(view.filterLoadedSavedViewsByType(rows,mode),[]);
 }
 for(const mode of ["all","hosts","services","policies","unsupported"])
  assert.equal(view.isSavedViewTargetFilter(mode),true);
 for(const invalid of [undefined,null,{items:rows},"text",[null],[[1]],[true],Array.from({length:101},()=>({}))])
  assert.deepEqual(view.filterLoadedSavedViewsByType(invalid,"all"),[]);
});

test("G-32 native target facet filters loaded names BEFORE local sort; collision/100-row Core gates unaffected",()=>{
 const src=readFileSync(join(root,"src","uxb-saved-views.tsx"),"utf8");
 assert.match(src,/const \[targetFacet,setTargetFacet\]=useState<SavedViewTargetFilter>\("all"\)/);
 assert.match(src,/const typedVisibleRows=filterLoadedSavedViewsByType\(visibleRows\.items,targetFacet\)/);
 assert.match(src,/const sortedVisibleRows=sortLoadedSavedViews\(typedVisibleRows,listSort\)/);
 assert.match(src,/const duplicate=conflictingSavedViewName\(rows,name\)/);
 assert.match(src,/const incompleteNames=rows\.length>=100/);
 assert.match(src,/aria-label="Filter loaded saved view resource type"/);
 assert.match(src,/onChange=\{e=>setTargetFacet\(isSavedViewTargetFilter\(e.target.value\)\?e.target.value:"all"\)\}/);
 for(const [value,label] of [["all","All types"],["hosts","Hosts"],["services","Services"],["policies","Policies"],["unsupported","Unsupported"]])
  assert.ok(src.includes('<option value="'+value+'">'+label+'</option>'),label);
 assert.match(src,/Legacy\/unsupported views are listed separately/);
 assert.match(src,/rows\.length\?sortedVisibleRows\.length/);
 assert.match(src,/No matching loaded saved filters/);
 assert.match(src,/No saved views yet/);
 assert.doesNotMatch(src,/\/api\/v1\/saved-views\?type=/);
 const rendered=html(rows);
 assert.match(rendered,/Filter loaded saved view resource type/);
 assert.match(rendered,/Unsupported/);
 assert.match(rendered,/Host/);
 assert.match(rendered,/Policy/);
 assert.match(rendered,/Legacy/);
 assert.doesNotMatch(rendered,/DONT_READ|HIDDEN|api_key/);
});
