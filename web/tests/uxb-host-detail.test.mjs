// Pure projection tests only; no login/session, production Core, Agent or browser E2E.
import assert from "node:assert/strict";
import {test} from "node:test";
import {build} from "esbuild";
import {mkdtempSync,rmSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,"node_modules",".pfci-host-detail-"));
let hostDetailSections,hostConnectionState;
try{
 const outfile=join(scratch,"projection.mjs");
 await build({entryPoints:[join(root,"src","uxb-host-detail.ts")],outfile,
  bundle:true,platform:"node",format:"esm",logLevel:"silent"});
 ({hostDetailSections,hostConnectionState}=await import(pathToFileURL(outfile).href));
}finally{rmSync(scratch,{recursive:true,force:true})}
const flatten=v=>hostDetailSections(v).flatMap(x=>x.fields.map(y=>y.label+": "+y.value)).join(" | ");

test("Three ordered task-specific groups with bounded safe host facts",()=>{
 const groups=hostDetailSections({
   id:"host-22",name:"Test Server",hostname:"db.example.org",label:"Finance node",
   trust_status:"trusted",admission_state:"PENDING_APPROVAL",connected:false,
   agent_platform:"linux",agent_version:"3.0.0",last_seen:"2026-10-10T02:00:00Z"
 });
 assert.deepEqual(groups.map(x=>x.title),["Identity","Trust & Admission","Connectivity & Version"]);
 const fields=groups.flatMap(x=>x.fields);
 assert.ok(fields.some(x=>x.label==="Admission"&&x.value==="Pending approval"));
 assert.ok(fields.some(x=>x.label==="Connection"&&x.value==="Disconnected"));
 assert.ok(fields.some(x=>x.label==="Host ID"&&x.value==="host-22"));
 assert.ok(fields.some(x=>x.label==="Agent version"&&x.value==="3.0.0"));
});

test("Host list and drawer must use one evidence-qualified tri-state Core connection fact",()=>{
  for(const [raw,expected] of [
    [true,"Connected"],[1,"Connected"],
    [false,"Disconnected"],[0,"Disconnected"],
    [null,"UNKNOWN"],[undefined,"UNKNOWN"],
    ["true","UNKNOWN"],["false","UNKNOWN"],[2,"UNKNOWN"],
  ]){
    const row={id:"host-a",connected:raw,status:"active",
      agent_lifecycle_state:"connected"};
    assert.equal(hostConnectionState(row),expected);
    const detail=flatten(row);
    assert.ok(detail.includes("Connection: "+expected),String(raw));
  }
});

test("SQLite numeric 0/1 connection state does not become UNKNOWN",()=>{
 assert.match(flatten({id:"node-a",connected:1}),/Connection: Connected/);
 assert.match(flatten({id:"node-b",connected:0}),/Connection: Disconnected/);
 assert.match(flatten({id:"node-c",connected:2}),/Connection: UNKNOWN/);
 assert.match(flatten({id:"node-d",connected:"1"}),/Connection: UNKNOWN/);
});

test("No observed Core state means UNKNOWN, never Approved or Connected",()=>{
 const text=flatten({id:"unknown-node"});
 assert.match(text,/Admission: UNKNOWN/);
 assert.match(text,/Management trust: UNKNOWN/);
 assert.match(text,/Connection: UNKNOWN/);
 assert.doesNotMatch(text,/Approved|Connected/);
 for(const value of [null,[],{}])assert.match(flatten(value),/Host identity: UNKNOWN/);
});

test("Never project arbitrary object keys, secret strings or nested values",()=>{
 const out=JSON.stringify(hostDetailSections({
  id:"safe-host",name:"Visible",token:"HIDDEN_TOKEN_X",password:"HIDDEN_PASSWORD_X",
  private_key:"HIDDEN_RSA_X",credential:"HIDDEN_CREDENTIAL_X",
  csrf_token:"HIDDEN_CSRF_X",session_cookie:"HIDDEN_COOKIE_X",
  metadata:{raw_secret:"HIDDEN_META_X"},
  agent_platform:{nested:"hidden"}, admission_state:"UNRECOGNIZED",
  connected:"true",
 }));
 for(const bad of ["HIDDEN_","metadata","password","private_key","cookie","csrf","session"]) {
  assert.ok(!out.includes(bad),bad);
 }
 assert.match(out,/UNKNOWN/);
 assert.doesNotMatch(out,/Connected/);
});

test("Control text sanitized, bounded, with safe explicit field names only",()=>{
 const strange="S".repeat(330)+"\u202e\nTOKENISH";
 const group=hostDetailSections({name:strange,description:" D\u0000e\u007fscription "});
 const fields=group.flatMap(x=>x.fields);
 const title=fields.find(x=>x.label==="Host name");
 assert.ok(title&&title.value.length<=140);
 assert.ok(!JSON.stringify(fields).includes("\u202e"));
 assert.ok(!JSON.stringify(fields).includes("\u0000"));
 assert.ok(!JSON.stringify(fields).includes("\n"));
});
