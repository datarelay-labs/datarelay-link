// UXB-06F read-only Change History source/SSR contract; not a real browser E2E.
import assert from "node:assert/strict";
import {before,after,test} from "node:test";
import {mkdtempSync,rmSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
import {build} from "esbuild";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";

const root=dirname(dirname(fileURLToPath(import.meta.url)));
let scratch,RevisionHistory,validateObservedRevisionPage;
before(async()=>{
  scratch=mkdtempSync(join(root,"node_modules",".uxb-revisions-"));
  const outfile=join(scratch,"revisions.mjs");
  await build({entryPoints:[join(root,"src","uxb-revisions.tsx")],outfile,
    bundle:true,platform:"node",format:"esm",jsx:"automatic",
    external:["react","react/jsx-runtime"],logLevel:"silent"});
  ({RevisionHistory,validateObservedRevisionPage}=await import(pathToFileURL(outfile).href));
});
after(()=>{if(scratch)rmSync(scratch,{recursive:true,force:true})});

const api=async()=>{throw Error("SSR must not fetch Core or pretend E2E")};
const markup=initial=>renderToStaticMarkup(React.createElement(RevisionHistory,{initial,api}));

test("populated Core revision history is task-first, readable and paginated",()=>{
  const html=markup({resource_type:"revision",items:[
    {revision:218,actor:"admin-a",command:"set rule",created_at:"2026-10-09T01:00:00Z",summary:"Narrow SSH allow"},
    {revision:217,actor:"admin-b",command:"set group",created_at:"2026-10-09T00:00:00Z",summary:"Office group"},
  ],next_cursor:"opaque-core-cursor",limit:100});
  assert.match(html,/Change History/);
  assert.match(html,/Activity &amp; Health/);
  assert.match(html,/not live connection status/);
  assert.match(html,/Narrow SSH allow/);
  assert.match(html,/admin-a/);
  assert.match(html,/Page 1/);
  assert.match(html,/older revisions available/);
  assert.match(html,/Older revisions →/);
  assert.match(html,/Newer revisions/);
  assert.match(html,/Refresh history/);
  assert.doesNotMatch(html,/Missing Core|No configuration revisions/);
});
test("confirmed empty Core revisions is not an error or inferred from a failed API",()=>{
  const html=markup({resource_type:"revision",items:[],next_cursor:null,limit:100});
  assert.match(html,/No configuration revisions on this observed Core page/);
  assert.doesNotMatch(html,/Older revisions →/);
  assert.doesNotMatch(html,/UNKNOWN · Core Change History unavailable/);
});
test("Core revision pages must be revision-scoped, bounded and strictly newest first",()=>{
  const valid={resource_type:"revision",limit:100,next_cursor:null,items:[
    {revision:8,actor:"admin",command:"set rule",created_at:"2026-10-09T01:00:00Z",summary:"narrow"},
    {revision:5,actor:"op",command:"group",created_at:"2026-10-09T00:00:00Z",summary:"host"}
  ]};
  assert.equal(validateObservedRevisionPage(valid),valid);
  assert.equal(validateObservedRevisionPage({...valid,items:[]}).items.length,0);
  for(const broken of [null,{},[],{items:[]},{...valid,resource_type:"managed-host"},
    {...valid,limit:50},{...valid,limit:"100"},{...valid,next_cursor:42},
    {...valid,items:[{revision:"8"}]},{...valid,items:[{revision:-1}]},
    {...valid,items:[{revision:8},{revision:8}]},
    {...valid,items:[{revision:5},{revision:8}]},
    {...valid,items:[] ,next_cursor:"next"},
    {...valid,items:Array.from({length:101},(_,i)=>({revision:101-i}))},
    {...valid,items:[{revision:8,actor:{secret:true}}]},
  ]){
    assert.throws(()=>validateObservedRevisionPage(broken),/UNKNOWN/);
    assert.match(markup(broken),/UNKNOWN · Core Change History unavailable/);
  }
});
test("malformed Core collection never renders a fake empty Revision History",()=>{
  for(const invalid of [null,{},[],{items:null},{items:[null]},
    {items:[],next_cursor:123}]) {
    const html=markup(invalid);
    assert.match(html,/UNKNOWN · Core Change History unavailable/);
    assert.doesNotMatch(html,/No configuration revisions on this observed Core page/);
  }
});
