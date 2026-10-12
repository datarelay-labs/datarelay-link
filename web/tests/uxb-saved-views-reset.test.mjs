// G-33: original Saved Views local presentation reset, no persisted/private Core writes.
// Pure/SSR/source qualification only; never treat this as authenticated Browser E2E.
import assert from "node:assert/strict";
import {test} from "node:test";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const tmp=mkdtempSync(join(root,"node_modules",".drlink-g33-saved-reset-"));
let helper;
try{
 const outfile=join(tmp,"saved.mjs");
 await build({entryPoints:[join(root,"src","uxb-saved-views.tsx")],outfile,
  bundle:true,platform:"node",format:"esm",jsx:"automatic",
  external:["react","react/jsx-runtime"],logLevel:"silent"});
 helper=await import(pathToFileURL(outfile).href);
}finally{rmSync(tmp,{recursive:true,force:true})}
const available=(text="",facet="all",sort="core")=>helper.savedViewsDisplayResetAvailable(text,facet,sort);
const items=[{id:"v1",name:"One",payload:{resource_type:"managed-host",filter:"offline"}},
 {id:"v2",name:"Two",payload:{resource_type:"access-rule",filter:"provider-4",plane:"ai"}}];
const html=()=>renderToStaticMarkup(React.createElement(helper.SavedViewsWorkspace,{
 data:{items},api:()=>{throw Error("SSR must not call Core")},
 refresh:()=>{throw Error("SSR must not refresh Core")},onNavigate:()=>{}
}));

test("G-33 reset is visible ONLY for an active local name/type/sort display choice",()=>{
 assert.equal(available(),false);
 assert.equal(available("host"),true);
 assert.equal(available("   "),true,"operator can clear a typed whitespace query");
 assert.equal(available("","hosts"),true);
 assert.equal(available("","unsupported"),true);
 assert.equal(available("","all","updated_desc"),true);
 assert.equal(available("","all","updated_asc"),true);
 assert.equal(available("provider-4","policies","updated_desc"),true);
});

test("G-33 invalid display filter values cannot trigger action or broaden Core state",()=>{
 for(const text of [null,undefined,24,{},[],true,"unsafe\u202e","bad\nline","x".repeat(81)]){
  assert.equal(helper.savedViewsDisplayResetAvailable(text,"all","core"),false);
  assert.equal(helper.savedViewsDisplayResetAvailable(text,"hosts","updated_asc"),false);
 }
 for(const facet of [null,undefined,{},[],"ALL","policy","__proto__",12]){
  assert.equal(helper.savedViewsDisplayResetAvailable("name",facet,"core"),false);
 }
 for(const mode of [null,undefined,"updated_recent","date","core ","__proto__",{},[]]){
  assert.equal(helper.savedViewsDisplayResetAvailable("name","all",mode),false);
 }
});

test("G-33 default SSR remains native accessible and no Reset button when already default",()=>{
 const ssr=html();
 assert.match(ssr,/My saved filters/);
 assert.match(ssr,/Find my saved filters/);
 assert.match(ssr,/Filter loaded saved view resource type/);
 assert.match(ssr,/Sort loaded private saved filters/);
 assert.doesNotMatch(ssr,/>Reset Saved Views display filters</,"reset must not be shown for a clean display");
 assert.match(ssr,/One/);
 assert.match(ssr,/Two/);
 assert.doesNotMatch(ssr,/PRIVATE_KEY|NOT_SEARCHED/);
});

test("G-33 reset handler clears only three local controls and restores keyboard focus",()=>{
 const src=readFileSync(join(root,"src","uxb-saved-views.tsx"),"utf8");
 assert.match(src,/export function savedViewsDisplayResetAvailable\(/);
 assert.match(src,/const displayResetAvailable=savedViewsDisplayResetAvailable\(listQuery,targetFacet,listSort\)/);
 assert.match(src,/\{displayResetAvailable&&<button type="button" className="secondary"/);
 assert.match(src,/Reset Saved Views display filters<\/button>/);
 assert.ok(src.includes('onClick={()=>{setListQuery("");setTargetFacet("all");setListSort("core");setPageIndex(0);listQueryInputRef.current?.focus()}}'));
 assert.match(src,/const listQueryInputRef=useRef<HTMLInputElement>\(null\)/);
 assert.match(src,/ref=\{listQueryInputRef\}/);
 assert.match(src,/const duplicate=conflictingSavedViewName\(rows,name\)/);
 assert.match(src,/const incompleteNames=rows\.length>=100/);
 assert.match(src,/const typedVisibleRows=filterLoadedSavedViewsByType\(visibleRows\.items,targetFacet\)/);
 assert.match(src,/const sortedVisibleRows=sortLoadedSavedViews\(typedVisibleRows,listSort\)/);
 const specific=src.slice(src.indexOf("Reset Saved Views display filters")-500,
  src.indexOf("Reset Saved Views display filters")+300);
 assert.doesNotMatch(specific,/setName\(|setFilter\(|setAdmission\(|setPolicyPlane\(|setConfirmReplace\(|api\(|refresh\(/);
 assert.doesNotMatch(src,/\/api\/v1\/saved-views\?reset=/);
});
