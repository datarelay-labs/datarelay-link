// M2 Core/Web authorized Admin integration inventory projection.
// Unit/source evidence only; no live host or privileged external action.
import assert from "node:assert/strict";
import {test} from "node:test";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const temp=mkdtempSync(join(root,"node_modules",".drlink-m2-inventory-"));
let helper;
try{
 const outfile=join(temp,"proj.mjs");
 await build({entryPoints:[join(root,"src","uxb-integrations-state.ts")],
  outfile,platform:"node",format:"esm",bundle:true,logLevel:"silent"});
 helper=await import(pathToFileURL(outfile).href);
}finally{rmSync(temp,{recursive:true,force:true})}
const msa="msa_"+"a".repeat(24),wh="wh_"+"b".repeat(24);
const sa={id:msa,name:"robot",permissions:["management-read"],
  enabled:true,expires_at:"",created_at:"2026-10-12T01:30:00Z",
  credential:"drlink_sa_SECRET_DO_NOT_STORE",metadata:{private_key:"HIDDEN_KEY"}};
const webhook={id:wh,name:"Alert hook",url:"https://hooks.example.test/events",
  event_classes:["attention","security.lifecycle"],enabled:true,
  delivery_counts:{PENDING:0,DELIVERED:3},
  secret:"drlink_wh_SECRET_DO_NOT_STORE",metadata:{token:"HIDDEN_KEY"}};
const inventory=(type,items)=>helper.observedIntegrationInventory(type,items);

test("M2 Core Account inventory exposes only vetted public fields; credential/hash/nested metadata cannot reach DOM",()=>{
 assert.deepEqual(inventory("service-accounts",[sa]),[{
  id:msa,name:"robot",permissions:["management-read"],enabled:true,expires_at:""
 }]);
 const output=JSON.stringify(inventory("service-accounts",[sa]));
 assert.doesNotMatch(output,/HIDDEN_KEY|SECRET_DO_NOT_STORE|metadata|credential|token/);
 assert.equal(helper.serviceAccountOperationalStatus(inventory("service-accounts",[sa])[0]),"Active");
 assert.deepEqual(inventory("service-accounts",[]),[],"verified empty list is distinct from UNKNOWN");
});

test("M2 Core Webhook inventory exposes only vetted endpoint/classes and known delivery counts",()=>{
 assert.deepEqual(inventory("webhooks",[webhook]),[{
  id:wh,name:"Alert hook",url:"https://hooks.example.test/events",
  event_classes:["attention","security.lifecycle"],enabled:true,
  delivery_counts:{PENDING:0,DELIVERED:3}
 }]);
 assert.equal(helper.webhookStatus(inventory("webhooks",[webhook])[0]),"Enabled");
 assert.equal(helper.webhookDeliverySummary(inventory("webhooks",[webhook])[0]),
  "PENDING:0 · DELIVERED:3");
 assert.doesNotMatch(JSON.stringify(inventory("webhooks",[webhook])),
  /HIDDEN_KEY|SECRET_DO_NOT_STORE|metadata|secret/);
 const incomplete=inventory("webhooks",[{...webhook,delivery_counts:{BROKEN:123,api_key:"SECRET"}}]);
 assert.equal(incomplete?.length,1);
 assert.equal(helper.webhookDeliverySummary(incomplete[0]),"UNKNOWN",
  "unexpected Core statuses become UNKNOWN, never invented zero");
});

test("M2 malformed Core resource entries never render as zero, JSX objects, unsafe URLs or actionable unknown identities",()=>{
 const badAccounts=[
  {...sa,id:{private_key:"HIDDEN_KEY"}},{...sa,id:"msa_../unsafe"},
  {...sa,name:{token:"SECRET"}},{...sa,name:"bad\u202e"},
  {...sa,permissions:{token:"SECRET"}},{...sa,permissions:["unknown-admin"]},
  {...sa,permissions:["management-read","management-read"]},
 ];
 for(const item of badAccounts)assert.equal(inventory("service-accounts",[item]),null);
 const badWebhooks=[
  {...webhook,id:{"secret":"HIDDEN"}},{...webhook,url:{token:"SECRET"}},
  {...webhook,url:"javascript:alert(1)"},{...webhook,url:"https://user:pass@evil.example.test"},
  {...webhook,url:"https://hooks.example.test/path?api_key=SECRET"},
  {...webhook,url:"https://hooks.example.test/#frag"},
  {...webhook,url:"https://127.0.0.1/events"},
  {...webhook,url:"https://localhost/events"},
  {...webhook,url:"https://hooks.example.test:444/events"},
  {...webhook,name:"secret\nvalue"},{...webhook,event_classes:"attention"},
  {...webhook,event_classes:["CUSTOM_ADMIN"]},
 ];
 for(const item of badWebhooks)assert.equal(inventory("webhooks",[item]),null);
 for(const items of [null,undefined,{},["unsafe"],[null],[[1]],Array.from({length:201},()=>sa)]){
  assert.equal(inventory("service-accounts",items),null);
 }
 assert.equal(inventory("everyone",[sa]),null);
 assert.equal(inventory("service-accounts",[sa,sa]),null,"Core IDs must be unique");
});

test("M2 unknown/malformed status and expiry must remain UNKNOWN; no mutation UI can appear",()=>{
 const projected=inventory("service-accounts",[
  {...sa,enabled:"true",expires_at:{token:"SECRET"}}
 ]);
 assert.equal(projected?.length,1);
 assert.equal(helper.serviceAccountOperationalStatus(projected[0]),"UNKNOWN");
 assert.equal(helper.serviceAccountExpiry(projected[0]),"UNKNOWN");
 const unknownWebhook=inventory("webhooks",[{...webhook,enabled:"true",delivery_counts:null}]);
 assert.equal(helper.webhookStatus(unknownWebhook[0]),"UNKNOWN");
 assert.equal(helper.webhookDeliverySummary(unknownWebhook[0]),"UNKNOWN");
 assert.doesNotMatch(JSON.stringify(projected),/SECRET/);
});

test("M2 Web Admin Integrations list is Core-projected before React render and partial first-200 limit remains honest",()=>{
 const main=readFileSync(join(root,"src","main.tsx"),"utf8");
 const panel=main.split("function IntegrationsPanel(",2)[1]?.split("function CommandCenter(",1)[0]||"";
 assert.match(main,/import \{observedIntegrationInventory\} from "\.\/uxb-integrations-state"/);
 assert.match(panel,/const accountsObserved=observedIntegrationInventory\("service-accounts",accountsPage.items\)/);
 assert.match(panel,/const webhooksObserved=observedIntegrationInventory\("webhooks",hooksPage.items\)/);
 assert.match(panel,/if\(!accountsObserved\|\|!webhooksObserved\)throw new Error\(/);
 assert.match(panel,/setAccounts\(accountsObserved\);setHooks\(webhooksObserved\)/);
 assert.doesNotMatch(panel,/setAccounts\(accountsPage.items\);setHooks\(hooksPage.items\)/);
 assert.match(panel,/accounts.length===200\|\|hooks.length===200/);
 assert.match(panel,/only the first 200 Core items/);
 assert.match(panel,/Integration inventory · \{inventoryState==="loading"\?"Loading":"UNKNOWN"\}/);
 assert.match(panel,/setInventoryState\("unknown"\)/);
 assert.doesNotMatch(panel,/h\.event_classes\|\|\[\]\)\.join\(".*?token/);
});

test("M2/R4 Webhook HTTP delivery evidence distinguishes zero observation, queue, failure, and transport-only receipt",()=>{
 const pulse=counts=>helper.observedWebhookDeliveryPulse({delivery_counts:counts});
 assert.deepEqual(pulse({}),{
  state:"NO_EVENTS_OBSERVED",pending:0,sending:0,delivered:0,failed:0
 });
 assert.deepEqual(pulse({DELIVERED:3}),{
  state:"HTTP_ACKNOWLEDGED_ONLY",pending:0,sending:0,delivered:3,failed:0
 });
 assert.deepEqual(pulse({PENDING:2,SENDING:1}),{
  state:"QUEUED_OR_SENDING",pending:2,sending:1,delivered:0,failed:0
 });
 assert.deepEqual(pulse({PENDING:2,DELIVERED:3,FAILED:1}),{
  state:"FAILURE_RECORDED",pending:2,sending:0,delivered:3,failed:1
 });
 const observed=inventory("webhooks",[{...webhook,delivery_counts:{DELIVERED:8,SENDING:2}}])[0];
 assert.equal(helper.observedWebhookDeliveryPulse(observed).state,"QUEUED_OR_SENDING");
 assert.equal(helper.observedWebhookDeliveryPulse({delivery_counts:{DELIVERED:0}}).state,"NO_EVENTS_OBSERVED");
 for(const data of [null,undefined,{},[],{delivery_counts:null},
    {delivery_counts:{FAILED:"2"}},{delivery_counts:{PENDING:-1}},
    {delivery_counts:{ADMIN_PWNED:4,auth_token:"SECRET"}},
    {delivery_counts:{DELIVERED:Infinity}},
    {delivery_counts:{FAILED:NaN}}]){
   assert.equal(helper.observedWebhookDeliveryPulse(data).state,"UNKNOWN");
   assert.doesNotMatch(JSON.stringify(helper.observedWebhookDeliveryPulse(data)),/SECRET|auth_token|ADMIN_PWNED/);
 }
});

test("M2/R4 Admin Webhook delivery UI labels HTTP2xx-only vs real downstream processing without raw Core metadata",()=>{
 const source=readFileSync(join(root,"src","main.tsx"),"utf8");
 const panel=source.split("function IntegrationsPanel(",2)[1]?.split("function CommandCenter(",1)[0]||"";
 assert.match(source,/observedWebhookDeliveryPulse/);
 assert.match(panel,/observedWebhookDeliveryPulse\(h\)\.state/);
 assert.match(panel,/HTTP-acknowledged does not prove the receiver processed the event/);
 assert.match(panel,/Core outbox observations can be incomplete or expire under retention/);
 assert.doesNotMatch(panel,/Webhook delivery healthy/);
});
