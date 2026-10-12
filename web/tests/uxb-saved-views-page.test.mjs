// G-35 original loaded-only operator-private Saved Views paging.
// No Core pagination, no browser role/E2E qualification.
import assert from "node:assert/strict";
import {test} from "node:test";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const temp=mkdtempSync(join(root,"node_modules",".drlink-g35-view-page-"));
let page,view;
try{
 const helperPath=join(temp,"page.mjs"),viewPath=join(temp,"view.mjs");
 await build({entryPoints:[join(root,"src","uxb-saved-views-page.ts")],
  outfile:helperPath,platform:"node",format:"esm",bundle:true,logLevel:"silent"});
 await build({entryPoints:[join(root,"src","uxb-saved-views.tsx")],
  outfile:viewPath,platform:"node",format:"esm",bundle:true,jsx:"automatic",
  external:["react","react/jsx-runtime"],logLevel:"silent"});
 page=await import(pathToFileURL(helperPath).href);
 view=await import(pathToFileURL(viewPath).href);
}finally{rmSync(temp,{recursive:true,force:true})}
const entries=Array.from({length:100},(_,i)=>({
 id:"v"+String(i+1).padStart(3,"0"),
 name:"Private item "+String(i+1).padStart(3,"0"),
 payload:{resource_type:"managed-host",filter:"host"}
}));
const take=(items,p=0)=>page.paginateLoadedSavedViews(items,p);
const ssr=items=>renderToStaticMarkup(React.createElement(view.SavedViewsWorkspace,{
 data:{items},api:()=>{throw Error("SSR no Core access")},
 refresh:()=>{},onNavigate:()=>{}
}));

test("G35 exact 25/page bounded local slices, preserved identity/order, last page and full first-100",()=>{
 const first=take(entries,0),second=take(entries,1),last=take(entries,3);
 assert.deepEqual({...first,items:[]},{items:[],total:100,from:1,to:25,pageIndex:0,pageCount:4});
 assert.deepEqual({...second,items:[]},{items:[],total:100,from:26,to:50,pageIndex:1,pageCount:4});
 assert.deepEqual({...last,items:[]},{items:[],total:100,from:76,to:100,pageIndex:3,pageCount:4});
 assert.equal(first.items.length,25);
 assert.equal(second.items[0],entries[25]);
 assert.equal(last.items[24],entries[99]);
 assert.equal(first.items[0],entries[0]);
 assert.deepEqual(entries.slice(0,3).map(x=>x.id),["v001","v002","v003"]);
 assert.notEqual(first.items,entries,"new slice no input mutation");
});

test("G35 partial, empty and stale page index are accurate not fictitious server pages",()=>{
 assert.deepEqual(take([],0),{items:[],total:0,from:0,to:0,pageIndex:0,pageCount:0});
 assert.deepEqual({...take(entries.slice(0,1),0),items:[]},
  {items:[],total:1,from:1,to:1,pageIndex:0,pageCount:1});
 assert.deepEqual({...take(entries.slice(0,26),1),items:[]},
  {items:[],total:26,from:26,to:26,pageIndex:1,pageCount:2});
 assert.deepEqual({...take(entries.slice(0,27),999),items:[]},
  {items:[],total:27,from:26,to:27,pageIndex:1,pageCount:2},
  "Core refresh/partial result clamps a stale page to the last actually loaded one");
 assert.deepEqual(take(entries.slice(0,25),999).items,entries.slice(0,25));
});

test("G35 invalid Core list, more than 100, unsafe index and nonrows fail closed without false counts",()=>{
 for(const rows of [null,undefined,{},[], "untrusted", [null],[[1]],[1],[true],
  Array.from({length:101},()=>({name:"overflow"}))]){
  if(Array.isArray(rows)&&rows.length===0)continue;
  assert.equal(take(rows,0),null,JSON.stringify(rows)?.slice(0,40));
 }
 for(const p of [-1,0.5,NaN,Infinity,"0",null,{},2**54]){
  assert.equal(take(entries,p),null,String(p));
 }
 const malformed=entries.slice(0,3);malformed[1]={id:"unsafe",password:"PRIVATE"};
 assert.equal(take(malformed,0).items[1],malformed[1],
  "local paging doesn't coerce/expose other Core fields; display remains separate");
});

test("G35 SSR shows only the first 25 loaded rows, accurate loaded range, no global total or user secrets",()=>{
 const html=ssr(entries.slice(0,28));
 assert.match(html,/Showing 1–25 of 28 matching loaded private views/);
 assert.match(html,/28 loaded private Core views/);
 assert.match(html,/Page 1 of 2/);
 assert.match(html,/Previous saved view page/);
 assert.match(html,/Next saved view page/);
 assert.match(html,/Private item 001/);
 assert.match(html,/Private item 025/);
 assert.doesNotMatch(html,/Private item 026/);
 assert.match(html,/not a Core global total/);
 assert.doesNotMatch(html,/total server views|PRIVATE_PASSWORD/);
 const one=ssr(entries.slice(0,1));
 assert.match(one,/Showing 1–1 of 1 matching loaded private views/);
 assert.doesNotMatch(one,/Previous saved view page|Next saved view page/);
 const empty=ssr([]);
 assert.match(empty,/No saved views yet/);
 assert.match(empty,/Showing 0–0 of 0 matching loaded private views/);
 assert.doesNotMatch(empty,/Previous saved view page|Next saved view page/);
 const cap=ssr(entries);
 assert.match(cap,/Core returned the first 100 private views; additional private views may exist/);
});

test("G35 safe pagination runs after G30/G32/G31 and cannot change form/permissions/Core backend",()=>{
 const s=readFileSync(join(root,"src","uxb-saved-views.tsx"),"utf8");
 assert.match(s,/import \{paginateLoadedSavedViews\} from "\.\/uxb-saved-views-page"/);
 assert.match(s,/const \[pageIndex,setPageIndex\]=useState\(0\)/);
 assert.match(s,/const savedPage=paginateLoadedSavedViews\(sortedVisibleRows,pageIndex\)/);
 assert.match(s,/const duplicate=conflictingSavedViewName\(rows,name\)/);
 assert.match(s,/const incompleteNames=rows\.length>=100/);
 assert.match(s,/savedPage\.items\.map\(\(item:any,i:number\)=>/);
 assert.match(s,/onChange=\{e=>\{setListQuery\(e.target.value\);setPageIndex\(0\)\}\}/);
 assert.match(s,/setTargetFacet\(isSavedViewTargetFilter\(e.target.value\)\?e.target.value:"all"\);setPageIndex\(0\)/);
 assert.match(s,/setListSort\(isSavedViewSortMode\(e.target.value\)\?e.target.value:"core"\);setPageIndex\(0\)/);
 assert.match(s,/aria-label="Previous saved view page"/);
 assert.match(s,/aria-label="Next saved view page"/);
 assert.match(s,/Core returned the first 100 private views/);
 assert.match(s,/only the already loaded private views/);
 assert.doesNotMatch(s,/\/api\/v1\/saved-views\?(?:page|limit|offset)=/);
 const h=readFileSync(join(root,"src","uxb-saved-views-page.ts"),"utf8");
 assert.doesNotMatch(h,/\b(?:fetch|api|localStorage|sessionStorage|eval)\s*\(/);
});
