// G-13 independently implemented Core-loaded Service type/configuration facets.
// Source contract test only; NOT authenticated Browser/Agent/full-user E2E.
import assert from "node:assert/strict";
import {test} from "node:test";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";

const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,"node_modules",".drl3-service-facets-"));
let filterLoadedServiceFacets;
try {
 const outfile=join(scratch,"facets.mjs");
 await build({entryPoints:[join(root,"src","uxb-service-facets.ts")],
   outfile,bundle:true,platform:"node",format:"esm",logLevel:"silent"});
 ({filterLoadedServiceFacets}=await import(pathToFileURL(outfile).href));
}finally{rmSync(scratch,{recursive:true,force:true})}

const rows=[
 {id:"tcp",name:"TCP published",service_type:"tcp",enabled:true,released:false,token:"DO_NOT_EXPOSE"},
 {id:"ssh",name:"SSH published",service_type:"ssh",enabled:1,released:0},
 {id:"http",name:"HTTP disabled",service_type:"http",enabled:0,released:0},
 {id:"https",name:"HTTPS released",service_type:"https",enabled:true,released:true},
 {id:"missing",name:"Missing type",service_type:null,enabled:null,released:false},
 {id:"future",name:"Future type",service_type:"new_protocol",enabled:true,released:0},
 {id:"malformed",name:"Malformed type",service_type:{secret:"CREDENTIAL"},enabled:"true",released:false},
];
const ids=(kind="all",state="all",source=rows)=>
 filterLoadedServiceFacets(source,kind,state).items.map(x=>x.id);

test("G-13 displays only Core-observed exact Service kind and configuration-state labels",()=>{
 assert.deepEqual(ids(),rows.map(x=>x.id));
 for(const kind of ["tcp","ssh","http","https"])
  assert.deepEqual(ids(kind),[kind],kind);
 assert.deepEqual(ids("unknown"),["missing","future","malformed"]);
 assert.deepEqual(ids("all","enabled"),["tcp","ssh","future"]);
 assert.deepEqual(ids("all","disabled"),["http"]);
 assert.deepEqual(ids("all","released"),["https"]);
 assert.deepEqual(ids("all","unknown"),["missing","malformed"]);
 assert.deepEqual(ids("tcp","enabled"),["tcp"]);
 assert.deepEqual(ids("https","disabled"),[]);
 const observed=filterLoadedServiceFacets(rows,"tcp","enabled");
 assert.equal(observed.items[0],rows[0],"must not clone or mutate Core rows");
 assert.equal(observed.scope,"loaded-only");
 assert.equal(observed.loadedCount,rows.length);
 assert.equal(observed.unknownTypeCount,3);
 assert.equal(observed.unknownStateCount,2);
 assert.equal(observed.error,null);
});
test("G-13 fails closed on invalid filters; no inferred presence from malformed inventory",()=>{
 for(const kind of [null,undefined,2,"","TCP","udP","all ","../tcp",{},[]]){
  const result=filterLoadedServiceFacets(rows,kind,"all");
  assert.deepEqual(result.items,[],String(kind));
  assert.match(result.error,/filter|invalid/i);
 }
 for(const state of [null,undefined,true,"","online","active","Enabled","disconnected","unknown ",{},[]]){
  const result=filterLoadedServiceFacets(rows,"all",state);
  assert.deepEqual(result.items,[],String(state));
  assert.match(result.error,/filter|invalid/i);
 }
 for(const input of [null,undefined,{items:rows},"oops",{}]){
  const result=filterLoadedServiceFacets(input,"all","all");
  assert.deepEqual(result.items,[]);
  assert.match(result.error,/Core|inventory/i);
 }
 const untrusted=[...rows,null,[],{id:"",name:"No identity",service_type:"tcp"},
  {id:"id-only",service_type:"tcp"},{id:{value:"secret"},name:"unsafe",service_type:"tcp"}];
 const filtered=filterLoadedServiceFacets(untrusted,"tcp","all");
 assert.deepEqual(filtered.items.map(x=>x.id),["tcp"]);
 assert.equal(filtered.invalidCount,5);
 assert.equal(filtered.unknownTypeCount,8);
 assert.equal(filtered.unknownStateCount,7);
 assert.equal(filtered.items[0],rows[0],"facets retain the original Core row for existing safe presentation");
});
test("G-13 quick facets respect upstream loaded/text-filtered Core scope",()=>{
 const textFiltered=rows.filter(x=>x.name.includes("published"));
 assert.deepEqual(ids("ssh","enabled",textFiltered),["ssh"]);
 assert.deepEqual(ids("tcp","enabled",textFiltered),["tcp"]);
 assert.deepEqual(ids("https","released",textFiltered),[]);
 assert.deepEqual(ids("https","released",rows.filter(x=>x.name.includes("released"))),["https"]);
 assert.deepEqual(ids("http","disabled",textFiltered),[]);
 assert.equal(filterLoadedServiceFacets(textFiltered,"tcp","disabled").scope,"loaded-only");
});
test("G-13 Web renders accessible local facets, avoids Core write and preserves user navigation",()=>{
 const source=readFileSync(join(root,"src","main.tsx"),"utf8");
 const scope=source.split("function ResourceWorkspace(",2)[1]?.split("function UsersPanel(",1)[0]||"";
 assert.match(scope,/const \[serviceTypeFilter,setServiceTypeFilter\]=useState/);
 assert.match(scope,/const \[serviceConfigFilter,setServiceConfigFilter\]=useState/);
 assert.match(scope,/filterLoadedServiceFacets\(serviceSearch\?\.items\|\|\[\],serviceTypeFilter,serviceConfigFilter\)/);
 assert.match(scope,/role="group" aria-label="Filter loaded Service types"/);
 assert.match(scope,/role="group" aria-label="Filter loaded Service configuration states"/);
 assert.match(scope,/aria-pressed=\{serviceTypeFilter===kind\}/);
 assert.match(scope,/aria-pressed=\{serviceConfigFilter===state\}/);
 assert.match(scope,/type="button"/);
 assert.match(scope,/onClick=\{\(\)=>setServiceTypeFilter\(kind\)\}/);
 assert.match(scope,/onClick=\{\(\)=>setServiceConfigFilter\(state\)\}/);
 assert.match(scope,/All types/);
 assert.match(scope,/All configurations/);
 assert.match(scope,/UNKNOWN/);
 assert.match(scope,/Service quick facets are not saved/);
 assert.match(scope,/Loaded Core Service facts do not prove live reachability/);
 assert.match(scope,/serviceStateLabel\(item\)/);
 assert.match(scope,/serviceSearch\?\.warning/);
 assert.match(scope,/Partial Core inventory/);
 assert.match(scope,/Load more Remote Services/);
 const helper=readFileSync(join(root,"src","uxb-service-facets.ts"),"utf8");
 assert.doesNotMatch(helper,/\b(?:fetch|api|localStorage|sessionStorage|eval)\s*\(/);
 const css=readFileSync(join(root,"dist","styles.css"),"utf8");
 assert.match(css,/\.dr-form-actions\{[^}]*flex-wrap:wrap/);
});
