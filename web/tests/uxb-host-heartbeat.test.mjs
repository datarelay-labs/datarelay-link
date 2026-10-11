// G-16 independent, safe projection of Core Agent heartbeat separate from activity.
// Source tests are NOT live Agent or signed 3-role Browser E2E.
import assert from "node:assert/strict";
import {test} from "node:test";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,"node_modules",".drlink-g16-heartbeat-"));
let facts;
try{
 const outfile=join(scratch,"heartbeat.mjs");
 await build({entryPoints:[join(root,"src","uxb-host-detail.ts")],
   outfile,platform:"node",format:"esm",bundle:true,logLevel:"silent"});
 facts=await import(pathToFileURL(outfile).href);
}finally{rmSync(scratch,{recursive:true,force:true})}

test("G-16 Core timezone-qualified Agent heartbeat and Core last activity are distinct observations",()=>{
 const row={
  id:"host-a",name:"Host A",connected:false,agent_heartbeat_at:"2026-10-11T23:59:01.123Z",
  last_seen:"2026-10-10T21:00:00Z",trust_status:"trusted",agent_platform:"linux",agent_version:"3.0"
 };
 assert.deepEqual(facts.hostInventoryFacts(row),{
  trust:"Trusted",platform:"linux",version:"3.0",
  lastActivity:"2026-10-10T21:00:00Z",lastHeartbeat:"2026-10-11T23:59:01.123Z"
 });
 assert.equal(facts.hostConnectionState(row),"Disconnected",
   "heartbeat must never override observed Core connection boolean");
 const sections=facts.hostDetailSections(row);
 const matching=sections.flatMap(x=>x.fields).find(x=>x.label==="Last heartbeat");
 assert.equal(matching?.value,"2026-10-11T23:59:01.123Z");
});
test("G-16 invalid, non-timezone, contradictory and secret-bearing heartbeat never becomes a literal status",()=>{
 const base={id:"host-1",last_seen:"2026-10-12T00:00:00Z",connected:true};
 for(const bad of [
   null,undefined,42,{},["2026-10-12T00:00:00Z"],"",
   "now","2026-02-30T08:00:00Z","2025-02-29T00:00:00Z",
   "2026-10-12","2026-10-12T08:00:00",
   "2026-10-12T08:00:00+14:30",
   "2026-10-12T08:00:00Z\u202eTOKEN",
   "2026-10-12T08:00:00Z"+"X".repeat(100)
 ]){
  const candidate={...base,agent_heartbeat_at:bad};
  assert.equal(facts.hostInventoryFacts(candidate).lastHeartbeat,"UNKNOWN",String(bad));
  const detail=facts.hostDetailSections(candidate).flatMap(x=>x.fields)
    .find(x=>x.label==="Last heartbeat");
  assert.equal(detail?.value,"UNKNOWN",String(bad));
  assert.equal(facts.hostConnectionState(candidate),"Connected","Core connected state remains independent");
 }
 const out=JSON.stringify(facts.hostInventoryFacts({
  ...base,agent_heartbeat_at:{token:"PRIVATE_KEY"},password:"OTHER_PRIVATE_KEY"
 }));
 assert.doesNotMatch(out,/PRIVATE_KEY/);
});
test("G-16 exact leap day, offset and missing optional dates are visible without runtime freshness inference",()=>{
 for(const date of ["2028-02-29T02:00:00Z","2026-10-12T00:01:00+09:00",
   "2026-10-12T10:11:12.123456789Z"]){
  assert.equal(facts.hostInventoryFacts({agent_heartbeat_at:date}).lastHeartbeat,date);
 }
 assert.equal(facts.hostInventoryFacts({last_seen:"2026-10-12T04:00:00Z"}).lastHeartbeat,"UNKNOWN");
 assert.equal(facts.hostInventoryFacts({agent_heartbeat_at:"2026-10-12T04:00:00Z"}).lastActivity,"UNKNOWN");
});
test("G-16 Hosts list shows independent Agent heartbeat and Last activity from exact Core projection",()=>{
 const main=readFileSync(join(root,"src","main.tsx"),"utf8");
 const view=main.split("function ResourceWorkspace(",2)[1]?.split("function UsersPanel(",1)[0]||"";
 assert.match(view,/<th>Agent heartbeat<\/th><th>Last activity<\/th>/);
 assert.match(view,/hostInventoryFacts\(item\)\.lastHeartbeat/);
 assert.match(view,/hostInventoryFacts\(item\)\.lastActivity/);
 assert.match(view,/Agent heartbeat and Core Last activity are separate observations/);
 assert.match(view,/not a verified active tunnel or policy decision/);
 assert.match(view,/Partial Core inventory/);
 assert.match(view,/Load more Managed Hosts/);
 assert.match(view,/hostConnectionState\(item\)/);
 assert.doesNotMatch(view,/Last heartbeat.*?just now|heartbeat==connected/);
 const backend=readFileSync(join(dirname(root),"lib","drlink_management_service.py"),"utf8");
 assert.match(backend,/c\.agent_heartbeat_at AS agent_heartbeat_at/);
});
