// Pure source-backed projection; no live Core, login, Browser or credential mutation.
import assert from "node:assert/strict";
import {test} from "node:test";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";

const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,"node_modules",".pfci-service-detail-"));
let serviceStateLabel,serviceDetailSections,serviceVisibleIdentity,sshConnectionTemplate,serviceUseAction;
try{
 const output=join(scratch,"projection.mjs");
 await build({entryPoints:[join(root,"src","uxb-service-detail.ts")],outfile:output,
  bundle:true,platform:"node",format:"esm",logLevel:"silent"});
 ({serviceStateLabel,serviceDetailSections,serviceVisibleIdentity,sshConnectionTemplate,serviceUseAction}=await import(pathToFileURL(output).href));
}finally{rmSync(scratch,{recursive:true,force:true})}
const flatten=value=>serviceDetailSections(value).flatMap(s=>s.fields).map(f=>f.label+": "+f.value).join(" | ");

test("Core remote-service enabled/released flags are tri-state and never guessed",()=>{
 for(const [row,want] of [
  [{released:true}, "Released"],
  [{released:1,enabled:true},"Released"],
  [{released:false,enabled:true},"Enabled"],
  [{released:0,enabled:1},"Enabled"],
  [{released:false,enabled:false},"Disabled"],
  [{released:0,enabled:0},"Disabled"],
  [{released:null,enabled:1},"UNKNOWN"],
  [{released:0,enabled:null},"UNKNOWN"],
  [{released:"false",enabled:1},"UNKNOWN"],
  [{released:2,enabled:1},"UNKNOWN"],
  [{released:0,enabled:"false"},"UNKNOWN"],
  [{released:false,enabled:2},"UNKNOWN"],
  [{released:0}, "UNKNOWN"],
  [{enabled:false}, "UNKNOWN"],
  [{}, "UNKNOWN"],
  [null, "UNKNOWN"],
 ]){
  assert.equal(serviceStateLabel(row),want,JSON.stringify(row));
 }
});

test("Remote Service drawer is bounded by explicit Core inventory field whitelist",()=>{
 const rows=serviceDetailSections({
  id:"svc-10",name:"SSH management",managed_host_id:"host-10",managed_host:"jump.example",
  service_type:"tcp",target_mode:"host",target_host:"10.10.1.8",
  target_port:22,public_port:2200,enabled:1,released:0,
 });
 assert.deepEqual(rows.map(s=>s.title),[
   "Service identity","Owning Managed Host","Published endpoint","Service state"]);
 const fields=rows.flatMap(x=>x.fields);
 for(const [label,want] of [
  ["Service ID","svc-10"],["Managed Host","jump.example"],["Managed Host ID","host-10"],
  ["Service type","tcp"],["Target Host","10.10.1.8"],
  ["Target port","22"],["Public port","2200"],["State","Enabled"],
 ])assert.ok(fields.some(x=>x.label===label&&x.value===want),label);
});

test("Missing/invalid Core service state stays UNKNOWN and does not fabricate deployment",()=>{
 const text=flatten({id:"svc-10",enabled:undefined,released:undefined});
 assert.match(text,/State: UNKNOWN/);
 assert.match(text,/Managed Host: UNKNOWN/);
 assert.match(text,/Public port: UNKNOWN/);
 assert.doesNotMatch(text,/State: Disabled|State: Enabled/);
 assert.match(flatten(null),/Service identity: UNKNOWN/);
 assert.match(flatten({target_port:-1,public_port:"443"}),/Target port: UNKNOWN/);
 assert.match(flatten({target_port:-1,public_port:"443"}),/Public port: UNKNOWN/);
});


test("UXR-2.7 protocol use actions never invent a public host or execute a command",()=>{
 const base={public_port:8443,enabled:true,released:false};
 assert.deepEqual(serviceUseAction({...base,service_type:"https"}),{kind:"https",copyText:"https://PUBLIC_SERVER_HOST:8443/",openUrl:null,note:"Open is unavailable until a public service host is separately verified."});
 assert.equal(serviceUseAction({...base,service_type:"https"},"relay.example.com")?.openUrl,"https://relay.example.com:8443/");
 assert.equal(serviceUseAction({...base,service_type:"http",public_port:8080},"evil.example@attacker.test")?.openUrl,null);
 assert.equal(serviceUseAction({...base,service_type:"tcp",public_port:6001})?.copyText,"PUBLIC_SERVER_HOST:6001");
 assert.equal(serviceUseAction({...base,service_type:"ssh",public_port:6000})?.copyText,"ssh -p 6000 USERNAME@PUBLIC_SERVER_HOST");
 for(const invalid of [{...base,service_type:"rdp"},{...base,service_type:"https",enabled:false},{...base,service_type:"https",public_port:"443"}])assert.equal(serviceUseAction(invalid),null);
 const main=readFileSync(join(root,"src","main.tsx"),"utf8");
 assert.match(main,/function ServiceUseActions/);assert.match(main,/Open verified URL/);assert.match(main,/disabled=\{!action\.openUrl\}/);
 assert.doesNotMatch(main,/window\.open\(action\.copyText/);
});

test("Remote Service drawer never renders unapproved arbitrary/secret fields or control text",()=>{
 const obj={
  id:"service-id",name:"A\u202e\nB".repeat(100),target_host:"10.0.0.1",
  enabled:true,released:false,
  token:"SENSITIVE_TOKEN_1",password:"SENSITIVE_PASSWORD_1",
  private_key:"SENSITIVE_KEY_1",session_secret:"SENSITIVE_SESSION_1",
  webhook_secret:"SENSITIVE_WEBHOOK_1",auth_uri:"SENSITIVE_URL_1",
  runtime_metadata:{password:"SENSITIVE_NESTED"},
 };
 const output=JSON.stringify(serviceDetailSections(obj));
 for(const value of ["SENSITIVE","password","private_key","session_secret","webhook_secret","auth_uri","runtime_metadata","\u202e","\n"]){
  assert.ok(!output.includes(value),value);
 }
 assert.ok(serviceDetailSections(obj).flatMap(s=>s.fields).every(f=>f.value.length<=160));
});

test("Actual Web inventory list and drawer use the same safe status and detail projection",()=>{
 const source=readFileSync(join(root,"src","main.tsx"),"utf8");
 const resource=source.split("function ResourceWorkspace(",2)[1]?.split("function UsersPanel(",1)[0]||"";
 assert.match(source,/import \{serviceStateLabel,serviceDetailSections,serviceUseAction\} from "\.\/uxb-service-detail"/);
 assert.match(resource,/serviceStateLabel\(item\)/);
 assert.match(resource,/serviceStateLabel\(selected\)/);
 assert.match(resource,/serviceDetailSections\(selected\)\.map/);
 assert.doesNotMatch(resource,/Object\.entries\(selected\)/);
 assert.match(resource,/Why can \/ cannot connect\?/);
});

test("UXR-2.6 Service catalog shows type identity and separates config from policy and transport evidence",()=>{
 const src=readFileSync(join(root,"src","main.tsx"),"utf8");
 const resource=src.split("function ResourceWorkspace(",2)[1]?.split("function UsersPanel(",1)[0]||"";
 assert.match(src,/function ServiceTypeGlyph/);
 assert.match(resource,/ServiceTypeGlyph type=\{item\.service_type\}/);
 assert.match(src,/function ServiceEvidenceStatus/);
 assert.match(resource,/ServiceEvidenceStatus service=\{selected\}/);
 assert.match(src,/Access policy<\/span><strong>Not checked/);
 assert.match(src,/Transport<\/span><strong>Not tested/);
 assert.match(resource,/Managed host/);assert.match(resource,/Public port/);
});

test("Remote Service list and drawer headings never display unbounded control text",()=>{
 const visible=serviceVisibleIdentity({id:"svc1",name:"service\u202e\nR".repeat(160)});
 assert.ok(visible.primary.length<=140);
 assert.ok(!/[\u202e\n]/.test(JSON.stringify(visible)));
 assert.deepEqual(serviceVisibleIdentity({id:"s",name:""}),{primary:"s",secondary:"s"});
 assert.deepEqual(serviceVisibleIdentity(null),{primary:"UNKNOWN",secondary:"UNKNOWN"});
 const src=readFileSync(join(root,"src","main.tsx"),"utf8");
 const section=src.split("function ResourceWorkspace(",2)[1]?.split("function UsersPanel(",1)[0]||"";
 assert.match(section,/serviceVisibleIdentity\(item\)\.primary/);
 assert.match(section,/serviceVisibleIdentity\(selected\)\.primary/);
 assert.match(section,/Enabled means configuration is selected/);
});


test("G-10 Core-confirmed SSH public port yields only a placeholder command template",()=>{
 const ssh={service_type:"ssh",public_port:6000,enabled:true,released:false,
  target_host:"10.10.1.11",managed_host:"internal.test",password:"secret"};
 assert.equal(sshConnectionTemplate(ssh),"ssh -p 6000 USERNAME@PUBLIC_SERVER_HOST");
 assert.equal(sshConnectionTemplate({...ssh,public_port:1}),"ssh -p 1 USERNAME@PUBLIC_SERVER_HOST");
 assert.equal(sshConnectionTemplate({...ssh,public_port:65535}),"ssh -p 65535 USERNAME@PUBLIC_SERVER_HOST");
 assert.doesNotMatch(sshConnectionTemplate(ssh),/10\.10\.1\.11|internal\.test|secret/);
});
test("G-10 never invents commands for unknown type, invalid port or non-enabled service",()=>{
 const base={service_type:"ssh",public_port:6000,enabled:true,released:false};
 for(const invalid of [null,{},[],
  {...base,service_type:"tcp"},{...base,service_type:"SSH "},{...base,service_type:{bad:1}},
  {...base,public_port:0},{...base,public_port:65536},{...base,public_port:"6000"},
  {...base,public_port:1.5},{...base,public_port:NaN},{...base,public_port:Infinity},
  {...base,released:true},{...base,released:null},{...base,released:"false"},
  {...base,enabled:false},{...base,enabled:0},{...base,enabled:null},{...base,enabled:"true"}])
  assert.equal(sshConnectionTemplate(invalid),null,JSON.stringify(invalid));
});
test("G-10 protocol templates and explicit clipboard result use native actions without Core/credential mutation",()=>{
 const src=readFileSync(join(root,"src","main.tsx"),"utf8");
 const hint=src.split("function ServiceUseActions(",2)[1]?.split("function ResourceWorkspace(",1)[0]||"";
 const resource=src.split("function ResourceWorkspace(",2)[1]?.split("function UsersPanel(",1)[0]||"";
 assert.match(src,/import \{serviceStateLabel,serviceDetailSections,serviceUseAction\} from "\.\/uxb-service-detail"/);
 assert.match(resource,/!isHost&&<ServiceUseActions.*?service=\{selected\}/);
 assert.match(hint,/serviceUseAction\(service\)/);
 assert.match(hint,/aria-label="Service use actions"/);
 assert.match(hint,/navigator\.clipboard\.writeText\(action!\.copyText\)/);
 assert.match(hint,/Clipboard unavailable/);
 assert.match(hint,/Open verified URL/);
 assert.match(hint,/disabled=\{!action\.openUrl\}/);
 assert.match(hint,/type="button"/);
 assert.doesNotMatch(hint,/\b(?:api|fetch|load|apply|eval)\s*\(/);
 assert.match(hint,/overflowWrap:"anywhere"/);
});
