import React,{useEffect,useState} from "react";
import {EnrollmentOnboarding,hostReadinessLabel} from "./p0-enrollment";
import {AccessEvidenceExplorer,GuidedPolicyJourney,type AccessPlane,type LinkApi} from "./p0-access-policy";
import {RemoteServiceEditor} from "./uxb-remote-service";
type Navigate=(id:string,groupId?:string)=>void;
export type SetupDraft={
  plane?:AccessPlane,step?:number,selectedHost?:string,serviceName?:string,
  source?:string,destination?:string,selector?:string,
  service?:{owner:string,name:string,service:string,destination:string}
};

export const firstUseStages = {
  remote:["Add & approve Agent","Publish one Remote Service","Define a narrow access rule","Verify the decision"],
  internet:["Select managed source","Choose outside destination","Define an Internet Access rule","Verify the decision"],
  ai:["Select AI Identity","Choose a Permission Object","Define an AI Access rule","Verify the permission"],
} as const;

export function FirstConnectionSetup({api,operator,onNavigate,initialDraft,onDraftChange}:{
  api:LinkApi,operator:any,onNavigate?:Navigate,initialDraft?:SetupDraft|null,
  onDraftChange?:(draft:SetupDraft)=>void,
}){
  const [plane,setPlane]=useState<AccessPlane>(initialDraft?.plane||"remote");
  const [step,setStep]=useState(Math.min(4,Math.max(1,initialDraft?.step||1)));
  const [hosts,setHosts]=useState<any[]|null>(null),[services,setServices]=useState<any[]|null>(null);
  // Null means not observed / API unavailable; an authoritative empty list is different.
  const [enrollments,setEnrollments]=useState<any>(null);
  const [error,setError]=useState(""),[checking,setChecking]=useState(false);
  const [selectedHost,setSelectedHost]=useState(initialDraft?.selectedHost||"");
  const [serviceName,setServiceName]=useState(initialDraft?.serviceName||"");
  const [serviceDraft,setServiceDraft]=useState(initialDraft?.service||{owner:"",name:"",service:"",destination:"this-host"});
  const [source,setSource]=useState(initialDraft?.source||"");
  const [destination,setDestination]=useState(initialDraft?.destination||"");
  const [selector,setSelector]=useState(initialDraft?.selector||"");
  const canEdit=operator?.role==="Admin"||operator?.role==="Operator";
  const selected=hosts?.find(h=>String(h.id)===selectedHost)||null;
  const service=services?.find(s=>String(s.name||s.id)===serviceName)||null;
  useEffect(()=>{void refreshCore()},[]);
  // Only non-secret form choices stay in Shell's current authenticated React
  // session. A Core change plan, OTP, token or invitation is never persisted.
  useEffect(()=>{onDraftChange?.({plane,step,selectedHost,serviceName,
    source,destination,selector,service:serviceDraft})},
    [plane,step,selectedHost,serviceName,source,destination,selector,serviceDraft]);
  async function refreshCore(){
    setChecking(true);setError("");
    const r=await Promise.allSettled([
      api("/api/v1/inventory?resource_type=managed-host&limit=100"),
      api("/api/v1/inventory?resource_type=remote-service&limit=100"),
      api("/api/v1/enrollments?limit=50"),
    ]);
    if(r[0].status==="fulfilled"&&Array.isArray(r[0].value?.items)){
      const list=r[0].value.items;setHosts(list);
      // Do not silently switch the owning Agent to the first list entry.
      // Also discard the retained editor owner when its formerly selected
      // Agent vanishes; a remounted editor must not revive that old target.
      if(selectedHost&&!list.some((x:any)=>String(x.id)===selectedHost)){
        setServiceDraft(prev=>({...prev,owner:""}));
      }
      setSelectedHost(prev=>prev&&list.some((x:any)=>String(x.id)===prev)?prev:"");
    }else{setHosts(null);setError("Managed Host inventory unavailable; prerequisite state is UNKNOWN.")}
    if(r[1].status==="fulfilled"&&Array.isArray(r[1].value?.items))setServices(r[1].value.items);
    else setServices(null);
    if(r[2].status==="fulfilled"&&Array.isArray(r[2].value?.items))setEnrollments(r[2].value);
    else setEnrollments(null); // UNKNOWN, never a fabricated empty enrollment list.
    setChecking(false);
  }
  const stages=firstUseStages[plane];
  function changePlane(value:AccessPlane){setPlane(value);setStep(1);setSource("");setDestination("");setSelector("");
    setServiceName("");setServiceDraft({owner:"",name:"",service:"",destination:"this-host"});setError("")}
  return <div className="dr-uxb-setup" data-testid="uxb-connection-setup">
    <section className="card dr-uxb-setup-hero">
      <p className="dr-eyebrow">One safe path · Core-authoritative connection setup</p>
      <h2>Set up and verify a connection</h2>
      <p className="muted">One workspace, four stages. Progress indicates where you are, not that Core has completed a step. Every change still requires its own preview, tests and confirmation.</p>
      <label className="dr-field"><span>What are you connecting?</span><select value={plane} onChange={e=>changePlane(e.target.value as AccessPlane)}>
        <option value="remote">Remote Access · outside → approved internal service</option>
        <option value="internet">Internet Access · managed source → approved outside destination</option>
        <option value="ai">AI Access · authenticated AI Identity → named permission</option>
      </select></label>
      <ol className="dr-uxb-stage-menu" aria-label="First-connection stages">
        {stages.map((title,i)=><li key={title} className={step===i+1?"active":""}>
          <button type="button" aria-current={step===i+1?"step":undefined} onClick={()=>setStep(i+1)}>
            <span>{i+1}</span><strong>{title}</strong></button>
        </li>)}
      </ol>
      <div className="dr-uxb-flow-buttons">
        <button className="secondary" disabled={step===1} onClick={()=>setStep(i=>Math.max(1,i-1))}>← Previous</button>
        <button className="secondary" disabled={step===4} onClick={()=>setStep(i=>Math.min(4,i+1))}>Next stage →</button>
        <button className="secondary" onClick={refreshCore} disabled={checking}>{checking?"Checking Core…":"Refresh observed state"}</button>
      </div>
      {error&&<p className="warning-box" role="alert">{error}</p>}
      {plane==="remote"&&<div className="dr-uxb-evidence-strip">
        <span>Agent: {selected?hostReadinessLabel(selected):hosts===null?"UNKNOWN":"NO HOST SELECTED"}</span>
        <span>Remote Service: {service?String(service.enabled?"CONFIGURED · VERIFY JOB":"DISABLED · VERIFY JOB"):services===null?"UNKNOWN":"NOT SELECTED"}</span>
        <span>Core policy reachability: NOT VERIFIED</span>
      </div>}
    </section>
    {step===1&&plane==="remote"&&<>
      <div className="dr-uxb-context">
        <strong>Why add an Agent?</strong>
        <p>A Managed Host is the internal server running a DRLink Agent. Installing one does not publish its ports or grant all users access.</p>
      </div>
      <EnrollmentOnboarding api={api} data={enrollments} refresh={refreshCore} operator={operator} onNavigate={onNavigate}/>
      <section className="card dr-uxb-choice"><h3>Continue with an enrolled server</h3>
        <label className="dr-field"><span>Managed Host</span><select value={selectedHost} onChange={e=>setSelectedHost(e.target.value)}>
          {!selectedHost&&<option value="">{hosts===null?"Managed Host inventory: UNKNOWN":hosts.length?"Select an observed Managed Host":"No observed Managed Host"}</option>}
          {(hosts||[]).map(h=><option key={h.id} value={String(h.id)}>{h.name||h.label||h.id} · {h.id}</option>)}
        </select></label>
        {selected&&<p>{hostReadinessLabel(selected)} · Trust: {selected.trust_status||"UNKNOWN"} · Last seen: {selected.agent_heartbeat_at||"UNKNOWN"}</p>}
        <p className="muted">An unobserved, disconnected or pending-approval Host is not ready for a verified connection.</p>
      </section>
    </>}
    {step===1&&plane!=="remote"&&<section className="card dr-uxb-choice">
      <h3>{plane==="internet"?"Identify the managed source":"Select a trusted AI Identity"}</h3>
      <p>{plane==="internet"
        ?"Internet Access controls permitted outbound requests from a managed/protected source, not published inbound Remote Services."
        :"AI Access grants named permissions to an authenticated AI Identity. It does not expose an SSH port."}</p>
      <button className="secondary" onClick={()=>onNavigate?.(plane==="internet"?"hosts":"objects","connections")}>Inspect canonical resources →</button>
    </section>}
    {step===2&&plane==="remote"&&<div className="dr-uxb-setup-section">
      <div className="dr-uxb-context"><strong>Why publish a Remote Service?</strong><p>Choose exactly one service/port from an approved Agent. This queues an authenticated Agent job — it does not instantly prove success or user authorization.</p></div>
      <label className="dr-field"><span>Use observed Managed Host as owner</span><select value={selectedHost} onChange={e=>setSelectedHost(e.target.value)}>
        {!selectedHost&&<option value="">{hosts===null?"Managed Host inventory: UNKNOWN":hosts.length?"Select an observed Managed Host":"No observed Managed Host"}</option>}
        {(hosts||[]).map(h=><option key={h.id} value={String(h.id)}>{h.name||h.label||h.id}</option>)}
      </select></label>
      {canEdit?<RemoteServiceEditor api={api} ownerHint={selectedHost} initialSelection={serviceDraft}
        onSelection={s=>{setServiceDraft(s);setServiceName(s.name);if(s.service)setSelector(s.service)}}/>:
      <p className="warning-box">Your role can inspect services but cannot publish them.</p>}
      <button className="secondary" onClick={()=>onNavigate?.("services","connections")}>View actual Published Services →</button>
    </div>}
    {step===2&&plane!=="remote"&&<section className="card dr-uxb-choice">
      <h3>{plane==="internet"?"Select the intended outside destination":"Select a named Permission Object"}</h3>
      <p>{plane==="internet"?"Use an approved Network Object/Group for the external destination and a Service Object/Group for its protocol/port."
        :"Choose Permission Object/Group and an AI destination. A permission is not a network port."}</p>
      <button className="secondary" onClick={()=>onNavigate?.("objects","access")}>Browse Objects & Groups (advanced) →</button>
    </section>}
    {step===3&&<div className="dr-uxb-setup-section">
      <div className="dr-uxb-context"><strong>{plane==="remote"?"Grant only the intended source":"Define the exact intended access"}</strong>
        <p>{plane==="remote"?"An enabled Remote Service is not open until the relevant Remote Access policy permits the source. Use Network/Service Object names, not Agent credentials."
          :plane==="internet"?"Outbound access requires an explicitly selected network source, destination and service. No Remote Service is required."
          :"AI Access uses a verified AI Identity, destination and Permission Object; it is separate from Remote Access."}</p>
      </div>
      {canEdit?<GuidedPolicyJourney key={plane} api={api} initialPlane={plane} lockedPlane
        initialFlow={{source,destination,selector}}
        onFlowChange={f=>{setSource(f.source);setDestination(f.destination);setSelector(f.selector)}} onNavigate={onNavigate}/>:
        <p className="warning-box">Your role is read-only. You can test access but cannot create or apply a rule.</p>}
    </div>}
    {step===4&&<div className="dr-uxb-setup-section">
      <div className="dr-uxb-context"><strong>Verify the actual Core decision</strong>
        <p>Enter Network/Service or AI Identity/Permission object names and run a real Core trace. ALLOW is a policy result, not proof a target is reachable. Unknown remains UNKNOWN.</p></div>
      <div className="dr-uxb-form">
        <label className="dr-field"><span>Source object / identity</span><input value={source} onChange={e=>setSource(e.target.value)} placeholder="Actual Core name"/></label>
        <label className="dr-field"><span>Destination object</span><input value={destination} onChange={e=>setDestination(e.target.value)} placeholder="Actual Core name"/></label>
        <label className="dr-field"><span>{plane==="ai"?"Permission":"Service"} Object / Group</span><input value={selector} onChange={e=>setSelector(e.target.value)} placeholder="Actual Core name"/></label>
      </div>
      <AccessEvidenceExplorer api={api} plane={plane} source={source} destination={destination} selector={selector}
        onSelect={f=>{setSource(f.source);setDestination(f.destination);setSelector(f.selector)}} onNavigate={onNavigate}/>
      <p className="muted">To prove end-to-end network reachability, test from the intended client and inspect actual Agent/job/target evidence separately.</p>
    </div>}
  </div>;
}
