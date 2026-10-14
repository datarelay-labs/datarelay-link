// G-11: original, loaded-only Core Host connection-state filter. Not live Agent/Browser E2E.
import assert from "node:assert/strict";
import {test} from "node:test";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,"node_modules",".drl3-host-connection-filter-"));
let filtering;
try {
 const output=join(scratch,"helper.mjs");
 await build({entryPoints:[join(root,"src","uxb-host-connection-filter.ts")],
    bundle:true,platform:"node",format:"esm",outfile:output,logLevel:"silent"});
 filtering=await import(pathToFileURL(output).href);
}finally{rmSync(scratch,{recursive:true,force:true})}
const hosts=[
 {id:"a",name:"Host A",connected:true,admission_state:"APPROVED"},
 {id:"b",name:"Host B",connected:1,admission_state:"APPROVED"},
 {id:"c",name:"Host C",connected:false,admission_state:"QUARANTINED"},
 {id:"d",name:"Host D",connected:0},
 {id:"e",name:"Host E"},
 {id:"f",name:"Host F",connected:null},
 {id:"g",name:"Host G",connected:"false"},
 {id:"h",name:"Host H",connected:{private_token:"must never stringify"}},
];
const ids=(state,rows=hosts)=>filtering.filterLoadedHostConnections(rows,state).items.map(x=>x.id);
test("G-11 read-only exact loaded Host connection boolean/SQLite states",()=>{
 assert.deepEqual(ids("all"),hosts.map(x=>x.id));
 assert.deepEqual(ids("connected"),["a","b"]);
 assert.deepEqual(ids("disconnected"),["c","d"]);
 assert.deepEqual(ids("unknown"),["e","f","g","h"]);
 const view=filtering.filterLoadedHostConnections(hosts,"disconnected");
 assert.equal(view.loadedCount,8);
 assert.equal(view.unknownCount,4);
 assert.equal(view.scope,"loaded-only");
 assert.equal(view.error,null);
 assert.equal(view.items[0],hosts[2]);
});
test("G-11 fails closed on unsupported selector, bad inventory, and never mutates Core Host rows",()=>{
 for(const selection of ["", "Connection", "ONLINE", "Disconnected", "connected ", null, undefined, 1, {}, []]){
  const value=filtering.filterLoadedHostConnections(hosts,selection);
  assert.deepEqual(value.items,[],String(selection));
  assert.match(value.error,/state|filter/i);
 }
 for(const value of [undefined,null,{items:hosts}, {}, "hosts"]){
  const result=filtering.filterLoadedHostConnections(value,"all");
  assert.deepEqual(result.items,[]);
  assert.ok(result.error);
 }
 const input=[...hosts, {connected:1}, null, [],{id:"",name:"Bad",connected:1}];
 const result=filtering.filterLoadedHostConnections(input,"connected");
 assert.deepEqual(result.items.map(x=>x.id),["a","b"]);
 assert.equal(result.unknownCount,8); // four valid UNKNOWN plus four excluded invalid records
 assert.equal(hosts[7].connected.private_token,"must never stringify");
});
test("G-11 intersects existing Host typed and admission filters without inventing a fleet search",()=>{
 const prefiltered=hosts.filter(x=>x.admission_state==="APPROVED");
 assert.deepEqual(ids("connected",prefiltered),["a","b"]);
 assert.deepEqual(ids("disconnected",prefiltered),[]);
 assert.equal(filtering.filterLoadedHostConnections(prefiltered,"disconnected").unknownCount,0);
});
test("G-11 Host UI supports accessible state buttons, partial/UNKNOWN warnings, no new API or saved-filter fiction",()=>{
 const src=readFileSync(join(root,"src","main.tsx"),"utf8");
 const host=src.split("function ResourceWorkspace(",2)[1]?.split("function UsersPanel(",1)[0]||"";
 assert.match(host,/const \[connectionFilter,setConnectionFilter\]=useState/);
 assert.match(host,/filterLoadedHostConnections\(hostSearch\?\.items\|\|\[\],connectionFilter\)/);
 assert.match(host,/role="group" aria-label="Filter loaded Host connection state"/);
 assert.match(host,/aria-pressed=\{connectionFilter===status\}/);
 assert.match(host,/onClick=\{\(\)=>setConnectionFilter\(status\)\}/);
 assert.match(host,/All connections/);
 assert.match(host,/Connected/);
 assert.match(host,/Disconnected/);
 assert.match(host,/UNKNOWN/);
 assert.match(host,/some loaded Host.*UNKNOWN|UNKNOWN connectivity.*absence/i);
 assert.match(host,/Connection quick filter is not saved/);
 assert.match(host,/\bLoad more Managed Hosts/);
 assert.match(host,/Partial Core inventory/);
 assert.match(host,/hostConnectionState\(item\)/);
 const css=readFileSync(join(root,"dist","styles.css"),"utf8");
 assert.match(css,/\.dr-form-actions\{[^}]*flex-wrap:wrap/);
});
