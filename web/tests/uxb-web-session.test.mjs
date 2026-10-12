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
 assert.match(source,/import \{observedAuthenticatedWebSession\} from "\.\/uxb-web-session"/);
 assert.match(login,/const observed=observedAuthenticatedWebSession\(d\);/);
 assert.match(login,/if\(!observed\)throw new Error\("Core authenticated session/);
 assert.match(login,/csrf=observed\.csrf_token;onLogin\(observed\.operator\)/);
 assert.match(login,/csrf=observed\.csrf_token;setRecoveryCodes/);
 assert.match(app,/api\("\/api\/v1\/session"\)\.then\(d=>\{/);
 assert.match(app,/const observed=observedAuthenticatedWebSession\(d\);/);
 assert.match(app,/csrf=observed\.csrf_token;/);
 assert.match(app,/setOperator\(observed\.operator\)/);
 assert.doesNotMatch(source,/csrf=d\.csrf_token;/);
});
