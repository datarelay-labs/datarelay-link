// Pure projection tests only; no login/session, production Core, Agent or browser E2E.
import assert from "node:assert/strict";
import {test} from "node:test";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,"node_modules",".pfci-host-detail-"));
let hostDetailSections,hostConnectionState,hostInventoryFacts,hostVisibleIdentity;
try{
 const outfile=join(scratch,"projection.mjs");
 await build({entryPoints:[join(root,"src","uxb-host-detail.ts")],outfile,
  bundle:true,platform:"node",format:"esm",logLevel:"silent"});
 ({hostDetailSections,hostConnectionState,hostInventoryFacts,hostVisibleIdentity}=await import(pathToFileURL(outfile).href));
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

test("Host table Trust, platform, version and Core last activity fail closed on missing facts",()=>{
 const actual=hostInventoryFacts({
   id:"agent-1",trust_status:"trusted",agent_platform:"linux",
   agent_version:"3.0.1",agent_heartbeat_at:"2026-10-11T00:01:00Z",
   last_seen:"2026-10-10T23:58:00Z",
 });
 assert.deepEqual(actual,{trust:"Trusted",platform:"linux",version:"3.0.1",
   lastActivity:"2026-10-10T23:58:00Z"});
 for(const [trust,expected] of [
   ["trusted","Trusted"],["revoked","Revoked"],["untrusted","Untrusted"],
   [null,"UNKNOWN"],["legacy_tRUSTED","UNKNOWN"],[42,"UNKNOWN"]
 ]){
   assert.equal(hostInventoryFacts({trust_status:trust}).trust,expected,JSON.stringify(trust));
 }
 const noActivity=hostInventoryFacts({
   agent_heartbeat_at:"2026-10-11T00:01:00Z",connected:1,
   agent_platform:0,agent_version:"",trust_status:null
 });
 assert.equal(noActivity.lastActivity,"UNKNOWN");
 assert.equal(noActivity.platform,"UNKNOWN");
 assert.equal(noActivity.version,"UNKNOWN");
 assert.equal(noActivity.trust,"UNKNOWN");
 assert.match(flatten({trust_status:null}),/Management trust: UNKNOWN/);
 const weird=hostInventoryFacts({
   agent_platform:"linux\nINJECTED",agent_version:"x".repeat(400),
   last_seen:{nested:"secret"},trust_status:"trusted",
 });
 assert.doesNotMatch(JSON.stringify(weird),/\n/);
 assert.ok(weird.version.length<=140);
});

test("Host table never conflates Agent heartbeat with Core last-activity evidence",()=>{
 const source=readFileSync(join(root,"src","main.tsx"),"utf8");
 const resource=source.split("function ResourceWorkspace(",2)[1]?.split("function UsersPanel(",1)[0]||"";
 assert.match(resource,/hostInventoryFacts\(item\)\.trust/);
 assert.match(resource,/hostInventoryFacts\(item\)\.lastActivity/);
 assert.doesNotMatch(resource,/item\.agent_heartbeat_at\|\|item\.last_seen/);
});

test("Host list and detail heading use sanitized bounded visible names",()=>{
 const obj={id:"host-a",name:"A\u202e\nB".repeat(120),hostname:"machine\nspoofed"};
 const visible=hostVisibleIdentity(obj);
 assert.equal(visible.primary.length<=140,true);
 assert.equal(visible.secondary.length<=140,true);
 assert.ok(!/[\u202e\n]/.test(JSON.stringify(visible)));
 assert.deepEqual(hostVisibleIdentity({id:"host-a",name:" "}),
   {primary:"host-a",secondary:"host-a"});
 assert.deepEqual(hostVisibleIdentity({}),{primary:"UNKNOWN",secondary:"UNKNOWN"});
 const source=readFileSync(join(root,"src","main.tsx"),"utf8");
 const resource=source.split("function ResourceWorkspace(",2)[1]?.split("function UsersPanel(",1)[0]||"";
 assert.match(resource,/hostVisibleIdentity\(item\)\.primary/);
 assert.match(resource,/hostVisibleIdentity\(selected\)\.primary/);
});
