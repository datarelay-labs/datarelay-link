// Source-only Web contract: not a live browser, Agent or fleet-wide Core query.
import assert from "node:assert/strict";
import {test} from "node:test";
import {build} from "esbuild";
import {mkdtempSync,rmSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";

const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,"node_modules",".pfci-host-search-"));
let filterObservedHosts;
try {
  const outfile=join(scratch,"host-search.mjs");
  await build({entryPoints:[join(root,"src","uxb-host-search.ts")],outfile,
    bundle:true,platform:"node",format:"esm",logLevel:"silent"});
  ({filterObservedHosts}=await import(pathToFileURL(outfile).href));
} finally {rmSync(scratch,{recursive:true,force:true})}

const rows=[
  {id:"host-a",name:"Edge Alpha",hostname:"srv01.example",status:"active",
    trust_status:"trusted",admission_state:"APPROVED",
    agent_platform:"linux",agent_version:"3.0.0",
    token:"private-example",tags:["unprojected-tag"]},
  {id:"host-b",name:"Beta Router",hostname:"router.internal",status:"offline",
    trust_status:"revoked",admission_state:"QUARANTINED",
    agent_platform:"windows",agent_version:"2.4.0"},
  {id:"host-c",name:"Gamma",hostname:"gamma.local",status:"connected",
    trust_status:null,admission_state:"PENDING_APPROVAL",
    agent_platform:null,agent_version:null}
];
const search=(query)=>filterObservedHosts(rows,query);

test("Blank and free text only read known Core-projected fields, never arbitrary metadata",()=>{
  assert.deepEqual(search("").items.map(x=>x.id),["host-a","host-b","host-c"]);
  assert.deepEqual(search("alpha").items.map(x=>x.id),["host-a"]);
  assert.deepEqual(search("srv01").items.map(x=>x.id),["host-a"]);
  assert.deepEqual(search("private-example").items.map(x=>x.id),[]);
  assert.deepEqual(search("unprojected-tag").items.map(x=>x.id),[]);
});
test("Documented allowlisted typed facets combine as AND over observed rows",()=>{
  for(const text of ["name:edge","host:srv01","hostname:srv01","id:host-a",
    "os:linux","version:3.0","status:active","trust:trusted","admission:approved"]){
    assert.deepEqual(search(text).items.map(x=>x.id),["host-a"],text);
  }
  assert.deepEqual(search("os:linux admission:APPROVED").items.map(x=>x.id),["host-a"]);
  assert.deepEqual(search("os:linux admission:quarantined").items,[]);
});
test("Security/admission/connection typed state is exact, never substring truth",()=>{
  const source=[
    {id:"one",name:"One",status:"inactive",trust_status:"untrusted",
      admission_state:"PENDING_APPROVAL",connected:0},
    {id:"two",name:"Two",status:"active",trust_status:"trusted",
      admission_state:"APPROVED",connected:1}
  ];
  const find=(query)=>filterObservedHosts(source,query);
  for(const query of ["status:active","trust:trusted","admission:approved",
    "connected:1","connected:true","connected:connected"]){
    assert.deepEqual(find(query).items.map(r=>r.id),["two"],query);
  }
  for(const query of ["connected:0","connected:false","connected:disconnected"]){
    assert.deepEqual(find(query).items.map(r=>r.id),["one"],query);
  }
  const invalid=find("connected:maybe");
  assert.equal(invalid.applied,false);
  assert.ok(invalid.error);
});

test("Unsupported tag/group/ip facets never silently filter into an empty result",()=>{
  for(const field of ["tag","group","ip","owner","remote-desktop"]){
    const result=search(field+":test");
    assert.equal(result.applied,false,field);
    assert.equal(result.items.length,3,field);
    assert.match(result.error,/unsupported|not available|does not expose/i);
  }
});
test("Malformed queries never claim a successful search or fleet-wide completeness",()=>{
  for(const query of ["os:","hostname:","os:linux tag:sre","x".repeat(121),null,3]){
    const result=search(query);
    assert.equal(result.applied,false,String(query));
    assert.equal(result.items.length,3);
    assert.ok(result.error);
  }
  assert.equal(search("os:linux").scope,"loaded-only");
});
test("Free-text no-match does not claim absence when loaded Core fields are UNKNOWN",()=>{
  const result=search("unknown-release");
  assert.equal(result.applied,true);
  assert.equal(result.scope,"loaded-only");
  assert.deepEqual(result.items,[]);
  assert.equal(result.unknownCount,1);
  assert.match(result.warning,/UNKNOWN requested field values/);
  const blank=search("");
  assert.equal(blank.unknownCount,0);
  assert.equal(blank.warning,null);
});
test("Missing OS/trust fields are UNKNOWN, not evidence of no host or false zero",()=>{
  const os=search("os:freebsd");
  assert.equal(os.applied,true);
  assert.deepEqual(os.items,[]);
  assert.equal(os.unknownCount,1);
  assert.match(os.warning,/UNKNOWN|not observed|missing/i);
  const trust=search("trust:trusted");
  assert.deepEqual(trust.items.map(x=>x.id),["host-a"]);
  assert.equal(trust.unknownCount,1);
  assert.match(trust.warning,/UNKNOWN|not observed|missing/i);
});
