// G-15: independently implemented, loaded-only Host sorting; not a Core fleet query
// or authenticated browser/persona E2E claim.
import assert from "node:assert/strict";
import {test} from "node:test";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,"node_modules",".drlink-g15-sort-"));
let helper;
try{
 const outfile=join(scratch,"sort.mjs");
 await build({entryPoints:[join(root,"src","uxb-host-sort.ts")],
  outfile,platform:"node",format:"esm",bundle:true,logLevel:"silent"});
 helper=await import(pathToFileURL(outfile).href);
}finally{rmSync(scratch,{recursive:true,force:true})}

const observed=[
 {id:"h-4",name:"zebra",admission_state:"APPROVED",connected:true},
 {id:"h-2",name:"Bravo",admission_state:"QUARANTINED",connected:false},
 {id:"h-3",name:"alpha",admission_state:"PENDING_APPROVAL",connected:true},
 {id:"h-1",name:"alpha",admission_state:"APPROVED",connected:false},
 {id:"h-5",name:"charlie",admission_state:"PENDING_APPROVAL",connected:true},
 {id:"h-6",name:"Bravo",admission_state:"APPROVED",connected:true},
 {id:"h-7",name:"Zebra",admission_state:"QUARANTINED",connected:true}
];
const ids=(mode,rows=observed)=>helper.sortLoadedHosts(rows,mode).map(x=>x.id);

test("G-15 preserves existing review-priority default and stable loaded row order on equal tier",()=>{
 assert.deepEqual(ids("review"),["h-3","h-5","h-2","h-7","h-4","h-1","h-6"]);
 assert.deepEqual(observed.map(x=>x.id),["h-4","h-2","h-3","h-1","h-5","h-6","h-7"],
  "sorting never mutates the Core loaded inputs");
});
test("G-15 stable case-insensitive Host display-name ascending and descending with allowed Core identities",()=>{
 assert.deepEqual(ids("name_asc"),["h-3","h-1","h-2","h-6","h-5","h-4","h-7"]);
 assert.deepEqual(ids("name_desc"),["h-4","h-7","h-5","h-2","h-6","h-3","h-1"]);
 const loaded=observed.filter(x=>x.id==="h-2"||x.id==="h-4");
 assert.deepEqual(ids("name_asc",loaded),["h-2","h-4"]);
 assert.equal(helper.sortLoadedHosts(loaded,"review")[0],loaded[1],"keeps original Core row identity");
});
test("G-15 untrusted mode / list fails closed; unknown names fall back to bounded id and do not process secrets",()=>{
 for(const mode of ["","Name ASC","desc","name_asc ","__proto__",null,{},[],42])
  assert.deepEqual(helper.sortLoadedHosts(observed,mode),[],String(mode));
 for(const list of [undefined,null,{}, {items:observed},"string"])
  assert.deepEqual(helper.sortLoadedHosts(list,"review"),[]);
 const raw=[
  {id:"zeta",name:null,admission_state:"APPROVED",private_key:"KEY_SHOULD_NOT_READ"},
  {id:"beta",name:"beta",admission_state:"APPROVED"},
  {id:"alpha",name:"Alpha\u202e",admission_state:"APPROVED"},
  {id:"bad",name:{nested:"UNSAFE"}},
 ];
 assert.deepEqual(helper.sortLoadedHosts(raw,"name_asc").map(x=>x.id),["alpha","bad","beta","zeta"]);
 assert.equal(raw[0].private_key,"KEY_SHOULD_NOT_READ");
});
test("G-15 native accessible sort chooser only rearranges observed Host rows and does not alter Core or saved views",()=>{
 const src=readFileSync(join(root,"src","main.tsx"),"utf8");
 const host=src.split("function ResourceWorkspace(",2)[1]?.split("function UsersPanel(",1)[0]||"";
 assert.match(src,/import \{sortLoadedHosts,isHostSortMode,type HostSortMode\} from "\.\/uxb-host-sort"/);
 assert.match(host,/const \[hostSort,setHostSort\]=useState<HostSortMode>\("review"\)/);
 assert.match(host,/const rows=isHost\?sortLoadedHosts\(hostConnection\?\.items\|\|\[\],hostSort\):\(serviceFacets\?\.items\|\|\[\]\)/);
 assert.match(host,/aria-label="Sort loaded Hosts"/);
 assert.match(host,/onChange=\{e=>setHostSort\(isHostSortMode\(e.target.value\)\?e.target.value:"review"\)\}/);
 for(const [value,text] of [["review","Review priority (default)"],["name_asc","Host name A–Z"],["name_desc","Host name Z–A"]]){
  assert.ok(host.includes('<option value="'+value+'">'+text+'</option>'),text);
 }
 assert.match(host,/Host sorting changes only loaded rows; no Core or Saved View update/);
 assert.match(host,/Host sort is not saved/);
 assert.match(host,/Partial Core inventory/);
 assert.match(host,/Load more Managed Hosts/);
 assert.match(host,/Filter loaded Host connection state/);
 assert.doesNotMatch(readFileSync(join(root,"src","uxb-host-sort.ts"),"utf8"),/\b(?:fetch|api|localStorage|sessionStorage|eval)\s*\(/);
 const css=readFileSync(join(root,"dist","styles.css"),"utf8");
 assert.match(css,/\.dr-form-actions\{[^}]*flex-wrap:wrap/);
});
