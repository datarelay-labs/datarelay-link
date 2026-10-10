// Pure, loaded-only Core Remote Service search; not server-side or fleet-wide discovery.
import assert from "node:assert/strict";
import {test} from "node:test";
import {build} from "esbuild";
import {readFileSync,mkdtempSync,rmSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";

const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,"node_modules",".pfci-service-search-"));
let filterObservedServices;
try{
 const file=join(scratch,"search.mjs");
 await build({entryPoints:[join(root,"src","uxb-service-search.ts")],outfile:file,
  platform:"node",format:"esm",bundle:true,logLevel:"silent"});
 ({filterObservedServices}=await import(pathToFileURL(file).href));
}finally{rmSync(scratch,{recursive:true,force:true})}
const rows=[
 {id:"ssh-1",name:"Admin SSH",managed_host:"jump01",managed_host_id:"host-1",
  service_type:"tcp",target_host:"10.0.1.8",target_mode:"this-host",
  public_port:2222,target_port:22,enabled:1,released:0,token:"SECRET_CREDENTIAL"},
 {id:"web-2",name:"Portal HTTPS",managed_host:"web01",managed_host_id:"host-2",
  service_type:"tcp",target_host:"10.0.2.10",target_mode:"host",
  public_port:443,target_port:8443,enabled:0,released:0,private_key:"SECRET_KEY"},
 {id:"db-3",name:"DB Gate",managed_host:"db01",managed_host_id:"host-3",
  service_type:"tcp",target_host:"10.0.3.30",
  public_port:null,target_port:5432,enabled:1,released:1},
];

test("Named Host/Service/port/state filters only inspect observed Core inventory fields",()=>{
 for(const [q,ids] of [
  ["ssh",["ssh-1"]],["name:portal",["web-2"]],["host:jump",["ssh-1"]],
  ["host:host-2",["web-2"]],["port:22",["ssh-1"]],
  ["port:2222",["ssh-1"]],["port:8443",["web-2"]],
  ["state:enabled",["ssh-1"]],["state:disabled",["web-2"]],
  ["state:released",["db-3"]],["type:tcp",["ssh-1","web-2","db-3"]],
  ["state:enabled host:jump",["ssh-1"]],
 ]){
  const result=filterObservedServices(rows,q);
  assert.equal(result.applied,true,q);
  assert.deepEqual(result.items.map(x=>x.id),ids,q);
  assert.equal(result.scope,"loaded-only");
 }
});

test("Unapproved Core fields and malformed expressions never search secrets or claim no matches",()=>{
 for(const q of ["token:SECRET","ip:10.0","password:q","port:abc","port:0",
  "state:maybe","name:","host:","bad:name","x".repeat(121),"name:SSH\u202e"]){
  const result=filterObservedServices(rows,q);
  assert.equal(result.applied,false,q);
  assert.ok(result.error,q);
  assert.equal(result.items.length,rows.length,q);
 }
 assert.deepEqual(filterObservedServices(rows,"SECRET").items,[]);
 assert.equal(filterObservedServices(rows,"SECRET").scope,"loaded-only");
 assert.equal(filterObservedServices(null,"").error?.includes("unavailable"),true);
});

test("Incomplete/malformed Core rows and partial service facts stay visibly UNKNOWN",()=>{
 const partial=[
  ...rows,{id:"broken",name:"Broken Service",managed_host:null,
    service_type:null,public_port:null,target_port:null,enabled:null,released:null},
  {name:"no-id"},{id:"missing-name"},
 ];
 const match=filterObservedServices(partial,"host:jump");
 assert.deepEqual(match.items.map(x=>x.id),["ssh-1"]);
 assert.ok(match.unknownCount>0);
 assert.match(match.warning||"",/UNKNOWN|invalid/i);
 const noMatch=filterObservedServices(partial,"host:unobserved");
 assert.equal(noMatch.items.length,0);
 assert.match(noMatch.warning||"",/cannot prove absence|incomplete/i);
 const bad=filterObservedServices([{name:"only"}],"");
 assert.equal(bad.applied,false);
 assert.ok(bad.error);
});

test("Remote Service page wiring shows actual filtered Core page only, not whole fleet",()=>{
 const source=readFileSync(join(root,"src","main.tsx"),"utf8");
 const page=source.split("function ResourceWorkspace(",2)[1]?.split("function UsersPanel(",1)[0]||"";
 assert.match(source,/import \{filterObservedServices\} from "\.\/uxb-service-search"/);
 assert.match(page,/const serviceSearch=isHost\?null:filterObservedServices\(loaded,filter\)/);
 assert.match(page,/serviceSearch\?\.items/);
 assert.match(page,/serviceSearch\?\.error/);
 assert.match(page,/serviceSearch\?\.warning/);
 assert.match(page,/Load more Remote Services/);
 assert.doesNotMatch(page,/Object\.values\(item\)\.some/);
});
