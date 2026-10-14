// G-23 independent NetBird-informed, Core-loaded policy list presentation.
// Pure source/SSR evidence, NOT authentic browser or installed E2E.
import assert from "node:assert/strict";
import {test} from "node:test";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,"node_modules",".drlink-g23-policy-sort-"));
let helper;
try{
 const outfile=join(scratch,"sort.mjs");
 await build({entryPoints:[join(root,"src","uxb-policy-sort.ts")],
  outfile,platform:"node",format:"esm",bundle:true,logLevel:"silent"});
 helper=await import(pathToFileURL(outfile).href);
}finally{rmSync(scratch,{recursive:true,force:true})}

const policies=[
 {id:"p-z",name:"Zebra",plane:"remote",row_version:1},
 {id:"p-b1",name:"beta",plane:"internet",row_version:2},
 {id:"p-a1",name:"Alpha",plane:"ai",row_version:3},
 {id:"p-b2",name:"BETA",plane:"remote",row_version:4},
 {id:"p-x",name:"masked\u202e",plane:"ai",secret:"DO_NOT_READ"},
 {id:"p-m",name:{secret:"NEVER_READ"},plane:"remote"},
 {id:"bad\nid",name:"Aaa",plane:"remote",api_token:"HIDDEN"}
];
const ids=(mode,items=policies)=>helper.sortLoadedPolicies(items,mode).map(x=>x.id);

test("G-23 Core-order default preserves exact Core-loaded input order and immutable row identity",()=>{
 assert.deepEqual(ids("core"),["p-z","p-b1","p-a1","p-b2","p-x","p-m","bad\nid"]);
 const result=helper.sortLoadedPolicies(policies,"core");
 assert.notEqual(result,policies);
 for(let i=0;i<policies.length;i++)assert.equal(result[i],policies[i]);
});

test("G-23 name ordering is stable, case-folded and safe with missing/unsafe name fallback",()=>{
 assert.deepEqual(ids("name_asc"),["p-a1","p-b1","p-b2","p-m","p-x","p-z","bad\nid"]);
 assert.deepEqual(ids("name_desc"),["p-z","p-x","p-m","p-b1","p-b2","p-a1","bad\nid"]);
 assert.deepEqual(policies.map(x=>x.id),["p-z","p-b1","p-a1","p-b2","p-x","p-m","bad\nid"]);
 assert.equal(helper.sortLoadedPolicies(policies,"name_asc")[2],policies[3]);
 assert.deepEqual(ids("name_asc",policies.slice(0,2)),["p-b1","p-z"],"sorts only loaded subset");
 assert.doesNotMatch(JSON.stringify(ids("name_asc")),/DO_NOT_READ|NEVER_READ|HIDDEN/);
});

test("G-23 rejects invalid sort selectors and non-array Core evidence without coercion",()=>{
 for(const mode of ["", "name", "name_asc ", "__proto__", "Name ASC",null,42,[],{}]){
  assert.equal(helper.isPolicySortMode(mode),false);
  assert.deepEqual(helper.sortLoadedPolicies(policies,mode),[]);
 }
 for(const rows of [null,undefined,"policies",{items:policies},42])
  assert.deepEqual(helper.sortLoadedPolicies(rows,"core"),[]);
 for(const mode of ["core","name_asc","name_desc"])
  assert.equal(helper.isPolicySortMode(mode),true);
});

test("G-23 native Policy Table/Cards control only sorts filtered, Core-loaded rows; no drawer rewrite",()=>{
 const src=readFileSync(join(root,"src","main.tsx"),"utf8");
 const policy=src.split("function PolicyWorkspace(",2)[1]?.split("function ServiceUseActions(",1)[0]||"";
 assert.match(src,/import \{sortLoadedPolicies,isPolicySortMode,type PolicySortMode\} from "\.\/uxb-policy-sort"/);
 assert.match(policy,/const \[policySort,setPolicySort\]=useState<PolicySortMode>\("core"\)/);
 assert.match(policy,/const rows=sortLoadedPolicies<any>\(filterObservedPoliciesByExpiry<any>\(policyStatusRows,expiryFilter,expiryObservedAt\),policySort\)/);
 assert.match(policy,/aria-label="Sort loaded Policies"/);
 assert.match(policy,/onChange=\{e=>setPolicySort\(isPolicySortMode\(e.target.value\)\?e.target.value:"core"\)\}/);
 for(const [mode,title] of [["core","Core order (default)"],["name_asc","Policy name A–Z"],["name_desc","Policy name Z–A"]])
  assert.ok(policy.includes('<option value="'+mode+'">'+title+'</option>'),title);
 assert.match(policy,/Policy ordering is display-only for loaded Core rows/);
 assert.match(policy,/Core rule evaluation\/precedence and Saved Views remain unchanged/);
 assert.match(policy,/policyView==="cards"\?<div className="dr-resource-cards"/);
 assert.match(policy,/dr-resource-table/);
 assert.match(policy,/Core policy list may be incomplete/);
 assert.match(policy,/Load more/);
 assert.match(policy,/Recent activity/,"existing protected drawer navigation remains");
 assert.doesNotMatch(readFileSync(join(root,"src","uxb-policy-sort.ts"),"utf8"),/\b(?:fetch|api|localStorage|sessionStorage|eval)\s*\(/);
 const css=readFileSync(join(root,"dist","styles.css"),"utf8");
 assert.match(css,/\.dr-form-actions\{[^}]*flex-wrap:wrap/);
});
