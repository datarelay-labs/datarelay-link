// Read-only Web operator view projection. No live Web sessions, MFA credentials or mutations.
import assert from "node:assert/strict";
import {test} from "node:test";
import {build} from "esbuild";
import {readFileSync,mkdtempSync,rmSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,"node_modules",".pfci-users-state-"));
let view;
try{
  const out=join(scratch,"projection.mjs");
  await build({entryPoints:[join(root,"src","uxb-users-state.ts")],
    outfile:out,bundle:true,platform:"node",format:"esm",logLevel:"silent"});
  view=await import(pathToFileURL(out).href);
}finally{rmSync(scratch,{recursive:true,force:true})}

test("Web user state requires explicit Core boolean or SQLite 0/1",()=>{
 for(const [v,status] of [[true,"Enabled"],[false,"Disabled"],[1,"Enabled"],[0,"Disabled"],
   [null,"UNKNOWN"],[undefined,"UNKNOWN"],["false","UNKNOWN"],[2,"UNKNOWN"]]){
   assert.equal(view.operatorAccountState({enabled:v}),status);
 }
});

test("User MFA status refuses unknown and inconsistent Core state",()=>{
 for(const [required,enrolled,status] of [
   [true,true,"Enabled"],[true,false,"Setup pending"],
   [false,false,"Disabled"],[false,true,"UNKNOWN"],
   [null,false,"UNKNOWN"],[false,null,"UNKNOWN"],[undefined,false,"UNKNOWN"],
   ["false",false,"UNKNOWN"],[1,1,"Enabled"],[0,0,"Disabled"]
 ]){
   assert.equal(view.operatorMfaState({mfa_required:required,mfa_enrolled:enrolled}),
     status,JSON.stringify([required,enrolled]));
 }
});

test("MFA action is disabled without complete, valid Core row identity",()=>{
 const base={id:"user-1",username:"operator",role:"Operator",enabled:true};
 assert.deepEqual(view.operatorMfaAction({...base,mfa_required:false,mfa_enrolled:false}),
   {required:true,label:"Enable MFA"});
 assert.deepEqual(view.operatorMfaAction({...base,mfa_required:true,mfa_enrolled:true}),
   {required:false,label:"Disable MFA"});
 assert.deepEqual(view.operatorMfaAction({...base,mfa_required:true,mfa_enrolled:false}),
   {required:false,label:"Disable MFA"});
 for(const variant of [
   {...base,mfa_required:null,mfa_enrolled:false},
   {...base,mfa_required:false,mfa_enrolled:true},
   {...base,mfa_required:false,mfa_enrolled:null},
   {...base,id:"",mfa_required:false,mfa_enrolled:false},
   {...base,role:"UNTRUSTED",mfa_required:false,mfa_enrolled:false},
   null,
 ]){
   assert.deepEqual(view.operatorMfaAction(variant),
     {required:null,label:"MFA status UNKNOWN"},JSON.stringify(variant));
 }
});

test("Absent last-login is UNKNOWN; explicit never-login null is distinct",()=>{
 assert.equal(view.operatorLastLogin({last_login_at:null}),"Never");
 assert.equal(view.operatorLastLogin({}),"UNKNOWN");
 assert.equal(view.operatorLastLogin({last_login_at:0}),"UNKNOWN");
 assert.equal(view.operatorLastLogin({last_login_at:"2026-10-11T00:11:00Z"}),
   "2026-10-11T00:11:00Z");
 assert.equal(view.operatorLastLogin({last_login_at:"x\u202e\\n".repeat(60)}).includes("\u202e"),false);
});

test("Web operator names and MFA button labels are bounded and cannot spoof with control text",()=>{
 assert.equal(view.operatorUserLabel({username:" alice "}),"alice");
 assert.equal(view.operatorUserLabel({username:null}),"UNKNOWN");
 assert.equal(view.operatorUserLabel({}),"UNKNOWN");
 const name=view.operatorUserLabel({username:("a".repeat(120)+"\u202e\nspoofed")});
 assert.ok(name.length<=100);
 assert.doesNotMatch(name,/[\u202e\n]/);
 const main=readFileSync(join(root,"src","main.tsx"),"utf8");
 const section=main.split("function UsersPanel(",2)[1]?.split("function IntegrationsPanel(",1)[0]||"";
 assert.match(section,/operatorUserLabel\(x\)/);
 assert.match(section,/aria-label=\{mfaChange.label\+" for "\+operatorUserLabel\(x\)\}/);
});
test("Real UsersPanel is wired fail-closed without changing Core MFA endpoints",()=>{
 const source=readFileSync(join(root,"src","main.tsx"),"utf8");
 const section=source.split("function UsersPanel(",2)[1]?.split("function IntegrationsPanel(",1)[0]||"";
 assert.match(source,/import \{operatorAccountState,operatorMfaState,operatorMfaAction,operatorLastLogin\} from "\.\/uxb-users-state"/);
 assert.match(section,/operatorMfaAction\(x\)/);
 assert.match(section,/operatorAccountState\(x\)/);
 assert.match(section,/operatorMfaState\(x\)/);
 assert.match(section,/operatorLastLogin\(x\)/);
 assert.match(section,/mfaChange.required===null/);
 assert.match(section,/setMfa\(x.id,mfaChange.required\)/);
 assert.match(section,/api\("\/api\/v1\/operators\/"\+encodeURIComponent\(id\)\+"\/mfa"/);
 assert.doesNotMatch(section,/onClick=\{\(\)=>setMfa\(x.id,!x.mfa_required\)\}/);
});
