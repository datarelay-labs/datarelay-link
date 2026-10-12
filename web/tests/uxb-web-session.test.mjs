// R2.2/M2: source contract of Core Web authentication/session identities.
// Offline source tests; not a real browser sign-in or user E2E.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {mkdtempSync,rmSync,readFileSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {build} from 'esbuild';
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,'node_modules','.drlink-m2-web-session-'));
let auth;
try{
 const outfile=join(scratch,'session.mjs');
 await build({entryPoints:[join(root,'src','uxb-web-session.ts')],outfile,
   platform:'node',format:'esm',bundle:true,logLevel:'silent'});
 auth=await import(pathToFileURL(outfile).href);
}finally{rmSync(scratch,{recursive:true,force:true})}
const base={session_id:'ws_'+'1'.repeat(24),csrf_token:'a'.repeat(64),
 operator:{id:'wop_'+'2'.repeat(24),username:'alice.admin',role:'Admin',
  password_hash:'NO_WEB_EXPORT',mfa_secret:'NO_EXPORT',permissions:['admin']},
 session_token:'SERVER_COOKIE_ONLY'};
test('Core Web session success projects only observed operator and CSRF, never nested claims',()=>{
 for(const role of ['Admin','Operator','Read Only']){
  const got=auth.observedAuthenticatedWebSession({...base,operator:{...base.operator,role}});
  assert.deepEqual(got,{operator:{id:base.operator.id,username:'alice.admin',role},
    csrf_token:'a'.repeat(64)});
  assert.doesNotMatch(JSON.stringify(got),/NO_WEB_EXPORT|NO_EXPORT|password_hash|permissions|session_token|session_id/);
 }
});
test('Core malformed actor, ambiguous role or invalid session/CSRF never unlocks Web',()=>{
 const good={...base,operator:{id:base.operator.id,username:base.operator.username,role:'Admin'}};
 for(const bad of [
  null,{},[],{...good,operator:null},{...good,operator:{...good.operator,role:'SuperAdmin'}},
  {...good,operator:{...good.operator,role:'admin'}},
  {...good,operator:{...good.operator,id:'wop_NOT_REAL'}},
  {...good,operator:{...good.operator,id:'wop_'+'z'.repeat(24)}},
  {...good,operator:{...good.operator,username:'alice\u202eadmin'}},
  {...good,operator:{...good.operator,username:'alice admin'}},
  {...good,operator:{...good.operator,username:{token:'SECRET'}}},
  {...good,session_id:'forged'},{...good,session_id:undefined},
  {...good,csrf_token:'wrong'},{...good,csrf_token:'a'.repeat(63)},
  {...good,csrf_token:'A'.repeat(64)},{...good,csrf_token:undefined},
  {...good,mfa_setup_required:true},
 ]){
  assert.equal(auth.observedAuthenticatedWebSession(bad),null,JSON.stringify(bad));
 }
});
test('Login, MFA confirmation and cookie-backed GET /session verify Core actor before Web role or CSRF becomes active',()=>{
 const source=readFileSync(join(root,'src','main.tsx'),'utf8');
 const login=source.split('function Login(',2)[1].split('function AuthScaffold(',1)[0]
   .split('function Metric(',1)[0];
 const app=source.split('function App()',2)[1];
 assert.match(source,/import \{observedAuthenticatedWebSession,observedWebMfaChallenge,observedWebMfaCompletion\} from "\.\/uxb-web-session"/);
 assert.match(login,/const observed=observedAuthenticatedWebSession\(d\);/);
 assert.match(login,/if\(!observed\)throw new Error\("Core authenticated session/);
 assert.match(login,/csrf=observed\.csrf_token;onLogin\(observed\.operator\)/);
 assert.match(login,/csrf=completed\.session\.csrf_token;setRecoveryCodes/);
 assert.match(app,/api\("\/api\/v1\/session"\)\.then\(d=>\{/);
 assert.match(app,/const observed=observedAuthenticatedWebSession\(d\);/);
 assert.match(app,/csrf=observed\.csrf_token;/);
 assert.match(app,/setOperator\(observed\.operator\)/);
 assert.doesNotMatch(source,/csrf=d\.csrf_token;/);
});

test('R2.2 Core MFA setup QR binds only exact issuer/secret/user and validates opaque enrollment',()=>{
 const id='wop_'+'c'.repeat(24),username='alice.admin',secret='A'.repeat(32);
 const uri='otpauth://totp/Data%20Relay%20Link%3Aalice.admin?secret='+secret
   +'&issuer=Data%20Relay%20Link&digits=6&period=30';
 const challenge={mfa_setup_required:true,enrollment_token:'x'.repeat(43),
   totp_secret:secret,otpauth_uri:uri,expires_at:'2030-01-01T00:00:00Z',
   operator:{id,username,role:'Operator',authorization:'DO_NOT_COPY'},
   session_id:'ws_FORGED',csrf_token:'not-authenticated'};
 const result=auth.observedWebMfaChallenge(challenge);
 assert.deepEqual(result,{mfa_setup_required:true,enrollment_token:'x'.repeat(43),
   totp_secret:secret,otpauth_uri:uri,expires_at:challenge.expires_at,
   operator:{id,username,role:'Operator'}});
 assert.doesNotMatch(JSON.stringify(result),/DO_NOT_COPY|ws_FORGED|csrf_token/);
 for(const invalid of [
  {...challenge,mfa_setup_required:'true'},
  {...challenge,enrollment_token:'no'},
  {...challenge,totp_secret:'12345'},
  {...challenge,totp_secret:'A'.repeat(31)},
  {...challenge,otpauth_uri:uri.replace('alice.admin','bob')},
  {...challenge,otpauth_uri:'https://evil.example/?secret='+secret},
  {...challenge,otpauth_uri:uri.replace('digits=6','digits=8')},
  {...challenge,otpauth_uri:uri+'&unsafe=1'},
  {...challenge,expires_at:'2030-02-30T00:00:00Z'},
  {...challenge,operator:{...challenge.operator,role:'Root'}},
  {...challenge,operator:{...challenge.operator,id:'malformed'}},
 ])assert.equal(auth.observedWebMfaChallenge(invalid),null,JSON.stringify(invalid).slice(0,140));
});
test('R2.2 Core MFA completion must supply ten unique canonical recovery codes with verified session',()=>{
 const alphabet='ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
 const codes=Array.from({length:10},(_,i)=>alphabet[i].repeat(4)+'-'+
  alphabet[(i+1)%alphabet.length].repeat(4)+'-'+
  alphabet[(i+2)%alphabet.length].repeat(4)+'-'+
  alphabet[(i+3)%alphabet.length].repeat(4));
 const receipt={...base,recovery_codes:codes,extra_secret:'SECRET_IGNORED'};
 assert.deepEqual(auth.observedWebMfaCompletion(receipt),{
   session:auth.observedAuthenticatedWebSession(base),recovery_codes:codes});
 for(const wrong of [
  {...receipt,recovery_codes:undefined},
  {...receipt,recovery_codes:codes.slice(0,9)},
  {...receipt,recovery_codes:[...codes.slice(0,9),codes[0]]},
  {...receipt,recovery_codes:[...codes.slice(0,9),{private:'NO'}]},
  {...receipt,recovery_codes:[...codes.slice(0,9),'abcd-efgh-abcd-efgh']},
  {...receipt,csrf_token:'invalid'},
 ])assert.equal(auth.observedWebMfaCompletion(wrong),null);
 const source=readFileSync(join(root,'src','main.tsx'),'utf8');
 assert.match(source,/const challenge=observedWebMfaChallenge\(d\);/);
 assert.match(source,/if\(!challenge\)throw new Error\("Core MFA setup challenge/);
 assert.match(source,/setSetup\(challenge\)/);
 assert.match(source,/const completed=observedWebMfaCompletion\(d\);/);
 assert.match(source,/csrf=completed\.session\.csrf_token;setRecoveryCodes\(completed\.recovery_codes\)/);
 assert.match(source,/setPendingOperator\(completed\.session\.operator\)/);
});
