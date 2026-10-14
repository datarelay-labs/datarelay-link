// M1-A G-19: original optional resource cards, loaded-only Core evidence.
// This contract/pure-helper suite does not qualify authenticated 320/375 Browser E2E.
import assert from "node:assert/strict";
import {test} from "node:test";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,"node_modules",".drl3-resource-cards-"));
let cards;
try{
 const outfile=join(scratch,"cards.mjs");
 await build({entryPoints:[join(root,"src","uxb-resource-cards.ts")],
  outfile,bundle:true,platform:"node",format:"esm",logLevel:"silent"});
 cards=await import(pathToFileURL(outfile).href);
}finally{rmSync(scratch,{recursive:true,force:true})}

test("G-19 Host card reads only already loaded canonical Host facts, never guessing Agent liveness",()=>{
 const row={id:"h-01",name:"Edge Host",hostname:"edge.example",connected:1,
   admission_state:"APPROVED",trust_status:"trusted",
   agent_heartbeat_at:"2026-10-11T16:01:00Z",
   last_seen:"2026-10-12T00:11:00Z",password:"SECRET_PW",token:"SECRET_TOKEN",
   details:{oauth:"SECRET_NESTED"}};
 const out=cards.resourceCardSummary("host",row);
 assert.deepEqual(out,{
  title:"Edge Host",subtitle:"edge.example",status:"Connected",
  facts:[{label:"Admission",value:"Approved"},
   {label:"Trust",value:"Trusted"},
   {label:"Agent heartbeat",value:"2026-10-11T16:01:00Z"}]
 });
 assert.doesNotMatch(JSON.stringify(out),/SECRET_|last_seen|Last activity|oauth/);
 assert.equal(cards.resourceCardSummary("host",{id:"h-02",name:"B",connected:true}).status,"Connected");
});
test("G-19 Service card reuses exact safe existing Core detail projections",()=>{
 const value={id:"svc-7",name:"Admin SSH",managed_host:"jump01",
  service_type:"ssh",public_port:2222,enabled:true,released:false,
  target_host:"10.0.0.8",credential:"SECRET",api_key:"SECRET2"};
 const out=cards.resourceCardSummary("service",value);
 assert.deepEqual(out,{
   title:"Admin SSH",subtitle:"svc-7",status:"Enabled",
   facts:[{label:"Managed Host",value:"jump01"},
    {label:"Service type",value:"ssh"},
    {label:"Public port",value:"2222"}]
 });
 assert.doesNotMatch(JSON.stringify(out),/SECRET|10\.0\.0\.8/);
 assert.equal(cards.resourceCardSummary("service",{...value,enabled:false}).status,"Disabled");
 assert.equal(cards.resourceCardSummary("service",{...value,released:true}).status,"Released");
});
test("G-19 unknown/invalid rows do not fabricate authority or expose object secrets",()=>{
 for(const wrong of [null,undefined,0,false,[],{}, {name:"no-id"}]){
  assert.equal(cards.resourceCardSummary("host",wrong),null,String(wrong));
  assert.equal(cards.resourceCardSummary("service",wrong),null,String(wrong));
 }
 assert.equal(cards.resourceCardSummary("policy",{id:"p",name:"P"}),null);
 const h=cards.resourceCardSummary("host",{id:"h-3",name:"Server",connected:"false",
   trust_status:"SUPER_ADMIN",agent_heartbeat_at:"tomorrow",admission_state:"IMPLIED_APPROVAL",
   private_key:"DO_NOT_EXPOSE"});
 assert.equal(h.status,"UNKNOWN");
 assert.deepEqual(h.facts,[
  {label:"Admission",value:"UNKNOWN"},
  {label:"Trust",value:"UNKNOWN"},
  {label:"Agent heartbeat",value:"UNKNOWN"}
 ]);
 assert.doesNotMatch(JSON.stringify(h),/DO_NOT_EXPOSE|IMPLIED_APPROVAL|SUPER_ADMIN/);
 const s=cards.resourceCardSummary("service",{id:"s-3",name:"Public Web",public_port:"443",
   managed_host:{secret:"NO"},service_type:null,enabled:"true",released:false,session_key:"PRIVATE"});
 assert.equal(s.status,"UNKNOWN");
 assert.deepEqual(s.facts.map(x=>x.value),["UNKNOWN","UNKNOWN","UNKNOWN"]);
 assert.doesNotMatch(JSON.stringify(s),/PRIVATE|"NO"/);
});
test("G-19 native Table/Cards toggle is local, accessible, responsive and keeps the same detail drawer",()=>{
 const src=readFileSync(join(root,"src","main.tsx"),"utf8");
 const page=src.split("function ResourceWorkspace(",2)[1]?.split("function UsersPanel(",1)[0]||"";
 assert.match(src,/import \{resourceCardSummary\} from "\.\/uxb-resource-cards"/);
 assert.match(page,/const \[inventoryView,setInventoryView\]=useState<"table"\|"cards">\("table"\)/);
 assert.match(page,/role="group" aria-label="Inventory view"/);
 assert.match(page,/aria-pressed=\{inventoryView==="table"\}/);
 assert.match(page,/aria-pressed=\{inventoryView==="cards"\}/);
 assert.match(page,/onClick=\{\(\)=>setInventoryView\("table"\)\}/);
 assert.match(page,/onClick=\{\(\)=>setInventoryView\("cards"\)\}/);
 assert.match(page,/inventoryView==="cards"\?<div className="dr-resource-cards"/);
 assert.match(page,/const info=resourceCardSummary\(kind,item\)/);
 assert.match(page,/className="dr-resource-card"/);
 assert.match(page,/onClick=\{\(\)=>setSelected\(item\)\}/);
 assert.match(page,/aria-label=\{"Inspect "\+heading\+" "\+info.title\}/);
 assert.match(page,/role="list"/);
 assert.match(page,/role="listitem"/);
 assert.match(page,/dr-table-scroll/);
 assert.match(page,/Partial Core inventory/);
 assert.match(page,/Filters check loaded rows only/);
 assert.match(page,/hostConnection\?\.items/);
 assert.match(page,/serviceFacets\?\.items/);
 assert.match(page,/Load more Remote Services/);
 const css=readFileSync(join(root,"dist","styles.css"),"utf8");
 assert.match(css,/\.dr-resource-cards\{[^}]*display:grid/);
 assert.match(css,/\.dr-resource-card\{[^}]*min-width:0/);
 assert.match(css,/\.dr-resource-card:focus-visible\{[^}]*outline:/);
 assert.match(css,/@media\(max-width:560px\)\{\.dr-resource-cards\{/);
});
