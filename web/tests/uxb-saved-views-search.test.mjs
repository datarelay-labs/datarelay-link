// M1-B G-30: operator-private Loaded Saved View name quick-find.
// Source/SSR contract only, not authenticated browser or another user's data.
import assert from "node:assert/strict";
import {test} from "node:test";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,"node_modules",".drlink-g30-saved-search-"));
let view;
try{
 const output=join(scratch,"views.mjs");
 await build({entryPoints:[join(root,"src","uxb-saved-views.tsx")],
  outfile:output,bundle:true,platform:"node",format:"esm",jsx:"automatic",
  external:["react","react/jsx-runtime"],logLevel:"silent"});
 view=await import(pathToFileURL(output).href);
}finally{rmSync(scratch,{recursive:true,force:true})}
const rows=[
 {id:"v2",name:"Vendor AI",payload:{resource_type:"access-rule",filter:"provider-4",plane:"ai",secret:"PRIVATE_CREDENTIAL"}},
 {id:"v3",name:"Host triage",payload:{resource_type:"managed-host",filter:"offline"}},
 {id:"v4",name:"SSH services",payload:{resource_type:"remote-service",filter:"ssh"}},
 {id:"v5",name:{password:"SECRET_NAME"},payload:{resource_type:"access-rule",filter:"SECRET_FILTER",plane:"remote"}}
];
const names=(query,input=rows)=>view.filterObservedSavedViewList(input,query).items.map(x=>x.name);
const render=items=>renderToStaticMarkup(React.createElement(view.SavedViewsWorkspace,{
 data:{items},api:()=>{throw Error("SSR cannot call API")},refresh:()=>{},
 onNavigate:()=>{}
}));

test("G-30 name quick-find preserves loaded Core list order and object identity",()=>{
 assert.deepEqual(names(""),rows.map(x=>x.name));
 assert.deepEqual(names("vendor"),["Vendor AI"]);
 assert.deepEqual(names("HOST"),["Host triage"]);
 assert.deepEqual(names("ssh"),["SSH services"]);
 const filtered=view.filterObservedSavedViewList(rows,"ven");
 assert.equal(filtered.items[0],rows[0]);
 assert.equal(filtered.loadedCount,4);
 assert.equal(filtered.scope,"loaded-only");
 assert.equal(filtered.error,null);
 assert.deepEqual(names("vendor",rows.slice(1)),[]);
});

test("G-30 name-only search never searches payload text, secret metadata or unsafe display name",()=>{
 for(const secret of ["provider-4","PRIVATE_CREDENTIAL","SECRET_FILTER","SECRET_NAME"])
  assert.deepEqual(names(secret),[],secret);
 assert.deepEqual(names("[object Object]"),[]);
 assert.equal(view.filterObservedSavedViewList(rows,"  vendor  ").items[0],rows[0]);
 assert.deepEqual(rows.map(x=>x.id),["v2","v3","v4","v5"],"never sorts or mutates");
});

test("G-30 invalid local query and unavailable Core list are explicit fail-closed",()=>{
 for(const query of [null,undefined,{},[],42,"x".repeat(81),"bad\nline","sh\u202eow"]){
  const result=view.filterObservedSavedViewList(rows,query);
  assert.deepEqual(result.items,[]);
  assert.match(result.error,/invalid/i);
  assert.equal(result.loadedCount,4);
 }
 for(const input of [null,undefined,{},[], "string"]){
  const result=view.filterObservedSavedViewList(input,"ssh");
  assert.deepEqual(result.items,[]);
  assert.equal(result.scope,"loaded-only");
 }
});

test("G-30 accessible local search doesn't change private collision or 100-row completeness gates",()=>{
 const html=render(rows);
 assert.match(html,/Find my saved filters/);
 assert.match(html,/aria-label="Find my saved filters"/);
 assert.doesNotMatch(html,/Clear saved filter search/,"clear is available only when a search is active");
 const src=readFileSync(join(root,"src","uxb-saved-views.tsx"),"utf8");
 assert.match(src,/const visibleRows=filterObservedSavedViewList\(rows,listQuery\)/);
 assert.match(src,/const duplicate=conflictingSavedViewName\(rows,name\)/);
 assert.match(src,/const incompleteNames=rows\.length>=100/);
 assert.match(src,/const typedVisibleRows=filterLoadedSavedViewsByType\(visibleRows\.items,targetFacet\)/);
 assert.match(src,/const sortedVisibleRows=sortLoadedSavedViews\(typedVisibleRows,listSort\)/);
 assert.match(src,/savedPage\.items\.map\(\(item:any,i:number\)=>/);
 assert.match(src,/No matching loaded saved filters/);
 assert.match(src,/No saved views yet/);
 assert.match(src,/aria-label="Find my saved filters"/);
 assert.ok(src.includes('onChange={e=>{setListQuery(e.target.value);setPageIndex(0)}}'));
 assert.ok(src.includes('onClick={()=>{setListQuery("");setPageIndex(0)}}'));
 assert.match(src,/Only names in the loaded private list/);
 assert.doesNotMatch(src,/\/api\/v1\/saved-views\?q=/);
 assert.match(src,/\/api\/v1\/saved-views/);
 assert.deepEqual(view.conflictingSavedViewName(rows,"Host TRIAGE"),"Host triage",
  "collision check keeps the full unfiltered list");
 const css=readFileSync(join(root,"dist","styles.css"),"utf8");
 assert.match(css,/\.dr-form-actions\{[^}]*flex-wrap:wrap/);
});
