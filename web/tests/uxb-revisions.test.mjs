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
let scratch,RevisionHistory;
before(async()=>{
  scratch=mkdtempSync(join(root,"node_modules",".uxb-revisions-"));
  const outfile=join(scratch,"revisions.mjs");
  await build({entryPoints:[join(root,"src","uxb-revisions.tsx")],outfile,
    bundle:true,platform:"node",format:"esm",jsx:"automatic",
    external:["react","react/jsx-runtime"],logLevel:"silent"});
  ({RevisionHistory}=await import(pathToFileURL(outfile).href));
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
test("malformed Core collection never renders a fake empty Revision History",()=>{
  for(const invalid of [null,{},[],{items:null},{items:[null]},
    {items:[],next_cursor:123}]) {
    assert.throws(()=>markup(invalid),/Core|UNKNOWN/);
  }
});
