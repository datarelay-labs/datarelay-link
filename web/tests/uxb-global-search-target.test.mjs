// M1-A G-18: selected Core Global Search identity -> freshly authorized loaded detail.
// This suite validates source/contract only; no real logged-in Browser acceptance.
import assert from "node:assert/strict";
import {test} from "node:test";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,"node_modules",".drlink-m1-search-"));
let projector,matchers;
try{
 for(const [name,entry] of [["projection","uxb-global-search-target.ts"],["matchers","uxb-audit-context.ts"]]){
  await build({entryPoints:[join(root,"src",entry)],outfile:join(scratch,name+".mjs"),
    bundle:true,platform:"node",format:"esm",logLevel:"silent"});
 }
 projector=await import(pathToFileURL(join(scratch,"projection.mjs")).href);
 matchers=await import(pathToFileURL(join(scratch,"matchers.mjs")).href);
}finally{rmSync(scratch,{recursive:true,force:true})}
const hit=(resource_type,id,name="Observed")=>({resource_type,id,name,item:{id}});
const project=(rows)=>projector.projectObservedGlobalSearchResults(rows);

test("M1-A exact Host/Service/three-plane Policy hits preserve only validated route and ephemeral selection",()=>{
 const input=[
  {...hit("managed-host","host-123","Host 123"),item:{id:"host-123",token:"NO_EXPORT"}},
  hit("remote-service","svc-4","Service 4"),
  ...["remote","internet","ai"].map(plane=>({...hit("access-policy-rule","rule-"+plane),
    item:{id:"rule-"+plane,plane,credential:"DO_NOT_COPY"}})),
 ];
 const result=project(input);
 assert.equal(result?.totalCount,5);
 assert.equal(result?.invalidCount,0);
 assert.equal(result?.scope,"bounded-core-search");
 assert.deepEqual(result?.items.map(x=>x.destination),[
  {id:"hosts",group:"connections",exact:true,
   context:{savedFilter:"id:host-123",inspectResourceId:"host-123",searchResultKey:"host:host-123"}},
  {id:"services",group:"connections",exact:true,
   context:{savedFilter:"id:svc-4",inspectResourceId:"svc-4",searchResultKey:"service:svc-4"}},
  ...["remote","internet","ai"].map(plane=>({id:"policies",group:"access",exact:true,
   context:{plane,inspectPolicyId:"rule-"+plane,searchResultKey:"policy:"+plane+":rule-"+plane}}))
 ]);
 assert.deepEqual(result?.items.map(x=>x.name),["Host 123","Service 4","Observed","Observed","Observed"]);
 assert.doesNotMatch(JSON.stringify(result),/NO_EXPORT|DO_NOT_COPY|credential|token/);
});
test("M1-A unsupported inventory categories remain honest browse-only, unknown categories not actionable",()=>{
 const a=project([hit("network-object","obj-1","Network"),hit("service-group","grp-3"),
   hit("permission-object","perm-4"),hit("ai-identity","ai-4"),
   hit("service-account","acct-4"),hit("random-kind","foo-9")]);
 assert.equal(a?.invalidCount,0);
 assert.deepEqual(a?.items.slice(0,4).map(x=>x.destination),
  Array(4).fill(null).map(()=>({id:"objects",group:"access",exact:false,context:null})));
 assert.deepEqual(a?.items.slice(4).map(x=>x.destination),[null,null]);
});
test("M1-A mismatched Core identity, missing policy plane, malicious type/id and nested data are rejected",()=>{
 const invalid=[
  {...hit("managed-host","a"),item:{id:"not-a"}},
  {...hit("remote-service","s"),item:{id:"s",authorization:"MALICIOUS"} ,id:"s\u202e"},
  {...hit("access-policy-rule","p"),item:{id:"p"}},
  {...hit("access-policy-rule","p"),item:{id:"p",plane:"ALL"}},
  {...hit("access-policy-rule","p"),item:{id:"other",plane:"remote"}},
  {...hit("managed-host","../danger")},
  {...hit("remote-service","id\nprivate")},
  {resource_type:{private:"TOKEN"},id:"x",name:"bad"},
  {resource_type:"managed-host",id:"host-a",name:"Name",item:{id:{unsafe:1}}},
  null,[],{resource_type:"managed-host",id:null},
 ];
 const v=project([...invalid,hit("managed-host","safe-host")]);
 assert.equal(v?.invalidCount,invalid.length);
 assert.deepEqual(v?.items.map(x=>x.id),["safe-host"]);
 assert.doesNotMatch(JSON.stringify(v),/MALICIOUS|TOKEN|private/);
 assert.equal(project({items:[]}),null);
 assert.equal(project(null),null);
 assert.equal(project(Array.from({length:21},(_,i)=>hit("managed-host","h"+i))),null);
});
test("M1-A untrusted labels never reveal nested secrets, control characters, or excess text",()=>{
 for(const name of [null,["nested"],{credential:"VISIBLE_NEVER"},"x\u202eSECRET","z".repeat(161),"\n"]){
   const v=project([hit("managed-host","host-clean",name)]);
   assert.equal(v?.items[0].name,"host-clean",JSON.stringify(name));
   assert.doesNotMatch(JSON.stringify(v),/VISIBLE_NEVER|SECRET/);
 }
 assert.equal(project([hit("managed-host","host-clean","safe name")])?.items[0].name,"safe name");
});
test("M1-A Core search does not grant details: must revalidate one unique fresh loaded ID/plane",()=>{
 const found=project([hit("managed-host","host-1"),hit("remote-service","svc-2"),
  {...hit("access-policy-rule","p-2"),item:{id:"p-2",plane:"ai"}}]);
 const host=found.items[0].destination.context;
 const svc=found.items[1].destination.context;
 const rule=found.items[2].destination.context;
 assert.equal(matchers.matchObservedAuditReturn([{id:"host-1",name:"authorized"}],host.inspectResourceId)?.name,"authorized");
 assert.equal(matchers.matchObservedAuditReturn([{id:"host-1"},{id:"host-1"}],host.inspectResourceId),null);
 assert.equal(matchers.matchObservedAuditReturn([{id:"another"}],host.inspectResourceId),null);
 assert.equal(matchers.matchObservedAuditReturn([{id:"svc-2",name:"current"}],svc.inspectResourceId)?.name,"current");
 assert.equal(matchers.matchObservedAuditReturn([{id:"other-service"}],svc.inspectResourceId),null);
 assert.equal(matchers.matchObservedPolicyReturn([{id:"p-2",plane:"ai"}],rule.inspectPolicyId,rule.plane)?.id,"p-2");
 assert.equal(matchers.matchObservedPolicyReturn([{id:"p-2",plane:"remote"}],rule.inspectPolicyId,rule.plane),null);
 assert.equal(matchers.matchObservedPolicyReturn([{id:"p-2",plane:"ai"},{id:"p-2",plane:"ai"}],rule.inspectPolicyId,rule.plane),null);
});
test("M1-A real Global Search Web wiring carries only projected context, guards stale queries and distinguishes empty/UNKNOWN",()=>{
 const src=readFileSync(join(root,"src","main.tsx"),"utf8");
 const global=src.split("function GlobalSearch(",2)[1]?.split("function Shell(",1)[0]||"";
 const shell=src.split("function Shell(",2)[1]?.split("function App(",1)[0]||"";
 const resource=src.split("function ResourceWorkspace(",2)[1]?.split("function UsersPanel(",1)[0]||"";
 assert.match(src,/import \{observedBoundedCoreSearchResponse\} from "\.\/uxb-global-search-target"/);
 assert.match(global,/observedBoundedCoreSearchResponse\(data,q\)/);
 assert.match(global,/const \[searchStatus,setSearchStatus\]=useState/);
 assert.match(global,/setSearchStatus\("ready"\)/);
 assert.match(global,/searchStatus==="ready".*?No matching Core resources in the returned search page/s);
 assert.match(global,/searchStatus==="unknown"/);
 assert.match(global,/setRejectedCount\(projection\.invalidCount\)/);
 assert.match(global,/onNavigate\(id,group,context\)/);
 assert.match(global,/onClick=\{\(\)=>\{if\(item\.destination\)go\(item\.destination\.id,item\.destination\.group,item\.destination\.context\|\|undefined\)\}\}/);
 assert.match(global,/disabled=\{!item\.destination\}/);
 assert.match(global,/visibleRoute\(id,operator\.role\)/);
 assert.match(global,/requestGeneration\.current!==generation/);
 assert.match(global,/onCloseRef\.current\(\)/);
 assert.match(shell,/navigationContext\?\.searchResultKey/);
 assert.match(resource,/Exact resource details open only if one currently loaded Core inventory item matches/);
 assert.match(resource,/Use Load more/);
 assert.match(resource,/matchObservedAuditReturn\(loaded,initialInspectId\)/);
 assert.match(src,/matchObservedPolicyReturn\(\[\.\.\.\(data\.items\|\|\[\]\),\.\.\.additional\],inspectPolicyId,carriedPlane\)/);
});

test("R2.2 M2 Core Search page is bound to the submitted query and exact 20-row contract",()=>{
 const q="branch server";
 const page={query:q,limit:20,items:[hit("managed-host","host-1")]};
 const valid=projector.observedBoundedCoreSearchResponse(page,q);
 assert.equal(valid?.scope,"bounded-core-search");
 assert.deepEqual(valid?.items.map(entry=>entry.id),["host-1"]);
 assert.deepEqual(projector.observedBoundedCoreSearchResponse({...page,items:[]},q)?.items,[]);
 for(const bad of [
   {items:[]}, {...page,query:"other server"},
   {...page,query:null}, {...page,limit:50},
   {...page,limit:"20"}, {...page,items:null},
   {...page,items:Array.from({length:21},(_,i)=>hit("managed-host","host-"+i))},
   {...page,items:[hit("managed-host","host-1"),hit("managed-host","host-1")]},
 ])assert.equal(projector.observedBoundedCoreSearchResponse(bad,q),null);
 for(const badQuery of ["", " branch server", "x".repeat(129), "branch\nserver"]){
   assert.equal(projector.observedBoundedCoreSearchResponse(page,badQuery),null);
 }
 const source=readFileSync(join(root,"src","main.tsx"),"utf8");
 const global=source.split("function GlobalSearch(",2)[1]?.split("function Shell(",1)[0]||"";
 assert.ok(global.includes("observedBoundedCoreSearchResponse(data,q)"));
});
