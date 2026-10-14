// G-17: independent operator-facing active Host display chips, without Core I/O.
// Source and pure helper validation are NOT authenticated Browser/Agent E2E.
import assert from "node:assert/strict";
import {test} from "node:test";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,"node_modules",".drlink-g17-chips-"));
let chip;
try{
 const output=join(scratch,"chips.mjs");
 await build({entryPoints:[join(root,"src","uxb-host-filter-chips.ts")],
   outfile:output,bundle:true,platform:"node",format:"esm",logLevel:"silent"});
 chip=await import(pathToFileURL(output).href);
}finally{rmSync(scratch,{recursive:true,force:true})}
const active=(text="",approval="all",connection="all",sort="review")=>
 chip.activeHostFilterChips(text,approval,connection,sort);

test("G-17 four independent active Host facets are represented in stable, plain-language order",()=>{
 assert.deepEqual(active(),[]);
 assert.deepEqual(active("name:branch","all","all","review"),[
  {id:"search",label:"Search",value:"Active"}]);
 assert.deepEqual(active("","PENDING_APPROVAL","disconnected","name_asc"),[
  {id:"admission",label:"Admission",value:"Pending approval"},
  {id:"connection",label:"Connection",value:"Disconnected"},
  {id:"sort",label:"Sort",value:"Host name A–Z"}
 ]);
 assert.deepEqual(active("alpha","APPROVED","unknown","name_desc"),[
  {id:"search",label:"Search",value:"Active"},
  {id:"admission",label:"Admission",value:"Approved"},
  {id:"connection",label:"Connection",value:"UNKNOWN"},
  {id:"sort",label:"Sort",value:"Host name Z–A"}
 ]);
 assert.deepEqual(active("","QUARANTINED","connected","review"),[
  {id:"admission",label:"Admission",value:"Quarantined"},
  {id:"connection",label:"Connection",value:"Connected"}
 ]);
});
test("G-17 never echoes search input, unknown states or credential-looking values and keeps them individually removable",()=>{
 const untrusted="token:SECRET_VALUE\u202e";
 const out=active(untrusted,"ADMIN_TOKEN","other","../admin");
 assert.deepEqual(out,[
  {id:"search",label:"Search",value:"Active"},
  {id:"admission",label:"Admission",value:"UNKNOWN"},
  {id:"connection",label:"Connection",value:"UNKNOWN"},
  {id:"sort",label:"Sort",value:"UNKNOWN"}
 ]);
 assert.doesNotMatch(JSON.stringify(out),/SECRET_VALUE|ADMIN_TOKEN|\.\.\/admin/);
 assert.deepEqual(active("  ",null,null,null).map(x=>x.id),
   ["admission","connection","sort"]);
 assert.deepEqual(active(null,"all","all","review"),[
   {id:"search",label:"Search",value:"UNKNOWN"}]);
 assert.equal(out.length,4);
});
test("G-17 Active Host chips are native keyboard actions, each clearing exactly one local facet",()=>{
 const src=readFileSync(join(root,"src","main.tsx"),"utf8");
 const host=src.split("function ResourceWorkspace(",2)[1]?.split("function UsersPanel(",1)[0]||"";
 assert.match(src,/import \{activeHostFilterChips,type HostFilterChipId\} from "\.\/uxb-host-filter-chips"/);
 assert.match(host,/const hostFilterChips=isHost\?activeHostFilterChips\(filter,admissionFilter,connectionFilter,hostSort\):\[\]/);
 assert.match(host,/function removeHostFilterChip\(id:HostFilterChipId\)/);
 const handler=host.match(/function removeHostFilterChip\(id:HostFilterChipId\)\{([\s\S]*?)\n  \}/)?.[1]||"";
 for(const [id,setter,clear] of [
  ["search","setFilter",'""'],["admission","setAdmissionFilter",'"all"'],
  ["connection","setConnectionFilter",'"all"'],["sort","setHostSort",'"review"']
 ]){
  assert.match(handler,new RegExp('id==="'+id+'"'));
  assert.match(handler,new RegExp(setter+'\\('+clear+'\\)'));
 }
 assert.doesNotMatch(handler,/\b(?:api|fetch|load|setLoaded|setCursor|saveDraftForResource|setSelected|setAuditPage)\s*\(/);
 assert.match(host,/role="group"\s+aria-label="Active Host display filters"/);
 assert.match(host,/hostFilterChips\.map\(entry=><button/);
 assert.match(host,/aria-label=\{"Remove "\+entry\.label\+" filter"\}/);
 assert.match(host,/onClick=\{\(\)=>removeHostFilterChip\(entry\.id\)\}/);
 assert.match(host,/type="button"/);
 assert.match(host,/chip values do not disclose search text/i);
 assert.match(host,/onClick=\{clearHostDisplayFilters\}>Clear Host filters/);
 assert.match(host,/Host sort is not saved/);
 assert.match(host,/Partial Core inventory/);
 const css=readFileSync(join(root,"dist","styles.css"),"utf8");
 assert.match(css,/\.dr-form-actions\{[^}]*flex-wrap:wrap/);
});
