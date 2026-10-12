// M2 Web Admin Operator inventory and MFA Core confirmation contract.
// No real operator credentials/session/hostname, no E2E, no production writes.
import assert from "node:assert/strict";
import {test} from "node:test";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,"node_modules",".drlink-m2-users-contract-"));
let view;
try{
 const outfile=join(scratch,"users.mjs");
 await build({entryPoints:[join(root,"src","uxb-users-state.ts")],outfile,
  platform:"node",format:"esm",bundle:true,logLevel:"silent"});
 view=await import(pathToFileURL(outfile).href);
}finally{rmSync(scratch,{recursive:true,force:true})}
const id="wop_"+"a".repeat(24),id2="wop_"+"b".repeat(24);
const operator={id,username:"alice.admin",role:"Admin",enabled:true,
 recovery_admin:true,mfa_required:true,mfa_enrolled:false,
 last_login_at:null,created_at:"2026-10-11T00:00:00Z",
 updated_at:"2026-10-12T00:00:00Z",
 mfa_secret_ciphertext:"SECRET_NOT_FOR_UI",token_hash:"HIDDEN_KEY"};
const inventory=rows=>view.observedOperatorInventory(rows);
const receipt=(data,requestedId=id,required=true)=>
 view.observedOperatorMfaReceipt(data,requestedId,required);

test("M2 authenticated Core users list must be precisely observed and redacted before UI",()=>{
 assert.deepEqual(inventory([operator]),[{
  id,username:"alice.admin",role:"Admin",enabled:true,recovery_admin:true,
  mfa_required:true,mfa_enrolled:false,last_login_at:null
 }]);
 assert.equal(view.operatorMfaAction(inventory([operator])[0]).required,false);
 assert.equal(view.operatorLastLogin(inventory([operator])[0]),"Never");
 assert.doesNotMatch(JSON.stringify(inventory([operator])),/SECRET_NOT_FOR_UI|HIDDEN_KEY|mfa_secret|hash/);
 assert.deepEqual(inventory([]),[]);
});

test("M2 malformed operator ID/user/role/duplicates/overcap cannot become actionable MFA targets",()=>{
 for(const invalid of [
  {...operator,id:{token:"DONT_SHOW"}},{...operator,id:"wop_../../admin"},
  {...operator,username:{password:"DONT_SHOW"}},{...operator,username:"alice\u202e"},
  {...operator,username:"alice with spaces"},
  {...operator,role:"SuperAdmin"},{...operator,role:"read only"}
 ])assert.equal(inventory([invalid]),null);
 for(const invalid of [undefined,null,{},[null],[[1]],["a"],
  Array.from({length:501},()=>operator),[operator,operator]])
  assert.equal(inventory(invalid),null);
 assert.equal(inventory([operator,{...operator,id:id2,username:"bob"}]).length,2);
});

test("M2 untrusted Core MFA booleans or last-login do not gain button authority",()=>{
 const projected=inventory([{...operator,mfa_required:"true",
  mfa_enrolled:{password:"DONT_SHOW"},last_login_at:"yesterday",
  recovery_admin:"true",enabled:"true"}]);
 assert.equal(projected.length,1);
 assert.equal(view.operatorMfaAction(projected[0]).required,null);
 assert.equal(view.operatorMfaState(projected[0]),"UNKNOWN");
 assert.equal(view.operatorAccountState(projected[0]),"UNKNOWN");
 assert.equal(view.operatorLastLogin(projected[0]),"UNKNOWN");
 assert.equal(projected[0].recovery_admin,undefined);
 assert.doesNotMatch(JSON.stringify(projected),/DONT_SHOW|yesterday|password/);
});

test("M2 Core MFA write receipt must bind exact operator ID/intent and acknowledge sessions",()=>{
 const result={operator_id:id,username:"alice.admin",mfa_required:true,
  mfa_enrolled:false,changed:true,sessions_revoked:2};
 assert.deepEqual(receipt(result),{
  operator_id:id,mfa_required:true,changed:true,sessions_revoked:2
 });
 assert.deepEqual(receipt({...result,mfa_required:false,changed:false,
  mfa_enrolled:true,sessions_revoked:0},id,false),{
    operator_id:id,mfa_required:false,changed:false,sessions_revoked:0
 });
 assert.equal(receipt({...result,operator_id:id2}),null);
 for(const changes of [
  {mfa_required:"true"},{mfa_enrolled:null},{changed:"true"},
  {sessions_revoked:-1},{sessions_revoked:"2"},{sessions_revoked:1.2},
  {username:{password:"SECRET"}},{username:"unsafe\nname"},
  {changed:false,sessions_revoked:1},
  {changed:true,mfa_enrolled:true},
 ])assert.equal(receipt({...result,...changes}),null,JSON.stringify(changes));
 assert.equal(receipt(null),null);
 assert.equal(receipt(result,"/../../admin"),null);
});

test("M2 UsersPanel uses Core projection before state and verified receipt before any reload/write-success",()=>{
 const main=readFileSync(join(root,"src","main.tsx"),"utf8");
 const panel=main.split("function UsersPanel(",2)[1]?.split("function IntegrationsPanel(",1)[0]||"";
 assert.match(main,/import \{observedOperatorInventory,observedOperatorMfaReceipt,observedOperatorCreateReceipt\} from "\.\/uxb-users-state"/);
 assert.match(panel,/const observed=observedOperatorInventory\(page.items\)/);
 assert.match(panel,/if\(!observed\)throw new Error\(/);
 assert.match(panel,/setData\(\{items:observed\}\)/);
 assert.doesNotMatch(panel,/setData\(requireObservedMenuPayload\("users"/);
 assert.match(panel,/const receipt=observedOperatorMfaReceipt\(result,id,required\)/);
 assert.match(panel,/if\(!receipt\)throw new Error\(/);
 assert.match(panel,/if\(id===operator.id\)\{window.location.reload\(\);return\}/);
 assert.match(panel,/Core MFA change outcome UNKNOWN/);
 assert.match(panel,/Inspect Users and Audit before retrying/);
 assert.match(panel,/operatorMfaAction\(x\)/);
 assert.match(panel,/mfaChange.required===null/);
 assert.match(panel,/api\("\/api\/v1\/operators\/"\+encodeURIComponent\(id\)\+"\/mfa"/);
});


test("M2 Core operator create acknowledgment requires exact generated identity, role and default-OFF MFA",()=>{
 const expected={operator_id:id2,username:"bob",role:"Operator",
  mfa_required:false,mfa_enrolled:false};
 assert.deepEqual(view.observedOperatorCreateReceipt(expected,{username:"bob",role:"Operator"}),
  {operator_id:id2,username:"bob",role:"Operator"});
 for(const altered of [
  {operator_id:"wop_"+"z".repeat(24)},{username:"alice"},{role:"Admin"},
  {mfa_required:true},{mfa_enrolled:true},
  {operator_id:{secret:"SHOULD_NOT_SHOW"}},
  {operator_id:"../"+id2}
 ])assert.equal(view.observedOperatorCreateReceipt({...expected,...altered},
    {username:"bob",role:"Operator"}),null);
 for(const intent of [{username:"bob",role:"Root"},{username:"bad\nname",role:"Admin"},
  null,{},[],{username:{token:"SECRET"},role:"Admin"}])
  assert.equal(view.observedOperatorCreateReceipt(expected,intent),null);
});

test("M2 UsersPanel create and MFA are non-idempotent; unknown write preserves identity, clears typed password, no blind retry",()=>{
 const main=readFileSync(join(root,"src","main.tsx"),"utf8");
 const panel=main.split("function UsersPanel(",2)[1]?.split("function IntegrationsPanel(",1)[0]||"";
 assert.match(panel,/const createUserInFlight=useRef\(false\)/);
 assert.match(panel,/if\(createUserInFlight\.current\|\|mfaMutationInFlight\.current/);
 assert.match(panel,/createUserInFlight\.current=true/);
 assert.match(panel,/createUserInFlight\.current=false/);
 assert.match(panel,/const receipt=observedOperatorCreateReceipt\(result,\{username:newUsername,role:newRole\}\)/);
 assert.match(panel,/if\(!receipt\)throw new Error\(/);
 assert.match(panel,/Core operator creation outcome UNKNOWN/);
 assert.match(panel,/Inspect Users and Audit before retrying/);
 assert.match(panel,/finally\{setNewPassword\("".*?\);createUserInFlight\.current=false/);
 assert.match(panel,/disabled=\{!!busy\|\|!newUsername\|\|!newPassword\}/);
 assert.match(panel,/disabled=\{!!busy\|\|mfaChange.required===null\}/);
 assert.match(panel,/if\(mfaMutationInFlight\.current\|\|createUserInFlight\.current\)return/);
 assert.match(panel,/mfaMutationInFlight\.current=false/);
});
