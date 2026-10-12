// G-34: active operator-private Saved Views filter chips; never echo raw search.
// Static projector/SSR/wiring test, not real authenticated Browser E2E.
import assert from "node:assert/strict";
import {test} from "node:test";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const temp=mkdtempSync(join(root,"node_modules",".drlink-g34-chips-"));
let view;
try{
 const out=join(temp,"views.mjs");
 await build({entryPoints:[join(root,"src","uxb-saved-views.tsx")],
  outfile:out,bundle:true,platform:"node",format:"esm",jsx:"automatic",
  external:["react","react/jsx-runtime"],logLevel:"silent"});
 view=await import(pathToFileURL(out).href);
}finally{rmSync(temp,{recursive:true,force:true})}
const chips=(query="",type="all",sort="core")=>view.activeSavedViewFilterChips(query,type,sort);
const rows=[{id:"v-1",name:"Private policy",payload:{resource_type:"access-rule",filter:"do-not-echo",plane:"ai"}}];

test("G-34 fixed active chips show only loaded Saved Views local filter dimensions",()=>{
 assert.deepEqual(chips(),[]);
 assert.deepEqual(chips("robot-3"),[{id:"search",label:"Name search",value:"Active"}]);
 assert.deepEqual(chips("","hosts"),[{id:"type",label:"Resource type",value:"Hosts"}]);
 assert.deepEqual(chips("","unsupported"),[{id:"type",label:"Resource type",value:"Unsupported"}]);
 assert.deepEqual(chips("","all","updated_asc"),[{id:"sort",label:"Order",value:"Oldest updated"}]);
 assert.deepEqual(chips("","all","updated_desc"),[{id:"sort",label:"Order",value:"Recently updated"}]);
 assert.deepEqual(chips("secret-token","policies","updated_desc"),[
  {id:"search",label:"Name search",value:"Active"},
  {id:"type",label:"Resource type",value:"Policies"},
  {id:"sort",label:"Order",value:"Recently updated"}
 ]);
 assert.ok(chips("secret-token","policies","updated_desc").length<=3);
});

test("G-34 chip projection never leaks private typed query or coerces bad Core-looking values",()=>{
 for(const q of ["password","alice@example.org","secret-id\u202e","PRIVATE_TOKEN", "secret\nvalue"]){
  const projected=chips(q,"all","core");
  assert.ok(!JSON.stringify(projected).includes(q),"typed secret must not appear in chip output");
  assert.deepEqual(projected,/\u202e|\n/.test(q)?[]:
    [{id:"search",label:"Name search",value:"Active"}]);
 }
 for(const invalid of [null,undefined,23,true,[],{},"x".repeat(81),"name\u202e","bad\ntext"]){
  assert.deepEqual(view.activeSavedViewFilterChips(invalid,"hosts","updated_desc"),[]);
 }
 for(const invalid of ["invalid","ALL","__proto__",null,{},[],17]){
  assert.deepEqual(view.activeSavedViewFilterChips("valid",invalid,"core"),[]);
 }
 for(const invalid of ["recent","updated_asc ","__proto__",null,{},[],17]){
  assert.deepEqual(view.activeSavedViewFilterChips("valid","all",invalid),[]);
 }
});

test("G-34 no chips on initial SSR default; underlying saved views still private and intact",()=>{
 const html=renderToStaticMarkup(React.createElement(view.SavedViewsWorkspace,{
  data:{items:rows},api:()=>{throw Error("SSR may not invoke Core API")},
  refresh:()=>{},onNavigate:()=>{}
 }));
 assert.match(html,/My saved filters/);
 assert.match(html,/Private policy/);
 assert.match(html,/Filter loaded saved view resource type/);
 assert.match(html,/Sort loaded private saved filters/);
 assert.doesNotMatch(html,/Active Saved Views display filters/);
 assert.doesNotMatch(html,/Remove Name search filter/);
 assert.doesNotMatch(html,/PRIVATE_TOKEN|secret-id/);
});

test("G-34 native chip buttons independently remove ONLY local search/type/sort and preserve all existing safety gates",()=>{
 const src=readFileSync(join(root,"src","uxb-saved-views.tsx"),"utf8");
 assert.match(src,/export function activeSavedViewFilterChips\(/);
 assert.match(src,/const savedViewChips=activeSavedViewFilterChips\(listQuery,targetFacet,listSort\)/);
 assert.match(src,/role="group" aria-label="Active Saved Views display filters"/);
 assert.match(src,/savedViewChips\.map\(chip=><button/);
 assert.match(src,/aria-label=\{"Remove "\+chip.label\+" filter"\}/);
 assert.ok(src.includes('onClick={()=>{if(chip.id==="search")setListQuery("");else if(chip.id==="type")setTargetFacet("all");else setListSort("core");setPageIndex(0);listQueryInputRef.current?.focus()}}'));
 assert.match(src,/Reset Saved Views display filters/);
 assert.match(src,/const duplicate=conflictingSavedViewName\(rows,name\)/);
 assert.match(src,/const incompleteNames=rows\.length>=100/);
 assert.match(src,/const typedVisibleRows=filterLoadedSavedViewsByType\(visibleRows\.items,targetFacet\)/);
 assert.match(src,/const sortedVisibleRows=sortLoadedSavedViews\(typedVisibleRows,listSort\)/);
 assert.match(src,/\/api\/v1\/saved-views/);
 assert.doesNotMatch(src,/\/api\/v1\/saved-views\?filter=/);
 assert.match(src,/const \[name,setName\]=useState\(""/);
 const region=src.slice(src.indexOf('aria-label="Active Saved Views display filters"')-85,
  src.indexOf('aria-label="Active Saved Views display filters"')+630);
 assert.doesNotMatch(region,/setName\(|setFilter\(|setAdmission\(|setPolicyPlane\(|setConfirmReplace\(|api\(|refresh\(/);
});
