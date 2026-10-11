// G-14 original preference: no Core authorization, session or saved query in storage.
// Supplemental source test, NOT authenticated 2-user real Web/browser E2E.
import assert from "node:assert/strict";
import {test} from "node:test";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,"node_modules",".drl3-start-page-"));
let start;
try {
 const output=join(scratch,"start.mjs");
 await build({entryPoints:[join(root,"src","uxb-start-page.ts")],
   outfile:output,bundle:true,platform:"node",format:"esm",logLevel:"silent"});
 start=await import(pathToFileURL(output).href);
}finally{rmSync(scratch,{recursive:true,force:true})}
const admin={id:"id-admin-001",username:"Alice",role:"Admin"};
const operator={id:"id-operator-002",username:"Bob",role:"Operator"};
const readOnly={id:"id-reader-003",username:"Claire",role:"Read Only"};
function fakeStore(){
 const data=new Map();
 return {data,getItem:key=>data.has(key)?data.get(key):null,
   setItem:(key,value)=>{data.set(key,value)}};
}

test("G-14 strict stable page allowlist and exact actor/role-specific browser key",()=>{
 assert.deepEqual(start.START_PAGE_OPTIONS.map(x=>x.id),
  ["overview","hosts","services","policies","access","health","audit","jobs","views","users"]);
 const key=start.startPageKeyForOperator(admin);
 assert.match(key,/drlink_web_start_page_v1/);
 assert.notEqual(key,start.startPageKeyForOperator(operator));
 assert.notEqual(key,start.startPageKeyForOperator({...admin,role:"Read Only"}));
 assert.equal(start.startPageKeyForOperator({...admin,username:"Different label"}),key);
 for(const invalid of [null,{},[],{id:null,role:"Admin"},
   {id:"../root",role:"Admin"},{id:"host\nunsafe",role:"Admin"},
   {id:"x".repeat(161),role:"Admin"},{id:"good",role:"Unknown"},
   {id:"good",role:"Administrator"}])
  assert.equal(start.startPageKeyForOperator(invalid),null,JSON.stringify(invalid));
});

test("G-14 supported preference survives reload for only matching actor and unchanged authorized role",()=>{
 const store=fakeStore();
 assert.equal(start.readPreferredStartPage(admin,store),"overview");
 assert.equal(start.writePreferredStartPage(admin,"services",store),true);
 assert.equal(start.readPreferredStartPage(admin,store),"services");
 assert.equal(start.readPreferredStartPage(operator,store),"overview");
 assert.equal(start.readPreferredStartPage({...admin,role:"Read Only"},store),"overview");
 assert.equal(start.writePreferredStartPage(admin,"users",store),true);
 assert.equal(start.readPreferredStartPage(admin,store),"users");
 assert.equal(start.readPreferredStartPage({...admin,role:"Read Only"},store),"overview");
 assert.equal(start.writePreferredStartPage(readOnly,"users",store),false);
 assert.equal(start.writePreferredStartPage(operator,"users",store),false);
 assert.equal(start.readPreferredStartPage(operator,store),"overview");
 assert.equal(start.writePreferredStartPage(readOnly,"audit",store),true);
 assert.equal(start.readPreferredStartPage(readOnly,store),"audit");
 assert.equal(start.readPreferredStartPage({...readOnly,role:"Operator"},store),"overview");
});

test("G-14 stale, malicious and malformed preferences fail closed; no writes for unsupported routes",()=>{
 const store=fakeStore();
 const key=start.startPageKeyForOperator(admin);
 for(const bad of ["../../admin","drafts","enrollments","system","javascript:alert(1)",
   "{\"route\":\"users\",\"token\":\"SECRET\"}","", "Users","__proto__"]){
  store.data.set(key,bad);
  assert.equal(start.readPreferredStartPage(admin,store),"overview");
  assert.equal(start.writePreferredStartPage(admin,bad,store),false,bad);
  assert.equal(store.data.get(key),bad,"invalid selection must not overwrite existing state");
 }
 const roleMismatchStore=fakeStore();
 roleMismatchStore.data.set(start.startPageKeyForOperator({...admin,role:"Read Only"}),"users");
 assert.equal(start.readPreferredStartPage({...admin,role:"Read Only"},roleMismatchStore),"overview");
});

test("G-14 denied browser storage or missing stable Core actor never claims saved",()=>{
 const broken={getItem(){throw new Error("blocked read")},setItem(){throw new Error("blocked write")}};
 assert.equal(start.readPreferredStartPage(admin,broken),"overview");
 assert.equal(start.writePreferredStartPage(admin,"hosts",broken),false);
 assert.equal(start.readPreferredStartPage(admin,null),"overview");
 assert.equal(start.writePreferredStartPage(admin,"hosts",null),false);
 const dropping={getItem(){return null},setItem(){/* dropped */}};
 assert.equal(start.writePreferredStartPage(admin,"hosts",dropping),false);
 assert.equal(start.writePreferredStartPage({role:"Admin"},"hosts",fakeStore()),false);
});

test("G-14 Shell uses role-safe preference only for start page, never automatic auth bypass or navigation context",()=>{
 const src=readFileSync(join(root,"src","main.tsx"),"utf8");
 const shell=src.split("function Shell(",2)[1]?.split("function App(",1)[0]||"";
 assert.match(src,/import \{START_PAGE_OPTIONS,startPageKeyForOperator,readPreferredStartPage,writePreferredStartPage\} from "\.\/uxb-start-page"/);
 assert.match(shell,/const \[active,setActive\]=useState\(\(\)=>readBrowserStartingPage\(operator\)\)/);
 assert.match(shell,/const \[preferredStartPage,setPreferredStartPage\]=useState\(\(\)=>readBrowserStartingPage\(operator\)\)/);
 assert.match(shell,/function chooseStartingPage\(route:string\)/);
 const choose=shell.match(/function chooseStartingPage\(route:string\)\{([\s\S]*?)\n  \}/)?.[1]||"";
 assert.match(choose,/writePreferredStartPage\(operator,route,(?:window\.)?localStorage\)/);
 assert.match(choose,/setPreferredStartPage\(route\)/);
 assert.doesNotMatch(choose,/\b(?:api|fetch|activate|setActive|setNavigationContext|onLogout)\s*\(/);
 assert.match(shell,/startPageKeyForOperator\(operator\)/);
 assert.match(shell,/role="group" aria-label="Starting page preference"/);
 assert.match(shell,/<summary.*?Starting page/);
 assert.match(shell,/<select[^>]*aria-label="Preferred starting page"/);
 assert.match(shell,/START_PAGE_OPTIONS\.filter\(item=>visibleRoute\(item.id,operator.role\)\)/);
 assert.match(shell,/onChange=\{e=>chooseStartingPage\(e.target.value\)\}/);
 assert.match(shell,/aria-live="polite"/);
 assert.match(shell,/Applies on next sign-in or reload/);
 assert.match(shell,/Core permissions do not change/);
 assert.match(shell,/\[operator\.id,operator\.role\]/);
 assert.match(shell,/onClick=\{logout\}/);
 assert.match(shell,/returnFocusRef=\{searchReturnFocusRef\}/);
 const css=readFileSync(join(root,"dist","styles.css"),"utf8");
 assert.match(css,/\.dr-start-page-settings>summary\{[^}]*min-height:34px/);
 assert.match(css,/\.dr-start-page-settings-panel\{[^}]*max-width:/);
 assert.match(css,/@media\(max-width:560px\)\{\.dr-start-page-settings-panel\{/);
});

test("G-14 authenticated actor/role swap remounts Shell before stale page presentation",()=>{
 const src=readFileSync(join(root,"src","main.tsx"),"utf8");
 const app=src.split("function App(",2)[1]?.split("createRoot(",1)[0]||"";
 assert.match(app,/return <Shell key=\{String\(operator\.id\|\|""\)\+":"\+String\(operator\.role\|\|""\)\}/);
 assert.match(app,/operator=\{operator\} onLogout=\{\(\)=>setOperator\(null\)\}/);
});
