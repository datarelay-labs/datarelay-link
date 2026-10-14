// G-36 original read-only same-Core-scope Audit refresh guard, source-only QA.
// This does not constitute installed Server/Agent or logged-in user E2E.
import assert from "node:assert/strict";
import {test} from "node:test";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const tmp=mkdtempSync(join(root,"node_modules",".drlink-g36-audit-refresh-"));
let helper;
try{
 const outfile=join(tmp,"audit.mjs");
 await build({entryPoints:[join(root,"src","uxb-audit-refresh.ts")],
  outfile,platform:"node",format:"esm",bundle:true,logLevel:"silent"});
 helper=await import(pathToFileURL(outfile).href);
}finally{rmSync(tmp,{recursive:true,force:true})}
const q="limit=50&category=CONTROL&actor=operator-9";
const initial={cursor:"",history:[]};
const older={cursor:"eyJwYWdlIjoyfQ==",history:[""]};
const prev={cursor:"eyJwYWdlIjozfQ==",history:["","eyJwYWdlIjoyfQ=="]};
// Preserve explicitly passed undefined; JavaScript default parameters would
// accidentally turn invalid test input back into an authorized baseline.
const allowed=(...args)=>helper.observedAuditPageRefreshAvailable(
 args.length>0?args[0]:"ready",args.length>1?args[1]:q,
 args.length>2?args[2]:q,args.length>3?args[3]:initial);

test("G36 permits only a successful already applied equal filter scope and exact current keyset page",()=>{
 assert.equal(allowed(),true);
 assert.equal(allowed("ready","limit=50","limit=50",initial),true);
 assert.equal(allowed("ready",q,q,older),true);
 assert.equal(allowed("ready",q,q,prev),true);
 assert.equal(allowed("ready",q,"limit=50&category=ACCESS_DECISION&actor=operator-9"),false);
 assert.equal(allowed("ready",q,"limit=50"),false);
 for(const state of ["unknown","idle","loading",null,undefined,{},[]])
  assert.equal(allowed(state),false);
});

test("G36 rejected invalid, non-whitelisted, unsubmitted or spoofed Audit scope cannot refresh",()=>{
 for(const candidate of [null,undefined,"","limit=1","limit=500","cursor=secrets&limit=50",
  "limit=50&token=TOKEN","limit=50&limit=50","limit=50&actor=bad%0Ainjection",
  "limit=50&category=NOT_VALID","limit=50&start=2026-02-31T00%3A00%3A00Z",
  "limit=50&start=2026-10-13T00%3A00%3A00Z&end=2026-10-12T00%3A00%3A00Z"]){
  assert.equal(allowed("ready",candidate,candidate),false,String(candidate));
 }
 assert.equal(allowed("ready",q,q+" ",older),false);
 assert.equal(allowed("ready",q,q+"&result=deny",older),false);
});

test("G36 Core-issued opaque page position must be bounded and well shaped, not an arbitrary URL or injected Core state",()=>{
 for(const pos of [null,undefined,{},[],{cursor:null,history:[]},
  {cursor:"abc",history:null},{cursor:"abc",history:[null]},
  {cursor:"abc",history:["ok\nunsafe"]},
  {cursor:"bad\u202e",history:[""]},
  {cursor:"x".repeat(4097),history:[""]},
  {cursor:"",history:[""]},
  {cursor:"abc",history:Array.from({length:101},()=>"")},
  {cursor:4,history:[]}]){
  assert.equal(allowed("ready",q,q,pos),false,JSON.stringify(pos)?.slice(0,60));
 }
});

test("G36 UI refresh uses existing read epoch Core API and current page; edited draft cannot falsely relabel evidence",()=>{
 const src=readFileSync(join(root,"src","main.tsx"),"utf8");
 const body=src.split("function AuditExplorer(",2)[1]?.split("function AgentRolloutPreviewPanel(",1)[0]||"";
 assert.match(src,/import \{observedAuditPageRefreshAvailable\} from "\.\/uxb-audit-refresh"/);
 assert.match(body,/const auditRefreshAllowed=observedAuditPageRefreshAvailable\(auditState,auditFilterKey,filterParams\(\)\.toString\(\),auditPage\)/);
 assert.match(body,/disabled=\{!auditRefreshAllowed\}/);
 assert.match(body,/onClick=\{\(\)=>\{if\(auditRefreshAllowed\)load\(auditPage\)\}\}/);
 assert.match(body,/Refresh loaded Audit page/);
 assert.match(body,/Search audit/);
 assert.match(body,/Filters changed since the loaded Audit page/);
 assert.match(body,/const epoch=\+\+auditReadEpoch\.current/);
 assert.match(body,/setData\(null\);setAuditState\("loading"\)/);
 assert.match(body,/if\(position\.cursor\)q\.set\("cursor",position\.cursor\)/);
 assert.match(body,/setAuditFilterKey\(filterKey\);setAuditState\("ready"\)/);
 assert.match(body,/await api\("\/api\/v1\/audit\?"\+q\.toString\(\)\)/);
 assert.doesNotMatch(body,/setRetention\(null\);setAuditPage\(position\)/);
 assert.doesNotMatch(readFileSync(join(root,"src","uxb-audit-refresh.ts"),"utf8"),
  /\b(?:fetch|api|localStorage|sessionStorage|eval|setTimeout)\s*\(/);
});
