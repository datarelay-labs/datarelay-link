// UI06 fixed-field projection and role-action guard. No live user/API mutation.
import assert from "node:assert/strict";
import {test} from "node:test";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";

const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,"node_modules",".ui06-temp-access-"));
let ui06;
try{
 const out=join(scratch,"projection.mjs");
 await build({entryPoints:[join(root,"src","uxb-temporary-access-requests.ts")],
  outfile:out,bundle:true,platform:"node",format:"esm",logLevel:"silent"});
 ui06=await import(pathToFileURL(out).href);
}finally{rmSync(scratch,{recursive:true,force:true})}

const pending={
 id:"tar_abcdefghijklmnop",server_id:"srv-a",requester_actor_id:"web:wop-requester",
 requester_role:"Operator",plane:"remote",resource_type:"remote-access-rule",resource_ref:"ssh-rule",
 purpose:"Emergency maintenance",requested_duration_seconds:1800,approved_duration_seconds:null,
 requested_revision:7,status:"PENDING",created_at:"2026-10-14T08:00:00Z",
 reviewed_at:null,reviewer_actor_id:null,decision_reason:"",approved_expires_at:null,
 applied_revision:null,revoked_at:null,revoked_by_actor_id:null,revoked_revision:null,row_version:1
};

test("UI06 projection accepts only bounded fixed Core request fields",()=>{
 const row=ui06.observedTemporaryAccessRequest({...pending,secret:"DO_NOT_RENDER",nested:{token:"SECRET"}});
 assert.equal(row.id,pending.id);assert.equal(row.purpose,pending.purpose);
 assert.equal("secret" in row,false);assert.equal("nested" in row,false);
 assert.deepEqual(ui06.observedTemporaryAccessRequestPage({items:[pending],next_cursor:null,limit:50})?.items,[row]);
});

test("UI06 rejects malformed state, duration, identity, timestamps and control/bidi text",()=>{
 for(const bad of [
  {...pending,id:"request-1"},{...pending,plane:"remote",resource_type:"internet-access-rule"},
  {...pending,requested_duration_seconds:299},{...pending,requested_duration_seconds:86401},
  {...pending,purpose:"safe\u202eadmin"},{...pending,created_at:"yesterday"},
  {...pending,row_version:0},{...pending,status:"APPROVED"},
  {...pending,status:"REJECTED",reviewed_at:null,reviewer_actor_id:null},
 ]){
  assert.equal(ui06.observedTemporaryAccessRequest(bad),null,JSON.stringify(bad));
 }
 assert.equal(ui06.observedTemporaryAccessRequestPage({items:new Array(51).fill(pending),next_cursor:null,limit:50}),null);
});

test("UI06 role actions enforce distinct reviewer and approved-only revoke",()=>{
 const requester={id:"wop-requester",role:"Operator"},admin={id:"wop-admin",role:"Admin"};
 assert.equal(ui06.temporaryAccessCanReview(pending,requester),false);
 assert.equal(ui06.temporaryAccessCanReview(pending,{id:"wop-requester",role:"Admin"}),false);
 assert.equal(ui06.temporaryAccessCanReview(pending,admin),true);
 const approved={...pending,status:"APPROVED",approved_duration_seconds:900,
  approved_expires_at:"2026-10-14T08:15:00Z",applied_revision:8,
  reviewed_at:"2026-10-14T08:00:10Z",reviewer_actor_id:"web:wop-admin",row_version:2};
 assert.ok(ui06.observedTemporaryAccessRequest(approved));
 assert.equal(ui06.temporaryAccessCanRevoke(approved,requester),true);
 assert.equal(ui06.temporaryAccessCanRevoke(approved,admin),true);
 assert.equal(ui06.temporaryAccessCanRevoke(pending,admin),false);
});

test("UI06 duration labels preserve requested-vs-approved distinction",()=>{
 assert.equal(ui06.temporaryAccessDurationLabel(300),"5m");
 assert.equal(ui06.temporaryAccessDurationLabel(900),"15m");
 assert.equal(ui06.temporaryAccessDurationLabel(3600),"1h");
 assert.equal(ui06.temporaryAccessDurationLabel(86400),"24h");
 assert.equal(ui06.temporaryAccessDurationLabel(null),"—");
});

test("Actual Policies UI uses request/review/revoke endpoints and does not call direct Apply from UI06 panel",()=>{
 const main=readFileSync(join(root,"src","main.tsx"),"utf8");
 const section=readFileSync(join(root,"src","uxb-temporary-access-requests-panel.tsx"),"utf8");
 assert.match(section,/export function TemporaryAccessRequestsPanel\(\{api,operator\}/);
 assert.match(section,/\/api\/v1\/temporary-access-requests/);
 assert.match(section,/\/review/);assert.match(section,/\/revoke/);
 assert.match(section,/Request temporary access/);
 assert.match(section,/Request history/);assert.match(section,/Reviewed at/);assert.match(section,/Revoked at/);
 assert.match(section,/Read Only can inspect policy state but cannot request, review, or revoke Temporary Access/);
 assert.match(section,/Approve request/);assert.match(section,/Deny request/);
 assert.match(section,/outcome UNKNOWN/);
 assert.doesNotMatch(section,/\/api\/v1\/temporary-access\/apply/);
 assert.match(main,/TemporaryAccessRequestsPanel api=\{api\} operator=\{operator\}/);
 assert.match(main,/Advanced · direct Temporary Access/);
});
