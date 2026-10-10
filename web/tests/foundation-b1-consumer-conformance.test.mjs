// Source-only PF-5B B1 Administration consumer conformance. No browser
// process, actual Core requests, identity seeding or preview mutation.
import assert from "node:assert/strict";
import {after, before, test} from "node:test";
import {mkdtempSync, readFileSync, rmSync} from "node:fs";
import {dirname, join} from "node:path";
import {fileURLToPath, pathToFileURL} from "node:url";
import {build} from "esbuild";
import {
  effectiveAdministrationAvailability
} from "@datarelay-labs/system-admin-ui";
import {verifyAdministrationConsumer} from "@datarelay-labs/testkit";

const webRoot=dirname(dirname(fileURLToPath(import.meta.url)));
const locked=JSON.parse(readFileSync(join(webRoot,"foundation.lock.json"),"utf8"));
let temp, createTasks;

before(async () => {
  temp=mkdtempSync(join(webRoot,"node_modules",".pf5b-b1-consumer-"));
  const outfile=join(temp,"link-projection.mjs");
  await build({
    entryPoints:[join(webRoot,"src","foundation-administration.ts")],
    outfile,bundle:true,platform:"node",format:"esm",
    external:["@datarelay-labs/foundation"],logLevel:"silent"
  });
  ({createLinkFoundationAdministrationTasks:createTasks}=await import(pathToFileURL(outfile).href));
});
after(() => {if(temp)rmSync(temp,{recursive:true,force:true});});

function actualLinkActionIds() {
  // Read the existing Link Web dispatch switch; do not invent a passing
  // provider list that could conceal a missing native UI action.
  const source=readFileSync(join(webRoot,"src","main.tsx"),"utf8");
  const start=source.indexOf("function LinkFoundationAdministration(");
  const end=source.indexOf("function SystemPanel(",start);
  assert.ok(start>=0 && end>start,"Link Administration dispatch must exist");
  const section=source.slice(start,end);
  const actions=[...section.matchAll(/case ["'](link\.[a-z0-9._-]+)["']\s*:/g)].map(match=>match[1]);
  assert.equal(new Set(actions).size,actions.length);
  assert.deepEqual(actions.sort(),[
    "link.users","link.audit","link.health","link.certificate","link.backup"
  ].sort());
  return actions;
}

function preflight(role, registeredActionIds=actualLinkActionIds()) {
  const tasks=createTasks(role);
  return verifyAdministrationConsumer({
    composition:{productId:"link",tasks},
    registeredPaths:[],
    registeredActionIds,
    requiredCoreTaskIds:role==="Admin"
      ? ["core.users","core.https","core.audit","core.health","core.backup-import"]
      : role==="Operator"||role==="Read Only"
        ? ["core.https","core.audit","core.health","core.backup-import"] : []
  });
}

test("exact Foundation B1 compiled Testkit is installed for the Link consumer", () => {
  assert.equal(locked.source_head,"8726549f80f85b79d94e91a87324d2523e27ddbb");
  assert.equal(locked.version,"0.1.0-pf8.4");
  assert.equal(locked.packages.length,10);
  assert.equal(typeof verifyAdministrationConsumer,"function");
});

for(const role of ["Admin","Operator","Read Only"]) {
  test(role+" matches canonical B1 task metadata and live Web dispatch action IDs", () => {
    assert.deepEqual(preflight(role),{ok:true,findings:[]});
    const tasks=createTasks(role);
    assert.equal(tasks.length,9);
    assert.deepEqual(tasks.map(task=>task.groupId),[
      "access-security","access-security","access-security",
      "platform-network","platform-network","lifecycle-recovery",
      "lifecycle-recovery","operations-audit","operations-audit"
    ]);
    assert.equal(tasks.filter(task=>effectiveAdministrationAvailability(task)==="supported").length,
      role==="Admin"?1:0);
    assert.equal(tasks.find(task=>task.id==="core.users").access,role==="Admin"?"manage":"none");
  });
}

test("unrecognized or missing product role never creates an actionable Administration menu", () => {
  for(const role of ["","Unknown","Administrator","admin","VIEWER","anonymous"]) {
    const tasks=createTasks(role);
    assert.equal(tasks.length,9);
    assert.deepEqual(
      tasks.filter(task=>effectiveAdministrationAvailability(task)!=="unavailable").map(task=>task.id),
      [],
      "Unexpected role "+JSON.stringify(role)+" must not show task actions"
    );
    assert.deepEqual(preflight(role),{ok:true,findings:[]});
  }
});

test("backup task is read-only and backed by existing Link native validator", () => {
  const source=readFileSync(join(webRoot,"src","main.tsx"),"utf8");
  const dispatch=source.split("function LinkFoundationAdministration(",2)[1].split("function SystemPanel(",1)[0];
  const system=source.split("function SystemPanel(",2)[1].split("function AccessOperations(",1)[0];
  assert.ok(dispatch.includes('case "link.backup":'));
  assert.ok(dispatch.includes('getElementById("drlink-backup-status")'));
  assert.ok(system.includes('id="drlink-backup-status"'));
  assert.ok(system.includes('onClick={validateBackup}'));
  assert.ok(system.includes('operator.role==="Admin"&&<button className="primary" onClick={createBackup}'));
  assert.ok(system.includes('operator.role==="Admin"&&validation?.valid'));
  for(const role of ["Admin","Operator","Read Only"]){
    const task=createTasks(role).find(task=>task.id==="core.backup-import");
    assert.equal(task.availability,"read_only");
    assert.equal(task.access,"view");
    assert.equal(task.target?.kind,"action");
    assert.equal(task.target?.actionId,"link.backup");
    assert.match(task.notes,/validation/i);
    assert.match(task.notes,/import.*unavailable/i);
  }
  const unknown=createTasks("Unknown").find(task=>task.id==="core.backup-import");
  assert.equal(unknown.access,"none");
  assert.equal(unknown.target,undefined);
});

test("missing real Link callback produces a structural failure, not a fabricated PASS", () => {
  const wrongActions=actualLinkActionIds().filter(id=>id!=="link.audit");
  const report=preflight("Admin",wrongActions);
  assert.equal(report.ok,false);
  assert.ok(report.findings.some(x=>x.id==="ADMIN_TARGET_UNREGISTERED"&&x.message.includes("core.audit")));
});

test("role/view action cannot be upgraded by invented Web action registrations", () => {
  const report=preflight("Read Only",[...actualLinkActionIds(),"link.fake.write"]);
  assert.deepEqual(report,{ok:true,findings:[]});
  const tasks=createTasks("Read Only");
  assert.equal(tasks.find(task=>task.id==="core.users").target,undefined);
});
